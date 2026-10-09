"""A current, cross-workspace history for one linked customer."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Course, Lead, LeadActivity, Learner, LearnerCourseRecord,
    LearnersCrmEnrollment, LearnersCrmProfile, MainCrmActivity,
    MainCrmLead, MarketingCampaign, UploadBatch, UpsellCourseCase, User,
)


def customer_lifecycle(db: Session, customer_id: int | None, user: User):
    if customer_id is None:
        return {"customer_id": None, "events": []}

    from app.services.verified_enrolments import active_verifications_query
    from app.services.learner_course_mapping import mapping_for_course_names, normalize_course_name
    from app.models import ConversionVerification
    events = []
    enrolled_names = set()
    enrolments = []
    result_rows = []

    def add(kind, date, title, detail=None, status=None, href=None, key=None, fields=None, raw_data=None, source_label=None, verified=False):
        events.append({
            "key": key or f"{kind}-{len(events)}", "kind": kind,
            "date": date.isoformat() if date else None,
            "title": title, "detail": detail, "status": status, "href": href,
            "fields": fields or {}, "raw_data": raw_data or {},
            "source_label": source_label, "verified": verified,
        })

    main_query = select(MainCrmLead).where(MainCrmLead.customer_id == customer_id)
    if user.role != "ADMIN":
        main_query = main_query.where(MainCrmLead.assigned_to_user_id == user.id)
    main_leads = db.scalars(main_query.order_by(MainCrmLead.id)).all()
    if main_leads:
        by_id = {lead.id: lead for lead in main_leads}
        activities = db.scalars(select(MainCrmActivity).where(
            MainCrmActivity.lead_id.in_(by_id), MainCrmActivity.activity_type != "EDIT"
        ).order_by(MainCrmActivity.id)).all()
        with_activity = {activity.lead_id for activity in activities}
        for lead in main_leads:
            if lead.id not in with_activity:
                add("ENQUIRY", lead.created_at, "Enquiry received",
                    f"{lead.source or lead.source_category} · {lead.course or 'Course not provided'}",
                    lead.status_of_lead, f"/crm/leads/{lead.id}", f"lead-{lead.id}")
        labels = {
            "ENQUIRY": "Enquiry received", "DIRECT_CALL": "Phone enquiry",
            "CAMPAIGN_SENT": "Campaign sent", "CAMPAIGN_REPLY": "Campaign reply",
            "MIGRATION": "Old CRM record imported",
        }
        for activity in activities:
            lead = by_id[activity.lead_id]
            detail = activity.full_user_reply or activity.notes or activity.campaign_name or activity.course or lead.source
            kind = "MARKETING" if activity.activity_type in {"CAMPAIGN_SENT", "CAMPAIGN_REPLY"} else "ENQUIRY"
            add(kind, activity.activity_date or activity.created_at,
                labels.get(activity.activity_type, activity.activity_type.replace("_", " ").title()),
                detail, lead.status_of_lead, f"/crm/leads/{lead.id}", f"main-activity-{activity.id}",
                fields={"source": lead.source, "course": activity.course or lead.course,
                        "channel": activity.channel, "campaign": activity.campaign_name,
                        "message": activity.full_user_reply, "note": activity.notes},
                raw_data=activity.raw_data)

    profiles = db.scalars(select(LearnersCrmProfile).where(
        LearnersCrmProfile.customer_id == customer_id
    )).all()
    if profiles:
        profile_ids = {profile.id for profile in profiles}
        enrolments = db.scalars(select(LearnersCrmEnrollment).where(
            LearnersCrmEnrollment.learner_id.in_(profile_ids)
        ).order_by(LearnersCrmEnrollment.enrolment_id)).all()
        for enrolment in enrolments:
            link = f"/learners-crm/learners/{enrolment.learner_id}"
            detail = f"Enrolment {enrolment.enrolment_id}"
            add("ENROLMENT", enrolment.enrolment_date or enrolment.created_at,
                f"Enrolled in {enrolment.course_name}", detail,
                enrolment.completion_status, link, f"enrolment-{enrolment.enrolment_id}",
                verified=True, fields={"enrolment_id": enrolment.enrolment_id,
                        "start_date": enrolment.start_date.isoformat() if enrolment.start_date else None,
                        "completion_date": enrolment.completion_date.isoformat() if enrolment.completion_date else None})
            if enrolment.completion_date and (enrolment.completion_status or "").strip().casefold() == "completed":
                add("COMPLETION", enrolment.completion_date, f"Completed {enrolment.course_name}",
                    detail, "Completed", link, f"completion-{enrolment.enrolment_id}",
                    fields={"enrolment_id": enrolment.enrolment_id})

    learners = db.scalars(select(Learner).where(Learner.customer_id == customer_id)).all()
    if learners:
        numbers = {learner.learner_number for learner in learners}
        result_rows = db.execute(select(LearnerCourseRecord, Course, UploadBatch.import_type).join(
            Course, Course.id == LearnerCourseRecord.course_id
        ).outerjoin(UploadBatch, UploadBatch.id == LearnerCourseRecord.upload_batch_id
        ).where(LearnerCourseRecord.learner_number.in_(numbers)).order_by(
            LearnerCourseRecord.event_date, LearnerCourseRecord.id
        )).all()
        for record, course, import_type in result_rows:
            result_type = import_type or course.program_code or course.code
            if result_type == "IDIP": result_type = "IDP"
            add("RESULT", record.event_date, course.name,
                f"Learner #{record.learner_number}", record.result or record.enrollment_status,
                f"/upsell/learners/{record.learner_number}" if user.role == "ADMIN" else None,
                f"result-{record.id}", fields=record.details, source_label=f"Result data {result_type}")
        campaigns = db.scalars(select(MarketingCampaign).where(
            MarketingCampaign.learner_number.in_(numbers)
        ).order_by(MarketingCampaign.id)).all()
        for campaign in campaigns:
            add("MARKETING", campaign.created_at, "Marketing campaign sent",
                f"{campaign.marketing_type}: {campaign.campaign_name}", None,
                f"/upsell/learners/{campaign.learner_number}" if user.role == "ADMIN" else None,
                f"campaign-{campaign.id}")


    opportunity_query = select(Lead).where(Lead.customer_id == customer_id)
    if user.role != "ADMIN":
        opportunity_query = opportunity_query.where(Lead.assigned_to_user_id == user.id)
    opportunities = db.scalars(opportunity_query.order_by(Lead.id)).all()
    if opportunities:
        by_id = {lead.id: lead for lead in opportunities}
        for lead in opportunities:
            add("UPSELL", lead.trigger_date or lead.created_at,
                f"Upsell opportunity: {lead.target_code}", lead.reason,
                lead.status, f"/upsell/leads/{lead.id}", f"opportunity-{lead.id}")
        activities = db.scalars(select(LeadActivity).where(LeadActivity.lead_id.in_(by_id)).order_by(
            LeadActivity.id
        )).all()
        for activity in activities:
            lead = by_id[activity.lead_id]
            add("UPSELL", activity.created_at,
                f"Upsell {activity.activity_type.replace('_', ' ').title()}",
                activity.notes or activity.campaign_name or lead.target_code,
                lead.status, f"/upsell/leads/{lead.id}",
                f"upsell-activity-{activity.id}")

    # Uploaded evidence already supplies enrolments/results. Manual verification adds
    # an Enrolled event only, never completion, PASS, or an unverified conversion.
    course_names = [e.course_name for e in enrolments]
    mappings = mapping_for_course_names(db, course_names)
    for e in enrolments:
        mapped = mappings.get(normalize_course_name(e.course_name)) or {}
        enrolled_names.add(normalize_course_name(mapped.get("sub_category") or e.course_name))
    for record, course, _ in result_rows:
        enrolled_names.add({"IGC": "igc", "ID1": "idip -1", "ID2": "idip -2", "ID3": "idip -3"}.get(course.code, normalize_course_name(course.name)))
    query = active_verifications_query().where(ConversionVerification.customer_id == customer_id)
    allowed_main = {lead.id for lead in main_leads}
    allowed_upsell = {lead.id for lead in opportunities}
    query = query.add_columns(UpsellCourseCase, User.display_name).outerjoin(UpsellCourseCase, UpsellCourseCase.id == ConversionVerification.upsell_case_id).outerjoin(User, User.id == ConversionVerification.verified_by_id)
    for verification, item, actor_name in db.execute(query):
        if not verification.course_name: continue
        if verification.main_lead_id and verification.main_lead_id not in allowed_main: continue
        if item and item.lead_id not in allowed_upsell: continue
        key = verification.normalized_subcategory or normalize_course_name(verification.course_name)
        if key in enrolled_names: continue
        enrolled_names.add(key)
        href = f"/crm/leads/{verification.main_lead_id}" if verification.main_lead_id else f"/upsell/leads/{item.lead_id}"
        add("ENROLMENT", verification.verified_at, f"Enrolled in {verification.course_name}",
            "Admin verified enrolment", "Enrolled", href, f"verified-enrolment-{verification.id}",
            fields={"course": verification.course_name, "sub_category": verification.normalized_subcategory,
                    "verified_by": actor_name or "Former admin"},
            source_label="Admin verified enrolment", verified=True)

    events.sort(key=lambda item: (item["date"] or "", item["key"]), reverse=True)
    return {"customer_id": customer_id, "events": events}
