"""Company reporting over Main CRM, active Upsell opportunities, and exam uploads."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, extract, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Course, Lead, LearnerCourseRecord, MainCrmLead, User
from app.services.auth import require_admin
from app.services.date_filters import period_bounds
from app.services.lead_workflow import sync_opportunity_leads
from app.services.upsell_management import work_items

router = APIRouter(prefix="/company-dashboard", tags=["Company dashboard"])


def _label(value, fallback="Unknown"):
    return (value or "").strip() or fallback


def _percent(numerator, denominator):
    return round(numerator * 100 / denominator, 1) if denominator else 0


def _bounds(period, start_date, end_date):
    if start_date is None and end_date is None:
        return period_bounds(period)
    if start_date is None or end_date is None or start_date > end_date:
        raise HTTPException(status_code=400, detail="Select a valid start and end date.")
    return datetime.combine(start_date, time.min), datetime.combine(end_date + timedelta(days=1), time.min)


def _conditions(column, bounds):
    return [column >= bounds[0], column < bounds[1]] if bounds else []


def _trend(db, bounds):
    """Leads and conversions are grouped by lead creation cohort."""
    filters = _conditions(MainCrmLead.created_at, bounds)
    days = (bounds[1].date() - bounds[0].date()).days if bounds else None
    if days == 1:
        bucket = extract("hour", MainCrmLead.created_at)
        rows = db.execute(select(bucket, MainCrmLead.status_of_lead, func.count(MainCrmLead.id))
                          .where(*filters).group_by(bucket, MainCrmLead.status_of_lead)).all()
        counts = defaultdict(lambda: [0, 0])
        for hour, status, count in rows:
            counts[int(hour)][0] += count
            counts[int(hour)][1] += count if status == "CONVERTED" else 0
        return [{"label": f"{hour:02d}:00", "leads": counts[hour][0], "converted": counts[hour][1]}
                for hour in range(24)]

    if bounds is None or days > 60:
        year = extract("year", MainCrmLead.created_at)
        month = extract("month", MainCrmLead.created_at)
        rows = db.execute(select(year, month, MainCrmLead.status_of_lead, func.count(MainCrmLead.id))
                          .where(*filters).group_by(year, month, MainCrmLead.status_of_lead)).all()
        counts = defaultdict(lambda: [0, 0])
        for y, m, status, count in rows:
            key = (int(y), int(m))
            counts[key][0] += count
            counts[key][1] += count if status == "CONVERTED" else 0
        return [{"label": f"{y}-{m:02d}", "leads": counts[(y, m)][0], "converted": counts[(y, m)][1]}
                for y, m in sorted(counts)]

    day = func.date(MainCrmLead.created_at)
    rows = db.execute(select(day, MainCrmLead.status_of_lead, func.count(MainCrmLead.id))
                      .where(*filters).group_by(day, MainCrmLead.status_of_lead)).all()
    counts = defaultdict(lambda: [0, 0])
    for raw_day, status, count in rows:
        key = str(raw_day)[:10]
        counts[key][0] += count
        counts[key][1] += count if status == "CONVERTED" else 0
    start, end = bounds[0].date(), bounds[1].date()
    return [{"label": (start + timedelta(days=offset)).isoformat(),
             "leads": counts[(start + timedelta(days=offset)).isoformat()][0],
             "converted": counts[(start + timedelta(days=offset)).isoformat()][1]}
            for offset in range((end - start).days)]


@router.get("/overview")
def overview(period: str = Query("all"), admin: User = Depends(require_admin), db: Session = Depends(get_db),
             start_date: date | None = None, end_date: date | None = None):
    bounds = _bounds(period, start_date, end_date)
    filters = _conditions(MainCrmLead.created_at, bounds)
    status_rows = db.execute(select(MainCrmLead.status_of_lead, func.count(MainCrmLead.id))
                             .where(*filters).group_by(MainCrmLead.status_of_lead)).all()
    statuses = {status: count for status, count in status_rows}
    total_leads = sum(statuses.values())
    source_rows = db.execute(select(MainCrmLead.source, func.count(MainCrmLead.id))
                             .where(*filters).group_by(MainCrmLead.source)
                             .order_by(func.count(MainCrmLead.id).desc(), MainCrmLead.source.asc()).limit(7)).all()
    course_rows = db.execute(select(MainCrmLead.course, func.count(MainCrmLead.id))
                             .where(*filters, MainCrmLead.status_of_lead == "CONVERTED")
                             .group_by(MainCrmLead.course)
                             .order_by(func.count(MainCrmLead.id).desc(), MainCrmLead.course.asc()).limit(7)).all()
    sync_opportunity_leads(db)
    W = work_items().c
    upsell_filters = _conditions(W.created_at, bounds)
    upsell_total, upsell_converted = db.execute(select(
        func.count(W.id), func.sum(case((W.status == "CONVERTED", 1), else_=0))
    ).where(*upsell_filters)).one()
    upsell_converted = upsell_converted or 0
    return {
        "period": period,
        "cards": {"new_leads": statuses.get("NEW", 0), "converted_leads": statuses.get("CONVERTED", 0),
                  "total_leads": total_leads, "upsell_converted": upsell_converted,
                  "upsell_total": upsell_total, "upsell_conversion_rate": _percent(upsell_converted, upsell_total)},
        "trend": _trend(db, bounds),
        "top_sources": [{"name": _label(name), "count": count} for name, count in source_rows],
        "top_converted_courses": [{"name": _label(name, "Course not specified"), "count": count} for name, count in course_rows],
    }


@router.get("/sales")
def sales(period: str = Query("all"), admin: User = Depends(require_admin), db: Session = Depends(get_db),
          start_date: date | None = None, end_date: date | None = None):
    filters = _conditions(MainCrmLead.created_at, _bounds(period, start_date, end_date))
    rows = db.execute(select(
        MainCrmLead.assigned_to_user_id, User.display_name, MainCrmLead.status_of_lead,
        func.count(MainCrmLead.id)
    ).outerjoin(User, User.id == MainCrmLead.assigned_to_user_id)
      .where(*filters).group_by(MainCrmLead.assigned_to_user_id, User.display_name, MainCrmLead.status_of_lead)).all()
    counselors = {}
    for owner_id, name, status, count in rows:
        item = counselors.setdefault(owner_id, {"id": owner_id, "name": name or "Unassigned", "leads": 0, "converted": 0})
        item["leads"] += count
        item["converted"] += count if status == "CONVERTED" else 0
    for item in counselors.values():
        item["conversion_rate"] = _percent(item["converted"], item["leads"])
    counselor_rows = sorted(counselors.values(), key=lambda item: (-item["converted"], -item["leads"], item["name"]))
    decomposition = [{"id": item["id"], "name": item["name"], "count": item["converted"]}
                     for item in counselor_rows]
    total_leads = sum(item["leads"] for item in counselor_rows)
    total_converted = sum(item["converted"] for item in counselor_rows)
    return {"period": period,
            "cards": {"converted": total_converted, "leads": total_leads,
                      "conversion_rate": _percent(total_converted, total_leads),
                      "unassigned": counselors.get(None, {}).get("leads", 0)},
            "counselors": counselor_rows, "decomposition": decomposition}


def _owner_filter(counselor_id):
    return (MainCrmLead.assigned_to_user_id == counselor_id if counselor_id is not None
            else MainCrmLead.assigned_to_user_id.is_(None))


@router.get("/sales/courses")
def sales_courses(counselor_id: int | None = Query(None), period: str = Query("all"),
                  admin: User = Depends(require_admin), db: Session = Depends(get_db),
                  start_date: date | None = None, end_date: date | None = None):
    filters = [MainCrmLead.status_of_lead == "CONVERTED", _owner_filter(counselor_id),
               *_conditions(MainCrmLead.created_at, _bounds(period, start_date, end_date))]
    name = func.coalesce(func.nullif(func.trim(MainCrmLead.course), ""), "Course not specified")
    rows = db.execute(select(name, func.count(MainCrmLead.id))
                      .where(*filters).group_by(name)
                      .order_by(func.count(MainCrmLead.id).desc(), name.asc())).all()
    return [{"name": _label(name, "Course not specified"), "count": count} for name, count in rows]


@router.get("/sales/sources")
def sales_sources(course: str = Query(...), counselor_id: int | None = Query(None), period: str = Query("all"),
                  admin: User = Depends(require_admin), db: Session = Depends(get_db),
                  start_date: date | None = None, end_date: date | None = None):
    course_filter = func.coalesce(func.nullif(func.trim(MainCrmLead.course), ""), "Course not specified") == course
    filters = [MainCrmLead.status_of_lead == "CONVERTED", _owner_filter(counselor_id), course_filter,
               *_conditions(MainCrmLead.created_at, _bounds(period, start_date, end_date))]
    name = func.coalesce(func.nullif(func.trim(MainCrmLead.source), ""), "Unknown")
    rows = db.execute(select(name, func.count(MainCrmLead.id))
                      .where(*filters).group_by(name)
                      .order_by(func.count(MainCrmLead.id).desc(), name.asc())).all()
    return [{"name": _label(name), "count": count} for name, count in rows]


@router.get("/dinesh")
def dinesh(period: str = Query("all"), admin: User = Depends(require_admin), db: Session = Depends(get_db),
           start_date: date | None = None, end_date: date | None = None):
    codes = ("IGC", "ID1", "ID2", "ID3")
    bounds = _bounds(period, start_date, end_date)
    filters = [Course.code.in_(codes)]
    if bounds:
        filters.extend((LearnerCourseRecord.event_date >= bounds[0].date(),
                        LearnerCourseRecord.event_date < bounds[1].date()))
    ranked = select(
        LearnerCourseRecord.learner_number.label("learner_number"),
        Course.code.label("course_code"), LearnerCourseRecord.result.label("result"),
        func.row_number().over(
            partition_by=(LearnerCourseRecord.learner_number, Course.code),
            order_by=(LearnerCourseRecord.event_date.desc(), LearnerCourseRecord.id.desc()),
        ).label("rank"),
    ).join(Course, Course.id == LearnerCourseRecord.course_id).where(*filters).subquery()
    latest = db.execute(select(ranked.c.learner_number, ranked.c.course_code, ranked.c.result)
                        .where(ranked.c.rank == 1)).all()
    outcomes = {code: {"pass": 0, "fail": 0, "pending": 0, "learners": 0} for code in codes}
    idip_passes = defaultdict(int)
    learners = set()
    for learner_number, code, result in latest:
        learners.add(learner_number)
        item = outcomes[code]
        item["learners"] += 1
        bucket = "pass" if (result or "").upper() == "PASS" else "fail" if (result or "").upper() == "FAIL" else "pending"
        item[bucket] += 1
        if code != "IGC" and bucket == "pass":
            idip_passes[learner_number] += 1
    attempts = db.scalar(select(func.count(LearnerCourseRecord.id)).join(Course, Course.id == LearnerCourseRecord.course_id).where(*filters)) or 0
    progression = {"one_unit": 0, "two_units": 0, "three_units": 0}
    for count in idip_passes.values():
        if count >= 1: progression["one_unit"] += 1
        if count >= 2: progression["two_units"] += 1
        if count >= 3: progression["three_units"] += 1
    for item in outcomes.values():
        item["pass_rate"] = _percent(item["pass"], item["pass"] + item["fail"])
    return {"period": period, "cards": {"learners": len(learners), "result_rows": attempts,
                                          "igc_pass_rate": outcomes["IGC"]["pass_rate"],
                                          "idip_three_units_passed": progression["three_units"]},
            "igc": outcomes["IGC"],
            "idip_units": [{"code": code, **outcomes[code]} for code in ("ID1", "ID2", "ID3")],
            "idip_progression": progression}
