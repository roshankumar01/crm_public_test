import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Customer, Lead, Learner, LearnerCourseRecord, LearnersCrmEnrollment, LearnersCrmProfile,
    MainCrmActivity, MainCrmLead, MarketingCampaign, UploadBatch, User, Course,
)
from app.routers.uploads import ResetUploadsRequest, reset_selected_uploads
from app.routers.uploads import ResetAllDataRequest, reset_all_data
from app.services.data_reset import DATA_MODELS
from app.models import (AppSetting, CustomerIdentity, ConversionVerification, UpsellContactInfo,
    UpsellInfoEdit, UpsellCourseCase, UpsellCourseActivity, LearnerCourseCategory, LearnerCourseSubcategory, LearnerCourseMapping)
from app.routers.dashboard import dashboard_summary
from app.services.lead_workflow import sync_opportunity_leads


class UploadResetTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(username="admin", display_name="Admin", password_hash="x", role="ADMIN", active=True)
        self.db.add(self.admin)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_selected_main_crm_upload_preserves_shared_lead(self):
        first = UploadBatch(import_type="MAIN_CRM_INFO_EMAIL_LEADS", filename="first.csv")
        second = UploadBatch(import_type="MAIN_CRM_LIVE_ONLINE_LEADS", filename="second.csv")
        self.db.add_all([first, second])
        self.db.flush()
        lead = MainCrmLead(full_name="Shared", source_category="LIVE_ONLINE_LEADS", upload_batch_id=first.id)
        self.db.add(lead)
        self.db.flush()
        self.db.add_all([
            MainCrmActivity(lead_id=lead.id, upload_batch_id=first.id, activity_type="ENQUIRY"),
            MainCrmActivity(lead_id=lead.id, upload_batch_id=second.id, activity_type="ENQUIRY"),
        ])
        self.db.commit()

        result = reset_selected_uploads(ResetUploadsRequest(upload_ids=[first.id], confirmation="DELETE SELECTED UPLOADS"), self.admin, self.db)
        self.assertEqual(result["uploads_deleted"], 1)
        self.assertIsNone(self.db.get(UploadBatch, first.id))
        self.assertIsNotNone(self.db.get(UploadBatch, second.id))
        self.assertIsNone(self.db.get(MainCrmLead, lead.id).upload_batch_id)
        self.assertEqual([item.upload_batch_id for item in self.db.scalars(select(MainCrmActivity)).all()], [second.id])

    def test_selected_learner_upload_only_removes_its_enrolments(self):
        first = UploadBatch(import_type="LEARNERS_CRM", filename="first.csv")
        second = UploadBatch(import_type="LEARNERS_CRM", filename="second.csv")
        self.db.add_all([first, second])
        self.db.flush()
        profile = LearnersCrmProfile(learner_name="Shared", email_id="s@example.com", normalized_email="s@example.com")
        self.db.add(profile)
        self.db.flush()
        self.db.add_all([
            LearnersCrmEnrollment(enrolment_id="a", learner_id=profile.id, course_name="A", upload_batch_id=first.id),
            LearnersCrmEnrollment(enrolment_id="b", learner_id=profile.id, course_name="B", upload_batch_id=second.id),
        ])
        self.db.commit()
        reset_selected_uploads(ResetUploadsRequest(upload_ids=[first.id], confirmation="DELETE SELECTED UPLOADS"), self.admin, self.db)
        self.assertIsNone(self.db.get(LearnersCrmEnrollment, "a"))
        self.assertIsNotNone(self.db.get(LearnersCrmEnrollment, "b"))
        self.assertIsNotNone(self.db.get(LearnersCrmProfile, profile.id))

    def test_selected_upsell_upload_removes_orphan_learner(self):
        batch = UploadBatch(import_type="IGC", filename="igc.csv")
        course = Course(code="IGC", name="IGC", program_code="IGC")
        learner = Learner(learner_number="L1", name="Learner")
        self.db.add_all([batch, course, learner])
        self.db.flush()
        self.db.add(LearnerCourseRecord(learner_number="L1", course_id=course.id, upload_batch_id=batch.id,
            event_date=__import__("datetime").date(2026, 1, 1), row_hash="unique"))
        self.db.commit()
        reset_selected_uploads(ResetUploadsRequest(upload_ids=[batch.id], confirmation="DELETE SELECTED UPLOADS"), self.admin, self.db)
        self.assertIsNone(self.db.get(Learner, "L1"))
        self.assertIsNotNone(self.db.get(Course, course.id))

    def test_confirmation_and_missing_ids_do_not_delete(self):
        batch = UploadBatch(import_type="MARKETING_CAMPAIGN", filename="campaign.csv")
        self.db.add(batch)
        self.db.commit()
        for payload in (
            ResetUploadsRequest(upload_ids=[batch.id], confirmation="wrong"),
            ResetUploadsRequest(upload_ids=[batch.id, 9999], confirmation="DELETE SELECTED UPLOADS"),
        ):
            with self.assertRaises(HTTPException):
                reset_selected_uploads(payload, self.admin, self.db)
            self.assertIsNotNone(self.db.get(UploadBatch, batch.id))

    def test_reset_removes_opportunities_from_dashboard_counts(self):
        batch = UploadBatch(import_type="IGC", filename="igc.csv")
        course = Course(code="IGC", name="IGC", program_code="IGC")
        customer = Customer(primary_name="Reset me", primary_email="reset@example.com")
        learner = Learner(learner_number="RESET-1", customer_id=None, name="Reset me", email_id="reset@example.com")
        self.db.add_all([batch, course, customer, learner])
        self.db.flush()
        learner.customer_id = customer.id
        self.db.add(LearnerCourseRecord(learner_number="RESET-1", course_id=course.id, upload_batch_id=batch.id,
            event_date=__import__("datetime").date(2026, 1, 1), result="PASS", row_hash="reset-hash"))
        self.db.commit()
        sync_opportunity_leads(self.db)
        self.assertGreater(self.db.query(Lead).count(), 0)
        reset_selected_uploads(ResetUploadsRequest(upload_ids=[batch.id], confirmation="DELETE SELECTED UPLOADS"), self.admin, self.db)
        self.assertEqual(dashboard_summary(self.admin, self.db)["total_opportunities"], 0)

    def test_total_reset_clears_manual_orphans_and_all_new_tables_without_uploads(self):
        customer = Customer(primary_name="Left over")
        category = LearnerCourseCategory(name="Safety", normalized_name="safety")
        course = Course(code="IGC", name="IGC", program_code="IGC")
        self.db.add_all([customer, category, course, AppSetting(key="recommendation_cooling_days", value="90")]); self.db.flush()
        sub = LearnerCourseSubcategory(category_id=category.id, name="IGC", normalized_name="igc")
        main = MainCrmLead(customer_id=customer.id, full_name="Left over", source_category="DIRECT_CALLS", status_of_lead="CONVERTED")
        learner = Learner(learner_number="LEFT", customer_id=customer.id, name="Left over")
        profile = LearnersCrmProfile(customer_id=customer.id, learner_name="Left over", email_id="left@example.com", normalized_email="left@example.com")
        lead = Lead(customer_id=customer.id, target_code="IGC", opportunity_key="IGC", status="CONVERTED")
        self.db.add_all([sub, main, learner, profile, lead]); self.db.flush()
        mapping = LearnerCourseMapping(category_id=category.id, subcategory_id=sub.id, course_name="IGC", normalized_name="igc")
        case = UpsellCourseCase(lead_id=lead.id, customer_id=customer.id, main_category="Safety", sub_category="IGC", normalized_subcategory="igc", course_name="IGC", status="CONVERTED")
        self.db.add_all([mapping, case]); self.db.flush()
        self.db.add_all([
            MainCrmActivity(lead_id=main.id, activity_type="EDIT", notes="Manual edit with no upload"),
            CustomerIdentity(customer_id=customer.id, identity_type="EMAIL", normalized_value="left@example.com"),
            ConversionVerification(upsell_case_id=case.id, customer_id=customer.id, course_name="IGC", verified_by_id=self.admin.id),
            UpsellContactInfo(customer_id=customer.id, overrides={}), UpsellInfoEdit(lead_id=lead.id, raw_data={}),
            UpsellCourseActivity(case_id=case.id, user_id=self.admin.id, activity_type="NOTE", notes="Manual contact"),
            LearnersCrmEnrollment(enrolment_id="LEFT", learner_id=profile.id, course_name="IGC"),
            LearnerCourseRecord(learner_number=learner.learner_number, course_id=course.id, event_date=__import__("datetime").date.today(), row_hash="left-result", result="PASS"),
        ]); self.db.commit()
        result = reset_all_data(ResetAllDataRequest(confirmation="RESET ALL CRM DATA"), self.admin, self.db)
        self.assertEqual(result["rows_deleted"]["main_crm_leads"], 1)
        for model in DATA_MODELS: self.assertEqual(self.db.query(model).count(), 0, model.__tablename__)
        self.assertEqual(self.db.query(User).count(), 1)
        self.assertEqual(self.db.query(LearnerCourseMapping).count(), 1)
        self.assertEqual(self.db.query(Course).count(), 1)
        self.assertEqual(self.db.get(AppSetting, "recommendation_cooling_days").value, "90")
        self.assertEqual(dashboard_summary(self.admin, self.db)["total_opportunities"], 0)
        repeated = reset_all_data(ResetAllDataRequest(confirmation="RESET ALL CRM DATA"), self.admin, self.db)
        self.assertTrue(all(count == 0 for count in repeated["rows_deleted"].values()))

    def test_total_reset_requires_admin_confirmation_and_no_running_upload(self):
        lead = MainCrmLead(full_name="Keep", source_category="DIRECT_CALLS")
        self.db.add(lead); self.db.commit()
        counselor = User(username="counselor", display_name="Counselor", password_hash="x", role="COUNSELOR")
        for actor, phrase in [(counselor, "RESET ALL CRM DATA"), (self.admin, "wrong")]:
            with self.assertRaises(HTTPException): reset_all_data(ResetAllDataRequest(confirmation=phrase), actor, self.db)
        self.assertEqual(self.db.query(MainCrmLead).count(), 1)
        self.db.add(UploadBatch(import_type="IGC", filename="running.csv", status="PROCESSING")); self.db.commit()
        with self.assertRaises(HTTPException) as error:
            reset_all_data(ResetAllDataRequest(confirmation="RESET ALL CRM DATA"), self.admin, self.db)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.query(MainCrmLead).count(), 1)


if __name__ == "__main__":
    unittest.main()
