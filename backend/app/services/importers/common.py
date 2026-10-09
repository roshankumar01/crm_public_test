import hashlib
import json
import re
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, Learner, LearnerCourseRecord


def clean(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    value = str(value).strip()
    return value or None


def normalize_header(value):
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def clean_learner_number(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_date(value):
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def date_to_iso(value):
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def normalize_result(value):
    value = clean(value)
    if not value:
        return None
    value = value.upper()
    if value in {"PASS", "PASSED"}:
        return "PASS"
    if value in {"FAIL", "FAILED"}:
        return "FAIL"
    if value in {"TBA", "PENDING", "AWAITING"}:
        return "PENDING"
    return value


def normalize_status(value):
    value = clean(value)
    if not value:
        return None
    text = value.upper()
    if "ENROL" in text:
        return "ENROLLED"
    if "PROGRESS" in text:
        return "IN_PROGRESS"
    if "COMPLETE" in text:
        return "COMPLETED"
    if "WITHDRAW" in text:
        return "WITHDRAWN"
    return text


def first_non_empty(row, keys):
    for key in keys:
        value = clean(row.get(key))
        if value is not None:
            return value
    return None


def read_upload(upload_file):
    filename = (upload_file.filename or "").lower()
    upload_file.file.seek(0)
    if filename.endswith(".xlsx"):
        df = pd.read_excel(upload_file.file)
    elif filename.endswith(".csv"):
        df = pd.read_csv(upload_file.file)
    else:
        raise ValueError("Only .xlsx and .csv files are supported.")
    df.columns = [normalize_header(column) for column in df.columns]
    return df


UPLOAD_CHUNK_SIZE = 500


def upload_chunks(frame):
    """Convert only one slice at a time; yield the row count after each slice."""
    for start in range(0, len(frame), UPLOAD_CHUNK_SIZE):
        rows = frame.iloc[start:start + UPLOAD_CHUNK_SIZE].to_dict(orient="records")
        yield min(start + UPLOAD_CHUNK_SIZE, len(frame)), rows


def upload_rows(frame):
    for end, rows in upload_chunks(frame):
        for row_number, row in enumerate(rows, end - len(rows) + 1):
            yield row_number, row


def require_columns(df, required_columns, importer_name):
    missing = set(required_columns) - set(df.columns)
    if missing:
        raise ValueError(
            f"{importer_name} file is missing required columns: {', '.join(sorted(missing))}"
        )


def dataframe_row_to_dict(row):
    return {str(key): clean(value) for key, value in row.items()}


def get_profile(row):
    return {
        "learner_number": clean_learner_number(row.get("learnernumber")),
        "name": clean(row.get("name")),
        "nationality": clean(row.get("nationality")),
        "contact_number": clean(row.get("contactnumber")),
        "email_id": clean(row.get("emailid")),
    }


def get_course(db: Session, course_code: str):
    return db.scalar(select(Course).where(Course.code == course_code))


def upsert_learner(
    db: Session,
    learner_number: str,
    name: str | None,
    nationality: str | None,
    contact_number: str | None,
    email_id: str | None,
    event_date: date,
):
    from app.services.customer_identity import mark_customer_converted, resolve_customer

    learner = db.get(Learner, learner_number)
    # IGC and IDIP board rows share learner_number. Keep that link even when
    # a later result has a changed or missing email/phone. Other course uploads
    # do not call this importer and continue to match by email or phone.
    customer = resolve_customer(db, name, email_id, contact_number,
                                preferred_customer_id=learner.customer_id if learner else None)
    if not learner:
        learner = Learner(
            learner_number=learner_number,
            customer_id=customer.id,
            name=name or "Unknown",
            nationality=nationality,
            contact_number=contact_number,
            email_id=email_id,
            last_activity_date=event_date,
        )
        db.add(learner)
        db.flush()
    else:
        learner.customer_id = customer.id
    if learner.last_activity_date is None or event_date >= learner.last_activity_date:
        if name:
            learner.name = name
        if nationality:
            learner.nationality = nationality
        if contact_number:
            learner.contact_number = contact_number
        if email_id:
            learner.email_id = email_id
        learner.last_activity_date = event_date
    db.flush()
    mark_customer_converted(db, customer.id, learner.learner_number)
    return learner


def create_row_hash(learner_number, course_code, event_date, result, enrollment_status, event_type, details):
    payload = {
        "learner_number": learner_number,
        "course_code": course_code,
        "event_date": event_date.isoformat(),
        "event_type": event_type,
        "result": result,
        "enrollment_status": enrollment_status,
        "details": details,
    }
    text = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_record(db: Session, normalized, raw_data, upload_batch_id, course_cache=None, known_hashes=None):
    course_code = normalized["course_code"]
    course = course_cache.get(course_code) if course_cache is not None else get_course(db, course_code)
    if not course:
        raise ValueError(
            f"Course '{course_code}' does not exist in the courses table. Add/seed the course first."
        )

    upsert_learner(
        db=db,
        learner_number=normalized["learner_number"],
        name=normalized.get("name"),
        nationality=normalized.get("nationality"),
        contact_number=normalized.get("contact_number"),
        email_id=normalized.get("email_id"),
        event_date=normalized["event_date"],
    )

    row_hash = create_row_hash(
        learner_number=normalized["learner_number"],
        course_code=course_code,
        event_date=normalized["event_date"],
        result=normalized.get("result"),
        enrollment_status=normalized.get("enrollment_status"),
        event_type=normalized["event_type"],
        details=normalized.get("details", {}),
    )

    existing = row_hash in known_hashes if known_hashes is not None else db.scalar(
        select(LearnerCourseRecord.id).where(LearnerCourseRecord.row_hash == row_hash)
    )
    if existing:
        return False

    if known_hashes is not None:
        known_hashes.add(row_hash)

    db.add(LearnerCourseRecord(
        learner_number=normalized["learner_number"],
        course_id=course.id,
        upload_batch_id=upload_batch_id,
        event_date=normalized["event_date"],
        event_type=normalized["event_type"],
        enrollment_status=normalized.get("enrollment_status"),
        result=normalized.get("result"),
        details=normalized.get("details", {}),
        raw_data=raw_data,
        row_hash=row_hash,
    ))
    return True
