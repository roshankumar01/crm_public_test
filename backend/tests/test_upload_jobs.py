import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Course, LearnerCourseRecord, LearnersCrmEnrollment, MainCrmLead, MarketingCampaign, User
from app.routers.uploads import run_upload_job, start_upload_job
from app.routers.learners import get_learner
from app.routers.learners_crm import get_learner_profile
from app.routers.main_crm import get_main_crm_lead
from app.services.upload_jobs import get_job


class UploadJobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'jobs.sqlite'}")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as db:
            db.add_all([
                User(username="admin", display_name="Admin", password_hash="x", role="ADMIN", active=True),
                Course(code="IGC", name="IGC", program_code="IGC"),
                Course(code="ID1", name="IDIP Unit 1", program_code="IDP"),
            ])
            db.commit()
        self.patch = patch("app.routers.uploads.SessionLocal", self.sessions)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.engine.dispose()
        self.directory.cleanup()

    def run_file(self, kind, body, import_type=None, source_category=None):
        with self.sessions() as db:
            admin = db.scalar(select(User).where(User.username == "admin"))
            tasks = BackgroundTasks()
            response = start_upload_job(tasks, UploadFile(file=BytesIO(body.encode()), filename="data.csv"),
                                        kind, import_type, source_category, "CREATE", None, admin, db)
            self.assertEqual(get_job(response["job_id"])["status"], "PROCESSING")
            run_upload_job(response["job_id"], body.encode(), "data.csv", kind, import_type,
                           source_category, "CREATE", None, admin.id)
            return get_job(response["job_id"])

    def test_each_upload_finishes_and_reports_counts(self):
        main = self.run_file("MAIN_CRM", "full_name,email,phone_number,source,course\nAda,ada@example.com,1234567890,Web,IGC\n",
                             source_category="INFO_EMAIL_LEADS")
        learner = self.run_file("LEARNERS_CRM", "enrolment_id,learner_name,email_id,course_name,enrolment_date,start_date,completion_date,completion_status\nE1,Ada,ada@example.com,IGC,,,,Completed\n")
        with self.sessions() as db:
            admin = db.scalar(select(User).where(User.username == "admin"))
            lead = db.scalar(select(MainCrmLead))
            before = get_main_crm_lead(lead.id, admin, db)["lifecycle"]["events"]
            self.assertEqual(sum(event["kind"] == "RESULT" for event in before), 0)
        course = self.run_file("COURSE", "learner_number,date,overall_result,name,email_id,ig1_result,ig2_result,unit,bilingual_dictionary,reg\nL1,2026-01-01,Pass,Ada,ada@example.com,31,100,IG2,Yes,Ind\n", import_type="IGC")
        idip = self.run_file("COURSE", "learner_number,date,course,result,name,email_id\nL1,2026-02-01,ID1,Pass,Ada,ada@example.com\n", import_type="IDP")
        campaign_rows = "learner_number,marketing_type,campaign_name\n" + "".join(f"L1,Email,Campaign {i}\n" for i in range(501))
        campaign = self.run_file("CAMPAIGN", campaign_rows)
        for job in (main, learner, course, idip, campaign):
            self.assertEqual(job["status"], "COMPLETED", job.get("error_message"))
            self.assertEqual(job["processed"], job["rows_total"])
        self.assertEqual((main["rows_imported"], learner["rows_imported"], course["rows_imported"], idip["rows_imported"], campaign["rows_imported"]), (1, 1, 1, 1, 501))
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(MainCrmLead)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(LearnersCrmEnrollment)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(LearnerCourseRecord)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(MarketingCampaign)), 501)
            admin = db.scalar(select(User).where(User.username == "admin"))
            lead = db.scalar(select(MainCrmLead))
            enrolment = db.scalar(select(LearnersCrmEnrollment))
            main_kinds = {item["kind"] for item in get_main_crm_lead(lead.id, admin, db)["lifecycle"]["events"]}
            learner_kinds = {item["kind"] for item in get_learner_profile(enrolment.learner_id, admin, db)["lifecycle"]["events"]}
            upsell_kinds = {item["kind"] for item in get_learner("L1", admin, db)["lifecycle"]["events"]}
            for kinds in (main_kinds, learner_kinds, upsell_kinds):
                self.assertTrue({"ENQUIRY", "ENROLMENT", "RESULT", "MARKETING"}.issubset(kinds))
            for detail in (get_main_crm_lead(lead.id, admin, db),
                           get_learner_profile(enrolment.learner_id, admin, db),
                           get_learner("L1", admin, db)):
                self.assertEqual(sum(event["kind"] == "RESULT" for event in detail["lifecycle"]["events"]), 2)
                igc = next(event for event in detail["lifecycle"]["events"] if event["kind"] == "RESULT" and event["title"] == "IGC")
                self.assertEqual(igc["fields"]["ig1_result"], "31")

    def test_failed_replacement_keeps_previous_enrolments(self):
        original = self.run_file("LEARNERS_CRM", "enrolment_id,learner_name,email_id,course_name,enrolment_date,start_date,completion_date,completion_status\nE1,Ada,ada@example.com,IGC,,,,Completed\n")
        target = original["result"]["unique_number"]
        invalid = "unrelated,column\na,b\n".encode()
        with self.sessions() as db:
            admin = db.scalar(select(User).where(User.username == "admin"))
            response = start_upload_job(BackgroundTasks(), UploadFile(file=BytesIO(invalid), filename="bad.csv"),
                                        "LEARNERS_CRM", None, None, "UPDATE", target, admin, db)
            run_upload_job(response["job_id"], invalid, "bad.csv", "LEARNERS_CRM", None,
                           None, "UPDATE", target, admin.id)
            self.assertEqual(get_job(response["job_id"])["status"], "FAILED")
            self.assertIsNotNone(db.get(LearnersCrmEnrollment, "E1"))


if __name__ == "__main__":
    unittest.main()
