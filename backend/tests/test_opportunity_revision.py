import unittest
from datetime import date, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AppSetting, Course, LearnerCourseCategory, LearnerCourseMapping, LearnerCourseRecord, LearnerCourseSubcategory, LearnersCrmEnrollment, LearnersCrmProfile, Lead, User
from app.routers.learners import get_contact, get_contacts
from app.routers.leads import get_tracked_leads
from app.routers.dashboard import dashboard_summary
from app.services.lead_analytics import build_lead_analytics
from app.services.course_rules import build_customer_opportunities
from app.services.lead_workflow import mark_opportunities_dirty, sync_opportunity_leads
from app.services.opportunities import get_all_opportunities
from app.services.importers.common import upsert_learner
from app.services.customer_identity import resolve_customer


class OpportunityRevisionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_mapping(self, course, subcategory):
        category = LearnerCourseCategory(name=subcategory, normalized_name=subcategory.casefold(), display_order=0)
        self.db.add(category)
        self.db.flush()
        sub = LearnerCourseSubcategory(category_id=category.id, name=subcategory, normalized_name=subcategory.casefold(), display_order=0)
        self.db.add(sub)
        self.db.flush()
        self.db.add(LearnerCourseMapping(category_id=category.id, subcategory_id=sub.id, course_name=course, normalized_name=course.casefold()))

    def test_enrolment_cooling_and_igc_pass_change_opportunities(self):
        customer = resolve_customer(self.db, "Ada", "ada@example.com", None)
        profile = LearnersCrmProfile(customer_id=customer.id, learner_name="Ada", email_id="ada@example.com", normalized_email="ada@example.com")
        self.db.add(profile)
        self.db.flush()
        self.add_mapping("Foundation", "Diploma")
        self.add_mapping("General Certificate", "IGC")
        self.db.add(LearnersCrmEnrollment(enrolment_id="E-1", learner_id=profile.id, course_name="Foundation", enrolment_date=date(2024, 1, 1)))
        self.db.commit()

        sync_opportunity_leads(self.db)
        self.assertEqual({lead.opportunity_key for lead in self.db.scalars(select(Lead).where(Lead.is_active.is_(True)))}, {"IGC", "PSM", "INCIDENT"})
        initial_summary = get_all_opportunities(self.db)
        self.assertEqual(initial_summary["summary"]["unique_learners"], 1)
        self.assertEqual({item["key"]: item["count"] for item in initial_summary["sections"]}["PSM_2"], 1)
        self.assertEqual({item["key"]: item["count"] for item in initial_summary["sections"]}["INCIDENT_3"], 0)

        self.db.add(LearnersCrmEnrollment(enrolment_id="E-2", learner_id=profile.id, course_name="General Certificate", enrolment_date=date(2024, 3, 1), completion_status="Completed", completion_date=date(2024, 5, 1)))
        mark_opportunities_dirty(self.db)
        self.db.commit()
        sync_opportunity_leads(self.db)
        active = {lead.opportunity_key: lead for lead in self.db.scalars(select(Lead).where(Lead.is_active.is_(True)))}
        self.assertEqual(set(active), {"PSM", "INCIDENT", "IDP_ENTRY"})
        self.assertEqual(active["PSM"].stage, 3)
        stage_summary = get_all_opportunities(self.db)
        stage_counts = {item["key"]: item["count"] for item in stage_summary["sections"]}
        self.assertEqual((stage_counts["PSM_2"], stage_counts["PSM_3"], stage_counts["INCIDENT_2"], stage_counts["INCIDENT_3"]), (0, 1, 0, 1))
        board = upsert_learner(self.db, "L-1", "Ada", None, None, "ada@example.com", date(2024, 5, 1))
        course = Course(code="IGC", name="IGC", program_code="IGC")
        self.db.add(course)
        self.db.flush()
        self.db.add(LearnerCourseRecord(learner_number=board.learner_number, course_id=course.id,
                                        event_date=date(2024, 5, 1), result="PASS", event_type="COURSE_RESULT", row_hash="a" * 64))
        mark_opportunities_dirty(self.db)
        self.db.commit()
        sync_opportunity_leads(self.db)
        self.assertIsNone(self.db.get(Lead, active["PSM"].id).learner_number)
        self.assertEqual(self.db.get(Lead, active["IDP_ENTRY"].id).learner_number, "L-1")
        admin = User(username="admin", display_name="Admin", password_hash="x", role="ADMIN", active=True)
        self.db.add(admin)
        self.db.commit()
        page = get_tracked_leads(1, 1, True, "PSM_3", None, None, None, "waiting", "desc", admin, self.db)
        self.assertEqual(page["total"], 1)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["stage"], 3)
        analytics = build_lead_analytics(self.db, admin)
        self.assertEqual(analytics["summary"]["total_leads"], 3)
        self.assertIn("PSM_3", {item["section_key"] for item in analytics["target_breakdown"]})
        self.assertEqual(dashboard_summary(admin, self.db)["total_learners"], 1)
        self.assertEqual(get_contacts(None, admin, self.db, 1)["items"][0]["customer_id"], customer.id)
        detail = get_contact(customer.id, admin, self.db)
        self.assertEqual({item["code"] for item in detail["recommendations"]}, {"PSM", "INCIDENT", "IDP"})
        self.assertEqual(len(detail["timeline"]), 3)

    def test_cooling_and_idip_pass(self):
        class Enrollment:
            def __init__(self, name, enrolled, status=None):
                self.course_name = name
                self.enrolment_date = enrolled
                self.completion_status = status
                self.completion_date = enrolled if status else None
        mapping = {"foundation": {"sub_category": "Diploma"}, "idip 1": {"sub_category": "IDIP -1"}}
        foundation = Enrollment("Foundation", date(2025, 1, 1))
        self.assertEqual(build_customer_opportunities([foundation], [], mapping, 60, date(2025, 2, 1)), [])
        self.assertEqual({item["key"] for item in build_customer_opportunities([foundation], [], mapping, 60, date(2025, 3, 2))}, {"IGC", "PSM", "INCIDENT"})
        unit = Enrollment("IDIP 1", date(2025, 1, 1))
        self.assertEqual(build_customer_opportunities([unit], [], mapping, 60, date(2025, 3, 2)), [])
        unit.completion_status = "Completed"
        unit.completion_date = date(2025, 2, 1)
        self.assertEqual({item["key"] for item in build_customer_opportunities([unit], [], mapping, 60, date(2025, 3, 2))}, {"ID2", "ID3"})

    def test_stage_three_excludes_courses_already_enrolled(self):
        class Enrollment:
            def __init__(self, name, status=None):
                self.course_name = name
                self.enrolment_date = date(2024, 1, 1)
                self.completion_status = status
                self.completion_date = date(2024, 3, 1) if status else None

        mapping = {
            "igc course": {"sub_category": "IGC"},
            "psm course": {"sub_category": "Nebosh PSM"},
        }
        rows = [Enrollment("IGC Course", "Completed"), Enrollment("PSM Course")]
        self.assertEqual({item["key"] for item in build_customer_opportunities(rows, [], mapping, 60, date(2024, 4, 1))}, {"INCIDENT", "IDP_ENTRY"})

    def test_refresh_waits_for_next_cooling_boundary(self):
        customer = resolve_customer(self.db, "Future", "future@example.com", None)
        profile = LearnersCrmProfile(customer_id=customer.id, learner_name="Future", email_id="future@example.com", normalized_email="future@example.com")
        self.db.add(profile)
        self.db.flush()
        self.add_mapping("Future Foundation", "Diploma")
        start = date.today() + timedelta(days=5)
        self.db.add(LearnersCrmEnrollment(enrolment_id="F-1", learner_id=profile.id, course_name="Future Foundation", enrolment_date=start))
        self.db.commit()
        sync_opportunity_leads(self.db)
        self.assertEqual(self.db.get(AppSetting, "opportunity_next_refresh_date").value, (start + timedelta(days=60)).isoformat())
        with patch("app.services.lead_workflow.build_customer_opportunities", side_effect=AssertionError("Rebuilt too early")):
            sync_opportunity_leads(self.db)


if __name__ == "__main__":
    unittest.main()
