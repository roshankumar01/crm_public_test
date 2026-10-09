import re
import json
import secrets
from io import BytesIO, StringIO
import csv
from datetime import datetime, timezone
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import AuthSession, Customer, CustomerIdentity, Learner, LearnersCrmProfile, MainCrmActivity, MainCrmLead, UploadBatch, User
from app.services.auth import get_current_user, hash_password, require_admin
from app.services.customer_identity import customer_is_registered, mark_customer_converted, resolve_customer
from app.services.customer_lifecycle import customer_lifecycle
from app.services.counselor_sync import sync_main_counselors
from app.services.importers.common import clean, dataframe_row_to_dict, parse_date, read_upload, require_columns, upload_rows, UPLOAD_CHUNK_SIZE
from app.services.date_filters import period_condition

from app.services.conversion_verification import verification_payloads, report_condition, verify_conversion
from app.services.counselor_activity import record_action, required_contact_note, new_contact_note

router = APIRouter(prefix="/crm/leads", tags=["Main CRM"])

SOURCE_CATEGORIES = {"INFO_EMAIL_LEADS", "LIVE_ONLINE_LEADS", "DIRECT_CALLS", "CAMPAIGN_REPLIES", "CAMPAIGN_DATA"}
MIGRATION_TYPE = "MAIN_CRM_MIGRATION"
MIGRATION_CONTACT_COLUMNS = {"email", "emailids", "mobile", "otherphonenumbers"}
MIGRATION_CHUNK_SIZE = 500
MIGRATION_PROGRESS = {}
REQUIRED_COLUMNS = {
    "INFO_EMAIL_LEADS": {"fullname", "email", "phonenumber", "source", "course"},
    "LIVE_ONLINE_LEADS": {"fullname", "email", "phonenumber", "whatsappnumber", "source", "course", "regions", "counsilorname", "country"},
    "DIRECT_CALLS": {"date", "email", "phonenumber", "course"},
    "CAMPAIGN_REPLIES": {"date", "email", "campaigntype", "course", "fulluserreply", "campaignname", "campaigndescription"},
    "CAMPAIGN_DATA": {"date", "email", "campaigntype", "campaignname", "campaigndescription", "coursecampaign"},
}


class StatusUpdate(BaseModel):
    status: str
    note: str | None = None


class AssignmentUpdate(BaseModel):
    counselor_user_id: int | None = None


class LeadEditPayload(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    whatsapp_number: str | None = None
    course: str | None = None
    region: str | None = None
    country: str | None = None
    age: int | None = None
    sales_owner: str | None = None


class LeadNotePayload(BaseModel):
    note: str


class CounselorCreate(BaseModel):
    username: str
    display_name: str
    email: str
    country: str | None = None
    region: str | None = None
    password: str


class CounselorUpdate(BaseModel):
    display_name: str
    email: str
    country: str | None = None
    region: str | None = None
    password: str | None = None


def normalize_email(value):
    value = clean(value)
    return value.lower() if value else None


def normalize_phone(value):
    value = clean(value)
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits[-10:] if len(digits) >= 10 else digits or None


def row_value(row, *keys):
    for key in keys:
        value = clean(row.get(key))
        if value is not None:
            return value
    return None


def migration_category(source):
    value = (source or "").lower()
    if any(word in value for word in ("call", "telephone", "phone", "dial", "hotline")):
        return "DIRECT_CALLS"
    if any(word in value for word in ("live online", "live-online", "online", "webinar", "virtual")):
        return "LIVE_ONLINE_LEADS"
    return "INFO_EMAIL_LEADS"


def migration_contact(row):
    # The legacy `Email IDs` column is the primary address. `Email` is used
    # only as a fallback when Email IDs is blank or invalid.
    primary = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", row_value(row, "emailids") or "")
    fallback = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", row_value(row, "email") or "")
    email = (primary or fallback or [None])[0]
    phones = [re.sub(r"\.0$", "", value) if value else None for value in (row_value(row, "mobile"), row_value(row, "otherphonenumbers"))]
    phone = next((value for value in phones if value and len(re.sub(r"\D", "", value)) >= 7), None)
    return email, phone


def migration_status(value):
    status = re.sub(r"\s+", " ", (value or "").strip()).casefold()
    return {
        "": "BLANK", "new": "NEW", "no response": "NO_RESPONSE",
        "no response (rnr)": "NO_RESPONSE", "follow up": "FOLLOW_UP",
        "later": "LATER", "converted": "CONVERTED",
        "call me later": "CALL_ME_LATER", "good": "GOOD",
        "not interested": "NOT_INTERESTED", "invalid": "INVALID", "hot": "HOT",
    }.get(status, "OTHERS")


def previous_migration_status(value):
    status = (value or "").strip().lower()
    if any(word in status for word in ("convert", "won", "enrol", "register", "admission")):
        return "CONVERTED"
    if any(word in status for word in ("reject", "lost", "not interested", "closed", "invalid")):
        return "REJECTED"
    if any(word in status for word in ("follow", "pending", "callback")):
        return "FOLLOW_UP"
    if any(word in status for word in ("contact", "discussion", "negotiat")):
        return "IN_CONTACT"
    return "NEW"


def backfill_migration_statuses(db):
    rows = db.execute(
        select(MainCrmLead, MainCrmActivity.raw_data["statusoflead"].as_string())
        .join(MainCrmActivity, MainCrmActivity.lead_id == MainCrmLead.id)
        .join(UploadBatch, UploadBatch.id == MainCrmActivity.upload_batch_id)
        .where(UploadBatch.import_type == MIGRATION_TYPE, MainCrmLead.upload_batch_id == UploadBatch.id)
        .order_by(MainCrmActivity.id)
    ).all()
    seen = set()
    for lead, original in rows:
        if lead.id in seen:
            continue
        seen.add(lead.id)
        if lead.status_of_lead == previous_migration_status(original):
            lead.status_of_lead = migration_status(original)
    db.commit()


def migration_datetime(value):
    if clean(value) is None:
        return None
    text = clean(value)
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=not bool(re.match(r"^\d{4}-\d{1,2}-\d{1,2}", text)))
    if pd.isna(parsed):
        return None
    result = parsed.to_pydatetime()
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def validate_migration_columns(df):
    require_columns(df, {"name"}, "Old CRM migration")
    if not MIGRATION_CONTACT_COLUMNS.intersection(df.columns):
        raise ValueError("Old CRM migration needs at least one contact column: Email, Email IDs, Mobile, or Other Phone numbers.")


