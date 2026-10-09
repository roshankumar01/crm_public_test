from datetime import date, timedelta

from app.services.learner_course_mapping import normalize_course_name

IDP_COURSE_CODES = ("ID1", "ID2", "ID3")
COOLING_DAYS_KEY = "recommendation_cooling_days"
DEFAULT_COOLING_DAYS = 60

STAGE_ONE = {
    "advanced diploma", "pg - diploma", "diploma", "national general certificate",
    "iosh ms", "nebosh hsw",
}
TARGETS = {
    "IGC": ("IGC", "IGC", 2),
    "PSM": ("Nebosh PSM", "Nebosh PSM", 2),
    "INCIDENT": ("Nebosh Incident Investigation", "Nebosh Incident Investigation", 2),
    "IDP_ENTRY": ("Nebosh Idip", "Nebosh Idip", 3),
    "ID1": ("IDIP -1", "IDIP -1", 3),
    "ID2": ("IDIP -2", "IDIP -2", 3),
    "ID3": ("IDIP -3", "IDIP -3", 3),
}


def is_completed(record):
    if record.result:
        return record.result.strip().upper() == "PASS"
    return bool(record.enrollment_status and record.enrollment_status.strip().upper() == "COMPLETED")


def get_cooling_days(db):
    from app.models import AppSetting
    setting = db.get(AppSetting, COOLING_DAYS_KEY)
    try:
        return max(0, min(3650, int(setting.value))) if setting else DEFAULT_COOLING_DAYS
    except (TypeError, ValueError):
        return DEFAULT_COOLING_DAYS


def build_customer_opportunities(enrolments, history_rows, mapping_by_name, cooling_days=DEFAULT_COOLING_DAYS, today=None):
    """Recommend subcategories using all of a customer's course enrolments and board results."""
    today = today or date.today()
    enrolled = set()
    passed = set()
    pass_dates = {}
    mature_stage_one = []

    for enrolment in enrolments:
        mapping = mapping_by_name.get(normalize_course_name(enrolment.course_name)) or {}
        sub = normalize_course_name(mapping.get("sub_category") or "")
        if not sub:
            continue
        enrolled.add(sub)
        date_enrolled = enrolment.enrolment_date or enrolment.created_at.date()
        if sub in STAGE_ONE and date_enrolled + timedelta(days=cooling_days) <= today:
            mature_stage_one.append((sub, date_enrolled + timedelta(days=cooling_days)))
        if sub in {"igc", "idip -1", "idip -2", "idip -3"} and (enrolment.completion_status or "").strip().casefold() == "completed":
            passed.add(sub)
            passed_at = enrolment.completion_date or enrolment.updated_at.date()
            pass_dates[sub] = max(pass_dates.get(sub, passed_at), passed_at)

    for record, course in history_rows:
        code = course.code.strip().upper()
        sub = {"IGC": "igc", "ID1": "idip -1", "ID2": "idip -2", "ID3": "idip -3"}.get(code)
        if not sub:
            continue
        enrolled.add(sub)
        if (record.result or "").strip().upper() == "PASS":
            passed.add(sub)
            pass_dates[sub] = max(pass_dates.get(sub, record.event_date), record.event_date)

    opportunities = {}

    def offer(key, trigger_date, reason, stage, trigger_courses):
        subcategory, name, _ = TARGETS[key]
        if key == "IDP_ENTRY" and any(unit in enrolled for unit in ("idip -1", "idip -2", "idip -3")):
            return
        if normalize_course_name(subcategory) in enrolled:
            return
        opportunities[key] = {
            "key": key, "opportunity_type": "COURSE" if key != "IDP_ENTRY" else "PROGRAM_ENTRY",
            "target_code": "IDP" if key == "IDP_ENTRY" else key,
            "target_name": name, "target_subcategory": subcategory,
            "trigger_courses": trigger_courses, "trigger_date": trigger_date,
            "reason": reason, "priority": stage * 10, "stage": stage,
        }

    if mature_stage_one:
        trigger_sub, eligible_at = min(mature_stage_one, key=lambda item: item[1])
        for key in ("IGC", "PSM", "INCIDENT"):
            offer(key, eligible_at,
                  f"Enrolled in {trigger_sub.title()} and completed the {cooling_days}-day cooling period.",
                  2, [trigger_sub])

    if "igc" in passed:
        passed_at = pass_dates["igc"]
        for key in ("PSM", "INCIDENT", "IDP_ENTRY"):
            offer(key, passed_at, "Passed IGC and is eligible for Stage 3.", 3, ["IGC"])

    passed_idip = sorted(sub for sub in passed if sub in {"idip -1", "idip -2", "idip -3"})
    if passed_idip:
        passed_at = max(pass_dates[sub] for sub in passed_idip)
        for key in IDP_COURSE_CODES:
            offer(key, passed_at,
                  f"Passed an IDIP unit; {TARGETS[key][1]} has not been enrolled.",
                  3, passed_idip)

    return sorted(opportunities.values(), key=lambda item: (item["priority"], item["key"]))


def build_learner_opportunities(history_rows):
    """Compatibility helper for external-board history without e-learning enrolments."""
    return build_customer_opportunities([], history_rows, {})
