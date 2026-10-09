from collections import defaultdict, namedtuple
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AppSetting, Course, Lead, LeadActivity, Learner, LearnerCourseRecord, LearnersCrmEnrollment, LearnersCrmProfile, UpsellCourseCase, User
from app.services.course_rules import STAGE_ONE, build_customer_opportunities, get_cooling_days
from app.services.counselor_sync import sync_main_counselors
from app.services.learner_course_mapping import mapping_for_course_names, normalize_course_name

VALID_LEAD_STATUSES = ("NEW", "IN_CONTACT", "REJECTED", "CONVERTED")
VALID_ACTIVITY_TYPES = ("EMAIL_CAMPAIGN", "WHATSAPP_CAMPAIGN", "CALL", "NOTE")
COURSE_REVISION_KEY = "course_records_revision"
OPPORTUNITY_SYNC_KEY = "opportunity_sync_revision"
OPPORTUNITY_NEXT_REFRESH_KEY = "opportunity_next_refresh_date"
OPPORTUNITY_RULES_VERSION = "v5"
BoardResult = namedtuple("BoardResult", "learner_number result event_date")
BoardCourse = namedtuple("BoardCourse", "code")


def mark_opportunities_dirty(db: Session):
    setting = db.get(AppSetting, COURSE_REVISION_KEY)
    if setting:
        setting.value = uuid4().hex
    else:
        db.add(AppSetting(key=COURSE_REVISION_KEY, value=uuid4().hex))


