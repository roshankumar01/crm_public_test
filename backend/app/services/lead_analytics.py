from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Lead, LeadActivity, UpsellCourseActivity, UpsellCourseCase, User
from app.services.lead_workflow import sync_opportunity_leads
from app.services.opportunities import SECTION_CONFIG, section_key
from app.services.date_filters import period_condition
from app.services.upsell_management import work_items


def scoped_leads(db: Session, current_user: User, period: str = "all"):
    """Full rows are reserved for the explicit Excel export."""
    sync_opportunity_leads(db)
    query = select(Lead).where(Lead.is_active.is_(True))
    dates = period_condition(Lead.created_at, period)
    if dates:
        case_date = case((UpsellCourseCase.status == "CONVERTED", UpsellCourseCase.converted_at), else_=UpsellCourseCase.created_at)
        course_in_period = select(UpsellCourseCase.id).where(UpsellCourseCase.lead_id == Lead.id,
            *period_condition(case_date, period)).exists()
        query = query.where(or_(and_(*dates), course_in_period))
    if current_user.role != "ADMIN":
        query = query.where(Lead.assigned_to_user_id == current_user.id)
    return db.scalars(query.order_by(Lead.created_at.desc())).all()


def build_lead_analytics(db: Session, current_user: User, period: str = "all"):
    """Aggregate in SQL so dashboards do not materialize every lead/activity."""
    sync_opportunity_leads(db)
    W = work_items().c
    scope = []
    scope.extend(period_condition(W.created_at, period))
    if current_user.role != "ADMIN":
        scope.append(W.assigned_to_user_id == current_user.id)
    grouped = db.execute(select(
        W.status, W.target_code, W.opportunity_key, W.stage, W.assigned_to_user_id, W.is_active,
        func.count(W.id)
    ).where(*scope).group_by(W.status, W.target_code, W.opportunity_key, W.stage, W.assigned_to_user_id, W.is_active)).all()
    status_counts = Counter()
    target = defaultdict(Counter)
    counselor = defaultdict(Counter)
    total = assigned = active_rule_leads = 0
    for status, target_code, opportunity_key, stage, owner, is_active, count in grouped:
        total += count
        status_counts[status] += count
        section = section_key(opportunity_key, stage)
        target[(target_code, section)][status] += count
        target[(target_code, section)]["total"] += count
        if owner is not None:
            assigned += count
            counselor[owner][status] += count
            counselor[owner]["total"] += count
        if is_active:
            active_rule_leads += count
    ids = list(counselor)
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    counselor_rows = []
    for owner, counts in counselor.items():
        count = counts["total"]
        counselor_rows.append({
            "counselor_id": owner,
            "counselor_name": users[owner].display_name if owner in users else f"User {owner}",
            "total": count, "new": counts["NEW"], "in_contact": counts["IN_CONTACT"],
            "rejected": counts["REJECTED"], "converted": counts["CONVERTED"],
            "conversion_rate": round(counts["CONVERTED"] / count * 100, 1) if count else 0,
        })
    counselor_rows.sort(key=lambda item: (-item["conversion_rate"], -item["total"], item["counselor_name"]))
    target_rows = [{"target_code": code, "section_key": section,
                    "target_name": (SECTION_CONFIG[section][1] if section in SECTION_CONFIG and code == SECTION_CONFIG[section][0] else code), "total": counts["total"],
                    "new": counts["NEW"], "in_contact": counts["IN_CONTACT"],
                    "rejected": counts["REJECTED"], "converted": counts["CONVERTED"]}
                   for (code, section), counts in sorted(target.items())]

    activity_scope = [Lead.is_active.is_(True), *period_condition(Lead.created_at, period)] if current_user.role == "ADMIN" else [Lead.is_active.is_(True), *period_condition(Lead.created_at, period), Lead.assigned_to_user_id == current_user.id]
    activity_counts = Counter(dict(db.execute(select(LeadActivity.activity_type, func.count(LeadActivity.id))
        .join(Lead, LeadActivity.lead_id == Lead.id).where(*activity_scope)
        .group_by(LeadActivity.activity_type)).all()))

    case_activity_scope = period_condition(UpsellCourseCase.created_at, period)
    if current_user.role != "ADMIN": case_activity_scope.append(Lead.assigned_to_user_id == current_user.id)
    for kind, count in db.execute(select(UpsellCourseActivity.activity_type, func.count(UpsellCourseActivity.id))
        .join(UpsellCourseCase, UpsellCourseActivity.case_id == UpsellCourseCase.id).join(Lead, UpsellCourseCase.lead_id == Lead.id)
        .where(*case_activity_scope).group_by(UpsellCourseActivity.activity_type)):
        activity_counts[kind] += count

    open_scope = [*scope, W.status.not_in(("CONVERTED", "REJECTED"))]
    today = date.today()
    aging = {
        "0_7_days": db.scalar(select(func.count(W.id)).where(*open_scope, W.trigger_date >= today - timedelta(days=7))) or 0,
        "8_30_days": db.scalar(select(func.count(W.id)).where(*open_scope, W.trigger_date < today - timedelta(days=7), W.trigger_date >= today - timedelta(days=30))) or 0,
        "over_30_days": db.scalar(select(func.count(W.id)).where(*open_scope, W.trigger_date < today - timedelta(days=30))) or 0,
        "unknown": db.scalar(select(func.count(W.id)).where(*open_scope, W.trigger_date.is_(None))) or 0,
    }
    unique_learners = db.scalar(select(func.count(func.distinct(W.customer_id))).where(*scope)) or 0
    converted = status_counts["CONVERTED"]
    return {
        "scope": "ALL" if current_user.role == "ADMIN" else "MY_LEADS",
        "summary": {
            "total_leads": total, "unique_learners": unique_learners,
            "active_rule_leads": active_rule_leads, "assigned": assigned,
            "unassigned": total - assigned,
            "new": status_counts["NEW"], "in_contact": status_counts["IN_CONTACT"],
            "rejected": status_counts["REJECTED"], "converted": converted,
            "conversion_rate": round(converted / total * 100, 1) if total else 0,
            "email_campaign_activities": activity_counts["EMAIL_CAMPAIGN"],
            "whatsapp_campaign_activities": activity_counts["WHATSAPP_CAMPAIGN"],
            "calls": activity_counts["CALL"],
        },
        "counselor_breakdown": counselor_rows,
        "target_breakdown": target_rows,
        "aging": aging,
    }
