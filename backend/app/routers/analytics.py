from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer, Lead, LeadActivity, Learner, MarketingCampaign, UpsellCourseCase, UpsellCourseActivity, User
from app.services.auth import get_current_user
from app.services.lead_analytics import build_lead_analytics, scoped_leads
from app.services.opportunities import section_key

def excel_value(value):
    return value.isoformat() if getattr(value, "tzinfo", None) is not None else value


router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/leads")
def get_lead_analytics(
    period: str = "all",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_lead_analytics(db, current_user, period)


@router.get("/leads/export")
def export_lead_analytics(
    opportunity_key: str | None = Query(default=None),
    period: str = "all",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    analytics = build_lead_analytics(db, current_user, period)
    leads = scoped_leads(db, current_user, period)
    if opportunity_key:
        leads = [lead for lead in leads if section_key(lead.opportunity_key, lead.stage) == opportunity_key and lead.is_active]
    lead_ids = [lead.id for lead in leads]

    learners = {}
    learner_numbers = {lead.learner_number for lead in leads}
    if learner_numbers:
        learners = {
            learner.learner_number: learner
            for learner in db.execute(
                select(Learner).where(Learner.learner_number.in_(learner_numbers))
            ).scalars().all()
        }

    customer_ids = {lead.customer_id for lead in leads if lead.customer_id}
    customers = {customer.id: customer for customer in db.scalars(select(Customer).where(Customer.id.in_(customer_ids)))} if customer_ids else {}

    counselor_ids = {lead.assigned_to_user_id for lead in leads if lead.assigned_to_user_id}
    counselors = {}
    if counselor_ids:
        counselors = {
            user.id: user
            for user in db.execute(select(User).where(User.id.in_(counselor_ids))).scalars().all()
        }

    lead_rows = []
    for lead in leads:
        learner = learners.get(lead.learner_number)
        customer = customers.get(lead.customer_id)
        counselor = counselors.get(lead.assigned_to_user_id)
        lead_rows.append({
            "Lead ID": lead.id,
            "Learner Number": lead.learner_number,
            "Learner Name": customer.primary_name if customer else learner.name if learner else "",
            "Email": customer.primary_email if customer else learner.email_id if learner else "",
            "Phone": customer.primary_phone if customer else learner.contact_number if learner else "",
            "Opportunity": lead.opportunity_key,
            "Target": lead.target_code,
            "Trigger Date": lead.trigger_date,
            "CRM Status": lead.status,
            "Counselor": counselor.display_name if counselor else "Unassigned",
            "Current Rule Opportunity": "Yes" if lead.is_active else "No",
            "Assigned At": lead.assigned_at,
            "Status Updated At": lead.status_updated_at,
            "Lead Created At": lead.created_at,
        })

    activity_rows = []
    if lead_ids:
        rows = db.execute(
            select(LeadActivity, User, Lead)
            .join(Lead, LeadActivity.lead_id == Lead.id)
            .outerjoin(User, LeadActivity.user_id == User.id)
            .where(LeadActivity.lead_id.in_(lead_ids))
            .order_by(LeadActivity.created_at.desc())
        ).all()
        activity_rows = [
            {
                "Lead ID": activity.lead_id,
                "Learner Number": lead.learner_number,
                "Activity Type": activity.activity_type,
                "Channel": activity.channel,
                "Campaign Name": activity.campaign_name,
                "Notes": activity.notes,
                "User": user.display_name if user else "System",
                "Created At": activity.created_at,
            }
            for activity, user, lead in rows
        ]

    campaign_rows = []
    if learner_numbers:
        campaigns = db.execute(
            select(MarketingCampaign)
            .where(MarketingCampaign.learner_number.in_(learner_numbers))
            .order_by(MarketingCampaign.created_at.desc())
        ).scalars().all()
        campaign_rows = [
            {
                "Learner Number": campaign.learner_number,
                "Campaign Name": campaign.campaign_name,
                "Marketing Type": campaign.marketing_type,
                "Created At": campaign.created_at,
                "Upload Batch ID": campaign.upload_batch_id,
            }
            for campaign in campaigns
        ]

    if opportunity_key:
        from app.services.upsell_management import work_items
        from app.services.date_filters import period_condition
        W = work_items().c
        case_counts = dict(db.execute(select(W.status, func.count()).where(W.id.in_(lead_ids),
            *period_condition(W.created_at, period)).group_by(W.status)).all())
        summary_rows = [
            {"Metric": "Current opportunity", "Value": opportunity_key.replace("_", " ").title()},
            {"Metric": "Leads", "Value": sum(case_counts.values())},
            {"Metric": "New", "Value": case_counts.get("NEW", 0)},
            {"Metric": "In contact", "Value": case_counts.get("IN_CONTACT", 0)},
            {"Metric": "Converted", "Value": case_counts.get("CONVERTED", 0)},
            {"Metric": "Rejected", "Value": case_counts.get("REJECTED", 0)},
        ]
    else:
        summary_rows = [
            {"Metric": key.replace("_", " ").title(), "Value": value}
            for key, value in analytics["summary"].items()
        ]

    cases = db.scalars(select(UpsellCourseCase).where(UpsellCourseCase.lead_id.in_(lead_ids)).order_by(UpsellCourseCase.id)).all() if lead_ids else []
    course_rows = [{"Lead ID": item.lead_id, "Panel ID": item.id, "Main Category": item.main_category,
        "Subcategory": item.sub_category, "Course": item.course_name, "Status": item.status,
        "Converted At": item.converted_at.isoformat() if item.converted_at else None,
        "Counselor ID": item.counselor_id, "Converted By ID": item.converted_by_id} for item in cases]
    course_activities = db.scalars(select(UpsellCourseActivity).where(UpsellCourseActivity.case_id.in_([item.id for item in cases]))).all() if cases else []
    course_history_rows = [{"Panel ID": item.case_id, "Activity": item.activity_type, "Campaign": item.campaign_name,
        "Notes": item.notes, "User ID": item.user_id, "Created At": item.created_at.isoformat(),
        "Edited By ID": item.edited_by_id, "Edited At": item.updated_at.isoformat() if item.updated_at else None} for item in course_activities]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(lead_rows).map(excel_value).to_excel(writer, sheet_name="Leads", index=False)
        pd.DataFrame(analytics["counselor_breakdown"]).to_excel(
            writer, sheet_name="Counselor Breakdown", index=False
        )
        pd.DataFrame(analytics["target_breakdown"]).to_excel(
            writer, sheet_name="Target Breakdown", index=False
        )
        pd.DataFrame(activity_rows).map(excel_value).to_excel(writer, sheet_name="CRM Activities", index=False)
        pd.DataFrame(campaign_rows).map(excel_value).to_excel(writer, sheet_name="Campaigns", index=False)
        pd.DataFrame(course_rows).to_excel(writer, sheet_name="Course Conversations", index=False)
        pd.DataFrame(course_history_rows).to_excel(writer, sheet_name="Course Contact History", index=False)
    output.seek(0)

    filename = f"{opportunity_key.lower()}-current-leads.xlsx" if opportunity_key else ("lead-analytics.xlsx" if current_user.role == "ADMIN" else "my-lead-analytics.xlsx")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
