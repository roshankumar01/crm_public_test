"""Course-specific Upsell workflow and one-way Main CRM contact inheritance."""
from sqlalchemy import case, exists, func, select, union_all
from app.models import (Course, Customer, Lead, Learner, LearnerCourseRecord, LearnersCrmEnrollment,
    LearnersCrmProfile, LearnerCourseMapping, LearnerCourseSubcategory, MainCrmLead,
    UpsellContactInfo, UpsellCourseCase, UpsellCourseActivity, User)

PERSON_FIELDS = ("full_name", "email", "phone_number", "whatsapp_number", "region", "country", "age")


def contact_key(lead):
    return lead.customer_id if lead.customer_id is not None else ("board", lead.learner_number)


def contact_infos(db, leads):
    """Batch effective personal details for a page; no per-person database queries."""
    ids = {lead.customer_id for lead in leads if lead.customer_id}
    numbers = {lead.learner_number for lead in leads if lead.learner_number}
    customers = {c.id: c for c in db.scalars(select(Customer).where(Customer.id.in_(ids)))} if ids else {}
    boards = {b.learner_number: b for b in db.scalars(select(Learner).where(Learner.learner_number.in_(numbers)))} if numbers else {}
    rank = select(MainCrmLead.id.label("id"), func.row_number().over(partition_by=MainCrmLead.customer_id,
        order_by=(MainCrmLead.updated_at.desc(), MainCrmLead.id.desc())).label("rank")).where(MainCrmLead.customer_id.in_(ids)).subquery()
    mains = {m.customer_id: m for m in db.scalars(select(MainCrmLead).join(rank, rank.c.id == MainCrmLead.id).where(rank.c.rank == 1))} if ids else {}
    infos = {i.customer_id: i for i in db.scalars(select(UpsellContactInfo).where(UpsellContactInfo.customer_id.in_(ids)))} if ids else {}
    result = {}
    for lead in leads:
        customer = customers.get(lead.customer_id); main = mains.get(lead.customer_id); board = boards.get(lead.learner_number)
        fallback = {"full_name": customer.primary_name if customer else board.name if board else None,
            "email": customer.primary_email if customer else board.email_id if board else None,
            "phone_number": customer.primary_phone if customer else board.contact_number if board else None}
        baseline = {field: (getattr(main, field) if main and getattr(main, field) is not None else fallback.get(field)) for field in PERSON_FIELDS}
        effective = dict(baseline); info = infos.get(lead.customer_id)
        for field, saved in (info.overrides if info else {}).items():
            if field in baseline and saved.get("main_value") == baseline[field]: effective[field] = saved.get("value")
        result[contact_key(lead)] = (effective, baseline, main.id if main else None)
    return result


def contact_info(db, lead):
    return contact_infos(db, [lead])[contact_key(lead)]


def activity_payload(activity, users):
    return {"id": activity.id, "activity_type": activity.activity_type, "campaign_name": activity.campaign_name,
        "notes": activity.notes, "created_at": activity.created_at, "updated_at": activity.updated_at,
        "user_name": users.get(activity.user_id, "Unknown user"),
        "edited_by": users.get(activity.edited_by_id) if activity.edited_by_id else None}


def cases_payload(db, cases, include_activities=True):
    if not cases: return []
    from app.services.conversion_verification import verification_payloads
    checks = verification_payloads(db, UpsellCourseCase, [c.id for c in cases])
    ids = [c.id for c in cases]
    counts = dict(db.execute(select(UpsellCourseActivity.case_id, func.count()).where(UpsellCourseActivity.case_id.in_(ids))
                            .group_by(UpsellCourseActivity.case_id)).all()) if include_activities else {}
    ranked = select(UpsellCourseActivity.id.label("id"), func.row_number().over(partition_by=UpsellCourseActivity.case_id,
        order_by=(UpsellCourseActivity.created_at.desc(), UpsellCourseActivity.id.desc())).label("rank")).where(UpsellCourseActivity.case_id.in_(ids)).subquery()
    activities = db.scalars(select(UpsellCourseActivity).join(ranked, ranked.c.id == UpsellCourseActivity.id).where(ranked.c.rank <= 50)
        .order_by(UpsellCourseActivity.created_at.desc(), UpsellCourseActivity.id.desc())).all() if include_activities else []
    user_ids = {i for c in cases for i in (c.counselor_id, c.converted_by_id) if i}
    user_ids.update(i for a in activities for i in (a.user_id, a.edited_by_id) if i)
    users = dict(db.execute(select(User.id, User.display_name).where(User.id.in_(user_ids))).all()) if user_ids else {}
    grouped = {c.id: [] for c in cases}
    for activity in activities: grouped[activity.case_id].append(activity_payload(activity, users))
    return [{**checks[c.id], "id": c.id, "lead_id": c.lead_id, "mapping_id": c.mapping_id, "main_category": c.main_category,
        "sub_category": c.sub_category, "course_name": c.course_name, "status": c.status, "is_current": c.current_slot == 1,
        "converted_at": c.converted_at, "created_at": c.created_at, "counselor": users.get(c.counselor_id),
        "converted_by": users.get(c.converted_by_id), "activity_count": counts.get(c.id, 0), "activities": grouped[c.id]} for c in cases]


