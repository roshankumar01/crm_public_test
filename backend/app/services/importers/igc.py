from app.services.importers.common import clean, get_profile, normalize_result, parse_date, require_columns

IMPORT_TYPE = "IGC"
DISPLAY_NAME = "IGC Excel"
DESCRIPTION = "Imports IGC learner details, IG1/IG2 results, overall result, unit, registration and activity date."
REQUIRED_COLUMNS = {"learnernumber", "date", "overallresult"}
COLUMNS = (
    {"name": "learner_number", "required": True},
    {"name": "date", "required": True},
    {"name": "overall_result", "required": True},
    {"name": "name", "required": False},
    {"name": "nationality", "required": False},
    {"name": "contact_number", "required": False},
    {"name": "email_id", "required": False},
    {"name": "ig1_result", "required": False},
    {"name": "ig2_result", "required": False},
    {"name": "unit", "required": False},
    {"name": "bilingual_dictionary", "required": False},
    {"name": "reg", "required": False},
)


def validate_columns(df):
    require_columns(df, REQUIRED_COLUMNS, "IGC")


def parse_row(row):
    profile = get_profile(row)
    if not profile["learner_number"]:
        return []

    event_date = parse_date(row.get("date"))
    if not event_date:
        return []

    return [{
        **profile,
        "course_code": "IGC",
        "event_date": event_date,
        "event_type": "COURSE_RESULT",
        "enrollment_status": None,
        "result": normalize_result(row.get("overallresult")),
        "details": {
            "ig1_result": clean(row.get("ig1result")),
            "ig2_result": clean(row.get("ig2result")),
            "unit": clean(row.get("unit")),
            "bilingual_dictionary": clean(row.get("bilingualdictionary")),
            "registration": clean(row.get("reg")),
        },
    }]
