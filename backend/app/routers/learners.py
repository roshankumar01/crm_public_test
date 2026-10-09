from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Course, Customer, Lead, Learner, LearnerCourseRecord, LearnersCrmEnrollment, LearnersCrmProfile, MarketingCampaign, User
from app.services.auth import get_current_user, require_admin
from app.services.upsell_management import contact_info, contact_infos
from app.services.course_rules import is_completed
from app.services.customer_lifecycle import customer_lifecycle
from app.services.counselor_sync import main_counselors, counselor_fields
from app.services.lead_workflow import sync_opportunity_leads
from app.services.learner_course_mapping import mapping_for_course_names, normalize_course_name
from app.services.opportunities import SECTION_CONFIG, section_key
from app.services.recommendation import get_recommendations

router = APIRouter(prefix="/learners", tags=["Learners"])


@router.get("/contacts")
def get_contacts(
    search: str | None = Query(default=None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
):
    """List distinct learners, including those imported only through Learners CRM."""
    query = select(Customer).where(or_(
        Customer.id.in_(select(LearnersCrmProfile.customer_id).where(LearnersCrmProfile.customer_id.is_not(None))),
        Customer.id.in_(select(Learner.customer_id).where(Learner.customer_id.is_not(None))),
    ))
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(or_(Customer.primary_name.ilike(term), Customer.primary_email.ilike(term), Customer.primary_phone.ilike(term)))
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    customers = db.scalars(query.order_by(Customer.updated_at.desc(), Customer.id.desc()).offset((page - 1) * 50).limit(50)).all()
    customer_ids = [item.id for item in customers]
    owners = main_counselors(db, customer_ids)
    board_numbers = {}
    profiles_by_customer = {}
    if customer_ids:
        for number, linked_id in db.execute(select(Learner.learner_number, Learner.customer_id).where(Learner.customer_id.in_(customer_ids))):
            board_numbers.setdefault(linked_id, number)
        for profile in db.scalars(select(LearnersCrmProfile).where(LearnersCrmProfile.customer_id.in_(customer_ids))):
            profiles_by_customer.setdefault(profile.customer_id, profile)
    info = contact_infos(db, [SimpleNamespace(customer_id=item.id, learner_number=board_numbers.get(item.id)) for item in customers])
    items = [{**counselor_fields(owners, item.id), "customer_id": item.id, "name": info[item.id][0]["full_name"] or "Learner",
             "email_id": info[item.id][0]["email"],
             "contact_number": info[item.id][0]["phone_number"],
             "last_activity_date": item.updated_at.date(),
             "learner_number": board_numbers.get(item.id)}
            for item in customers]
    return {"items": items, "total": total, "page": page, "pages": max(1, (total + 49) // 50)}


@router.get("/contacts/{customer_id}")
def get_contact(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Learner not found.")
    if current_user.role != "ADMIN":
        sync_opportunity_leads(db)
        assigned = db.scalar(select(Lead.id).where(Lead.customer_id == customer_id,
                                                  Lead.assigned_to_user_id == current_user.id).limit(1))
        if not assigned:
            raise HTTPException(status_code=403, detail="This learner is not assigned to you.")
    profiles = db.scalars(select(LearnersCrmProfile).where(LearnersCrmProfile.customer_id == customer_id)).all()
    profile_ids = [profile.id for profile in profiles]
    enrolments = db.scalars(select(LearnersCrmEnrollment).where(
        LearnersCrmEnrollment.learner_id.in_(profile_ids)
    ).order_by(LearnersCrmEnrollment.enrolment_date, LearnersCrmEnrollment.enrolment_id)).all() if profile_ids else []
    numbers = db.scalars(select(Learner.learner_number).where(Learner.customer_id == customer_id)).all()
    history_rows = db.execute(select(LearnerCourseRecord, Course).join(
        Course, LearnerCourseRecord.course_id == Course.id
    ).where(LearnerCourseRecord.learner_number.in_(numbers)).order_by(LearnerCourseRecord.event_date)).all() if numbers else []
    mappings = mapping_for_course_names(db, [item.course_name for item in enrolments])
    sync_opportunity_leads(db)
    opportunities = db.scalars(select(Lead).where(Lead.customer_id == customer_id, Lead.is_active.is_(True)).order_by(Lead.stage, Lead.opportunity_key)).all()
    passed = []
    timeline = []
    for item in enrolments:
        mapping = mappings.get(normalize_course_name(item.course_name)) or {}
        sub = mapping.get("sub_category")
        completed = (item.completion_status or "").strip().casefold() == "completed"
        if completed:
            passed.append(item.course_name)
        timeline.append({"id": item.enrolment_id, "date": item.enrolment_date or item.created_at.date(),
                         "title": f"{item.course_name} - {item.completion_status or 'Enrolled'}",
                         "course_name": item.course_name, "course_code": sub or item.course_name,
                         "result": item.completion_status, "details": {"enrolment_id": item.enrolment_id}})
    for record, course in history_rows:
        if is_completed(record):
            passed.append(course.name)
        timeline.append({"id": f"board-{record.id}", "date": record.event_date,
                         "title": f"{course.name} - {record.result or record.enrollment_status or 'Activity'}",
                         "course_name": course.name, "course_code": course.code,
                         "result": record.result, "details": record.details})
    campaigns = db.scalars(select(MarketingCampaign).where(MarketingCampaign.learner_number.in_(numbers))
                           .order_by(MarketingCampaign.created_at.desc()).limit(20)).all() if numbers else []
    owners = main_counselors(db, [customer.id])
    info, _, _ = contact_info(db, SimpleNamespace(customer_id=customer.id, learner_number=numbers[0] if numbers else None))
    return {"learner": {**counselor_fields(owners, customer.id), "customer_id": customer.id, "learner_number": numbers[0] if numbers else None,
                         "name": info["full_name"] or "Learner",
                         "email_id": info["email"],
                         "contact_number": info["phone_number"],
                         "last_activity_date": customer.updated_at.date()},
            "passed_courses": list(dict.fromkeys(passed)),
            "recommendations": [{"code": item.target_code,
                                 "name": SECTION_CONFIG.get(section_key(item.opportunity_key, item.stage), (item.target_code,))[0],
                                 "reason": item.reason, "priority": (item.stage or 0) * 10} for item in opportunities],
            "timeline": sorted(timeline, key=lambda item: item["date"] or item["id"], reverse=True),
            "campaigns": [{"id": item.id, "marketing_type": item.marketing_type,
                           "campaign_name": item.campaign_name, "created_at": item.created_at} for item in campaigns],
            "lifecycle": customer_lifecycle(db, customer.id, current_user)}


@router.get("")
def get_learners(
    search: str | None = Query(default=None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = select(Learner)
    if search:
        text = f"%{search.strip()}%"
        query = query.where(
            or_(
                Learner.name.ilike(text),
                Learner.learner_number.ilike(text),
                Learner.email_id.ilike(text),
            )
        )

    learners = db.execute(
        query.order_by(Learner.last_activity_date.desc().nullslast())
    ).scalars().all()

    owners = main_counselors(db, [learner.customer_id for learner in learners])
    return [
        {
            **counselor_fields(owners, learner.customer_id),
            "learner_number": learner.learner_number,
            "name": learner.name,
            "nationality": learner.nationality,
            "contact_number": learner.contact_number,
            "email_id": learner.email_id,
            "last_activity_date": learner.last_activity_date,
        }
        for learner in learners
    ]


@router.get("/{learner_number}")
def get_learner(
    learner_number: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    learner = db.get(Learner, learner_number)
    if not learner:
        raise HTTPException(status_code=404, detail="Learner not found.")
    if learner.customer_id:
        return get_contact(learner.customer_id, current_user, db)

    if current_user.role != "ADMIN":
        sync_opportunity_leads(db)
        assigned = db.scalar(
            select(Lead.id).where(
                Lead.learner_number == learner_number,
                Lead.assigned_to_user_id == current_user.id,
            )
        )
        if not assigned:
            raise HTTPException(status_code=403, detail="This learner is not assigned to you.")

    history_rows = db.execute(
        select(LearnerCourseRecord, Course)
        .join(Course, LearnerCourseRecord.course_id == Course.id)
        .where(LearnerCourseRecord.learner_number == learner_number)
        .order_by(LearnerCourseRecord.event_date, LearnerCourseRecord.id)
    ).all()
    campaigns = db.execute(
        select(MarketingCampaign)
        .where(MarketingCampaign.learner_number == learner_number)
        .order_by(MarketingCampaign.created_at.desc(), MarketingCampaign.id.desc())
    ).scalars().all()

    timeline = []
    completed = []
    for record, course in history_rows:
        title = (
            f"{course.name} - {record.result}"
            if record.result
            else f"{course.name} - {record.enrollment_status}"
            if record.enrollment_status
            else f"{course.name} activity"
        )
        timeline.append({
            "id": record.id,
            "date": record.event_date,
            "event_type": record.event_type,
            "course_code": course.code,
            "program_code": course.program_code,
            "course_name": course.name,
            "result": record.result,
            "enrollment_status": record.enrollment_status,
            "title": title,
            "details": record.details,
        })
        if is_completed(record):
            completed.append(course.code)

    return {
        "learner": {
            "learner_number": learner.learner_number,
            "name": learner.name,
            "nationality": learner.nationality,
            "contact_number": learner.contact_number,
            "email_id": learner.email_id,
            "last_activity_date": learner.last_activity_date,
        },
        "passed_courses": list(dict.fromkeys(completed)),
        "recommendations": get_recommendations(history_rows),
        "timeline": timeline,
        "campaigns": [{
            "id": campaign.id,
            "marketing_type": campaign.marketing_type,
            "campaign_name": campaign.campaign_name,
            "created_at": campaign.created_at,
        } for campaign in campaigns],
        "lifecycle": customer_lifecycle(db, learner.customer_id, current_user),
    }