def registration_exists():
    """Match the same linked person and mapped subcategory; conversion is not registration."""
    enrolled = select(LearnersCrmEnrollment.enrolment_id).join(LearnersCrmProfile,
        LearnersCrmEnrollment.learner_id == LearnersCrmProfile.id).join(LearnerCourseMapping,
        func.coalesce(LearnersCrmEnrollment.normalized_course_name, func.lower(func.trim(LearnersCrmEnrollment.course_name))) == LearnerCourseMapping.normalized_name).join(
        LearnerCourseSubcategory, LearnerCourseMapping.subcategory_id == LearnerCourseSubcategory.id).where(
        LearnersCrmProfile.customer_id == UpsellCourseCase.customer_id,
        ((LearnerCourseSubcategory.id == UpsellCourseCase.subcategory_id) |
         (UpsellCourseCase.subcategory_id.is_(None) &
          (LearnerCourseSubcategory.normalized_name == UpsellCourseCase.normalized_subcategory)))).correlate(UpsellCourseCase).exists()
    board_sub = case((Course.code == "IGC", "igc"), (Course.code == "ID1", "idip -1"),
                     (Course.code == "ID2", "idip -2"), (Course.code == "ID3", "idip -3"), else_="")
    board = select(LearnerCourseRecord.id).join(Learner, LearnerCourseRecord.learner_number == Learner.learner_number).join(
        Course, LearnerCourseRecord.course_id == Course.id).where(Learner.customer_id == UpsellCourseCase.customer_id,
        board_sub == UpsellCourseCase.normalized_subcategory).correlate(UpsellCourseCase).exists()
    return enrolled | board


def work_items():
    """One SQL work item per selected course, plus untouched legacy opportunities."""
    has_case = select(UpsellCourseCase.id).where(UpsellCourseCase.lead_id == Lead.id).exists()
    legacy = select(Lead.id.label("id"), Lead.customer_id, Lead.status, Lead.target_code,
        Lead.opportunity_key, Lead.stage, Lead.assigned_to_user_id, Lead.is_active, Lead.created_at, Lead.trigger_date
    ).where(Lead.is_active.is_(True), ~has_case)
    courses = select(Lead.id.label("id"), Lead.customer_id, UpsellCourseCase.status,
        UpsellCourseCase.sub_category.label("target_code"), Lead.opportunity_key, Lead.stage,
        case((UpsellCourseCase.status == "CONVERTED", UpsellCourseCase.counselor_id), else_=Lead.assigned_to_user_id).label("assigned_to_user_id"),
        Lead.is_active, case((UpsellCourseCase.status == "CONVERTED", UpsellCourseCase.converted_at),
                            else_=UpsellCourseCase.created_at).label("created_at"), Lead.trigger_date
    ).join(Lead, UpsellCourseCase.lead_id == Lead.id).where(
        Lead.is_active.is_(True) | (UpsellCourseCase.status == "CONVERTED"))
    return union_all(legacy, courses).subquery()


def preserve_legacy_conversions(db):
    """Retain old counselor-reported conversions without inventing a course variant."""
    from app.services.learner_course_mapping import normalize_course_name
    from app.models import LearnerCourseCategory
    subcategories = {sub.normalized_name: (sub, main) for sub, main in db.execute(
        select(LearnerCourseSubcategory, LearnerCourseCategory).join(LearnerCourseCategory,
            LearnerCourseSubcategory.category_id == LearnerCourseCategory.id)).all()}
    has_case = select(UpsellCourseCase.id).where(UpsellCourseCase.lead_id == Lead.id).exists()
    for lead in db.scalars(select(Lead).where(Lead.status == "CONVERTED", ~has_case)):
        subname = {"ID1":"IDIP -1", "ID2":"IDIP -2", "ID3":"IDIP -3", "IDP":"Nebosh Idip"}.get(lead.target_code, lead.target_code)
        normalized = normalize_course_name(subname)
        match = subcategories.get(normalized)
        db.add(UpsellCourseCase(lead_id=lead.id, customer_id=lead.customer_id, mapping_id=None,
            subcategory_id=match[0].id if match else None,
            main_category=match[1].name if match else "Not recorded", sub_category=match[0].name if match else subname,
            normalized_subcategory=normalized, course_name=f"{subname} (legacy conversion; course variant not recorded)",
            status="CONVERTED", counselor_id=lead.assigned_to_user_id,
            converted_at=lead.status_updated_at or lead.updated_at, created_at=lead.created_at))