def lead_dict(lead, counselor=None, is_migrated=False):
    return {
        "id": lead.id, "customer_id": lead.customer_id, "full_name": lead.full_name, "email": lead.email,
        "phone_number": lead.phone_number, "whatsapp_number": lead.whatsapp_number,
        "source_category": lead.source_category, "source": lead.source, "course": lead.course,
        "is_migrated": is_migrated,
        "region": lead.region, "country": lead.country, "age": lead.age, "status_of_lead": lead.status_of_lead,
        "assigned_to_user_id": lead.assigned_to_user_id,
        "counselor": counselor.display_name if counselor else None,
        "counselor_email": counselor.email if counselor else None,
        "sales_owner": lead.sales_owner, "notes": lead.notes,
        "matched_learner_number": lead.matched_learner_number,
        "created_at": lead.created_at, "updated_at": lead.updated_at,
    }


def accessible_lead(db, lead_id, user):
    lead = db.get(MainCrmLead, lead_id)
    if not lead or (user.role != "ADMIN" and lead.assigned_to_user_id != user.id):
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


def new_upload_number(db):
    while True:
        value = f"CRM-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
        if not db.scalar(select(UploadBatch).where(UploadBatch.unique_number == value)):
            return value


def counselor_dict(user):
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "email": user.email, "country": user.country, "region": user.region, "active": user.active}


