from datetime import datetime, timezone
import secrets
from io import BytesIO
import pandas as pd
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DailyLearnerRow, LearnersCrmEnrollment, LearnersCrmProfile, MainCrmLead, UploadBatch, User
from app.services.auth import get_current_user, require_admin
from app.services.customer_identity import mark_customer_converted, normalize_phone, resolve_customer
from app.services.customer_lifecycle import customer_lifecycle
from app.services.counselor_sync import main_counselors, counselor_fields, sync_main_counselors
from app.services.importers.common import clean, clean_learner_number, dataframe_row_to_dict, parse_date, read_upload, require_columns, upload_chunks
from app.services.learner_course_mapping import categories_for_course_names, mapping_for_course_names, normalize_course_name
from app.services.lead_workflow import mark_opportunities_dirty
from app.services.date_filters import period_condition

router = APIRouter(prefix="/learners-crm", tags=["Learners CRM"])
REQUIRED_COLUMNS = {"enrolmentid", "learnername", "emailid", "coursename", "enrolmentdate", "startdate", "completiondate", "completionstatus"}
DAILY_COLUMNS = {"enrolmentid", "learnername", "email", "phone", "course", "createddate", "enrolmentdate", "startdate", "counselorname"}


def normalize_email(value):
    value = clean(value)
    return value.lower() if value else None


def new_upload_number(db):
    while True:
        value = f"LCRM-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
        if not db.scalar(select(UploadBatch).where(UploadBatch.unique_number == value)):
            return value


@router.get("/overview")
def overview(current_user: User = Depends(get_current_user), db: Session = Depends(get_db), period: str = "all"):
    enrolment_filters = period_condition(LearnersCrmEnrollment.created_at, period)
    filtered_profile_ids = select(LearnersCrmEnrollment.learner_id).where(*enrolment_filters).distinct().subquery()
    total_learners = db.scalar(select(func.count()).select_from(filtered_profile_ids)) or 0
    total_enrolments = db.scalar(select(func.count()).select_from(LearnersCrmEnrollment).where(*enrolment_filters)) or 0
    normalized_status = func.upper(func.trim(LearnersCrmEnrollment.completion_status))
    status_counts = dict(db.execute(select(normalized_status, func.count()).select_from(
        LearnersCrmEnrollment).where(*enrolment_filters).group_by(normalized_status)).all())
    active = status_counts.get("NOT COMPLETED", 0)
    completed = status_counts.get("COMPLETED", 0)
    matched_enquiries = db.scalar(select(func.count()).select_from(LearnersCrmProfile).where(LearnersCrmProfile.id.in_(select(filtered_profile_ids.c.learner_id)),
        select(MainCrmLead.id).where(MainCrmLead.normalized_email == LearnersCrmProfile.normalized_email).exists()
    )) or 0
    course_rows = db.execute(select(LearnersCrmEnrollment.course_name, func.count()).where(*enrolment_filters).group_by(
        LearnersCrmEnrollment.course_name
    )).all()
    mapped_categories = categories_for_course_names(db, [name for name, _ in course_rows])
    category_counts = Counter()
    for name, count in course_rows:
        category_counts[mapped_categories.get(normalize_course_name(name), "Unmapped")] += count
    return {"total_learners": total_learners, "total_enrolments": total_enrolments, "completed": completed, "active": active, "matched_enquiries": matched_enquiries, "course_categories": [{"name": name, "enrolments": count} for name, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))]}