def sync_opportunity_leads(db: Session):
    today = date.today()
    source_revision = db.get(AppSetting, COURSE_REVISION_KEY)
    revision = f"{source_revision.value if source_revision else 'initial'}:{OPPORTUNITY_RULES_VERSION}"
    synced_revision = db.get(AppSetting, OPPORTUNITY_SYNC_KEY)
    next_refresh = db.get(AppSetting, OPPORTUNITY_NEXT_REFRESH_KEY)
    due = bool(next_refresh and next_refresh.value and next_refresh.value <= today.isoformat())
    if synced_revision and synced_revision.value == revision and not due:
        return
    if db.bind.dialect.name == "postgresql":
        # Only one request may rebuild opportunities for a new upload/day.
        db.execute(text("SELECT pg_advisory_xact_lock(294810753)"))
        db.expire_all()
        source_revision = db.get(AppSetting, COURSE_REVISION_KEY)
        revision = f"{source_revision.value if source_revision else 'initial'}:{OPPORTUNITY_RULES_VERSION}"
        synced_revision = db.get(AppSetting, OPPORTUNITY_SYNC_KEY)
        next_refresh = db.get(AppSetting, OPPORTUNITY_NEXT_REFRESH_KEY)
        due = bool(next_refresh and next_refresh.value and next_refresh.value <= today.isoformat())
        if synced_revision and synced_revision.value == revision and not due:
            db.commit()
            return
    enrolments_by_customer = defaultdict(list)
    course_names = set()
    for enrolment, customer_id in db.execute(select(LearnersCrmEnrollment, LearnersCrmProfile.customer_id).join(
        LearnersCrmProfile, LearnersCrmEnrollment.learner_id == LearnersCrmProfile.id
    ).where(LearnersCrmProfile.customer_id.is_not(None))):
        enrolments_by_customer[customer_id].append(enrolment)
        course_names.add(enrolment.course_name)
    mappings = mapping_for_course_names(db, course_names)

    from app.services.verified_enrolments import active_verifications_query
    for verification in db.scalars(active_verifications_query()):
        if not verification.normalized_subcategory: continue
        # A virtual name preserves the verified subcategory even if a catalog
        # course variant is renamed. It cannot be treated as a result or pass.
        name = f"admin verified enrolment {verification.id}"
        mappings[name] = {"sub_category": verification.normalized_subcategory}
        enrolments_by_customer[verification.customer_id].append(SimpleNamespace(
            course_name=name, enrolment_date=verification.verified_at.date(), created_at=verification.verified_at,
            completion_status="Not Completed", completion_date=None))

    history_by_customer = defaultdict(lambda: defaultdict(list))
    for customer_id, number, result, event_date, code in db.execute(select(
        Learner.customer_id, LearnerCourseRecord.learner_number,
        LearnerCourseRecord.result, LearnerCourseRecord.event_date, Course.code,
    ).join(Learner, LearnerCourseRecord.learner_number == Learner.learner_number)
     .join(Course, LearnerCourseRecord.course_id == Course.id)
     .where(Learner.customer_id.is_not(None), Course.code.in_(("IGC", "ID1", "ID2", "ID3")))):
        history_by_customer[customer_id][number].append((BoardResult(number, result, event_date), BoardCourse(code)))

    existing_leads = db.execute(select(Lead).order_by(Lead.id)).scalars().all()
    legacy_numbers = {lead.learner_number for lead in existing_leads if not lead.customer_id and lead.learner_number}
    legacy_customers = dict(db.execute(select(Learner.learner_number, Learner.customer_id).where(
        Learner.learner_number.in_(legacy_numbers)))) if legacy_numbers else {}
    by_key = {}
    for lead in existing_leads:
        if not lead.customer_id and lead.learner_number:
            lead.customer_id = legacy_customers.get(lead.learner_number)
        if lead.customer_id:
            by_key.setdefault((lead.customer_id, lead.opportunity_key), lead)
    current_keys = set()
    cooling_days = get_cooling_days(db)
    next_eligibility = None
    for customer_id in enrolments_by_customer.keys() | history_by_customer.keys():
        enrolments = enrolments_by_customer.get(customer_id, [])
        for enrolment in enrolments:
            subcategory = normalize_course_name((mappings.get(normalize_course_name(enrolment.course_name)) or {}).get("sub_category") or "")
            if subcategory in STAGE_ONE:
                eligible = (enrolment.enrolment_date or enrolment.created_at.date()) + timedelta(days=cooling_days)
                if eligible > today and (next_eligibility is None or eligible < next_eligibility):
                    next_eligibility = eligible
        enrolled_subcategories = {
            normalize_course_name((mappings.get(normalize_course_name(item.course_name)) or {}).get("sub_category") or "")
            for item in enrolments
        }
        # General course history uses contact matching. Board result sequences
        # are calculated separately for each learner number, so an IGC pass on
        # one board number cannot unlock IDIP units on another.
        chosen = {item["key"]: (item, None) for item in build_customer_opportunities(
            enrolments, [], mappings, cooling_days,
        )}
        for number, board_rows in history_by_customer.get(customer_id, {}).items():
            for item in build_customer_opportunities([], board_rows, {}, cooling_days):
                key = item["key"]
                if normalize_course_name(item["target_subcategory"]) in enrolled_subcategories:
                    continue
                previous = chosen.get(key)
                if previous is None or item["stage"] > previous[0]["stage"] or (key in {"IDP_ENTRY", "ID1", "ID2", "ID3"} and previous[1] is None):
                    chosen[key] = (item, number)
        for opportunity, source_number in chosen.values():
            key = (customer_id, opportunity["key"])
            board_number = source_number if opportunity["key"] in {"IDP_ENTRY", "ID1", "ID2", "ID3"} else None
            current_keys.add(key)
            lead = by_key.get(key)
            if lead is None:
                lead = Lead(
                    customer_id=customer_id,
                    learner_number=board_number,
                    opportunity_key=opportunity["key"],
                    target_code=opportunity["target_code"],
                    stage=opportunity["stage"],
                    reason=opportunity["reason"],
                    trigger_date=opportunity.get("trigger_date"),
                    status="NEW",
                    is_active=True,
                )
                db.add(lead)
                by_key[key] = lead
            else:
                lead.customer_id = customer_id
                lead.learner_number = board_number
                lead.target_code = opportunity["target_code"]
                lead.stage = opportunity["stage"]
                lead.reason = opportunity["reason"]
                lead.trigger_date = opportunity.get("trigger_date")
                lead.is_active = True

    managed_ids = set(db.scalars(select(UpsellCourseCase.lead_id).distinct()))
    for lead in existing_leads:
        if lead.id in managed_ids:
            lead.is_active = True
            continue
        if (lead.customer_id, lead.opportunity_key) not in current_keys or by_key.get((lead.customer_id, lead.opportunity_key)) is not lead:
            lead.is_active = False

    if synced_revision:
        synced_revision.value = revision
    else:
        db.add(AppSetting(key=OPPORTUNITY_SYNC_KEY, value=revision))
    if next_refresh:
        next_refresh.value = next_eligibility.isoformat() if next_eligibility else ""
    else:
        db.add(AppSetting(key=OPPORTUNITY_NEXT_REFRESH_KEY, value=next_eligibility.isoformat() if next_eligibility else ""))
    sync_main_counselors(db)
    db.commit()


