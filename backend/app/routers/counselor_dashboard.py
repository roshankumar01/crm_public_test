"""Admin reporting on Main CRM assignments and counselor-authored changes."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, case, cast, func, literal, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CounselorAction, Customer, Lead, MainCrmLead, User
from app.services.auth import require_admin


router = APIRouter(prefix="/company-dashboard/counselors", tags=["Counselor dashboard"])
INDIA = ZoneInfo("Asia/Kolkata")
PAGE_SIZE = 50


def bounds(period: str, start_date: date | None, end_date: date | None):
    today = datetime.now(INDIA).date()
    if period == "custom":
        if not start_date or not end_date or start_date > end_date:
            raise HTTPException(400, "Choose a valid start and end date.")
        first, last = start_date, end_date
    elif period == "all":
        return None
    elif period == "today":
        first = last = today
    elif period == "yesterday":
        first = last = today - timedelta(days=1)
    elif period == "last_7_days":
        first, last = today - timedelta(days=6), today
    elif period == "last_month":
        first, last = today - timedelta(days=29), today
    else:
        raise HTTPException(400, "Choose a valid date filter.")
    return (datetime.combine(first, time.min, INDIA).astimezone(timezone.utc),
            datetime.combine(last + timedelta(days=1), time.min, INDIA).astimezone(timezone.utc))


def in_period(column, window):
    return [column >= window[0], column < window[1]] if window else []


def person_key():
    """Use the shared contact across CRMs; keep unlinked leads distinct."""
    customer_id = func.coalesce(MainCrmLead.customer_id, Lead.customer_id)
    return case(
        (customer_id.is_not(None), literal("customer:") + cast(customer_id, String)),
        (CounselorAction.main_lead_id.is_not(None), literal("main:") + cast(CounselorAction.main_lead_id, String)),
        else_=literal("upsell:") + cast(CounselorAction.upsell_lead_id, String),
    )


def action_rows():
    return (select(CounselorAction)
            .outerjoin(MainCrmLead, MainCrmLead.id == CounselorAction.main_lead_id)
            .outerjoin(Lead, Lead.id == CounselorAction.upsell_lead_id))


@router.get("")
def summary(period: str = Query("last_7_days"), start_date: date | None = None,
            end_date: date | None = None, admin: User = Depends(require_admin),
            db: Session = Depends(get_db)):
    window = bounds(period, start_date, end_date)
    counselors = db.scalars(select(User).where(User.role == "COUNSELOR").order_by(User.display_name, User.id)).all()
    rows = {user.id: {"id": user.id, "name": user.display_name, "active": user.active,
                      "leads_given": 0, "main_updates": 0, "upsell_updates": 0, "total_updates": 0,
                      "unique_people": 0, "unique_main_people": 0, "unique_upsell_people": 0}
            for user in counselors}
    assigned = db.execute(select(MainCrmLead.assigned_to_user_id, func.count(MainCrmLead.id))
        .where(MainCrmLead.assigned_to_user_id.is_not(None), *in_period(MainCrmLead.assigned_at, window))
        .group_by(MainCrmLead.assigned_to_user_id)).all()
    for counselor_id, count in assigned:
        if counselor_id in rows:
            rows[counselor_id]["leads_given"] = count
    key = person_key()
    action_filters = [CounselorAction.user_id.is_not(None), *in_period(CounselorAction.created_at, window)]
    action_counts = db.execute(action_rows().with_only_columns(
        CounselorAction.user_id, CounselorAction.main_lead_id.is_not(None),
        func.count(CounselorAction.id), func.count(func.distinct(key)))
        .where(*action_filters).group_by(CounselorAction.user_id, CounselorAction.main_lead_id.is_not(None))).all()
    for counselor_id, is_main, count, unique_count in action_counts:
        if counselor_id in rows:
            rows[counselor_id]["main_updates" if is_main else "upsell_updates"] += count
            rows[counselor_id]["unique_main_people" if is_main else "unique_upsell_people"] += unique_count
            rows[counselor_id]["total_updates"] += count
    unique_rows = db.execute(action_rows().with_only_columns(
        CounselorAction.user_id, func.count(func.distinct(key)))
        .where(*action_filters).group_by(CounselorAction.user_id)).all()
    for counselor_id, unique_count in unique_rows:
        if counselor_id in rows:
            rows[counselor_id]["unique_people"] = unique_count
    people = sorted(rows.values(), key=lambda row: (-row["total_updates"], -row["leads_given"], row["name"].lower()))
    team_filter = [CounselorAction.user_id.in_(list(rows)), *in_period(CounselorAction.created_at, window)]
    team_unique = db.scalar(action_rows().with_only_columns(func.count(func.distinct(key)))
                            .where(*team_filter)) or 0
    team_workspace = db.execute(action_rows().with_only_columns(
        CounselorAction.main_lead_id.is_not(None), func.count(func.distinct(key)))
        .where(*team_filter).group_by(CounselorAction.main_lead_id.is_not(None))).all()
    unique_main = next((count for is_main, count in team_workspace if is_main), 0)
    unique_upsell = next((count for is_main, count in team_workspace if not is_main), 0)
    return {"cards": {"leads_given": sum(row["leads_given"] for row in people),
                      "main_updates": sum(row["main_updates"] for row in people),
                      "upsell_updates": sum(row["upsell_updates"] for row in people),
                      "total_updates": sum(row["total_updates"] for row in people),
                      "unique_people": team_unique, "unique_main_people": unique_main,
                      "unique_upsell_people": unique_upsell},
            "counselors": people}


@router.get("/changes")
def changes(counselor_id: int = Query(..., gt=0), page: int = Query(1, ge=1),
            period: str = Query("last_7_days"), start_date: date | None = None,
            end_date: date | None = None, admin: User = Depends(require_admin),
            db: Session = Depends(get_db), mode: str = "all", person: str | None = None):
    counselor = db.get(User, counselor_id)
    if not counselor or counselor.role != "COUNSELOR":
        raise HTTPException(404, "Counselor not found.")
    window = bounds(period, start_date, end_date)
    if mode not in {"all", "unique"}:
        raise HTTPException(400, "Choose all or unique updates.")
    filters = [CounselorAction.user_id == counselor_id, *in_period(CounselorAction.created_at, window)]
    key = person_key()
    if person:
        filters.append(key == person)
    base = action_rows().where(*filters)
    if mode == "unique":
        ranked = base.with_only_columns(
            CounselorAction.id.label("action_id"), key.label("person_key"),
            func.count(CounselorAction.id).over(partition_by=key).label("person_updates"),
            func.row_number().over(partition_by=key, order_by=(
                CounselorAction.created_at.desc(), CounselorAction.id.desc())).label("position"),
        ).subquery()
        total = db.scalar(base.with_only_columns(func.count(func.distinct(key)))) or 0
        selected = (select(ranked.c.action_id, ranked.c.person_key, ranked.c.person_updates)
                    .join(CounselorAction, CounselorAction.id == ranked.c.action_id)
                    .where(ranked.c.position == 1)
                    .order_by(CounselorAction.created_at.desc(), CounselorAction.id.desc())
                    .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).subquery()
    else:
        total = db.scalar(base.with_only_columns(func.count(CounselorAction.id))) or 0
        selected = (base.with_only_columns(CounselorAction.id.label("action_id"), key.label("person_key"),
                                           literal(None).label("person_updates"))
                    .order_by(CounselorAction.created_at.desc(), CounselorAction.id.desc())
                    .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).subquery()
    rows = db.execute(select(CounselorAction, MainCrmLead.full_name, Customer.primary_name,
                             Lead.learner_number, selected.c.person_key, selected.c.person_updates)
        .join(selected, selected.c.action_id == CounselorAction.id)
        .outerjoin(MainCrmLead, MainCrmLead.id == CounselorAction.main_lead_id)
        .outerjoin(Lead, Lead.id == CounselorAction.upsell_lead_id)
        .outerjoin(Customer, Customer.id == Lead.customer_id)
        .order_by(CounselorAction.created_at.desc(), CounselorAction.id.desc())).all()
    return {"counselor": {"id": counselor.id, "name": counselor.display_name},
            "total": total, "mode": mode, "page": page, "pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
            "items": [{"id": fact.id, "workspace": "main" if fact.main_lead_id else "upsell",
                       "lead_id": fact.main_lead_id or fact.upsell_lead_id,
                       "person_key": person_key_value, "person_updates": person_updates,
                       "lead_name": main_name or customer_name or learner_number or "Unknown lead",
                       "course": fact.course_name, "source": fact.source,
                       "action_type": fact.action_type, "channel": fact.channel,
                       "before_status": fact.before_status, "after_status": fact.after_status,
                       "before_note": fact.before_note, "after_note": fact.after_note,
                       "actor_name": fact.actor_name,
                       "assigned_counselor_name": fact.assigned_counselor_name,
                       "created_at": fact.created_at}
                      for fact, main_name, customer_name, learner_number, person_key_value, person_updates in rows]}
