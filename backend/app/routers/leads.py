from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Lead, LeadActivity, Learner, MarketingCampaign, UpsellCourseCase, User
from app.services.auth import get_current_user, require_admin
from app.services.lead_workflow import (
    add_lead_activity,
    assign_lead,
    change_lead_status,
    get_accessible_lead,
    sync_opportunity_leads,
)
from app.services.upsell_management import contact_info, contact_infos, contact_key
from app.services.opportunities import SECTION_CONFIG, section_filter, section_key

router = APIRouter(prefix="/leads", tags=["Leads"])


class StatusUpdate(BaseModel):
    status: str
    note: str | None = None


class AssignmentUpdate(BaseModel):
    counselor_user_id: int | None = None


class ActivityCreate(BaseModel):
    activity_type: str
    campaign_name: str | None = None
    notes: str | None = None


@router.get("/counselors")
def get_counselors(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    counselors = db.execute(
        select(User)
        .where(User.role == "COUNSELOR", User.active.is_(True))
        .order_by(User.display_name)
    ).scalars().all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "country": user.country,
            "region": user.region,
        }
        for user in counselors
    ]


@router.get("")
def get_tracked_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    active_only: bool = False,
    section: str | None = None,
    status: str | None = None,
    counselor: str | None = None,
    search: str | None = Query(None, max_length=320),
    sort: str = "waiting",
    direction: str = "desc",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sync_opportunity_leads(db)
    conditions = []
    if current_user.role != "ADMIN":
        conditions.append(Lead.assigned_to_user_id == current_user.id)
    if active_only:
        conditions.append(Lead.is_active.is_(True))
    if section:
        section_conditions = section_filter(section)
        if section_conditions is None:
            raise HTTPException(status_code=400, detail="Unknown opportunity section.")
        conditions.extend(section_conditions)
    if status and status != "ALL":
        conditions.append(Lead.status == status)
    if counselor and counselor != "ALL":
        if counselor == "UNASSIGNED":
            conditions.append(Lead.assigned_to_user_id.is_(None))
        elif counselor.isdecimal():
            conditions.append(Lead.assigned_to_user_id == int(counselor))
        else:
            raise HTTPException(status_code=400, detail="Invalid counselor filter.")
    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append(or_(Customer.primary_name.ilike(term), Customer.primary_email.ilike(term),
                              Customer.primary_phone.ilike(term), Lead.learner_number.ilike(term)))
    total = db.scalar(select(func.count(Lead.id)).outerjoin(Customer, Lead.customer_id == Customer.id).where(*conditions)) or 0
    sort_columns = {"learner": Customer.primary_name, "trigger": Lead.trigger_date,
                    "waiting": Lead.trigger_date, "status": Lead.status,
                    "counselor": User.display_name, "contact": Customer.primary_email,
                    "updated": Lead.updated_at}
    column = sort_columns.get(sort, Lead.trigger_date)
    descending = direction == "desc"
    if sort == "waiting":
        descending = not descending
    ordering = column.desc() if descending else column.asc()
    rows = db.execute(select(Lead, Customer, Learner, User)
        .outerjoin(Customer, Lead.customer_id == Customer.id)
        .outerjoin(Learner, Lead.learner_number == Learner.learner_number)
        .outerjoin(User, Lead.assigned_to_user_id == User.id)
        .where(*conditions).order_by(ordering, Lead.id.desc())
        .offset((page - 1) * page_size).limit(page_size)).all()
    learner_numbers = {lead.learner_number for lead, _, _, _ in rows if lead.learner_number}
    latest_campaign = {}
    if learner_numbers:
        ranked = select(MarketingCampaign.id.label("id"), func.row_number().over(
            partition_by=MarketingCampaign.learner_number,
            order_by=(MarketingCampaign.created_at.desc(), MarketingCampaign.id.desc())
        ).label("rank")).where(MarketingCampaign.learner_number.in_(learner_numbers)).subquery()
        for campaign in db.scalars(select(MarketingCampaign).join(ranked, MarketingCampaign.id == ranked.c.id).where(ranked.c.rank == 1)):
            latest_campaign[campaign.learner_number] = campaign
    from app.services.conversion_verification import verification_payloads
    lead_ids = [lead.id for lead, _, _, _ in rows]
    ranked_cases = select(UpsellCourseCase.id.label("id"), func.row_number().over(
        partition_by=UpsellCourseCase.lead_id, order_by=(UpsellCourseCase.converted_at.desc(), UpsellCourseCase.id.desc())).label("rank")
    ).where(UpsellCourseCase.lead_id.in_(lead_ids), UpsellCourseCase.status == "CONVERTED").subquery()
    latest_cases = db.scalars(select(UpsellCourseCase).join(ranked_cases, ranked_cases.c.id == UpsellCourseCase.id).where(ranked_cases.c.rank == 1)).all() if lead_ids else []
    checks = verification_payloads(db, UpsellCourseCase, [c.id for c in latest_cases])
    checks_by_lead = {c.lead_id: checks[c.id] for c in latest_cases}
    person_info = contact_infos(db, [lead for lead, _, _, _ in rows])
    items = [
        {
            **checks_by_lead.get(lead.id, {"verified": False}),
            "lead_id": lead.id,
            "customer_id": lead.customer_id,
            "learner_number": lead.learner_number,
            "name": person_info[contact_key(lead)][0]["full_name"] or "Unknown",
            "email_id": person_info[contact_key(lead)][0]["email"],
            "contact_number": person_info[contact_key(lead)][0]["phone_number"],
            "target_code": lead.target_code,
            "target_name": SECTION_CONFIG.get(section_key(lead.opportunity_key, lead.stage), (lead.target_code,))[0],
            "stage": lead.stage,
            "trigger_courses": [f"Stage {lead.stage}"] if lead.stage else [],
            "trigger_date": lead.trigger_date,
            "days_since_trigger": max((date.today() - lead.trigger_date).days, 0) if lead.trigger_date else None,
            "opportunity_key": lead.opportunity_key,
            "status": lead.status,
            "is_active": lead.is_active,
            "assigned_to_user_id": lead.assigned_to_user_id,
            "assigned_to_name": counselor.display_name if counselor else None,
            "assignment_source": "DAILY_LEARNERS" if lead.counselor_from_daily else "MAIN_CRM" if lead.counselor_from_main else None,
            "updated_at": lead.updated_at,
            "latest_campaign": ({
                "marketing_type": latest_campaign[lead.learner_number].marketing_type,
                "campaign_name": latest_campaign[lead.learner_number].campaign_name,
                "created_at": latest_campaign[lead.learner_number].created_at,
            } if lead.learner_number in latest_campaign else None),
        }
        for lead, customer, learner, counselor in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size)}


