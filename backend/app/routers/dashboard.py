from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, union
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Learner, LearnersCrmProfile, User
from app.services.auth import get_current_user
from app.services.lead_analytics import build_lead_analytics
from app.services.opportunities import get_all_opportunities
from app.services.date_filters import period_condition

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    period: str = "all",
):
    lead_analytics = build_lead_analytics(db, current_user, period)
    lead_summary = lead_analytics["summary"]

    if current_user.role != "ADMIN":
        return {
            "mode": "COUNSELOR",
            "assigned_leads": lead_summary["total_leads"],
            "new_leads": lead_summary["new"],
            "in_contact_leads": lead_summary["in_contact"],
            "converted_leads": lead_summary["converted"],
            "rejected_leads": lead_summary["rejected"],
            "conversion_rate": lead_summary["conversion_rate"],
            "email_campaign_activities": lead_summary["email_campaign_activities"],
            "whatsapp_campaign_activities": lead_summary["whatsapp_campaign_activities"],
        }

    linked_customers = union(
        select(Learner.customer_id).where(Learner.customer_id.is_not(None), *period_condition(Learner.updated_at, period)),
        select(LearnersCrmProfile.customer_id).where(LearnersCrmProfile.customer_id.is_not(None), *period_condition(LearnersCrmProfile.updated_at, period)),
    ).subquery()
    total_learners = db.scalar(select(func.count()).select_from(linked_customers)) or 0
    opportunity_summary = get_all_opportunities(db, current_user, period)["summary"]
    return {
        "mode": "ADMIN",
        "total_learners": total_learners,
        "opportunity_learners": opportunity_summary["unique_learners"],
        "total_opportunities": opportunity_summary["total_opportunities"],
        "course_opportunities": opportunity_summary["by_target"],
        "lead_total": lead_summary["total_leads"],
        "lead_assigned": lead_summary["assigned"],
        "lead_unassigned": lead_summary["unassigned"],
        "lead_converted": lead_summary["converted"],
        "lead_conversion_rate": lead_summary["conversion_rate"],
    }
