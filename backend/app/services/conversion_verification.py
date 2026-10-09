"""Upload-backed registration or explicit admin enrolment; never a result/pass."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models import (ConversionVerification, Learner, LearnerCourseRecord, LearnersCrmProfile, LearnersCrmEnrollment, MainCrmLead,
    UpsellCourseCase, LearnerCourseMapping, LearnerCourseSubcategory, User)
from app.services.learner_course_mapping import normalize_course_name


def main_registration_exists():
    # Retained contact shells after a reset are not uploaded registration evidence.
    return (select(LearnerCourseRecord.id).join(Learner, Learner.learner_number == LearnerCourseRecord.learner_number)
            .where(Learner.customer_id == MainCrmLead.customer_id).correlate(MainCrmLead).exists() |
            select(LearnersCrmEnrollment.enrolment_id).join(LearnersCrmProfile, LearnersCrmProfile.id == LearnersCrmEnrollment.learner_id)
            .where(LearnersCrmProfile.customer_id == MainCrmLead.customer_id).correlate(MainCrmLead).exists())


def admin_exists(model):
    column = ConversionVerification.main_lead_id if model is MainCrmLead else ConversionVerification.upsell_case_id
    course = MainCrmLead.course if model is MainCrmLead else UpsellCourseCase.course_name
    return select(ConversionVerification.id).where(column == model.id,
        ConversionVerification.customer_id == model.customer_id,
        ConversionVerification.course_name.is_not_distinct_from(course)).correlate(model).exists()


def verified_exists(model):
    from app.services.upsell_management import registration_exists
    return (main_registration_exists() if model is MainCrmLead else registration_exists()) | admin_exists(model)


def report_condition(model, state):
    if state not in {"pending", "verified", "all"}: raise HTTPException(400, "Invalid verification filter.")
    verified = verified_exists(model)
    return [] if state == "all" else [verified if state == "verified" else ~verified]


def verification_payloads(db, model, ids):
    if not ids: return {}
    from app.services.upsell_management import registration_exists
    automatic = main_registration_exists() if model is MainCrmLead else registration_exists()
    column = ConversionVerification.main_lead_id if model is MainCrmLead else ConversionVerification.upsell_case_id
    course = MainCrmLead.course if model is MainCrmLead else UpsellCourseCase.course_name
    rows = db.execute(select(model.id, automatic, ConversionVerification, User.display_name)
        .outerjoin(ConversionVerification, (column == model.id) & (ConversionVerification.customer_id == model.customer_id) &
                   ConversionVerification.course_name.is_not_distinct_from(course))
        .outerjoin(User, User.id == ConversionVerification.verified_by_id).where(model.id.in_(ids))).all()
    return {id: {"verified": bool(upload or saved), "verification_source": "Uploaded registration" if upload else "Admin verified enrolment" if saved else "Pending verification",
                 "verified_by": name if saved else None, "verified_at": saved.verified_at if saved else None}
            for id, upload, saved, name in rows}


def verify_conversion(db, item, admin):
    # Explicit check also protects direct service calls outside FastAPI dependency injection.
    if admin.role != "ADMIN": raise HTTPException(403, "Only an admin can verify a mismatch.")
    main = isinstance(item, MainCrmLead)
    if (item.status_of_lead if main else item.status) != "CONVERTED": raise HTTPException(409, "Only converted records can be verified.")
    if not item.customer_id: raise HTTPException(409, "Link this record to a person before verification.")
    model = MainCrmLead if main else UpsellCourseCase
    # Serialize retries for one conversion, without locking the whole dataset.
    db.execute(select(model.id).where(model.id == item.id).with_for_update())
    db.refresh(item)
    if (item.status_of_lead if main else item.status) != "CONVERTED": raise HTTPException(409, "Only converted records can be verified.")
    column = ConversionVerification.main_lead_id if main else ConversionVerification.upsell_case_id
    saved = db.scalar(select(ConversionVerification).where(column == item.id))
    course = item.course if main else item.course_name
    if saved and saved.customer_id == item.customer_id and saved.course_name == course:
        return verification_payloads(db, model, [item.id])[item.id]
    normalized_sub = item.normalized_subcategory if not main else None
    if main and course:
        mapping = db.scalar(select(LearnerCourseMapping).where(LearnerCourseMapping.normalized_name == normalize_course_name(course)))
        sub = db.get(LearnerCourseSubcategory, mapping.subcategory_id) if mapping else db.scalar(select(LearnerCourseSubcategory).where(
            LearnerCourseSubcategory.normalized_name == normalize_course_name(course)))
        normalized_sub = sub.normalized_name if sub else None
    if not saved:
        saved = ConversionVerification(main_lead_id=item.id if main else None, upsell_case_id=None if main else item.id)
        db.add(saved)
    saved.customer_id = item.customer_id
    saved.course_name = course
    saved.normalized_subcategory = normalized_sub
    saved.verified_by_id = admin.id
    saved.verified_at = datetime.now(timezone.utc)
    from app.services.lead_workflow import mark_opportunities_dirty
    mark_opportunities_dirty(db)
    db.commit()
    return verification_payloads(db, model, [item.id])[item.id]