def get_accessible_lead(db: Session, lead_id: int, current_user: User) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    if current_user.role == "ADMIN":
        return lead
    if lead.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="This lead is not assigned to you.")
    return lead


def change_lead_status(db: Session, lead: Lead, status: str, user: User, note: str | None = None):
    from app.services.counselor_activity import record_action, new_contact_note, latest_contact_note
    normalized = status.strip().upper()
    if normalized not in VALID_LEAD_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Status must be one of: {', '.join(VALID_LEAD_STATUSES)}.",
        )

    db.execute(select(Lead.id).where(Lead.id == lead.id).with_for_update())
    db.refresh(lead)
    previous = lead.status
    if previous == normalized:
        return lead

    note = new_contact_note(db, note, lead=lead)
    previous_note = latest_contact_note(db, lead=lead)
    lead.status = normalized
    lead.status_updated_at = datetime.now(timezone.utc)
    db.add(
        LeadActivity(
            lead_id=lead.id,
            user_id=user.id,
            activity_type="STATUS_CHANGE",
            channel="SYSTEM",
            notes=f"Status changed from {previous} to {normalized}. Contact note: {note}",
        )
    )
    record_action(db, user=user, lead=lead, action_type="STATUS_CHANGE",
        before_status=previous, after_status=normalized, before_note=previous_note, after_note=note)
    db.commit()
    db.refresh(lead)
    return lead


def assign_lead(db: Session, lead: Lead, counselor_user_id: int | None, admin_user: User):
    previous_user_id = lead.assigned_to_user_id
    counselor = None
    if counselor_user_id is not None:
        counselor = db.get(User, counselor_user_id)
        if not counselor or counselor.role != "COUNSELOR" or not counselor.active:
            raise HTTPException(status_code=400, detail="Choose an active counselor account.")

    if previous_user_id == counselor_user_id:
        return lead

    lead.assigned_to_user_id = counselor_user_id
    lead.counselor_from_main = False
    lead.counselor_from_daily = False
    lead.assigned_at = datetime.now(timezone.utc) if counselor_user_id is not None else None
    new_name = counselor.display_name if counselor else "Unassigned"
    db.add(
        LeadActivity(
            lead_id=lead.id,
            user_id=admin_user.id,
            activity_type="ASSIGNMENT",
            channel="SYSTEM",
            notes=f"Lead assignment changed to {new_name}.",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead


def add_lead_activity(
    db: Session,
    lead: Lead,
    user: User,
    activity_type: str,
    campaign_name: str | None,
    notes: str | None,
):
    normalized = activity_type.strip().upper()
    if normalized not in VALID_ACTIVITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Activity type must be one of: {', '.join(VALID_ACTIVITY_TYPES)}.",
        )

    if normalized in {"EMAIL_CAMPAIGN", "WHATSAPP_CAMPAIGN"} and not (campaign_name or "").strip():
        raise HTTPException(status_code=400, detail="Campaign name is required for email/WhatsApp activity.")

    channel_map = {
        "EMAIL_CAMPAIGN": "EMAIL",
        "WHATSAPP_CAMPAIGN": "WHATSAPP",
        "CALL": "CALL",
        "NOTE": "NOTE",
    }
    activity = LeadActivity(
        lead_id=lead.id,
        user_id=user.id,
        activity_type=normalized,
        channel=channel_map[normalized],
        campaign_name=(campaign_name or "").strip() or None,
        notes=(notes or "").strip() or None,
    )
    db.add(activity)
    from app.services.counselor_activity import record_action, latest_contact_note
    previous_note = latest_contact_note(db, lead=lead)
    record_action(db, user=user, lead=lead, action_type="NOTE" if normalized == "NOTE" else "CONTACT",
        before_note=previous_note, after_note=activity.notes, channel=channel_map[normalized])
    db.commit()
    db.refresh(activity)
    return activity