@router.get("/export")
def export_learners(period: str = "all", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    filters = period_condition(LearnersCrmEnrollment.created_at, period)
    rows = db.execute(select(LearnersCrmProfile, LearnersCrmEnrollment).join(LearnersCrmEnrollment, LearnersCrmEnrollment.learner_id == LearnersCrmProfile.id).where(*filters).order_by(LearnersCrmEnrollment.created_at.desc())).all()
    owners = main_counselors(db, [profile.customer_id for profile, _ in rows])
    values = [{"Counselor": counselor_fields(owners, profile.customer_id)["assigned_to_name"] or "Unassigned",
               "Counselor Email": counselor_fields(owners, profile.customer_id)["assigned_to_email"], "Learner": profile.learner_name, "Email": profile.email_id, "Phone": profile.phone_number,
               "Enrolment ID": enrollment.enrolment_id, "Course": enrollment.course_name,
               "Enrolment Date": enrollment.enrolment_date, "Completion Date": enrollment.completion_date,
               "Completion Status": enrollment.completion_status, "Created At": enrollment.created_at,
               "Updated At": enrollment.updated_at} for profile, enrollment in rows]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer: pd.DataFrame(values).to_excel(writer, sheet_name="Learners CRM", index=False)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="learners-crm-export.xlsx"'})


@router.get("/learners")
def search_learners(
    search: str = Query("", max_length=320),
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
    page: int = 1,
):
    page = max(1, page)
    query = search.strip()
    if query:
        enrolment_match = select(LearnersCrmEnrollment.enrolment_id).where(
            LearnersCrmEnrollment.learner_id == LearnersCrmProfile.id,
            func.lower(LearnersCrmEnrollment.enrolment_id).contains(query.lower()),
        ).exists()
        conditions = [LearnersCrmProfile.normalized_email.contains(query.lower()), enrolment_match]
        phone_query = normalize_phone(query)
        if phone_query and len(phone_query) >= 3 and not any(character.isalpha() for character in query):
            conditions.append(LearnersCrmProfile.normalized_phone.contains(phone_query))
        statement = select(LearnersCrmProfile).where(or_(*conditions)).order_by(LearnersCrmProfile.learner_name, LearnersCrmProfile.id).offset((page - 1) * 25).limit(25)
    else:
        latest_enrolment = select(
            LearnersCrmEnrollment.learner_id,
            func.max(LearnersCrmEnrollment.updated_at).label("last_updated"),
        ).group_by(LearnersCrmEnrollment.learner_id).subquery()
        statement = select(LearnersCrmProfile).outerjoin(
            latest_enrolment, latest_enrolment.c.learner_id == LearnersCrmProfile.id
        ).order_by(latest_enrolment.c.last_updated.desc(), LearnersCrmProfile.id.desc()).offset((page - 1) * 25).limit(25)
    profiles = db.execute(statement).scalars().all()
    return learner_profiles_payload(db, profiles, preview_limit=5)


def learner_profiles_payload(db, profiles, preview_limit=None):
    if not profiles:
        return []
    owners = main_counselors(db, [profile.customer_id for profile in profiles])
    profile_ids = [profile.id for profile in profiles]
    statement = select(LearnersCrmEnrollment).where(LearnersCrmEnrollment.learner_id.in_(profile_ids))
    if preview_limit is not None:
        ranked = select(
            LearnersCrmEnrollment.enrolment_id.label("id"),
            func.row_number().over(partition_by=LearnersCrmEnrollment.learner_id,
                order_by=(LearnersCrmEnrollment.enrolment_date.desc(), LearnersCrmEnrollment.enrolment_id)).label("rank"),
        ).where(LearnersCrmEnrollment.learner_id.in_(profile_ids)).subquery()
        statement = statement.join(ranked, LearnersCrmEnrollment.enrolment_id == ranked.c.id).where(ranked.c.rank <= preview_limit)
    enrolments = db.scalars(statement.order_by(LearnersCrmEnrollment.enrolment_date.desc(), LearnersCrmEnrollment.enrolment_id)).all()
    batch_ids = {item.upload_batch_id for item in enrolments if item.upload_batch_id}
    batch_types = dict(db.execute(select(UploadBatch.id, UploadBatch.import_type).where(UploadBatch.id.in_(batch_ids))).all()) if batch_ids else {}
    customer_ids = {profile.customer_id for profile in profiles if profile.customer_id}
    matched_customers = set(db.scalars(select(MainCrmLead.customer_id).where(MainCrmLead.customer_id.in_(customer_ids)).distinct())) if customer_ids else set()
    profile_customers = {profile.id: profile.customer_id for profile in profiles}
    mapped_categories = mapping_for_course_names(db, [enrolment.course_name for enrolment in enrolments])
    by_learner = {profile.id: [] for profile in profiles}
    for enrolment in enrolments:
        by_learner[enrolment.learner_id].append({
            "enrolment_id": enrolment.enrolment_id,
            "course_name": enrolment.course_name,
            "course_category": (mapped_categories.get(normalize_course_name(enrolment.course_name)) or {}).get("main_category"),
            "course_sub_category": (mapped_categories.get(normalize_course_name(enrolment.course_name)) or {}).get("sub_category"),
            "enrolment_date": enrolment.enrolment_date,
            "start_date": enrolment.start_date,
            "completion_date": enrolment.completion_date,
            "completion_status": enrolment.completion_status,
            "verification_status": ("VERIFIED" if profile_customers.get(enrolment.learner_id) in matched_customers else "UNMATCHED")
                if batch_types.get(enrolment.upload_batch_id) == "LEARNERS_CRM" else "VERIFIED",
            "created_at": enrolment.created_at,
            "updated_at": enrolment.updated_at,
        })
    return [{
        **counselor_fields(owners, profile.customer_id),
        "id": profile.id, "learner_name": profile.learner_name,
        "email_id": profile.email_id, "phone_number": profile.phone_number,
        "created_at": profile.created_at, "updated_at": profile.updated_at,
        "enrolments": by_learner[profile.id],
    } for profile in profiles]


@router.get("/learners/{learner_id}")
def get_learner_profile(learner_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(LearnersCrmProfile, learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Learner not found.")
    return {**learner_profiles_payload(db, [profile])[0],
            "lifecycle": customer_lifecycle(db, profile.customer_id, current_user)}


@router.get("/uploads")
def uploads(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(UploadBatch).where(UploadBatch.import_type.in_(("LEARNERS_CRM", "LEARNERS_DAILY"))).order_by(UploadBatch.uploaded_at.desc(), UploadBatch.id.desc())).scalars().all()
    return [{"id": row.id, "unique_number": row.unique_number, "filename": row.filename, "import_type": row.import_type, "status": row.status, "rows_total": row.rows_total, "rows_imported": row.rows_imported, "rows_skipped": row.rows_skipped, "uploaded_at": row.uploaded_at} for row in rows]


@router.post("/upload")
def upload(
    file: Annotated[UploadFile, File()], upload_mode: Annotated[str, Form()] = "CREATE",
    unique_number: Annotated[str | None, Form()] = None,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
    progress=None,
):
    mode = upload_mode.strip().upper()
    if mode == "UPDATE":
        if not unique_number:
            raise HTTPException(status_code=400, detail="Choose the learner upload to update.")
        batch = db.scalar(select(UploadBatch).where(UploadBatch.unique_number == unique_number, UploadBatch.import_type == "LEARNERS_CRM"))
        if not batch:
            raise HTTPException(status_code=404, detail="Learner upload number not found.")
        db.execute(delete(LearnersCrmEnrollment).where(LearnersCrmEnrollment.upload_batch_id == batch.id))
        batch.filename = file.filename or "unknown"; batch.status = "PROCESSING"
        batch.rows_total = 0; batch.rows_imported = 0; batch.rows_skipped = 0
        batch.error_message = None; batch.uploaded_at = datetime.now(timezone.utc); db.flush()
    elif mode == "CREATE":
        batch = UploadBatch(import_type="LEARNERS_CRM", unique_number=new_upload_number(db), filename=file.filename or "unknown", status="PROCESSING")
        db.add(batch); db.commit(); db.refresh(batch)
    else:
        raise HTTPException(status_code=400, detail="Upload mode must be CREATE or UPDATE.")
    try:
        frame = read_upload(file); require_columns(frame, REQUIRED_COLUMNS, "Learners CRM")
        batch.rows_total = len(frame); imported = skipped = mapped = 0; skipped_rows = []
        if progress:
            progress(rows_total=len(frame))
        mapped_categories = categories_for_course_names(db, [clean(value) for value in frame["coursename"]])
        unmapped_courses = set()
        converted_ids = set()
        for processed, rows in upload_chunks(frame):
            emails = {normalize_email(row.get("emailid")) for row in rows}
            enrolment_ids = {clean(row.get("enrolmentid")) for row in rows}
            profiles = {item.normalized_email: item for item in db.scalars(select(LearnersCrmProfile).where(
                LearnersCrmProfile.normalized_email.in_(emails - {None})
            ))}
            enrolments = {item.enrolment_id: item for item in db.scalars(select(LearnersCrmEnrollment).where(
                LearnersCrmEnrollment.enrolment_id.in_(enrolment_ids - {None})
            ))}
            resolved_emails = set()
            for row in rows:
                enrolment_id = clean(row.get("enrolmentid")); email = normalize_email(row.get("emailid"))
                if not enrolment_id or not email:
                    skipped += 1; skipped_rows.append({"row_number": processed - len(rows) + rows.index(row) + 2, "reason": "Missing enrolment ID or email", **dataframe_row_to_dict(row)}); continue
                phone = clean_learner_number(row.get("phonenumber")) if "phonenumber" in frame.columns else None
                profile = profiles.get(email)
                if not profile:
                    customer = resolve_customer(db, clean(row.get("learnername")), clean(row.get("emailid")), phone)
                    profile = LearnersCrmProfile(customer_id=customer.id, learner_name=clean(row.get("learnername")) or "Unknown", email_id=clean(row.get("emailid")), normalized_email=email, phone_number=phone, normalized_phone=normalize_phone(phone))
                    db.add(profile); db.flush()
                    profiles[email] = profile
                    resolved_emails.add(email)
                else:
                    profile.learner_name = clean(row.get("learnername")) or profile.learner_name
                    profile.email_id = clean(row.get("emailid")) or profile.email_id
                    phone_changed = bool(phone and phone != profile.phone_number)
                    if phone:
                        profile.phone_number = phone
                        profile.normalized_phone = normalize_phone(phone)
                    if email not in resolved_emails or phone_changed or not profile.customer_id:
                        customer = resolve_customer(db, profile.learner_name, profile.email_id, profile.phone_number)
                        profile.customer_id = customer.id
                        resolved_emails.add(email)
                if profile.customer_id not in converted_ids:
                    mark_customer_converted(db, profile.customer_id)
                    converted_ids.add(profile.customer_id)
                course_name = clean(row.get("coursename")) or "Unknown"
                if normalize_course_name(course_name) in mapped_categories:
                    mapped += 1
                else:
                    unmapped_courses.add(course_name)
                enrollment = enrolments.get(enrolment_id)
                values = {"learner_id": profile.id, "course_name": course_name, "enrolment_date": parse_date(row.get("enrolmentdate")), "start_date": parse_date(row.get("startdate")), "completion_date": parse_date(row.get("completiondate")), "completion_status": clean(row.get("completionstatus")), "upload_batch_id": batch.id}
                if enrollment:
                    for key, value in values.items(): setattr(enrollment, key, value)
                else:
                    enrollment = LearnersCrmEnrollment(enrolment_id=enrolment_id, **values)
                    db.add(enrollment)
                    enrolments[enrolment_id] = enrollment
                imported += 1
            db.flush()
            if progress:
                progress(processed=processed, rows_imported=imported, rows_skipped=skipped,
                         rows_mapped=mapped)
        orphaned = ~select(LearnersCrmEnrollment.enrolment_id).where(LearnersCrmEnrollment.learner_id == LearnersCrmProfile.id).exists()
        db.execute(delete(LearnersCrmProfile).where(orphaned))
        batch.rows_imported = imported; batch.rows_skipped = skipped; batch.status = "COMPLETED"
        if imported or mode == "UPDATE":
            mark_opportunities_dirty(db)
        db.commit()
        return {"unique_number": batch.unique_number, "rows_total": batch.rows_total, "rows_imported": imported, "rows_skipped": skipped, "rows_mapped": mapped, "unmapped_courses": sorted(unmapped_courses), "skipped_rows": skipped_rows}
    except Exception as exc:
        db.rollback(); failed = db.get(UploadBatch, batch.id)
        if failed:
            failed.status = "FAILED"; failed.error_message = str(exc); db.commit()
        raise HTTPException(status_code=400, detail=str(exc))


def _daily_counselor(db, name):
    name = (name or "").strip().casefold()
    if not name:
        return None
    users = db.scalars(select(User).where(User.active.is_(True), User.role == "COUNSELOR",
        func.lower(func.trim(User.display_name)) == name)).all()
    return users[0] if len(users) == 1 else None


def _daily_main_match(db, email, phone):
    conditions = []
    if email:
        conditions.append(MainCrmLead.normalized_email == email)
    if phone:
        conditions.append(MainCrmLead.normalized_phone == phone)
    if not conditions:
        return None
    return db.scalar(select(MainCrmLead).where(or_(*conditions)).order_by(
        MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()).limit(1))


def _activate_daily_row(db, row, admin, main_lead):
    if not row.counselor_user_id:
        raise HTTPException(400, "Choose an active counselor before verifying this learner.")
    existing = db.get(LearnersCrmEnrollment, row.enrolment_id)
    if existing:
        raise HTTPException(409, f"Enrolment ID {row.enrolment_id} already exists.")
    customer = resolve_customer(db, row.learner_name, row.email, row.phone,
        preferred_customer_id=main_lead.customer_id if main_lead else None)
    email_key = row.normalized_email or f"daily-missing-{row.id}@invalid.local"
    profile = db.scalar(select(LearnersCrmProfile).where(LearnersCrmProfile.normalized_email == email_key))
    if not profile:
        profile = LearnersCrmProfile(customer_id=customer.id, learner_name=row.learner_name,
            email_id=row.email or email_key, normalized_email=email_key, phone_number=row.phone,
            normalized_phone=row.normalized_phone)
        db.add(profile); db.flush()
    else:
        profile.customer_id = customer.id
        profile.learner_name = row.learner_name
        if row.phone:
            profile.phone_number = row.phone
            profile.normalized_phone = row.normalized_phone
    db.add(LearnersCrmEnrollment(enrolment_id=row.enrolment_id, learner_id=profile.id,
        course_name=row.course_name, enrolment_date=row.enrolment_date, start_date=row.start_date,
        completion_status="Not Completed", upload_batch_id=row.upload_batch_id,
        counselor_user_id=row.counselor_user_id,
        created_at=datetime.combine(row.created_date, datetime.min.time(), tzinfo=timezone.utc)
            if row.created_date else datetime.now(timezone.utc)))
    row.status = "VERIFIED"
    row.matched_main_lead_id = main_lead.id if main_lead else None
    row.verified_by_user_id = admin.id if admin else None
    row.verified_at = datetime.now(timezone.utc)
    mark_customer_converted(db, customer.id)
    mark_opportunities_dirty(db)
    db.flush()
    return customer.id


@router.post("/daily-upload")
def upload_daily(file: Annotated[UploadFile, File()], admin: User = Depends(require_admin),
                 db: Session = Depends(get_db), progress=None):
    batch = UploadBatch(import_type="LEARNERS_DAILY", unique_number=new_upload_number(db),
        filename=file.filename or "unknown", status="PROCESSING")
    db.add(batch); db.commit(); db.refresh(batch)
    try:
        frame = read_upload(file)
        require_columns(frame, DAILY_COLUMNS, "Daily learners")
        batch.rows_total = len(frame)
        db.commit()
        if progress: progress(rows_total=len(frame))
        imported = skipped = verified = 0
        skipped_rows = []
        for processed, rows in upload_chunks(frame):
            affected_customers = set()
            email_keys = {normalize_email(row.get("email")) for row in rows} - {None}
            phone_keys = {normalize_phone(clean_learner_number(row.get("phone"))) for row in rows} - {None}
            matched = db.scalars(select(MainCrmLead).where(or_(
                MainCrmLead.normalized_email.in_(email_keys),
                MainCrmLead.normalized_phone.in_(phone_keys)
            )).order_by(MainCrmLead.updated_at.desc(), MainCrmLead.id.desc())).all()
            by_email, by_phone = {}, {}
            for lead in matched:
                if lead.normalized_email: by_email.setdefault(lead.normalized_email, lead)
                if lead.normalized_phone: by_phone.setdefault(lead.normalized_phone, lead)
            names = {clean(row.get("counselorname")) for row in rows} - {None}
            counselors = {name: _daily_counselor(db, name) for name in names}
            ids = {clean_learner_number(row.get("enrolmentid")) for row in rows} - {None}
            existing = set(db.scalars(select(LearnersCrmEnrollment.enrolment_id).where(
                LearnersCrmEnrollment.enrolment_id.in_(ids))))
            existing.update(db.scalars(select(DailyLearnerRow.enrolment_id).where(
                DailyLearnerRow.enrolment_id.in_(ids))))
            for offset, data in enumerate(rows):
                row_number = processed - len(rows) + offset + 2
                enrolment_id = clean_learner_number(data.get("enrolmentid"))
                name = clean(data.get("learnername"))
                email = clean(data.get("email"))
                phone = clean_learner_number(data.get("phone"))
                course = clean(data.get("course"))
                owner_name = clean(data.get("counselorname"))
                enrolment_date = parse_date(data.get("enrolmentdate"))
                reason = None
                if not enrolment_id or not name or not course or not enrolment_date or not (email or phone):
                    reason = "Missing enrolment ID, learner name, course, enrolment date, or both contacts"
                elif enrolment_id in existing:
                    reason = "Duplicate enrolment ID"
                if reason:
                    skipped += 1
                    skipped_rows.append({"row_number": row_number, "reason": reason,
                        **dataframe_row_to_dict(data)})
                    continue
                existing.add(enrolment_id)
                email_key = normalize_email(email)
                phone_key = normalize_phone(phone)
                lead = by_email.get(email_key) or by_phone.get(phone_key)
                counselor = counselors.get(owner_name)
                row = DailyLearnerRow(upload_batch_id=batch.id, row_number=row_number,
                    enrolment_id=enrolment_id, learner_name=name, email=email,
                    normalized_email=email_key, phone=phone, normalized_phone=phone_key,
                    course_name=course, created_date=parse_date(data.get("createddate")),
                    enrolment_date=enrolment_date, start_date=parse_date(data.get("startdate")),
                    counselor_name=owner_name, counselor_user_id=counselor.id if counselor else None,
                    matched_main_lead_id=lead.id if lead else None)
                db.add(row); db.flush()
                imported += 1
                if lead and counselor:
                    affected_customers.add(_activate_daily_row(db, row, None, lead))
                    verified += 1
            if affected_customers:
                sync_main_counselors(db, affected_customers)
            batch.rows_imported = imported
            batch.rows_skipped = skipped
            db.commit()
            if progress: progress(processed=processed, rows_imported=imported, rows_skipped=skipped)
        batch.status = "COMPLETED"
        db.commit()
        return {"unique_number": batch.unique_number, "rows_total": len(frame),
            "rows_imported": imported, "rows_skipped": skipped, "rows_verified": verified,
            "rows_pending": imported - verified, "skipped_rows": skipped_rows}
    except Exception as exc:
        db.rollback()
        failed = db.get(UploadBatch, batch.id)
        if failed:
            failed.status = "FAILED"; failed.error_message = str(exc); db.commit()
        raise HTTPException(status_code=400, detail=str(exc))


class VerifyDailyLearner(BaseModel):
    email: str | None = None
    phone: str | None = None
    counselor_user_id: int | None = None


@router.post("/daily-rows/{row_id}/verify")
def verify_daily(row_id: int, payload: VerifyDailyLearner, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    row = db.get(DailyLearnerRow, row_id)
    if not row: raise HTTPException(404, "Daily learner row not found.")
    if row.status == "VERIFIED": raise HTTPException(409, "This learner is already verified.")
    row.email = clean(payload.email)
    row.normalized_email = normalize_email(row.email)
    row.phone = clean(payload.phone)
    row.normalized_phone = normalize_phone(row.phone)
    if not (row.email or row.phone): raise HTTPException(400, "Enter an email or phone number.")
    counselor = db.get(User, payload.counselor_user_id) if payload.counselor_user_id else None
    if not counselor or not counselor.active or counselor.role != "COUNSELOR":
        raise HTTPException(400, "Choose an active counselor.")
    row.counselor_user_id = counselor.id
    row.counselor_name = counselor.display_name
    lead = _daily_main_match(db, row.normalized_email, row.normalized_phone)
    customer_id = _activate_daily_row(db, row, admin, lead)
    sync_main_counselors(db, [customer_id])
    db.commit()
    return {"id": row.id, "status": row.status, "matched_main": bool(lead)}


@router.get("/verification")
def learner_verification(kind: str = "daily", page: int = 1,
                         admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    page = max(1, page)
    if kind in {"daily", "daily_verified"}:
        query = select(DailyLearnerRow).where(DailyLearnerRow.status == ("PENDING" if kind == "daily" else "VERIFIED"))
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(DailyLearnerRow.id.desc()).offset((page - 1) * 25).limit(25)).all()
        return {"total": total, "page": page, "items": [{"id": row.id,
            "enrolment_id": row.enrolment_id, "learner_name": row.learner_name,
            "email": row.email, "phone": row.phone, "course_name": row.course_name,
            "counselor_name": row.counselor_name, "counselor_user_id": row.counselor_user_id,
            "matched_main": bool(row.matched_main_lead_id), "status": row.status}
            for row in rows]}
    if kind in {"migrated", "migrated_matched"}:
        matched_main = select(MainCrmLead.id).where(
            MainCrmLead.customer_id == LearnersCrmProfile.customer_id).exists()
        query = select(LearnersCrmEnrollment, LearnersCrmProfile).join(
            LearnersCrmProfile, LearnersCrmEnrollment.learner_id == LearnersCrmProfile.id
        ).join(UploadBatch, LearnersCrmEnrollment.upload_batch_id == UploadBatch.id).where(
            UploadBatch.import_type == "LEARNERS_CRM", matched_main if kind == "migrated_matched" else ~matched_main)
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.execute(query.order_by(LearnersCrmEnrollment.created_at.desc(),
            LearnersCrmEnrollment.enrolment_id.desc()).offset((page - 1) * 25).limit(25)).all()
        return {"total": total, "page": page, "items": [{"id": enrolment.enrolment_id,
            "enrolment_id": enrolment.enrolment_id, "learner_name": profile.learner_name,
            "email": profile.email_id, "phone": profile.phone_number,
            "course_name": enrolment.course_name, "status": "VERIFIED" if kind == "migrated_matched" else "UNMATCHED"}
            for enrolment, profile in rows]}
    raise HTTPException(400, "Invalid verification list.")
