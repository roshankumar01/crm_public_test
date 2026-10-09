from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (Customer, Lead, LearnerCourseCategory, LearnerCourseMapping, LearnerCourseSubcategory,
    MainCrmLead, UpsellContactInfo, UpsellInfoEdit, UpsellCourseCase, UpsellCourseActivity, User)
from app.services.auth import get_current_user, require_admin
from app.services.lead_workflow import get_accessible_lead, sync_opportunity_leads
from app.services.upsell_management import PERSON_FIELDS, contact_info, cases_payload, registration_exists, activity_payload, contact_infos
from app.services.date_filters import period_condition
from app.services.learner_course_mapping import normalize_course_name

from app.services.conversion_verification import report_condition, verify_conversion
from app.services.counselor_activity import record_action, new_contact_note, latest_contact_note

router = APIRouter(prefix="/upsell/manage", tags=["Upsell course management"])


class InfoEdit(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=320)
    phone_number: str | None = Field(None, max_length=100)
    whatsapp_number: str | None = Field(None, max_length=100)
    region: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    age: int | None = Field(None, ge=0, le=150)


class CourseChoice(BaseModel):
    mapping_id: int


class CaseStatus(BaseModel):
    status: str
    note: str | None = None


class ConversionInput(BaseModel):
    note: str | None = None


class ActivityInput(BaseModel):
    activity_type: str = "NOTE"
    campaign_name: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=10000)


def checked_case(db, lead_id, case_id, user, writable=True):
    lead = get_accessible_lead(db, lead_id, user)
    db.execute(select(Lead.id).where(Lead.id == lead.id).with_for_update())
    item = db.scalar(select(UpsellCourseCase).where(UpsellCourseCase.id == case_id, UpsellCourseCase.lead_id == lead.id).with_for_update())
    if not item: raise HTTPException(404, "Course panel not found.")
    if writable and item.status == "CONVERTED": raise HTTPException(409, "This course is converted. Its history is preserved; choose a new course panel.")
    return lead, item


def activity_values(payload):
    kind = payload.activity_type.strip().upper()
    if kind not in {"NOTE", "CALL", "EMAIL_CAMPAIGN", "WHATSAPP_CAMPAIGN"}: raise HTTPException(400, "Choose a valid contact activity.")
    campaign = (payload.campaign_name or "").strip() or None
    notes = (payload.notes or "").strip() or None
    if kind.endswith("CAMPAIGN") and not campaign: raise HTTPException(400, "Enter the campaign name.")
    if not campaign and not notes: raise HTTPException(400, "Enter contact notes before saving.")
    return {"activity_type": kind, "campaign_name": campaign, "notes": notes}


@router.get("/catalog")
def catalog(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(LearnerCourseMapping, LearnerCourseCategory, LearnerCourseSubcategory)
        .join(LearnerCourseCategory, LearnerCourseMapping.category_id == LearnerCourseCategory.id)
        .join(LearnerCourseSubcategory, LearnerCourseMapping.subcategory_id == LearnerCourseSubcategory.id)
        .order_by(LearnerCourseCategory.display_order, LearnerCourseSubcategory.display_order, LearnerCourseMapping.course_name)).all()
    return [{"id": course.id, "course_name": course.course_name, "main_category": category.name,
        "category_id": category.id, "sub_category": sub.name, "subcategory_id": sub.id} for course, category, sub in rows]


