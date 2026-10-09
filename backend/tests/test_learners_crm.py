import unittest
from datetime import datetime, timezone
from io import BytesIO

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import LearnerCourseCategory, LearnerCourseMapping, LearnerCourseSubcategory, LearnersCrmEnrollment, LearnersCrmProfile, User
from app.routers.learner_course_mapping import (
    CategoryPayload, SubcategoryPayload, CoursePayload, CourseUpdate, create_category, create_subcategory, create_course,
    delete_category, list_mapping, update_category, update_course,
)
from app.routers.learners_crm import get_learner_profile, overview, search_learners, upload
from app.services.learner_course_mapping import seed_course_mapping


class LearnersCrmTests(unittest.TestCase):
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

    def import_csv(self, body):
        file = UploadFile(file=BytesIO(body.encode()), filename="learners.csv")
        return upload(file, "CREATE", None, self.admin, self.db)

    def test_optional_phone_and_search_by_email_phone_and_enrolment(self):
        self.import_csv("enrolment_id,learner_name,email_id,course_name,enrolment_date,start_date,completion_date,completion_status\nE-1,Ada,ada@example.com,IGC,,,,Not Completed\n")
        self.import_csv("enrolment_id,learner_name,email_id,phone_number,course_name,enrolment_date,start_date,completion_date,completion_status\nE-2,Ada,ada@example.com,+91 9876543210,ID1,,,,Completed\n")
        profile = self.db.scalar(select(LearnersCrmProfile).where(LearnersCrmProfile.normalized_email == "ada@example.com"))
        self.assertEqual(profile.phone_number, "+91 9876543210")
        self.assertEqual(profile.normalized_phone, "9876543210")
        detail = get_learner_profile(profile.id, self.admin, self.db)
        self.assertEqual(detail["email_id"], "ada@example.com")
        self.assertEqual({row["enrolment_id"] for row in detail["enrolments"]}, {"E-1", "E-2"})
        for query in ("ADA@EXAMPLE.COM", "9876543210", "e-2"):
            matches = search_learners(query, self.admin, self.db)
            self.assertEqual(len(matches), 1)
            self.assertEqual({row["enrolment_id"] for row in matches[0]["enrolments"]}, {"E-1", "E-2"})

    def test_overview_counts_each_enrolment_by_status(self):
        self.import_csv("enrolment_id,learner_name,email_id,course_name,enrolment_date,start_date,completion_date,completion_status\nE-1,Ada,ada@example.com,IGC,,,,Not Completed\nE-2,Ada,ada@example.com,ID1,,,,Completed\nE-3,Ben,ben@example.com,IGC,,,,Completed\nE-4,Ben,ben@example.com,ID1,,,,Completed\n")
        summary = overview(self.admin, self.db)
        self.assertEqual(summary["total_learners"], 2)
        self.assertEqual(summary["total_enrolments"], 4)
        self.assertEqual(summary["active"], 1)
        self.assertEqual(summary["completed"], 3)
        self.db.get(LearnersCrmEnrollment, "E-1").updated_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.db.commit()
        recent = search_learners("", self.admin, self.db)
        self.assertEqual({learner["email_id"] for learner in recent}, {"ada@example.com", "ben@example.com"})
        self.assertEqual(recent[0]["email_id"], "ada@example.com")
        self.assertEqual(self.db.scalar(select(LearnersCrmEnrollment).where(LearnersCrmEnrollment.enrolment_id == "E-1")).completion_status, "Not Completed")

    def test_seed_mapping_and_admin_edits_update_existing_enrolments(self):
        seed_course_mapping(self.db)
        seed_course_mapping(self.db)
        self.assertEqual(len(self.db.scalars(select(LearnerCourseCategory)).all()), 13)
        self.assertEqual(len(self.db.scalars(select(LearnerCourseSubcategory)).all()), 21)
        self.assertEqual(len(self.db.scalars(select(LearnerCourseMapping)).all()), 146)
        original = "NEBOSH IGC - Version 2.0"
        result = self.import_csv(f"enrolment_id,learner_name,email_id,course_name,enrolment_date,start_date,completion_date,completion_status\nE-1,Ada,ada@example.com,{original},,,,Completed\n")
        self.assertEqual(result["rows_mapped"], 1)
        self.assertEqual(search_learners("ada@example.com", self.admin, self.db)[0]["enrolments"][0]["course_category"], "Nebosh IGC")
        self.assertEqual(search_learners("ada@example.com", self.admin, self.db)[0]["enrolments"][0]["course_sub_category"], "IGC")
        self.assertIn({"name": "Nebosh IGC", "enrolments": 1}, overview(self.admin, self.db)["course_categories"])

        category = create_category(CategoryPayload(name="New Program"), self.admin, self.db)
        subcategory = create_subcategory(SubcategoryPayload(name="New Subcategory", category_id=category["id"]), self.admin, self.db)
        course = self.db.scalar(select(LearnerCourseMapping).where(LearnerCourseMapping.course_name == original))
        update_course(course.id, CourseUpdate(subcategory_id=subcategory["id"]), self.admin, self.db)
        self.assertEqual(search_learners("E-1", self.admin, self.db)[0]["enrolments"][0]["course_category"], "New Program")

        update_course(course.id, CourseUpdate(course_name="Replacement course"), self.admin, self.db)
        self.assertIsNone(search_learners("E-1", self.admin, self.db)[0]["enrolments"][0]["course_category"])
        self.assertIn(original, [item["course_name"] for item in list_mapping(self.admin, self.db)["unmapped_courses"]])
        create_course(CoursePayload(course_name=original, subcategory_id=subcategory["id"]), self.admin, self.db)
        self.assertEqual(search_learners("E-1", self.admin, self.db)[0]["enrolments"][0]["course_category"], "New Program")
        update_category(category["id"], CategoryPayload(name="Renamed Program"), self.admin, self.db)
        seed_course_mapping(self.db)
        self.assertEqual(search_learners("E-1", self.admin, self.db)[0]["enrolments"][0]["course_category"], "Renamed Program")
        with self.assertRaises(HTTPException):
            delete_category(category["id"], self.admin, self.db)
