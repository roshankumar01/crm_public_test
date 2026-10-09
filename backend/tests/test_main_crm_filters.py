import unittest
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Course, Customer, Learner, LearnerCourseRecord, MainCrmLead, UploadBatch, User
from app.routers.main_crm import lead_filter_options, list_leads
from app.services.customer_lifecycle import customer_lifecycle


class MainCrmFilterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(username="admin", display_name="Admin", role="ADMIN", password_hash="x", active=True)
        self.alex = User(username="alex", display_name="Alex", role="COUNSELOR", password_hash="x", active=True)
        self.ben = User(username="ben", display_name="Ben", role="COUNSELOR", password_hash="x", active=True)
        self.db.add_all([self.admin, self.alex, self.ben]); self.db.flush()
        self.db.add_all([
            MainCrmLead(full_name="A", source_category="INFO_EMAIL_LEADS", source="Website", course="IGC",
                        status_of_lead="NEW", assigned_to_user_id=self.alex.id,
                        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 3, 1)),
            MainCrmLead(full_name="B", source_category="DIRECT_CALLS", source="Phone", course="IDIP",
                        status_of_lead="CONVERTED", assigned_to_user_id=self.ben.id,
                        created_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)),
            MainCrmLead(full_name="C", source_category="DIRECT_CALLS", source="Phone", course="IGC",
                        status_of_lead="FOLLOW_UP", assigned_to_user_id=self.alex.id,
                        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 3, 1)),
            MainCrmLead(full_name="D", source_category="INFO_EMAIL_LEADS", source=None, course=None,
                        status_of_lead="BLANK", created_at=datetime(2026, 4, 1), updated_at=datetime(2026, 4, 1)),
        ]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def query(self, user=None, **kwargs):
        return list_leads(current_user=user or self.admin, db=self.db, page=1, page_size=50,
                          source_category="ALL", search="", **kwargs)

    def test_combined_filters_and_blank_values(self):
        rows = self.query(counselor_ids=[str(self.alex.id)], statuses=["NEW", "FOLLOW_UP"],
                          sources=["Website", "Phone"], courses=["IGC"])
        self.assertEqual(rows["total"], 2)
        self.assertEqual([row["full_name"] for row in rows["items"]], ["C", "A"])
        self.assertEqual(self.query(counselor_ids=["UNASSIGNED"], sources=["__EMPTY__"],
                                   courses=["__EMPTY__"])["items"][0]["full_name"], "D")

    def test_date_sorting_is_stable_and_paginated(self):
        self.assertEqual([row["full_name"] for row in self.query(sort_by="created_at", sort_direction="asc")["items"]], ["A", "C", "B", "D"])
        self.assertEqual([row["full_name"] for row in self.query(sort_by="updated_at", sort_direction="desc")["items"]], ["D", "C", "A", "B"])
        page = list_leads(self.admin, self.db, 2, 2, "ALL", "", sort_by="created_at", sort_direction="asc")
        self.assertEqual([row["full_name"] for row in page["items"]], ["B", "D"])
        self.assertEqual(page["pages"], 2)
        with self.assertRaises(HTTPException): self.query(sort_by="full_name")

    def test_options_and_results_preserve_counselor_scope(self):
        self.assertEqual(self.query(user=self.alex, counselor_ids=[str(self.ben.id)])["total"], 0)
        options = lead_filter_options(self.alex, self.db, "ALL")
        self.assertEqual(options["counselors"], [{"value": str(self.alex.id), "label": "Alex", "count": 2}])
        self.assertEqual({row["value"] for row in options["courses"]}, {"IGC"})
        self.assertEqual({row["value"] for row in options["sources"]}, {"Website", "Phone"})

    def test_journey_uses_result_upload_type(self):
        customer = Customer(primary_name="Learner")
        self.db.add(customer); self.db.flush()
        self.db.add(Learner(learner_number="L1", name="Learner", customer_id=customer.id))
        igc = Course(code="IGC", name="IGC", program_code="IGC")
        id1 = Course(code="ID1", name="ID1", program_code="IDP")
        upload = UploadBatch(import_type="IDP", filename="IDP_results.xlsx", status="COMPLETED")
        self.db.add_all([igc, id1, upload]); self.db.flush()
        self.db.add_all([
            LearnerCourseRecord(learner_number="L1", course_id=igc.id, event_date=date(2026, 3, 1), result="PASS", row_hash="igc"),
            LearnerCourseRecord(learner_number="L1", course_id=id1.id, upload_batch_id=upload.id,
                                event_date=date(2026, 3, 1), result="REFER", row_hash="id1"),
        ]); self.db.commit()
        events = customer_lifecycle(self.db, customer.id, self.admin)["events"]
        self.assertEqual({row["source_label"] for row in events}, {"Result data IGC", "Result data IDP"})


if __name__ == "__main__":
    unittest.main()