@router.get("/mismatch")
def mismatch(period: str = "all", page: int = Query(1, ge=1), user: User = Depends(get_current_user), db: Session = Depends(get_db), state: str = "pending"):
    conditions = [UpsellCourseCase.status == "CONVERTED", *report_condition(UpsellCourseCase, state), *period_condition(UpsellCourseCase.converted_at, period)]
    if user.role != "ADMIN": conditions.append(Lead.assigned_to_user_id == user.id)
    query = select(UpsellCourseCase).join(Lead, UpsellCourseCase.lead_id == Lead.id).where(*conditions)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    cases = db.scalars(query.order_by(UpsellCourseCase.converted_at.desc(), UpsellCourseCase.id.desc()).offset((page-1)*50).limit(50)).all()
    people = contact_infos(db, [SimpleNamespace(customer_id=c.customer_id, learner_number=None) for c in cases])
    payload = cases_payload(db, cases, include_activities=False)
    for item, case in zip(payload, cases):
        person = people[case.customer_id if case.customer_id is not None else ("board", None)][0]
        item.update(name=person["full_name"] or "Unknown", email=person["email"], phone=person["phone_number"])
        item.pop("activities", None)
    return {"items": payload, "total": total, "page": page, "pages": max(1, (total+49)//50)}


@router.get("/mismatch/export")
def export_mismatch(period: str = "all", user: User = Depends(get_current_user), db: Session = Depends(get_db), state: str = "pending"):
    conditions = [UpsellCourseCase.status == "CONVERTED", *report_condition(UpsellCourseCase, state), *period_condition(UpsellCourseCase.converted_at, period)]
    if user.role != "ADMIN": conditions.append(Lead.assigned_to_user_id == user.id)
    rows = db.execute(select(UpsellCourseCase, Customer, User.display_name).join(Lead, UpsellCourseCase.lead_id == Lead.id)
        .outerjoin(Customer, Customer.id == UpsellCourseCase.customer_id).outerjoin(User, User.id == UpsellCourseCase.counselor_id)
        .where(*conditions).order_by(UpsellCourseCase.converted_at.desc())).all()
    people = contact_infos(db, [SimpleNamespace(customer_id=item.customer_id, learner_number=None) for item, _, _ in rows])
    checks = {item["id"]: item for item in cases_payload(db, [item for item, _, _ in rows], include_activities=False)}
    values = [{"Verification": checks[item.id]["verification_source"], "Verified By": checks[item.id]["verified_by"], "Verified At": checks[item.id]["verified_at"].isoformat() if checks[item.id]["verified_at"] else None, "Name": people[item.customer_id if item.customer_id is not None else ("board", None)][0]["full_name"],
        "Email": people[item.customer_id if item.customer_id is not None else ("board", None)][0]["email"],
        "Phone": people[item.customer_id if item.customer_id is not None else ("board", None)][0]["phone_number"], "Main Category": item.main_category, "Subcategory": item.sub_category,
        "Course": item.course_name, "Converted Date": item.converted_at.isoformat() if item.converted_at else None,
        "Counselor": owner, "Lead ID": item.lead_id} for item, c, owner in rows]
    output = BytesIO()
    pd.DataFrame(values, columns=["Name", "Email", "Phone", "Main Category", "Subcategory", "Course", "Converted Date", "Counselor", "Lead ID", "Verification", "Verified By", "Verified At"]).to_excel(output, index=False)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="upsell-mismatch.xlsx"'})


@router.post("/mismatch/{case_id}/verify")
def verify_upsell_mismatch(case_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(UpsellCourseCase, case_id)
    if not item: raise HTTPException(404, "Course conversion not found.")
    return verify_conversion(db, item, admin)


@router.get("/{lead_id}")
def management(lead_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db), history_page: int = Query(1, ge=1)):
    sync_opportunity_leads(db)
    lead = get_accessible_lead(db, lead_id, user)
    info, _, main_id = contact_info(db, lead)
    suggestions = db.scalars(select(Lead).where(Lead.customer_id == lead.customer_id, Lead.is_active.is_(True), or_(Lead.status != "CONVERTED", select(UpsellCourseCase.id).where(UpsellCourseCase.lead_id == Lead.id).exists()))
        .order_by(Lead.stage.desc(), Lead.id).limit(20)).all() if lead.customer_id else [lead]
    completed_subcategories = set(db.scalars(select(UpsellCourseCase.normalized_subcategory).where(
        UpsellCourseCase.customer_id == lead.customer_id, UpsellCourseCase.status == "CONVERTED"))) if lead.customer_id else set()
    suggestions = [item for item in suggestions if normalize_course_name(item.target_code) not in completed_subcategories]
    open_cases = db.scalars(select(UpsellCourseCase).where(UpsellCourseCase.lead_id == lead.id, UpsellCourseCase.status != "CONVERTED")
        .order_by(UpsellCourseCase.id.desc()).limit(30)).all()
    scope = UpsellCourseCase.customer_id == lead.customer_id if lead.customer_id else UpsellCourseCase.lead_id == lead.id
    converted_query = select(UpsellCourseCase).where(scope, UpsellCourseCase.status == "CONVERTED")
    total = db.scalar(select(func.count()).select_from(converted_query.subquery())) or 0
    converted = db.scalars(converted_query.order_by(UpsellCourseCase.converted_at.desc(), UpsellCourseCase.id.desc()).offset((history_page-1)*20).limit(20)).all()
    main_conversions = db.scalars(select(MainCrmLead).where(MainCrmLead.customer_id == lead.customer_id, MainCrmLead.status_of_lead == "CONVERTED")
        .order_by(MainCrmLead.updated_at.desc()).limit(20)).all() if lead.customer_id else []
    from app.services.conversion_verification import verification_payloads
    main_checks = verification_payloads(db, MainCrmLead, [item.id for item in main_conversions])
    return {"info": info, "main_lead_id": main_id,
        "suggestions": [{"lead_id": item.id, "sub_category": item.target_code, "stage": item.stage, "reason": item.reason} for item in suggestions],
        "cases": cases_payload(db, open_cases), "conversions": cases_payload(db, converted), "conversion_total": total,
        "history_page": history_page, "history_pages": max(1, (total+19)//20),
        "main_conversions": [{**main_checks[item.id], "id": item.id, "course": item.course, "updated_at": item.updated_at} for item in main_conversions],
        "changes": [{"id": edit.id, "raw_data": edit.raw_data, "created_at": edit.created_at} for edit in db.scalars(
            select(UpsellInfoEdit).where(UpsellInfoEdit.lead_id == lead.id).order_by(UpsellInfoEdit.id.desc()).limit(10))]}


@router.patch("/{lead_id}/info")
def edit_info(lead_id: int, payload: InfoEdit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = get_accessible_lead(db, lead_id, user)
    if not lead.customer_id: raise HTTPException(400, "This lead needs a linked contact before editing information.")
    db.execute(select(Customer.id).where(Customer.id == lead.customer_id).with_for_update())
    effective, baseline, _ = contact_info(db, lead)
    info = db.get(UpsellContactInfo, lead.customer_id)
    if not info: info = UpsellContactInfo(customer_id=lead.customer_id, overrides={}); db.add(info)
    overrides = dict(info.overrides)
    changes = {}
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if isinstance(value, str): value = value.strip() or None
        if field == "full_name" and not value: raise HTTPException(400, "Enter the full name.")
        if value != effective[field]:
            changes[field] = {"from": effective[field], "to": value}
            overrides[field] = {"value": value, "main_value": baseline[field]}
    if changes:
        info.overrides = overrides
        db.add(UpsellInfoEdit(lead_id=lead.id, raw_data={"changes": changes, "edited_by": {"id": user.id, "name": user.display_name}}))
        db.flush()
        keep = select(UpsellInfoEdit.id).where(UpsellInfoEdit.lead_id == lead.id).order_by(UpsellInfoEdit.id.desc()).limit(10)
        db.execute(delete(UpsellInfoEdit).where(UpsellInfoEdit.lead_id == lead.id, UpsellInfoEdit.id.not_in(keep)))
    db.commit()
    return {"ok": True}


@router.post("/{lead_id}/cases")
def choose_course(lead_id: int, payload: CourseChoice, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = get_accessible_lead(db, lead_id, user)
    db.execute(select(Lead.id).where(Lead.id == lead.id).with_for_update())
    mapping = db.get(LearnerCourseMapping, payload.mapping_id)
    if not mapping or not mapping.subcategory_id: raise HTTPException(400, "Choose a mapped course with a subcategory.")
    sub = db.get(LearnerCourseSubcategory, mapping.subcategory_id)
    main = db.get(LearnerCourseCategory, mapping.category_id)
    item = db.scalar(select(UpsellCourseCase).where(UpsellCourseCase.lead_id == lead.id,
        UpsellCourseCase.mapping_id == mapping.id, UpsellCourseCase.status != "CONVERTED").order_by(UpsellCourseCase.id.desc()).limit(1))
    if not item:
        item = UpsellCourseCase(lead_id=lead.id, customer_id=lead.customer_id, mapping_id=mapping.id,
            subcategory_id=sub.id,
            main_category=main.name, sub_category=sub.name, normalized_subcategory=sub.normalized_name,
            course_name=mapping.course_name, status="NEW")
        db.add(item)
    db.execute(update(UpsellCourseCase).where(UpsellCourseCase.lead_id == lead.id).values(current_slot=None))
    item.current_slot = 1
    lead.status = item.status
    lead.is_active = True
    db.commit(); db.refresh(item)
    return {"case_id": item.id}


@router.patch("/{lead_id}/cases/{case_id}/status")
def case_status(lead_id: int, case_id: int, payload: CaseStatus, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead, item = checked_case(db, lead_id, case_id, user)
    status = payload.status.upper().strip()
    if status not in {"NEW", "IN_CONTACT", "REJECTED"}: raise HTTPException(400, "Use Update converted to record a course conversion.")
    if item.status != status:
        note = new_contact_note(db, payload.note, course_case=item)
        previous_note = latest_contact_note(db, course_case=item)
        db.add(UpsellCourseActivity(case_id=item.id, user_id=user.id, activity_type="STATUS_CHANGE",
            notes=f"Status changed from {item.status} to {status}. Contact note: {note}"))
        record_action(db, user=user, lead=lead, course_case=item, action_type="STATUS_CHANGE",
            before_status=item.status, after_status=status, before_note=previous_note, after_note=note)
    item.status = status; lead.status = status; lead.status_updated_at = datetime.now(timezone.utc)
    db.commit(); return {"ok": True}


@router.post("/{lead_id}/cases/{case_id}/activities")
def save_activity(lead_id: int, case_id: int, payload: ActivityInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead, item = checked_case(db, lead_id, case_id, user)
    values = activity_values(payload)
    previous_note = latest_contact_note(db, course_case=item)
    db.add(UpsellCourseActivity(case_id=item.id, user_id=user.id, **values))
    record_action(db, user=user, lead=lead, course_case=item,
        action_type="NOTE" if values["activity_type"] == "NOTE" else "CONTACT",
        before_note=previous_note, after_note=values["notes"], channel=values["activity_type"])
    db.commit(); return {"ok": True}


@router.patch("/{lead_id}/cases/{case_id}/activities/{activity_id}")
def edit_activity(lead_id: int, case_id: int, activity_id: int, payload: ActivityInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead, item = checked_case(db, lead_id, case_id, user)
    activity = db.get(UpsellCourseActivity, activity_id)
    if not activity or activity.case_id != item.id or activity.activity_type == "STATUS_CHANGE": raise HTTPException(404, "Editable contact activity not found.")
    values = activity_values(payload)
    before_note = activity.notes
    if all(getattr(activity, key) == value for key, value in values.items()):
        return {"ok": True}
    for key, value in values.items(): setattr(activity, key, value)
    activity.updated_at = datetime.now(timezone.utc); activity.edited_by_id = user.id
    record_action(db, user=user, lead=lead, course_case=item, action_type="CONTACT_EDIT",
        before_note=before_note, after_note=activity.notes, channel=activity.activity_type)
    db.commit(); return {"ok": True}


@router.post("/{lead_id}/cases/{case_id}/convert")
def convert_course(lead_id: int, case_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db), payload: ConversionInput | None = Body(None)):
    lead, item = checked_case(db, lead_id, case_id, user, writable=False)
    if item.status != "CONVERTED":
        note = new_contact_note(db, payload.note if isinstance(payload, ConversionInput) else None, course_case=item)
        previous_note = latest_contact_note(db, course_case=item)
        db.add(UpsellCourseActivity(case_id=item.id, user_id=user.id, activity_type="STATUS_CHANGE",
            notes=f"Status changed from {item.status} to CONVERTED. Contact note: {note}"))
        record_action(db, user=user, lead=lead, course_case=item, action_type="STATUS_CHANGE",
            before_status=item.status, after_status="CONVERTED", before_note=previous_note, after_note=note)
        item.status = "CONVERTED"; item.converted_at = datetime.now(timezone.utc)
        item.current_slot = None
        item.counselor_id = lead.assigned_to_user_id; item.converted_by_id = user.id
        lead.status = "CONVERTED"; lead.status_updated_at = item.converted_at
    db.commit(); return {"ok": True, "case_id": item.id}


@router.get("/{lead_id}/history/{case_id}")
def contact_history(lead_id: int, case_id: int, page: int = Query(1, ge=1), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = get_accessible_lead(db, lead_id, user)
    item = db.get(UpsellCourseCase, case_id)
    if not item or not (item.lead_id == lead.id or (lead.customer_id and item.customer_id == lead.customer_id)):
        raise HTTPException(404, "Course history not found.")
    query = select(UpsellCourseActivity).where(UpsellCourseActivity.case_id == case_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    activities = db.scalars(query.order_by(UpsellCourseActivity.created_at.desc(), UpsellCourseActivity.id.desc()).offset((page-1)*50).limit(50)).all()
    ids = {i for a in activities for i in (a.user_id, a.edited_by_id) if i}
    users = dict(db.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all()) if ids else {}
    return {"items": [activity_payload(a, users) for a in activities], "total": total, "page": page}
