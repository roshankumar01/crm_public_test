"""Indexed, paginated counselor follow-up reminders in both workspaces."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Lead, LeadReminder, MainCrmLead, User
from app.services.auth import get_current_user
from app.services.upsell_management import contact_infos, contact_key

router = APIRouter(prefix="/reminders", tags=["Counselor reminders"])
COMPANY_ZONE = timezone(timedelta(hours=5, minutes=30))


def company_today():
    return datetime.now(COMPANY_ZONE).date()


class ReminderInput(BaseModel):
    days: int = Field(ge=0, le=3650, strict=True)
    notes: str | None = Field(default=None, max_length=2000)


def workspace_model(workspace):
    if workspace not in {"main", "upsell"}: raise HTTPException(400, "Choose Main CRM or Upsell CRM.")
    return MainCrmLead if workspace == "main" else Lead


def reminder_column(workspace):
    return LeadReminder.main_lead_id if workspace == "main" else LeadReminder.upsell_lead_id


def accessible(db, workspace, lead_id, user, lock=False):
    model = workspace_model(workspace)
    query = select(model).where(model.id == lead_id)
    if lock: query = query.with_for_update()
    lead = db.scalar(query)
    if not lead: raise HTTPException(404, "Lead not found.")
    if user.role != "ADMIN" and lead.assigned_to_user_id != user.id: raise HTTPException(403, "This lead is not assigned to you.")
    return lead


def payload(reminder, today=None):
    today = today or company_today()
    days = (reminder.due_date - today).days
    return {"id": reminder.id, "lead_id": reminder.main_lead_id or reminder.upsell_lead_id,
        "due_date": reminder.due_date, "remaining_days": max(0, days), "overdue_days": max(0, -days),
        "due_now": days <= 0 and reminder.completed_at is None, "notes": reminder.notes,
        "completed_at": reminder.completed_at, "updated_at": reminder.updated_at}


@router.get("/{workspace}")
def list_reminders(workspace: str, view: str = "pending", page: int = Query(1, ge=1),
    counselor_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    model = workspace_model(workspace)
    if view not in {"pending", "due", "upcoming", "completed"}: raise HTTPException(400, "Invalid reminder filter.")
    today = company_today()
    owner = func.coalesce(model.assigned_to_user_id, LeadReminder.created_by_id)
    scope = []
    if user.role != "ADMIN": scope.append(model.assigned_to_user_id == user.id)
    elif counselor_id is not None: scope.append(owner == counselor_id)
    base = select(LeadReminder, model, User.display_name).join(model, model.id == reminder_column(workspace)).outerjoin(User, User.id == owner).where(*scope)
    def count(*conditions):
        return db.scalar(select(func.count()).select_from(base.where(*conditions).subquery())) or 0
    conditions = [LeadReminder.completed_at.is_not(None)] if view == "completed" else [LeadReminder.completed_at.is_(None)]
    if view == "due": conditions.append(LeadReminder.due_date <= today)
    if view == "upcoming": conditions.append(LeadReminder.due_date > today)
    total = count(*conditions)
    rows = db.execute(base.where(*conditions).order_by(LeadReminder.due_date, LeadReminder.id).offset((page-1)*50).limit(50)).all()
    people = contact_infos(db, [lead for _, lead, _ in rows]) if workspace == "upsell" else {}
    items = []
    for reminder, lead, counselor in rows:
        person = people[contact_key(lead)][0] if workspace == "upsell" else None
        items.append({**payload(reminder, today), "name": person["full_name"] if person else lead.full_name,
            "email": person["email"] if person else lead.email, "phone": person["phone_number"] if person else lead.phone_number,
            "course": lead.target_code if workspace == "upsell" else lead.course,
            "counselor": counselor, "lead_status": lead.status if workspace == "upsell" else lead.status_of_lead})
    return {"items": items, "total": total, "page": page, "pages": max(1, (total+49)//50), "today": today,
        "counts": {"due": count(LeadReminder.completed_at.is_(None), LeadReminder.due_date <= today),
                   "upcoming": count(LeadReminder.completed_at.is_(None), LeadReminder.due_date > today),
                   "completed": count(LeadReminder.completed_at.is_not(None))}}


@router.get("/{workspace}/{lead_id}")
def get_reminder(workspace: str, lead_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accessible(db, workspace, lead_id, user)
    reminder = db.scalar(select(LeadReminder).where(reminder_column(workspace) == lead_id))
    return {"reminder": payload(reminder) if reminder else None, "today": company_today()}


@router.put("/{workspace}/{lead_id}")
def set_reminder(workspace: str, lead_id: int, body: ReminderInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accessible(db, workspace, lead_id, user, lock=True)
    reminder = db.scalar(select(LeadReminder).where(reminder_column(workspace) == lead_id))
    if not reminder:
        reminder = LeadReminder(main_lead_id=lead_id if workspace == "main" else None,
            upsell_lead_id=lead_id if workspace == "upsell" else None, created_by_id=user.id)
        db.add(reminder)
    reminder.due_date = company_today() + timedelta(days=body.days)
    reminder.notes = (body.notes or "").strip() or None
    reminder.updated_by_id = user.id
    reminder.updated_at = datetime.now(timezone.utc)
    reminder.completed_at = None
    db.commit()
    return payload(reminder)


@router.post("/{workspace}/{lead_id}/complete")
def complete_reminder(workspace: str, lead_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accessible(db, workspace, lead_id, user, lock=True)
    reminder = db.scalar(select(LeadReminder).where(reminder_column(workspace) == lead_id))
    if not reminder: raise HTTPException(404, "No reminder is set for this lead.")
    if reminder.completed_at is None:
        reminder.completed_at = datetime.now(timezone.utc)
        reminder.updated_by_id = user.id
        reminder.updated_at = reminder.completed_at
        db.commit()
    return payload(reminder)
