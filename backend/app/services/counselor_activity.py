"""Append-only counselor activity facts for later performance reporting."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models import CounselorAction, User


def required_contact_note(value):
    note = (value or "").strip()
    if not note:
        raise HTTPException(400, "Add a new contact note explaining the conversation before changing status.")
    if len(note) > 2000:
        raise HTTPException(400, "Contact note must be 2,000 characters or fewer.")
    return note


def latest_contact_note(db, *, main=None, lead=None, course_case=None):
    if main:
        return main.notes
    column = CounselorAction.upsell_case_id if course_case else CounselorAction.upsell_lead_id
    target = course_case.id if course_case else lead.id
    return db.scalar(select(CounselorAction.after_note).where(
        column == target, CounselorAction.after_note.is_not(None)
    ).order_by(CounselorAction.created_at.desc(), CounselorAction.id.desc()).limit(1))


def new_contact_note(db, value, *, main=None, lead=None, course_case=None):
    note = required_contact_note(value)
    previous = latest_contact_note(db, main=main, lead=lead, course_case=course_case)
    if note == (previous or "").strip():
        raise HTTPException(400, "Add a new contact note before changing status.")
    return note


def record_action(db, *, user, action_type, main=None, lead=None, course_case=None,
                  before_status=None, after_status=None, before_note=None, after_note=None,
                  channel=None):
    if not main and not lead:
        raise ValueError("A counselor action must belong to a CRM lead.")
    assignee_id = (main or lead).assigned_to_user_id
    assignee = db.get(User, assignee_id) if assignee_id else None
    db.add(CounselorAction(
        main_lead_id=main.id if main else None,
        upsell_lead_id=lead.id if lead else None,
        upsell_case_id=course_case.id if course_case else None,
        user_id=user.id,
        actor_name=user.display_name or user.username,
        assigned_counselor_id=assignee_id,
        assigned_counselor_name=(assignee.display_name or assignee.username) if assignee else None,
        action_type=action_type,
        before_status=before_status,
        after_status=after_status,
        before_note=before_note,
        after_note=after_note,
        course_name=course_case.course_name if course_case else main.course if main else lead.target_code,
        source=main.source if main else None,
        channel=channel,
    ))
