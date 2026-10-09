import unittest
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Course, Customer, Lead, Learner, LearnerCourseRecord, LearnersCrmProfile, MainCrmLead, User
from app.routers.learners import get_contacts, get_contact
from app.routers.learners_crm import learner_profiles_payload
from app.routers.main_crm import AssignmentUpdate, update_assignment
from app.services.counselor_sync import main_counselors, sync_main_counselors
from app.services.customer_identity import resolve_customer
from app.services.lead_workflow import get_accessible_lead, sync_opportunity_leads


class CounselorSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(username="admin", display_name="Admin", role="ADMIN", password_hash="x", active=True)
        self.alex = User(username="alex", display_name="Alex", email="alex@test.com", role="COUNSELOR", password_hash="x", active=True)
        self.ben = User(username="ben", display_name="Ben", role="COUNSELOR", password_hash="x", active=True)
        self.db.add_all([self.admin, self.alex, self.ben]); self.db.flush()
        self.customer = resolve_customer(self.db, "Learner", "learner@test.com", "9876543210")
        self.main = MainCrmLead(customer_id=self.customer.id, full_name="Learner", source_category="DIRECT_CALLS",
                                assigned_to_user_id=self.alex.id, updated_at=datetime(2026, 1, 1))
        self.profile = LearnersCrmProfile(customer_id=self.customer.id, learner_name="Learner", email_id="learner@test.com",
                                          normalized_email="learner@test.com")
        self.lead = Lead(customer_id=self.customer.id, opportunity_key="IDP_ENTRY", target_code="IDP",
                         updated_at=datetime(2026, 2, 1))
        self.db.add_all([self.main, self.profile, self.lead]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_existing_leads_and_learner_payloads_use_main_owner(self):
        sync_main_counselors(self.db); self.db.commit()
        self.assertEqual(self.lead.assigned_to_user_id, self.alex.id)
        self.assertTrue(self.lead.counselor_from_main)
        self.assertEqual(self.lead.updated_at, datetime(2026, 2, 1))
        payload = learner_profiles_payload(self.db, [self.profile])[0]
        self.assertEqual(payload["assigned_to_name"], "Alex")
        self.assertEqual(payload["assigned_to_email"], "alex@test.com")
        self.assertEqual(get_contacts(search=None, admin_user=self.admin, db=self.db, page=1)["items"][0]["assigned_to_name"], "Alex")

    def test_main_reassignment_and_unassignment_propagate_and_change_access(self):
        sync_main_counselors(self.db); self.db.commit()
        update_assignment(self.main.id, AssignmentUpdate(counselor_user_id=self.ben.id), self.admin, self.db)
        self.assertEqual(self.lead.assigned_to_user_id, self.ben.id)
        self.assertEqual(get_accessible_lead(self.db, self.lead.id, self.ben).id, self.lead.id)
        with self.assertRaises(HTTPException): get_accessible_lead(self.db, self.lead.id, self.alex)
        update_assignment(self.main.id, AssignmentUpdate(counselor_user_id=None), self.admin, self.db)
        self.assertIsNone(self.lead.assigned_to_user_id)
        self.assertIsNone(self.lead.assigned_at)
        self.assertFalse(self.lead.counselor_from_main)

    def test_unmatched_manual_owner_is_preserved_and_removed_match_is_cleared(self):
        other = Customer(primary_name="Other")
        self.db.add(other); self.db.flush()
        manual = Lead(customer_id=other.id, opportunity_key="IGC", target_code="IGC", assigned_to_user_id=self.ben.id)
        self.db.add(manual)
        sync_main_counselors(self.db); self.db.commit()
        self.db.delete(self.main)
        sync_main_counselors(self.db); self.db.commit()
        self.assertIsNone(self.lead.assigned_to_user_id)
        self.assertEqual(manual.assigned_to_user_id, self.ben.id)

    def test_latest_assigned_main_record_wins_and_inactive_owner_is_ignored(self):
        newer = MainCrmLead(customer_id=self.customer.id, full_name="Learner", source_category="INFO_EMAIL_LEADS",
                            assigned_to_user_id=self.ben.id, updated_at=datetime(2026, 2, 1))
        self.db.add(newer); self.db.flush()
        sync_main_counselors(self.db)
        self.assertEqual(main_counselors(self.db, [self.customer.id])[self.customer.id]["assigned_to_name"], "Ben")
        self.assertEqual(self.lead.assigned_to_user_id, self.ben.id)
        self.ben.active = False
        sync_main_counselors(self.db)
        self.assertEqual(self.lead.assigned_to_user_id, self.alex.id)

    def test_new_opportunities_inherit_owner_and_counselor_can_open_contact(self):
        course = Course(code="IGC", name="IGC", program_code="IGC")
        self.db.add(course); self.db.flush()
        self.db.add(Learner(learner_number="L1", name="Learner", customer_id=self.customer.id))
        self.db.flush()
        self.db.add(LearnerCourseRecord(learner_number="L1", course_id=course.id, result="PASS",
                                        event_date=date(2026, 1, 1), row_hash="pass"))
        self.db.commit()
        sync_opportunity_leads(self.db)
        leads = self.db.scalars(select(Lead).where(Lead.customer_id == self.customer.id, Lead.is_active.is_(True))).all()
        self.assertGreater(len(leads), 0)
        self.assertTrue(all(lead.assigned_to_user_id == self.alex.id for lead in leads))
        self.assertEqual(get_contact(self.customer.id, self.alex, self.db)["learner"]["assigned_to_name"], "Alex")

    def test_email_or_phone_matching_in_either_upload_order(self):
        # Main CRM first: learner finds the same contact by phone alone.
        matched = resolve_customer(self.db, "Learner", phone="+91 98765 43210")
        self.assertEqual(matched.id, self.customer.id)
        # Learner first: later Main CRM upload finds their contact by email.
        first = resolve_customer(self.db, "First learner", "first@test.com")
        self.db.add(Lead(customer_id=first.id, opportunity_key="IGC", target_code="IGC")); self.db.flush()
        later = resolve_customer(self.db, "Main lead", "FIRST@test.com")
        self.db.add(MainCrmLead(customer_id=later.id, full_name="Main lead", source_category="DIRECT_CALLS", assigned_to_user_id=self.ben.id))
        sync_main_counselors(self.db)
        lead = self.db.scalar(select(Lead).where(Lead.customer_id == first.id))
        self.assertEqual(lead.assigned_to_user_id, self.ben.id)

    def test_owner_lookup_is_two_queries_for_a_page_and_empty_page_needs_none(self):
        statements = []
        def capture(*args): statements.append(args[2])
        # Resolve ids before recording queries so expired ORM attributes do not count.
        ids = [self.customer.id] * 50
        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            self.assertEqual(main_counselors(self.db, []), {})
            self.assertEqual(len(statements), 0)
            main_counselors(self.db, ids)
            self.assertEqual(len(statements), 2)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)


if __name__ == "__main__":
    unittest.main()
