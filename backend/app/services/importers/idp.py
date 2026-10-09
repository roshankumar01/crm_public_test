import re

from app.services.importers.common import (
    clean,
    first_non_empty,
    get_profile,
    normalize_result,
    normalize_status,
    parse_date,
    require_columns,
)

IMPORT_TYPE = "IDP"
DISPLAY_NAME = "IDP Excel"
DESCRIPTION = "Imports ID1, ID2 and ID3 activity, enrollment status, result and activity date."
REQUIRED_COLUMNS = {"learnernumber", "date"}
COLUMNS = (
    {"name": "learner_number", "required": True},
    {"name": "date", "required": True},
    {"name": "name", "required": False},
    {"name": "nationality", "required": False},
    {"name": "contact_number", "required": False},
    {"name": "email_id", "required": False},
    {"name": "course / course_code / module / unit", "required": False, "note": "Provide one of these headers for the row-based format."},
    {"name": "result / overall_result", "required": False},
    {"name": "status / enrollment_status / enrolment_status", "required": False},
    {"name": "reg", "required": False},
    {"name": "id1_result", "required": False, "note": "Alternatively, provide at least one ID1/ID2/ID3 result column for the wide format."},
    {"name": "id2_result", "required": False},
    {"name": "id3_result", "required": False},
)


def validate_columns(df):
    require_columns(df, REQUIRED_COLUMNS, "IDP")
    columns = set(df.columns)
    has_course_column = bool({"course", "coursecode", "module", "unit"} & columns)
    has_wide_results = bool({"id1result", "id2result", "id3result"} & columns)
    if not has_course_column and not has_wide_results:
        raise ValueError(
            "IDP file must contain Course/Module/Unit with ID1/ID2/ID3, or ID1 Result/ID2 Result/ID3 Result columns."
        )


def extract_idp_codes(value):
    value = clean(value)
    if not value:
        return []
    matches = re.findall(r"\bID\s*([123])\b", value.upper())
    return list(dict.fromkeys(f"ID{number}" for number in matches))


def parse_course_column_format(row, profile, event_date):
    course_value = first_non_empty(row, ["course", "coursecode", "module", "unit"])
    course_codes = extract_idp_codes(course_value)
    if not course_codes:
        return []

    result_value = first_non_empty(row, ["overallresult", "result"])
    status_value = first_non_empty(row, ["status", "enrollmentstatus", "enrolmentstatus"])

    return [
        {
            **profile,
            "course_code": code,
            "event_date": event_date,
            "event_type": "COURSE_ACTIVITY",
            "enrollment_status": normalize_status(status_value),
            "result": normalize_result(result_value),
            "details": {
                "unit": clean(row.get("unit")),
                "registration": clean(row.get("reg")),
            },
        }
        for code in course_codes
    ]


def parse_wide_result_format(row, profile, event_date):
    status_value = first_non_empty(row, ["status", "enrollmentstatus", "enrolmentstatus"])
    records = []
    for code in ["ID1", "ID2", "ID3"]:
        value = clean(row.get(code.lower() + "result"))
        if value is None:
            continue
        records.append({
            **profile,
            "course_code": code,
            "event_date": event_date,
            "event_type": "COURSE_RESULT",
            "enrollment_status": normalize_status(status_value),
            "result": normalize_result(value),
            "details": {"registration": clean(row.get("reg"))},
        })
    return records


def parse_row(row):
    profile = get_profile(row)
    if not profile["learner_number"]:
        return []
    event_date = parse_date(row.get("date"))
    if not event_date:
        return []

    records = parse_course_column_format(row, profile, event_date)
    return records if records else parse_wide_result_format(row, profile, event_date)
