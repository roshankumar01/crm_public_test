"""Virtual admin enrolments. Uploaded enrolments/results retain their provenance."""
from sqlalchemy import select
from app.models import ConversionVerification, MainCrmLead, UpsellCourseCase


def active_verifications_query():
    main = select(MainCrmLead.id).where(MainCrmLead.id == ConversionVerification.main_lead_id,
        MainCrmLead.customer_id == ConversionVerification.customer_id, MainCrmLead.status_of_lead == "CONVERTED",
        MainCrmLead.course.is_not_distinct_from(ConversionVerification.course_name)).correlate(ConversionVerification).exists()
    upsell = select(UpsellCourseCase.id).where(UpsellCourseCase.id == ConversionVerification.upsell_case_id,
        UpsellCourseCase.customer_id == ConversionVerification.customer_id, UpsellCourseCase.status == "CONVERTED",
        UpsellCourseCase.course_name == ConversionVerification.course_name).correlate(ConversionVerification).exists()
    return select(ConversionVerification).where(main | upsell).order_by(ConversionVerification.verified_at, ConversionVerification.id)