@router.get("/counselor-mapping")
def list_counselor_mapping(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.execute(select(User).where(User.role == "COUNSELOR").order_by(User.display_name)).scalars().all()
    return [counselor_dict(user) for user in users]


@router.post("/counselor-mapping")
def create_counselor(payload: CounselorCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    if not username or db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=400, detail="That username is already used or invalid.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must contain at least 8 characters.")
    user = User(username=username, display_name=payload.display_name.strip(), email=payload.email.strip().lower(), country=clean(payload.country), region=clean(payload.region), password_hash=hash_password(payload.password), role="COUNSELOR", active=True)
    db.add(user); db.commit(); db.refresh(user)
    return counselor_dict(user)


@router.patch("/counselor-mapping/{user_id}")
def update_counselor(user_id: int, payload: CounselorUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or user.role != "COUNSELOR":
        raise HTTPException(status_code=404, detail="Counselor not found.")
    user.display_name = payload.display_name.strip(); user.email = payload.email.strip().lower(); user.country = clean(payload.country); user.region = clean(payload.region)
    if payload.password:
        if len(payload.password) < 8:
            raise HTTPException(status_code=400, detail="Password must contain at least 8 characters.")
        user.password_hash = hash_password(payload.password)
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit(); db.refresh(user)
    return counselor_dict(user)


@router.get("")
def list_leads(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    source_category: str = Query("ALL"), search: str = Query("", max_length=320),
    counselor_ids: Annotated[list[str] | None, Query()] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    sources: Annotated[list[str] | None, Query()] = None,
    courses: Annotated[list[str] | None, Query()] = None,
    sort_by: str = "updated_at", sort_direction: str = "desc",
):
    category = source_category.strip().upper()
    if category not in {"ALL", *SOURCE_CATEGORIES}:
        raise HTTPException(status_code=400, detail="Invalid lead source category.")
    filters = []
    if current_user.role != "ADMIN":
        filters.append(MainCrmLead.assigned_to_user_id == current_user.id)
    if category != "ALL":
        filters.append(MainCrmLead.source_category == category)
    if counselor_ids:
        owner_filters = []
        for value in counselor_ids:
            if value == "UNASSIGNED": owner_filters.append(MainCrmLead.assigned_to_user_id.is_(None))
            elif value.isdigit() and int(value) > 0: owner_filters.append(MainCrmLead.assigned_to_user_id == int(value))
            else: raise HTTPException(status_code=400, detail="Invalid counselor filter.")
        filters.append(or_(*owner_filters))
    for column, values in ((MainCrmLead.status_of_lead, statuses), (MainCrmLead.source, sources), (MainCrmLead.course, courses)):
        if values:
            matches = [column.in_([value for value in values if value != "__EMPTY__"])]
            if "__EMPTY__" in values: matches.append(or_(column.is_(None), column == ""))
            filters.append(or_(*matches))
    if sort_by not in {"created_at", "updated_at"} or sort_direction not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid date sort option.")
    term = search.strip()
    if term:
        pattern = f"%{term}%"
        searchable = [MainCrmLead.full_name.ilike(pattern), MainCrmLead.email.ilike(pattern),
                      MainCrmLead.course.ilike(pattern), MainCrmLead.source.ilike(pattern)]
        digits = normalize_phone(term)
        if digits and len(digits) >= 3:
            searchable.append(MainCrmLead.normalized_phone.like(f"%{digits}%"))
        filters.append(or_(*searchable))
    total = db.scalar(select(func.count()).select_from(MainCrmLead).where(*filters)) or 0
    migrated = select(MainCrmActivity.id).where(MainCrmActivity.lead_id == MainCrmLead.id, MainCrmActivity.activity_type == "MIGRATION").exists()
    query = select(MainCrmLead, User, migrated).outerjoin(User, MainCrmLead.assigned_to_user_id == User.id).where(*filters)
    sort_column = getattr(MainCrmLead, sort_by)
    order = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
    tie_breaker = MainCrmLead.id.asc() if sort_direction == "asc" else MainCrmLead.id.desc()
    rows = db.execute(query.order_by(order, tie_breaker)
                      .limit(page_size).offset((page - 1) * page_size)).all()
    checks = verification_payloads(db, MainCrmLead, [lead.id for lead, _, _ in rows])
    return {"items": [dict(lead_dict(lead, counselor, is_migrated), **checks[lead.id]) for lead, counselor, is_migrated in rows],
            "total": total, "page": page, "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size)}


@router.get("/filter-options")
def lead_filter_options(current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
                        source_category: str = "ALL"):
    category = source_category.strip().upper()
    if category not in {"ALL", *SOURCE_CATEGORIES}:
        raise HTTPException(status_code=400, detail="Invalid lead source category.")
    filters = [] if current_user.role == "ADMIN" else [MainCrmLead.assigned_to_user_id == current_user.id]
    if category != "ALL": filters.append(MainCrmLead.source_category == category)
    result = {}
    for key, column, fallback in (("statuses", MainCrmLead.status_of_lead, "blank"),
                                  ("sources", MainCrmLead.source, "No source"),
                                  ("courses", MainCrmLead.course, "No course")):
        rows = db.execute(select(column, func.count(MainCrmLead.id)).where(*filters).group_by(column)).all()
        options = {}
        for value, count in rows:
            code = value or "__EMPTY__"
            item = options.setdefault(code, {"value": code, "label": value or fallback, "count": 0})
            item["count"] += count
        result[key] = sorted(options.values(), key=lambda item: item["label"].casefold())
    owners = db.execute(select(MainCrmLead.assigned_to_user_id, User.display_name, func.count(MainCrmLead.id))
                        .outerjoin(User, User.id == MainCrmLead.assigned_to_user_id).where(*filters)
                        .group_by(MainCrmLead.assigned_to_user_id, User.display_name)).all()
    result["counselors"] = sorted([{"value": str(owner_id) if owner_id is not None else "UNASSIGNED",
                                   "label": name or "Unassigned", "count": count}
                                  for owner_id, name, count in owners], key=lambda item: item["label"].casefold())
    return result


@router.get("/summary")
def lead_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db), period: str = "all"):
    filters = [] if current_user.role == "ADMIN" else [MainCrmLead.assigned_to_user_id == current_user.id]
    filters.extend(period_condition(MainCrmLead.created_at, period))
    registered_ids = set(db.execute(select(Learner.customer_id).where(Learner.customer_id.is_not(None))).scalars())
    registered_ids.update(db.execute(select(LearnersCrmProfile.customer_id).where(LearnersCrmProfile.customer_id.is_not(None))).scalars())
    if registered_ids:
        conversion_update = db.execute(MainCrmLead.__table__.update().where(MainCrmLead.customer_id.in_(registered_ids), MainCrmLead.status_of_lead != "CONVERTED").values(status_of_lead="CONVERTED"))
        if conversion_update.rowcount:
            db.commit()
    registered_customer_ids = set()
    if registered_ids:
        registered_customer_ids = set(db.execute(select(MainCrmLead.customer_id).where(*filters, MainCrmLead.customer_id.in_(registered_ids))).scalars())
    migration_activity = select(MainCrmActivity.id).where(
        MainCrmActivity.lead_id == MainCrmLead.id,
        MainCrmActivity.activity_type == "MIGRATION",
    ).exists()
    rows = db.execute(select(
        MainCrmLead.source, MainCrmLead.status_of_lead, migration_activity, func.count(),
        func.sum(case((MainCrmLead.customer_id.in_(registered_ids), 1), else_=0)) if registered_ids else func.sum(case((MainCrmLead.id == -1, 1), else_=0)),
        func.sum(case((MainCrmLead.assigned_to_user_id.is_(None), 1), else_=0)),
    ).where(*filters).group_by(MainCrmLead.source, MainCrmLead.status_of_lead, migration_activity)).all()
    source_counts = {}
    source_category_counts = {category: 0 for category in SOURCE_CATEGORIES}
    source_breakdown = {}
    status_counts = {}
    status_breakdown = {}
    total = unassigned = 0
    for source, status, migrated, count, matched, without_owner in rows:
        source_name = (source or "Unknown").strip() or "Unknown"
        total += count
        unassigned += without_owner or 0
        source_counts[source_name] = source_counts.get(source_name, 0) + count
        status_counts[status] = status_counts.get(status, 0) + count
        entry = source_breakdown.setdefault(source_name, {"total": 0, "converted": 0, "registered": 0})
        entry["total"] += count
        entry["registered"] += matched or 0
        if status == "CONVERTED": entry["converted"] += count
        status_entry = status_breakdown.setdefault(status, {"total": 0, "normal": 0, "migrated": 0})
        status_entry["total"] += count
        status_entry["migrated" if migrated else "normal"] += count
    category_rows = db.execute(select(MainCrmLead.source_category, func.count()).where(*filters).group_by(MainCrmLead.source_category)).all()
    source_category_counts.update({category: count for category, count in category_rows})
    return {"total": total, "registered": len(registered_customer_ids), "unassigned": unassigned,
            "source_counts": source_counts, "source_category_counts": source_category_counts,
            "status_counts": status_counts, "status_breakdown": status_breakdown,
            "source_breakdown": source_breakdown}


def _mismatch_query(current_user, period="all", state="pending"):
    filters = [MainCrmLead.status_of_lead == "CONVERTED", *period_condition(MainCrmLead.created_at, period), *report_condition(MainCrmLead, state)]
    if current_user.role != "ADMIN": filters.append(MainCrmLead.assigned_to_user_id == current_user.id)
    return select(MainCrmLead, User).outerjoin(User, User.id == MainCrmLead.assigned_to_user_id).where(*filters)


@router.get("/mismatch")
def converted_mismatch(period: str = "all", current_user: User = Depends(get_current_user), db: Session = Depends(get_db), page: int = 1, state: str = "pending"):
    if page < 1: raise HTTPException(400, "Invalid page.")
    query = _mismatch_query(current_user, period, state)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()).offset((page-1)*50).limit(50)).all()
    checks = verification_payloads(db, MainCrmLead, [lead.id for lead, _ in rows])
    return {"total": total, "page": page, "pages": max(1, (total+49)//50), "items": [dict(lead_dict(lead, owner), **checks[lead.id]) for lead, owner in rows]}


@router.post("/mismatch/{lead_id}/verify")
def verify_main_mismatch(lead_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    lead = db.get(MainCrmLead, lead_id)
    if not lead: raise HTTPException(404, "Lead not found.")
    return verify_conversion(db, lead, admin)


@router.get("/mismatch/export")
def export_converted_mismatch(period: str = "all", current_user: User = Depends(get_current_user), db: Session = Depends(get_db), state: str = "pending"):
    leads = db.execute(_mismatch_query(current_user, period, state).order_by(MainCrmLead.updated_at.desc(), MainCrmLead.id.desc())).all()
    checks = verification_payloads(db, MainCrmLead, [lead.id for lead, _ in leads])
    rows = [{"Lead ID": lead.id, "Name": lead.full_name, "Email": lead.email, "Phone": lead.phone_number,
             "Course": lead.course, "Source": lead.source, "Status": lead.status_of_lead,
             "Counselor": owner.display_name if owner else "Unassigned", "Verification": checks[lead.id]["verification_source"],
             "Verified By": checks[lead.id]["verified_by"], "Verified At": checks[lead.id]["verified_at"].isoformat() if checks[lead.id]["verified_at"] else None,
             "Created At": lead.created_at.isoformat() if lead.created_at else None, "Updated At": lead.updated_at.isoformat() if lead.updated_at else None} for lead, owner in leads]
    output = BytesIO()
    pd.DataFrame(rows).to_excel(output, index=False)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="converted-mismatches.xlsx"'})


@router.get("/export")
def export_main_crm(period: str = "all", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    filters = period_condition(MainCrmLead.created_at, period)
    if current_user.role != "ADMIN": filters.append(MainCrmLead.assigned_to_user_id == current_user.id)
    leads = db.scalars(select(MainCrmLead).where(*filters).order_by(MainCrmLead.created_at.desc())).all()
    rows = [{"Lead ID": lead.id, "Name": lead.full_name, "Email": lead.email, "Phone": lead.phone_number,
             "Course": lead.course, "Source": lead.source, "Source Category": lead.source_category,
             "Status": lead.status_of_lead, "Sales Owner": lead.sales_owner, "Created At": lead.created_at,
             "Updated At": lead.updated_at} for lead in leads]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer: pd.DataFrame(rows).to_excel(writer, sheet_name="Main CRM", index=False)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="main-crm-export.xlsx"'})


def activity_dict(activity, lead=None):
    return {
        "id": activity.id, "lead_id": activity.lead_id,
        "lead_name": lead.full_name if lead else None, "lead_email": lead.email if lead else None,
        "activity_type": activity.activity_type, "activity_date": activity.activity_date,
        "channel": activity.channel, "campaign_name": activity.campaign_name,
        "campaign_description": activity.campaign_description, "course": activity.course,
        "full_user_reply": activity.full_user_reply, "notes": activity.notes,
        "raw_data": activity.raw_data, "created_at": activity.created_at,
    }


@router.get("/campaign-activities")
def list_campaign_activities(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(MainCrmActivity, MainCrmLead).join(MainCrmLead, MainCrmActivity.lead_id == MainCrmLead.id).where(
        MainCrmActivity.activity_type.in_(["CAMPAIGN_SENT", "CAMPAIGN_REPLY"])
    )
    if current_user.role != "ADMIN":
        query = query.where(MainCrmLead.assigned_to_user_id == current_user.id)
    rows = db.execute(query.order_by(MainCrmActivity.activity_date.desc(), MainCrmActivity.id.desc())).all()
    return [activity_dict(activity, lead) for activity, lead in rows]


@router.get("/detail/{lead_id}")
def get_main_crm_lead(lead_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = accessible_lead(db, lead_id, current_user)
    counselor = db.get(User, lead.assigned_to_user_id) if lead.assigned_to_user_id else None
    activities = db.execute(select(MainCrmActivity).where(
        MainCrmActivity.lead_id == lead.id, MainCrmActivity.activity_type != "EDIT"
    ).order_by(
        MainCrmActivity.activity_date.desc(), MainCrmActivity.id.desc()
    )).scalars().all()
    migrated = any(item.activity_type == "MIGRATION" for item in activities)
    profile = dict(lead_dict(lead, counselor, migrated), **verification_payloads(db, MainCrmLead, [lead.id])[lead.id])
    if migrated:
        source_dates = []
        for item in activities:
            if item.activity_type != "MIGRATION":
                continue
            raw = (item.raw_data or {}).get("updatedat")
            parsed = migration_datetime(raw)
            if parsed:
                source_dates.append((parsed, clean(raw)))
        latest = max(source_dates, key=lambda item: item[0], default=None)
        profile["migration_updated_at"] = latest[1] if latest else None
    return {"lead": profile,
            "activities": [activity_dict(item) for item in activities],
            "changes": [activity_dict(item) for item in db.scalars(select(MainCrmActivity).where(
                MainCrmActivity.lead_id == lead.id, MainCrmActivity.activity_type == "EDIT"
            ).order_by(MainCrmActivity.created_at.desc(), MainCrmActivity.id.desc()).limit(10)).all()],
            "lifecycle": customer_lifecycle(db, lead.customer_id, current_user)}


@router.get("/uploads")
def list_crm_uploads(admin_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(
        select(UploadBatch).where(UploadBatch.import_type.like("MAIN_CRM_%"))
        .order_by(UploadBatch.uploaded_at.desc(), UploadBatch.id.desc())
    ).scalars().all()
    return [{
        "id": item.id, "unique_number": item.unique_number, "filename": item.filename,
        "source_category": item.import_type.removeprefix("MAIN_CRM_"), "status": item.status,
        "rows_total": item.rows_total, "rows_imported": item.rows_imported,
        "rows_skipped": item.rows_skipped, "uploaded_at": item.uploaded_at,
        "error_message": item.error_message,
    } for item in rows]


@router.post("/migration-preview")
def preview_migration(file: Annotated[UploadFile, File()], admin_user: User = Depends(require_admin)):
    try:
        df = read_upload(file)
        validate_migration_columns(df)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    counts = {}
    for _, row in df.iterrows():
        source = row_value(row, "source") or ""
        counts[source] = counts.get(source, 0) + 1
    return {"rows_total": len(df), "sources": [
        {"source": source, "count": count, "suggested_category": migration_category(source)}
        for source, count in sorted(counts.items())
    ]}


def run_background_migration(payload, filename, unique_number, source_categories):
    with SessionLocal() as db:
        try:
            upload = UploadFile(file=BytesIO(payload), filename=filename)
            result = upload_migration(upload, "UPDATE", unique_number, source_categories, None, db)
            MIGRATION_PROGRESS[unique_number] = {**MIGRATION_PROGRESS.get(unique_number, {}), "categories": result["categories"], "skipped_rows": result.get("skipped_rows", [])}
        except Exception as exc:
            db.rollback()
            message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            batch = db.scalar(select(UploadBatch).where(UploadBatch.unique_number == unique_number))
            if batch:
                batch.status = "FAILED"
                batch.error_message = str(message)
                db.commit()
            MIGRATION_PROGRESS[unique_number] = {**MIGRATION_PROGRESS.get(unique_number, {}), "error_message": str(message)}


@router.post("/migration-start")
def start_migration(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    upload_mode: Annotated[str, Form()] = "CREATE",
    unique_number: Annotated[str | None, Form()] = None,
    source_categories: Annotated[str, Form()] = "{}",
    admin_user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    try:
        df = read_upload(file)
        validate_migration_columns(df)
        overrides = json.loads(source_categories)
        if not isinstance(overrides, dict) or any(value not in {"INFO_EMAIL_LEADS", "LIVE_ONLINE_LEADS", "DIRECT_CALLS"} for value in overrides.values()):
            raise ValueError("Invalid source category mapping.")
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    file.file.seek(0)
    payload = file.file.read()
    mode = upload_mode.strip().upper()
    if mode == "UPDATE":
        batch = db.scalar(select(UploadBatch).where(UploadBatch.unique_number == unique_number, UploadBatch.import_type == MIGRATION_TYPE))
        if not batch:
            raise HTTPException(status_code=404, detail="Migration upload number not found.")
        if batch.status == "PROCESSING":
            raise HTTPException(status_code=409, detail="This migration is already processing.")
    elif mode == "CREATE":
        batch = UploadBatch(import_type=MIGRATION_TYPE, unique_number=new_upload_number(db), filename=file.filename or "unknown")
        db.add(batch)
    else:
        raise HTTPException(status_code=400, detail="Upload mode must be CREATE or UPDATE.")
    batch.filename = file.filename or "unknown"
    batch.status = "PROCESSING"
    batch.rows_total = len(df)
    batch.rows_imported = batch.rows_skipped = 0
    batch.error_message = None
    batch.uploaded_at = datetime.now(timezone.utc)
    db.commit()
    MIGRATION_PROGRESS[batch.unique_number] = {"processed": 0, "rows_total": len(df), "rows_imported": 0, "rows_skipped": 0, "skipped_rows": []}
    background_tasks.add_task(run_background_migration, payload, file.filename or "migration.xlsx", batch.unique_number, source_categories)
    return {"unique_number": batch.unique_number, "status": "PROCESSING", "rows_total": len(df)}


@router.get("/migration-progress/{unique_number}")
def migration_progress(unique_number: str, admin_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    batch = db.scalar(select(UploadBatch).where(UploadBatch.unique_number == unique_number, UploadBatch.import_type == MIGRATION_TYPE))
    if not batch:
        raise HTTPException(status_code=404, detail="Migration upload number not found.")
    progress = MIGRATION_PROGRESS.get(unique_number, {})
    return {"unique_number": unique_number, "status": batch.status, "rows_total": batch.rows_total,
            "processed": progress.get("processed", batch.rows_total if batch.status == "COMPLETED" else 0),
            "rows_imported": progress.get("rows_imported", batch.rows_imported),
            "rows_skipped": progress.get("rows_skipped", batch.rows_skipped),
            "error_message": batch.error_message, "categories": progress.get("categories")}


@router.get("/migration-skipped/{unique_number}")
def migration_skipped(unique_number: str, admin_user: User = Depends(require_admin)):
    progress = MIGRATION_PROGRESS.get(unique_number)
    if progress is None:
        raise HTTPException(status_code=404, detail="Migration upload not found in this session.")
    rows = progress.get("skipped_rows") or []
    output = StringIO(newline="")
    if rows:
        keys = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(output, fieldnames=keys, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)
    else:
        output.write("row_number,reason\n")
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="skipped-migration-{unique_number}.csv"'})


@router.post("/migration-upload")
def upload_migration(
    file: Annotated[UploadFile, File()],
    upload_mode: Annotated[str, Form()] = "CREATE",
    unique_number: Annotated[str | None, Form()] = None,
    source_categories: Annotated[str, Form()] = "{}",
    admin_user: User = Depends(require_admin), db: Session = Depends(get_db),
):
    try:
        df = read_upload(file)
        validate_migration_columns(df)
        overrides = json.loads(source_categories)
        if not isinstance(overrides, dict) or any(value not in {"INFO_EMAIL_LEADS", "LIVE_ONLINE_LEADS", "DIRECT_CALLS"} for value in overrides.values()):
            raise ValueError("Invalid source category mapping.")
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    mode = upload_mode.strip().upper()
    if mode not in {"CREATE", "UPDATE"}:
        raise HTTPException(status_code=400, detail="Upload mode must be CREATE or UPDATE.")
    if mode == "UPDATE":
        batch = db.scalar(select(UploadBatch).where(UploadBatch.unique_number == unique_number, UploadBatch.import_type == MIGRATION_TYPE))
        if not batch:
            raise HTTPException(status_code=404, detail="Migration upload number not found.")
    else:
        batch = UploadBatch(import_type=MIGRATION_TYPE, unique_number=new_upload_number(db), filename=file.filename or "unknown", status="PROCESSING")
        db.add(batch)
        db.flush()
    try:
        if mode == "UPDATE":
            db.execute(delete(MainCrmActivity).where(MainCrmActivity.upload_batch_id == batch.id))
            has_other_activity = select(MainCrmActivity.id).where(MainCrmActivity.lead_id == MainCrmLead.id).exists()
            db.execute(delete(MainCrmLead).where(MainCrmLead.upload_batch_id == batch.id, ~has_other_activity))
        batch.filename = file.filename or "unknown"
        batch.status = "PROCESSING"
        batch.rows_total = len(df)
        batch.rows_imported = batch.rows_skipped = 0
        batch.uploaded_at = datetime.now(timezone.utc)
        counselors = db.execute(select(User).where(User.role == "COUNSELOR", User.active.is_(True))).scalars().all()
        by_email = {normalize_email(user.email): user for user in counselors if user.email}
        by_name = {user.display_name.strip().lower(): user for user in counselors}
        learners = db.execute(select(Learner)).scalars().all()
        learners_by_email = {normalize_email(item.email_id): item for item in learners if item.email_id}
        learners_by_phone = {normalize_phone(item.contact_number): item for item in learners if item.contact_number}
        categories = {"INFO_EMAIL_LEADS": 0, "LIVE_ONLINE_LEADS": 0, "DIRECT_CALLS": 0}
        customers = {customer.id: customer for customer in db.execute(select(Customer)).scalars()}
        customer_by_email = {}
        customer_by_phone = {}
        for identity_type, normalized, customer_id in db.execute(select(
            CustomerIdentity.identity_type, CustomerIdentity.normalized_value, CustomerIdentity.customer_id
        )):
            customer = customers.get(customer_id)
            if customer:
                (customer_by_email if identity_type == "EMAIL" else customer_by_phone)[normalized] = customer
        lead_by_customer = {}
        lead_by_email = {}
        lead_by_phone = {}
        for existing in db.execute(select(MainCrmLead).order_by(MainCrmLead.id)).scalars():
            if existing.customer_id: lead_by_customer.setdefault(existing.customer_id, existing)
            if existing.normalized_email: lead_by_email.setdefault(existing.normalized_email, existing)
            if existing.normalized_phone: lead_by_phone.setdefault(existing.normalized_phone, existing)
        skipped_rows = []
        MIGRATION_PROGRESS[batch.unique_number] = {"processed": 0, "rows_total": len(df), "rows_imported": 0, "rows_skipped": 0}
        for start in range(0, len(df), MIGRATION_CHUNK_SIZE):
            chunk = df.iloc[start:start + MIGRATION_CHUNK_SIZE].to_dict(orient="records")
            prepared = []
            new_customers = []
            new_identities = []
            for row in chunk:
                email, phone = migration_contact(row)
                if not email and not phone:
                    batch.rows_skipped += 1
                    skipped_rows.append({"row_number": start + len(prepared) + 2, "reason": "Missing email and phone", **dataframe_row_to_dict(row)})
                    continue
                name = row_value(row, "name")
                normalized_email = normalize_email(email)
                normalized_phone = normalize_phone(phone)
                customer = (customer_by_email.get(normalized_email) if normalized_email else None) or (
                    customer_by_phone.get(normalized_phone) if normalized_phone else None
                )
                if not customer:
                    customer = Customer(primary_name=name, primary_email=email, primary_phone=phone)
                    new_customers.append(customer)
                else:
                    if name: customer.primary_name = name
                    if email: customer.primary_email = email
                    if phone: customer.primary_phone = phone
                if normalized_email and normalized_email not in customer_by_email:
                    customer_by_email[normalized_email] = customer
                    new_identities.append(("EMAIL", normalized_email, email, customer))
                if normalized_phone and normalized_phone not in customer_by_phone:
                    customer_by_phone[normalized_phone] = customer
                    new_identities.append(("PHONE", normalized_phone, phone, customer))
                prepared.append((row, email, phone, normalized_email, normalized_phone, customer))
            if new_customers:
                db.add_all(new_customers)
                db.flush()
                customers.update((customer.id, customer) for customer in new_customers)
            if new_identities:
                db.add_all(CustomerIdentity(customer_id=customer.id, identity_type=kind, normalized_value=value, raw_value=raw)
                           for kind, value, raw, customer in new_identities)
            new_leads = []
            activities = []
            for row, email, phone, normalized_email, normalized_phone, customer in prepared:
                source = row_value(row, "source") or ""
                category = overrides.get(source, migration_category(source))
                candidates = [item for item in (
                    lead_by_customer.get(customer.id),
                    lead_by_email.get(normalized_email) if normalized_email else None,
                    lead_by_phone.get(normalized_phone) if normalized_phone else None,
                ) if item]
                lead = min(candidates, key=lambda item: item.id if item.id is not None else float("inf")) if candidates else None
                counselor = by_email.get(normalize_email(row_value(row, "owneremail"))) or by_name.get((row_value(row, "salesowner") or "").lower())
                learner = learners_by_email.get(normalized_email) if normalized_email else None
                if not learner and normalized_phone: learner = learners_by_phone.get(normalized_phone)
                if customer_is_registered(db, customer.id):
                    mark_customer_converted(db, customer.id, learner.learner_number if learner else None)
                try:
                    age = int(float(row_value(row, "age"))) if row_value(row, "age") else None
                    if age is not None and not 0 <= age <= 120: age = None
                except ValueError:
                    age = None
                migration_created = migration_datetime(row.get("createdat"))
                values = {
                    "full_name": row_value(row, "name") or "Unknown", "email": email, "normalized_email": normalized_email,
                    "phone_number": phone, "normalized_phone": normalized_phone, "customer_id": customer.id,
                    "source_category": category, "source": source or category.replace("_", " ").title(),
                    "course": row_value(row, "coursename"), "region": row_value(row, "regions"),
                    "age": age, "status_of_lead": migration_status(row_value(row, "statusoflead")),
                    "assigned_to_user_id": counselor.id if counselor else None,
                    "assigned_at": (migration_datetime(row.get("lastassignedat")) or migration_created or datetime.now(timezone.utc)) if counselor else None,
                    "sales_owner": row_value(row, "salesowner"), "notes": row_value(row, "recentnote"),
                    "matched_learner_number": learner.learner_number if learner else None,
                    "upload_batch_id": batch.id,
                }
                if lead:
                    for key, value in values.items():
                        if key in {"customer_id", "source_category", "source", "status_of_lead", "upload_batch_id"}:
                            continue
                        if value is not None and getattr(lead, key) in (None, "", "Unknown"):
                            setattr(lead, key, value)
                else:
                    updated = migration_datetime(row.get("updatedat"))
                    if migration_created: values["created_at"] = migration_created
                    if updated: values["updated_at"] = updated
                    lead = MainCrmLead(**values)
                    new_leads.append(lead)
                    lead_by_customer.setdefault(customer.id, lead)
                    if normalized_email: lead_by_email.setdefault(normalized_email, lead)
                    if normalized_phone: lead_by_phone.setdefault(normalized_phone, lead)
                activities.append((lead, row, source, migration_created))
                batch.rows_imported += 1
                categories[category] += 1
            if new_leads:
                db.add_all(new_leads)
            db.flush()
            db.add_all(MainCrmActivity(
                lead_id=lead.id, upload_batch_id=batch.id, activity_type="MIGRATION",
                activity_date=created.date() if created else None, channel=source[:50] or None,
                course=row_value(row, "coursename"), full_user_reply=row_value(row, "message"),
                notes=row_value(row, "recentnote"), raw_data=dataframe_row_to_dict(row),
            ) for lead, row, source, created in activities)
            db.flush()
            MIGRATION_PROGRESS[batch.unique_number] = {"processed": min(start + MIGRATION_CHUNK_SIZE, len(df)),
                "rows_total": len(df), "rows_imported": batch.rows_imported, "rows_skipped": batch.rows_skipped}
        batch.status = "COMPLETED"
        sync_main_counselors(db)
        db.commit()
        return {"unique_number": batch.unique_number, "rows_total": batch.rows_total,
                "rows_imported": batch.rows_imported, "rows_skipped": batch.rows_skipped, "categories": categories, "skipped_rows": skipped_rows}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/upload")
def upload_leads(
    source_category: Annotated[str, Form()], file: Annotated[UploadFile, File()],
    upload_mode: Annotated[str, Form()] = "CREATE",
    unique_number: Annotated[str | None, Form()] = None,
    admin_user: User = Depends(require_admin), db: Session = Depends(get_db),
    progress=None,
):
    category = source_category.strip().upper()
    if category not in SOURCE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid lead source category.")
    mode = upload_mode.strip().upper()
    if mode == "UPDATE":
        if not unique_number:
            raise HTTPException(status_code=400, detail="Choose the upload number to update.")
        batch = db.scalar(select(UploadBatch).where(UploadBatch.unique_number == unique_number, UploadBatch.import_type.like("MAIN_CRM_%"), UploadBatch.import_type != MIGRATION_TYPE))
        if not batch:
            raise HTTPException(status_code=404, detail="Upload number not found.")
        db.execute(delete(MainCrmActivity).where(MainCrmActivity.upload_batch_id == batch.id))
        has_other_activity = select(MainCrmActivity.id).where(MainCrmActivity.lead_id == MainCrmLead.id).exists()
        db.execute(delete(MainCrmLead).where(MainCrmLead.upload_batch_id == batch.id, ~has_other_activity))
        batch.import_type = f"MAIN_CRM_{category}"; batch.filename = file.filename or "unknown"
        batch.status = "PROCESSING"; batch.rows_total = 0; batch.rows_imported = 0; batch.rows_skipped = 0
        batch.error_message = None; batch.uploaded_at = datetime.now(timezone.utc)
        db.flush()
    elif mode == "CREATE":
        batch = UploadBatch(import_type=f"MAIN_CRM_{category}", unique_number=new_upload_number(db), filename=file.filename or "unknown", status="PROCESSING")
        db.add(batch); db.commit(); db.refresh(batch)
    else:
        raise HTTPException(status_code=400, detail="Upload mode must be CREATE or UPDATE.")
    try:
        df = read_upload(file); batch.rows_total = len(df)
        if category == "DIRECT_CALLS" and "fullname" not in df.columns and "fullnmae" not in df.columns:
            raise ValueError("Direct calls file is missing required column: full_name")
        require_columns(df, REQUIRED_COLUMNS[category], category.replace("_", " ").title())
        if progress:
            progress(rows_total=len(df))
        imported = skipped = 0; skipped_rows = []
        counselors = db.execute(select(User).where(User.role == "COUNSELOR", User.active.is_(True))).scalars().all()
        by_email = {normalize_email(u.email): u for u in counselors if u.email}
        by_name = {u.display_name.strip().lower(): u for u in counselors}
        learners = db.execute(select(Learner)).scalars().all()
        learners_by_email = {normalize_email(item.email_id): item for item in learners if item.email_id}
        learners_by_phone = {normalize_phone(item.contact_number): item for item in learners if item.contact_number}
        for processed, row in upload_rows(df):
            email = normalize_email(row.get("email")); phone = normalize_phone(row_value(row, "phonenumber", "phone"))
            if not email and not phone:
                skipped += 1
                skipped_rows.append({"row_number": processed + 1, "reason": "Missing email and phone", **dataframe_row_to_dict(row)})
                if progress and (processed % UPLOAD_CHUNK_SIZE == 0 or processed == len(df)):
                    progress(processed=processed, rows_imported=imported, rows_skipped=skipped)
                continue
            customer = resolve_customer(db, row_value(row, "fullname", "fullnmae"), clean(row.get("email")), row_value(row, "phonenumber", "phone"))
            match_conditions = [MainCrmLead.customer_id == customer.id]
            if email: match_conditions.append(MainCrmLead.normalized_email == email)
            if phone: match_conditions.append(MainCrmLead.normalized_phone == phone)
            lead = db.scalar(select(MainCrmLead).where(or_(*match_conditions)).order_by(MainCrmLead.id))
            counselor_email = normalize_email(row_value(row, "counsiloremail", "counseloremail"))
            counselor_name = (row_value(row, "counselor", "counsilor", "counselorname", "counsilorname") or "").lower()
            counselor = by_email.get(counselor_email) or by_name.get(counselor_name)
            learner = learners_by_email.get(email) if email else None
            if not learner and phone: learner = learners_by_phone.get(phone)
            course = row_value(row, "course", "coursecampaign")
            values = {
                "full_name": row_value(row, "fullname", "fullnmae") or (lead.full_name if lead else "Unknown"), "email": clean(row.get("email")),
                "customer_id": customer.id,
                "normalized_email": email, "phone_number": row_value(row, "phonenumber", "phone"),
                "normalized_phone": phone, "whatsapp_number": row_value(row, "whatsappnumber", "whatsappno"),
                "source_category": category, "source": clean(row.get("source")) or category.replace("_", " ").title(), "course": course,
                "region": row_value(row, "regions", "region", "countryregion"), "country": clean(row.get("country")),
                "status_of_lead": (row_value(row, "statusoflead", "status") or (lead.status_of_lead if lead else "NEW")).upper().replace(" ", "_"),
                "assigned_to_user_id": counselor.id if counselor else (lead.assigned_to_user_id if lead else None), "sales_owner": clean(row.get("salesowner")),
                "notes": row_value(row, "note", "notes", "comment"),
                "matched_learner_number": learner.learner_number if learner else None, "upload_batch_id": batch.id,
            }
            try: values["age"] = int(float(row.get("age"))) if clean(row.get("age")) else None
            except (TypeError, ValueError): values["age"] = None
            if lead:
                old_assignee_id = lead.assigned_to_user_id
                for key, value in values.items():
                    if category in {"CAMPAIGN_REPLIES", "CAMPAIGN_DATA"} and key in {"source_category", "source", "upload_batch_id"}:
                        continue
                    if category in {"INFO_EMAIL_LEADS", "LIVE_ONLINE_LEADS", "DIRECT_CALLS"} or value is not None:
                        setattr(lead, key, value)
                if lead.assigned_to_user_id and lead.assigned_to_user_id != old_assignee_id:
                    lead.assigned_at = datetime.now(timezone.utc)
            else:
                lead = MainCrmLead(**values)
                if lead.assigned_to_user_id: lead.assigned_at = datetime.now(timezone.utc)
                db.add(lead)
            db.flush()
            if customer_is_registered(db, customer.id):
                mark_customer_converted(db, customer.id)
                lead.status_of_lead = "CONVERTED"
            activity_type = {"INFO_EMAIL_LEADS": "ENQUIRY", "LIVE_ONLINE_LEADS": "ENQUIRY", "DIRECT_CALLS": "DIRECT_CALL", "CAMPAIGN_REPLIES": "CAMPAIGN_REPLY", "CAMPAIGN_DATA": "CAMPAIGN_SENT"}[category]
            db.add(MainCrmActivity(
                lead_id=lead.id, upload_batch_id=batch.id, activity_type=activity_type,
                activity_date=parse_date(row.get("date")), channel=row_value(row, "campaigntype", "calltype", "source"),
                campaign_name=clean(row.get("campaignname")), campaign_description=clean(row.get("campaigndescription")),
                course=course, full_user_reply=clean(row.get("fulluserreply")),
                notes=row_value(row, "comment", "note", "notes"), raw_data=dataframe_row_to_dict(row),
            ))
            imported += 1
            if processed % UPLOAD_CHUNK_SIZE == 0 or processed == len(df):
                db.flush()
                if progress:
                    progress(processed=processed, rows_imported=imported, rows_skipped=skipped)
        batch.rows_imported = imported; batch.rows_skipped = skipped; batch.status = "COMPLETED"
        sync_main_counselors(db)
        db.commit()
        return {"unique_number": batch.unique_number, "rows_total": batch.rows_total, "rows_imported": imported, "rows_skipped": skipped, "skipped_rows": skipped_rows}
    except Exception as exc:
        db.rollback(); failed = db.get(UploadBatch, batch.id)
        if failed:
            failed.status = "FAILED"; failed.error_message = str(exc); db.commit()
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{lead_id}/status")
def update_status(lead_id: int, payload: StatusUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = accessible_lead(db, lead_id, current_user)
    db.execute(select(MainCrmLead.id).where(MainCrmLead.id == lead.id).with_for_update())
    db.refresh(lead)
    old_status = lead.status_of_lead
    next_status = payload.status.strip().upper()
    if old_status != next_status:
        note = new_contact_note(db, payload.note, main=lead)
        lead.status_of_lead = next_status
        previous_note = lead.notes
        lead.notes = note
        lead.updated_at = datetime.now(timezone.utc)
        from app.models import ConversionVerification
        if db.scalar(select(ConversionVerification.id).where(ConversionVerification.main_lead_id == lead.id)):
            from app.services.lead_workflow import mark_opportunities_dirty
            mark_opportunities_dirty(db)
        db.add(MainCrmActivity(lead_id=lead.id, activity_type="STATUS_CHANGE", activity_date=datetime.now(timezone.utc).date(),
            notes=note, raw_data={"from": old_status, "to": next_status,
                                  "actor": {"id": current_user.id, "name": current_user.display_name}}))
        record_action(db, user=current_user, main=lead, action_type="STATUS_CHANGE",
            before_status=old_status, after_status=next_status, before_note=previous_note, after_note=note)
    sync_main_counselors(db, [lead.customer_id])
    db.commit(); return {"id": lead.id, "status_of_lead": lead.status_of_lead}


@router.patch("/{lead_id}/details")
def update_details(lead_id: int, payload: LeadEditPayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = accessible_lead(db, lead_id, current_user)
    changes = {}
    for field in type(payload).model_fields:
        value = getattr(payload, field)
        if value is None:
            continue
        old = getattr(lead, field)
        if value != old:
            changes[field] = {"from": old, "to": value}
            setattr(lead, field, value)
            if field == "email": lead.normalized_email = normalize_email(value)
            if field == "phone_number": lead.normalized_phone = normalize_phone(value)
    if changes:
        if "course" in changes:
            from app.models import ConversionVerification
            if db.scalar(select(ConversionVerification.id).where(ConversionVerification.main_lead_id == lead.id)):
                from app.services.lead_workflow import mark_opportunities_dirty
                mark_opportunities_dirty(db)
        lead.updated_at = datetime.now(timezone.utc)
        db.add(MainCrmActivity(
            lead_id=lead.id, activity_type="EDIT", activity_date=datetime.now(timezone.utc).date(),
            notes="Lead information updated",
            raw_data={"changes": changes, "edited_by": {"id": current_user.id, "name": current_user.display_name}},
        ))
    sync_main_counselors(db, [lead.customer_id])
    db.commit()
    counselor = db.get(User, lead.assigned_to_user_id) if lead.assigned_to_user_id else None
    return lead_dict(lead, counselor)


@router.post("/{lead_id}/notes")
def add_note(lead_id: int, payload: LeadNotePayload, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lead = accessible_lead(db, lead_id, current_user)
    db.execute(select(MainCrmLead.id).where(MainCrmLead.id == lead.id).with_for_update())
    db.refresh(lead)
    note = required_contact_note(payload.note)
    if note == (lead.notes or "").strip():
        raise HTTPException(400, "This note is unchanged. Add what happened in the new contact.")
    previous_note = lead.notes
    lead.notes = note; lead.updated_at = datetime.now(timezone.utc)
    db.add(MainCrmActivity(lead_id=lead.id, activity_type="NOTE", activity_date=datetime.now(timezone.utc).date(),
        notes=note, raw_data={"actor": {"id": current_user.id, "name": current_user.display_name}}))
    record_action(db, user=current_user, main=lead, action_type="NOTE", before_note=previous_note, after_note=note)
    sync_main_counselors(db, [lead.customer_id])
    db.commit()
    return {"ok": True, "note": note}


@router.patch("/{lead_id}/assignment")
def update_assignment(lead_id: int, payload: AssignmentUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    lead = accessible_lead(db, lead_id, admin)
    counselor = db.get(User, payload.counselor_user_id) if payload.counselor_user_id else None
    if counselor and (counselor.role != "COUNSELOR" or not counselor.active):
        raise HTTPException(status_code=400, detail="Invalid counselor.")
    old_counselor = db.get(User, lead.assigned_to_user_id) if lead.assigned_to_user_id else None
    lead.assigned_to_user_id = counselor.id if counselor else None
    if (old_counselor.id if old_counselor else None) != lead.assigned_to_user_id:
        lead.assigned_at = datetime.now(timezone.utc) if counselor else None
    if counselor and (counselor.region or counselor.country):
        lead.region = counselor.region or counselor.country
    lead.updated_at = datetime.now(timezone.utc)
    if (old_counselor.id if old_counselor else None) != (counselor.id if counselor else None):
        db.add(MainCrmActivity(lead_id=lead.id, activity_type="ASSIGNMENT", activity_date=datetime.now(timezone.utc).date(), notes=f"Counselor changed to {counselor.display_name if counselor else 'Unassigned'}", raw_data={"from": old_counselor.display_name if old_counselor else None, "to": counselor.display_name if counselor else None}))
    sync_main_counselors(db, [lead.customer_id])
    db.commit(); return lead_dict(lead, counselor)