@router.get("/{lead_id}")
def get_lead(
    lead_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sync_opportunity_leads(db)
    lead = get_accessible_lead(db, lead_id, current_user)
    learner = db.get(Learner, lead.learner_number) if lead.learner_number else None
    customer = db.get(Customer, lead.customer_id) if lead.customer_id else None
    counselor = db.get(User, lead.assigned_to_user_id) if lead.assigned_to_user_id else None

    activity_rows = db.execute(
        select(LeadActivity, User)
        .outerjoin(User, LeadActivity.user_id == User.id)
        .where(LeadActivity.lead_id == lead.id)
        .order_by(LeadActivity.created_at.desc(), LeadActivity.id.desc())
    ).all()
    campaigns = db.execute(
        select(MarketingCampaign)
        .where(MarketingCampaign.learner_number == lead.learner_number)
        .order_by(MarketingCampaign.created_at.desc(), MarketingCampaign.id.desc())
    ).scalars().all() if lead.learner_number else []

    person_info = {contact_key(lead): contact_info(db, lead)}
    return {
        "lead": {
            "id": lead.id,
            "learner_number": lead.learner_number,
            "customer_id": lead.customer_id,
            "opportunity_key": lead.opportunity_key,
            "target_code": lead.target_code,
            "stage": lead.stage,
            "reason": lead.reason,
            "trigger_date": lead.trigger_date,
            "status": lead.status,
            "is_active": lead.is_active,
            "assigned_to_user_id": lead.assigned_to_user_id,
            "assigned_to_name": counselor.display_name if counselor else None,
            "assignment_source": "DAILY_LEARNERS" if lead.counselor_from_daily else "MAIN_CRM" if lead.counselor_from_main else None,
            "assigned_at": lead.assigned_at,
            "status_updated_at": lead.status_updated_at,
            "created_at": lead.created_at,
            "updated_at": lead.updated_at,
        },
        "learner": {
            "customer_id": lead.customer_id,
            "learner_number": lead.learner_number,
            "name": person_info[contact_key(lead)][0]["full_name"] or "Unknown",
            "email_id": person_info[contact_key(lead)][0]["email"],
            "contact_number": person_info[contact_key(lead)][0]["phone_number"],
            "nationality": learner.nationality if learner else None,
            "last_activity_date": learner.last_activity_date if learner else None,
        },
        "activities": [
            {
                "id": activity.id,
                "activity_type": activity.activity_type,
                "channel": activity.channel,
                "campaign_name": activity.campaign_name,
                "notes": activity.notes,
                "created_at": activity.created_at,
                "user_name": activity_user.display_name if activity_user else "System",
            }
            for activity, activity_user in activity_rows
        ],
        "campaigns": [
            {
                "id": campaign.id,
                "campaign_name": campaign.campaign_name,
                "marketing_type": campaign.marketing_type,
                "created_at": campaign.created_at,
            }
            for campaign in campaigns
        ],
    }


@router.patch("/{lead_id}/status")
def update_status(
    lead_id: int,
    payload: StatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = get_accessible_lead(db, lead_id, current_user)
    if payload.status.strip().upper() == "CONVERTED":
        raise HTTPException(409, "Open Manage, choose a mapped course and use Update converted.")
    current_case = db.scalar(select(UpsellCourseCase).where(UpsellCourseCase.lead_id == lead.id, UpsellCourseCase.current_slot == 1))
    if current_case:
        from app.routers.upsell_management import case_status, CaseStatus
        case_status(lead.id, current_case.id, CaseStatus(status=payload.status, note=payload.note), current_user, db)
        db.refresh(lead)
        return {"id": lead.id, "status": lead.status, "status_updated_at": lead.status_updated_at}
    updated = change_lead_status(db, lead, payload.status, current_user, payload.note)
    return {"id": updated.id, "status": updated.status, "status_updated_at": updated.status_updated_at}


@router.patch("/{lead_id}/assignment")
def update_assignment(
    lead_id: int,
    payload: AssignmentUpdate,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lead = get_accessible_lead(db, lead_id, admin_user)
    updated = assign_lead(db, lead, payload.counselor_user_id, admin_user)
    counselor = db.get(User, updated.assigned_to_user_id) if updated.assigned_to_user_id else None
    return {
        "id": updated.id,
        "assigned_to_user_id": updated.assigned_to_user_id,
        "assigned_to_name": counselor.display_name if counselor else None,
            "assignment_source": "DAILY_LEARNERS" if lead.counselor_from_daily else "MAIN_CRM" if lead.counselor_from_main else None,
        "assigned_at": updated.assigned_at,
    }


@router.post("/{lead_id}/activities")
def create_activity(
    lead_id: int,
    payload: ActivityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = get_accessible_lead(db, lead_id, current_user)
    activity = add_lead_activity(
        db,
        lead,
        current_user,
        payload.activity_type,
        payload.campaign_name,
        payload.notes,
    )
    return {
        "id": activity.id,
        "activity_type": activity.activity_type,
        "channel": activity.channel,
        "campaign_name": activity.campaign_name,
        "notes": activity.notes,
        "created_at": activity.created_at,
        "user_name": current_user.display_name,
    }
