from sqlalchemy import delete

from app.database import SessionLocal
from app.models import Lead, LeadActivity, Learner, LearnerCourseRecord, MarketingCampaign, UploadBatch


def reset_test_data():
    db = SessionLocal()
    try:
        from app.services.data_reset import clear_crm_data
        clear_crm_data(db)
        db.commit()
        print("Test data reset successfully. Courses and CRM users were preserved.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    confirmation = input(
        "This will DELETE all business data across Main, Learners and Upsell CRM, including contacts, history and verifications.\n"
        "CRM users and courses will be preserved.\n"
        "Type RESET to continue: "
    )
    if confirmation == "RESET":
        reset_test_data()
    else:
        print("Reset cancelled.")
