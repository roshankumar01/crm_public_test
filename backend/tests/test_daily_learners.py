import unittest
from io import BytesIO

from fastapi import UploadFile
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import DailyLearnerRow, Lead, LearnersCrmEnrollment, MainCrmLead, User
from app.routers.learners_crm import VerifyDailyLearner, learner_verification, upload, upload_daily, verify_daily
from app.services.customer_identity import resolve_customer
from app.services.lead_workflow import sync_opportunity_leads
from app.services.learner_course_mapping import seed_course_mapping


class DailyLearnerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(username="admin", display_name="Admin", password_hash="x", role="ADMIN", active=True)
        self.owner = User(username="owner", display_name="Asha Patel", password_hash="x", role="COUNSELOR", active=True)
        self.db.add_all([self.admin, self.owner]); self.db.commit()
        seed_course_mapping(self.db)

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def upload(self, csv):
        return upload_daily(UploadFile(file=BytesIO(csv.encode()), filename="daily.csv"), self.admin, self.db)

    def test_matched_daily_row_is_verified_and_uses_file_counselor_for_upsell(self):
        customer = resolve_customer(self.db, "Ada", "ada@example.com")
        self.db.add(MainCrmLead(customer_id=customer.id, full_name="Ada", email="ada@example.com",
            normalized_email="ada@example.com", source_category="DIRECT_CALLS"))
        self.db.commit()
        result = self.upload("enrolment_id,learner_name,email,phone,course,created_date,enrolment_date,start_date,counselor_name\n"
            "D-1,Ada,ada@example.com,9876543210,NEBOSH- Health and Safety at Work,2026-01-01,2026-01-01,2026-01-02,Asha Patel\n")
        self.assertEqual(result["rows_verified"], 1)
        row = self.db.scalar(select(DailyLearnerRow))
        self.assertEqual(row.status, "VERIFIED")
        enrollment = self.db.get(LearnersCrmEnrollment, "D-1")
        self.assertEqual(enrollment.counselor_user_id, self.owner.id)
        self.assertEqual(learner_verification("daily", 1, self.admin, self.db)["total"], 0)
        self.assertEqual(learner_verification("daily_verified", 1, self.admin, self.db)["total"], 1)
        sync_opportunity_leads(self.db)
        leads = self.db.scalars(select(Lead).where(Lead.customer_id == customer.id)).all()
        self.assertTrue(leads)
        self.assertTrue(all(lead.assigned_to_user_id == self.owner.id and lead.counselor_from_daily for lead in leads))

    def test_unmatched_daily_row_waits_until_admin_verifies_and_corrects_counselor(self):
        result = self.upload("enrolment_id,learner_name,email,phone,course,created_date,enrolment_date,start_date,counselor_name\n"
            "D-2,Ben,ben@example.com,9876543211,NEBOSH- Health and Safety at Work,2026-01-01,2026-01-01,2026-01-02,Unknown Person\n")
        self.assertEqual(result["rows_pending"], 1)
        row = self.db.scalar(select(DailyLearnerRow))
        self.assertIsNone(self.db.get(LearnersCrmEnrollment, "D-2"))
        self.assertEqual(learner_verification("daily", 1, self.admin, self.db)["total"], 1)
        verified = verify_daily(row.id, VerifyDailyLearner(email="ben@example.com", phone="9876543211",
            counselor_user_id=self.owner.id), self.admin, self.db)
        self.assertEqual(verified["status"], "VERIFIED")
        self.assertFalse(verified["matched_main"])
        self.assertEqual(self.db.get(LearnersCrmEnrollment, "D-2").counselor_user_id, self.owner.id)

    def test_migrated_unmatched_rows_remain_enrolled_and_show_red_until_main_match(self):
        upload(UploadFile(file=BytesIO(b"enrolment_id,learner_name,email_id,course_name,enrolment_date,start_date,completion_date,completion_status\nM-1,Mia,mia@example.com,IGC,2026-01-01,,,Not Completed\n"), filename="migrated.csv"),
            "CREATE", None, self.admin, self.db)
        self.assertIsNotNone(self.db.get(LearnersCrmEnrollment, "M-1"))
        self.assertEqual(learner_verification("migrated", 1, self.admin, self.db)["total"], 1)
        customer = resolve_customer(self.db, "Mia", "mia@example.com")
        self.db.add(MainCrmLead(customer_id=customer.id, full_name="Mia", email="mia@example.com",
            normalized_email="mia@example.com", source_category="DIRECT_CALLS"))
        self.db.commit()
        self.assertEqual(learner_verification("migrated", 1, self.admin, self.db)["total"], 0)
        self.assertEqual(learner_verification("migrated_matched", 1, self.admin, self.db)["total"], 1)

    def test_admin_corrects_contact_to_main_crm_match(self):
        customer = resolve_customer(self.db, "Nia", "nia@example.com")
        self.db.add(MainCrmLead(customer_id=customer.id, full_name="Nia", email="nia@example.com",
            normalized_email="nia@example.com", source_category="DIRECT_CALLS"))
        self.db.commit()
        self.upload("enrolment_id,learner_name,email,phone,course,created_date,enrolment_date,start_date,counselor_name\n"
            "D-3,Nia,typo@example.com,,NEBOSH- Health and Safety at Work,2026-01-01,2026-01-01,2026-01-02,Asha Patel\n")
        row = self.db.scalar(select(DailyLearnerRow))
        self.assertEqual(row.status, "PENDING")
        result = verify_daily(row.id, VerifyDailyLearner(email="nia@example.com", phone=None,
            counselor_user_id=self.owner.id), self.admin, self.db)
        self.assertTrue(result["matched_main"])
        self.assertEqual(self.db.get(LearnersCrmEnrollment, "D-3").counselor_user_id, self.owner.id)


if __name__ == "__main__":
    unittest.main()
