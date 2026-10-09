"""Clear business data across every workspace, preserving accounts and configuration."""
from fastapi import HTTPException
from sqlalchemy import delete, select
from app.models import (DailyLearnerRow, CounselorAction, LeadReminder, ConversionVerification, UpsellCourseActivity, UpsellCourseCase,
    UpsellInfoEdit, UpsellContactInfo, LeadActivity, MarketingCampaign, MainCrmActivity,
    MainCrmLead, Lead, LearnerCourseRecord, LearnersCrmEnrollment, DailyLearnerRow, LearnersCrmProfile,
    Learner, CustomerIdentity, Customer, UploadBatch)
from app.services.lead_workflow import mark_opportunities_dirty

DATA_MODELS = (CounselorAction, LeadReminder, ConversionVerification, UpsellCourseActivity, UpsellCourseCase,
    UpsellInfoEdit, UpsellContactInfo, LeadActivity, MarketingCampaign, MainCrmActivity,
    MainCrmLead, Lead, LearnerCourseRecord, LearnersCrmEnrollment, LearnersCrmProfile,
    Learner, CustomerIdentity, Customer, UploadBatch)


def clear_crm_data(db):
    if db.scalar(select(UploadBatch.id).where(UploadBatch.status == "PROCESSING").limit(1)):
        raise HTTPException(409, "An upload is still processing. Wait for it to finish before resetting data.")
    counts = {}
    for model in DATA_MODELS:
        result = db.execute(delete(model))
        counts[model.__tablename__] = result.rowcount
    mark_opportunities_dirty(db)
    return counts
