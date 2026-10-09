import unittest
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import CounselorAction, Customer, Lead, MainCrmLead, User
from app.routers.counselor_dashboard import bounds, changes, summary
from app.routers.main_crm import AssignmentUpdate, update_assignment


class CounselorDashboardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(username="admin", display_name="Admin", role="ADMIN", active=True, password_hash="x")
        self.alex = User(username="alex", display_name="Alex", role="COUNSELOR", active=True, password_hash="x")
        self.ben = User(username="ben", display_name="Ben", role="COUNSELOR", active=True, password_hash="x")
        self.db.add_all([self.admin, self.alex, self.ben]); self.db.flush()
        self.local_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        self.today = datetime.combine(self.local_today, time(12), ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
        self.old = self.today - timedelta(days=9)
        customer = Customer(primary_name="Upsell Person")
        self.db.add(customer); self.db.flush()
        self.main = MainCrmLead(full_name="Main Person", customer_id=customer.id,
                                source_category="DIRECT_CALLS", source="Phone",
                                assigned_to_user_id=self.alex.id, assigned_at=self.today,
                                created_at=self.old)
        self.old_lead = MainCrmLead(full_name="Old lead", source_category="DIRECT_CALLS",
                                    assigned_to_user_id=self.alex.id, assigned_at=self.old)
        self.upsell = Lead(customer_id=customer.id, opportunity_key="IGC", target_code="IGC")
        self.db.add_all([self.main, self.old_lead, self.upsell]); self.db.flush()
        self.db.add_all([
            CounselorAction(main_lead_id=self.main.id, user_id=self.alex.id, actor_name="Alex",
                            assigned_counselor_id=self.alex.id, assigned_counselor_name="Alex",
                            action_type="STATUS_CHANGE", before_status="NEW", after_status="HOT",
                            before_note="First call", after_note="Discussed IGC", created_at=self.today),
            CounselorAction(upsell_lead_id=self.upsell.id, user_id=self.alex.id, actor_name="Alex",
                            action_type="CONTACT_EDIT", before_note="Original note", after_note=".",
                            created_at=self.today),
            CounselorAction(main_lead_id=self.main.id, user_id=self.admin.id, actor_name="Admin",
                            action_type="NOTE", after_note="Admin note", created_at=self.today),
            CounselorAction(main_lead_id=self.old_lead.id, user_id=self.ben.id, actor_name="Ben",
                            action_type="NOTE", after_note="Old update", created_at=self.old),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_summary_uses_assignment_date_and_actual_author(self):
        data = summary("custom", self.local_today, self.local_today, self.admin, self.db)
        self.assertEqual(data["cards"], {"leads_given": 1, "main_updates": 1,
                                          "upsell_updates": 1, "total_updates": 2,
                                          "unique_people": 1, "unique_main_people": 1,
                                          "unique_upsell_people": 1})
        self.assertEqual(data["counselors"][0]["name"], "Alex")
        self.assertEqual(data["counselors"][0]["leads_given"], 1)
        self.assertEqual(data["counselors"][1]["total_updates"], 0)
        all_time = summary("all", None, None, self.admin, self.db)
        self.assertEqual(all_time["cards"]["leads_given"], 2)
        self.assertEqual(all_time["cards"]["total_updates"], 3)
        self.assertEqual(all_time["cards"]["unique_people"], 2)

    def test_repeated_updates_to_one_person_count_once_even_across_crms(self):
        self.db.add(CounselorAction(main_lead_id=self.main.id, user_id=self.alex.id,
                                    actor_name="Alex", action_type="NOTE", after_note="Another call",
                                    created_at=self.today + timedelta(minutes=1)))
        self.db.commit()
        data = summary("custom", self.local_today, self.local_today, self.admin, self.db)
        self.assertEqual(data["cards"]["total_updates"], 3)
        self.assertEqual(data["cards"]["unique_people"], 1)
        self.assertEqual(data["counselors"][0]["unique_people"], 1)
        self.assertEqual(data["counselors"][0]["unique_main_people"], 1)
        self.assertEqual(data["counselors"][0]["unique_upsell_people"], 1)
        unique = changes(self.alex.id, 1, "custom", self.local_today, self.local_today,
                         self.admin, self.db, mode="unique")
        self.assertEqual(unique["total"], 1)
        self.assertEqual(unique["items"][0]["after_note"], "Another call")
        self.assertEqual(unique["items"][0]["person_updates"], 3)
        key = unique["items"][0]["person_key"]
        all_person = changes(self.alex.id, 1, "custom", self.local_today, self.local_today,
                             self.admin, self.db, mode="all", person=key)
        self.assertEqual(all_person["total"], 3)

    def test_change_log_filters_actor_and_keeps_note_versions(self):
        data = changes(self.alex.id, 1, "custom", self.local_today, self.local_today, self.admin, self.db)
        self.assertEqual(data["total"], 2)
        self.assertEqual({row["workspace"] for row in data["items"]}, {"main", "upsell"})
        edit = next(row for row in data["items"] if row["workspace"] == "upsell")
        self.assertEqual((edit["lead_name"], edit["before_note"], edit["after_note"]),
                         ("Upsell Person", "Original note", "."))
        self.assertEqual(changes(self.ben.id, 1, "custom", self.local_today, self.local_today,
                                 self.admin, self.db)["total"], 0)
        with self.assertRaises(HTTPException):
            changes(self.admin.id, 1, "all", None, None, self.admin, self.db)

    def test_reassignment_updates_date_and_reallocates_current_lead(self):
        update_assignment(self.main.id, AssignmentUpdate(counselor_user_id=self.ben.id), self.admin, self.db)
        data = summary("custom", self.local_today, self.local_today, self.admin, self.db)
        by_name = {row["name"]: row for row in data["counselors"]}
        self.assertEqual(by_name["Alex"]["leads_given"], 0)
        self.assertEqual(by_name["Ben"]["leads_given"], 1)
        self.assertEqual(by_name["Alex"]["total_updates"], 2)

    def test_date_validation(self):
        with self.assertRaises(HTTPException): bounds("custom", self.local_today, None)
        with self.assertRaises(HTTPException): bounds("wrong", None, None)
