import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Course, Lead, Learner, LearnerCourseRecord, MainCrmLead, User
from app.routers import company_dashboard


class CompanyDashboardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(username="admin", display_name="Admin", password_hash="x", role="ADMIN", active=True)
        self.counselor = User(username="seller", display_name="Alex", password_hash="x", role="COUNSELOR", active=True)
        self.db.add_all([self.admin, self.counselor])
        self.db.flush()
        self.db.add_all([
            MainCrmLead(full_name="A", source_category="INFO_EMAIL_LEADS", source="Website", course="IGC", status_of_lead="CONVERTED", assigned_to_user_id=self.counselor.id),
            MainCrmLead(full_name="B", source_category="DIRECT_CALLS", source="Phone", course="IDIP", status_of_lead="NEW", assigned_to_user_id=self.counselor.id),
            MainCrmLead(full_name="C", source_category="INFO_EMAIL_LEADS", source="Website", course="IGC", status_of_lead="CONVERTED", assigned_to_user_id=self.counselor.id),
            MainCrmLead(full_name="D", source_category="DIRECT_CALLS", source="Phone", course="IDIP", status_of_lead="CONVERTED"),
            Lead(opportunity_key="IGC", target_code="IGC", status="CONVERTED", is_active=True),
            Lead(opportunity_key="ID1", target_code="ID1", status="NEW", is_active=True),
        ])
        self.db.add_all([Learner(learner_number="L1", name="Learner One"), Learner(learner_number="L2", name="Learner Two")])
        courses = [Course(code=code, name=code, program_code="IGC" if code == "IGC" else "IDP") for code in ("IGC", "ID1", "ID2", "ID3")]
        self.db.add_all(courses)
        self.db.flush()
        by_code = {course.code: course.id for course in courses}
        today = date.today()
        for index, (number, code, result, event_date) in enumerate([
            ("L1", "IGC", "PASS", today - timedelta(days=2)),
            ("L1", "IGC", "FAIL", today - timedelta(days=1)),
            ("L2", "IGC", "PASS", today),
            ("L1", "ID1", "PASS", today),
            ("L1", "ID2", "PENDING", today),
            ("L1", "ID3", "PASS", today),
        ]):
            self.db.add(LearnerCourseRecord(learner_number=number, course_id=by_code[code],
                                            event_date=event_date, result=result, row_hash=f"hash-{index}"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_overview_and_sales_use_grouped_lead_counts(self):
        with patch.object(company_dashboard, "sync_opportunity_leads"):
            overview = company_dashboard.overview("all", self.admin, self.db)
        self.assertEqual(overview["cards"]["new_leads"], 1)
        self.assertEqual(overview["cards"]["converted_leads"], 3)
        self.assertEqual(overview["cards"]["upsell_conversion_rate"], 50)
        self.assertEqual({row["name"]: row["count"] for row in overview["top_sources"]}, {"Phone": 2, "Website": 2})
        self.assertEqual(sum(point["leads"] for point in overview["trend"]), 4)

        sales = company_dashboard.sales("all", self.admin, self.db)
        self.assertEqual(sales["cards"]["converted"], 3)
        self.assertEqual(sales["cards"]["unassigned"], 1)
        alex = next(row for row in sales["decomposition"] if row["name"] == "Alex")
        self.assertEqual(alex["count"], 2)
        self.assertEqual(company_dashboard.sales_courses(self.counselor.id, "all", self.admin, self.db),
                         [{"name": "IGC", "count": 2}])
        self.assertEqual(company_dashboard.sales_sources("IGC", self.counselor.id, "all", self.admin, self.db),
                         [{"name": "Website", "count": 2}])

    def test_custom_date_range_filters_all_dashboard_sections(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        for lead in self.db.query(MainCrmLead).all():
            lead.created_at = datetime.combine(today, datetime.min.time())
        self.db.add(MainCrmLead(full_name="Recent", source_category="DIRECT_CALLS", source="Call",
                                course="IGC", status_of_lead="CONVERTED", assigned_to_user_id=self.counselor.id,
                                created_at=datetime.combine(yesterday, datetime.min.time())))
        self.db.commit()
        with patch.object(company_dashboard, "sync_opportunity_leads"):
            overview = company_dashboard.overview("all", self.admin, self.db, yesterday, yesterday)
        self.assertEqual(overview["cards"]["converted_leads"], 1)
        self.assertEqual(sum(point["leads"] for point in overview["trend"]), 1)
        self.assertEqual(company_dashboard.sales("all", self.admin, self.db, yesterday, yesterday)["cards"]["converted"], 1)
        self.assertEqual(company_dashboard.sales_courses(self.counselor.id, "all", self.admin, self.db, yesterday, yesterday),
                         [{"name": "IGC", "count": 1}])
        self.assertEqual(company_dashboard.dinesh("all", self.admin, self.db, yesterday, yesterday)["cards"]["result_rows"], 1)

    def test_dinesh_uses_latest_result_per_learner_and_unit(self):
        data = company_dashboard.dinesh("all", self.admin, self.db)
        self.assertEqual(data["igc"]["learners"], 2)
        self.assertEqual(data["igc"]["pass"], 1)
        self.assertEqual(data["igc"]["fail"], 1)
        self.assertEqual(data["cards"]["result_rows"], 6)
        self.assertEqual(data["idip_progression"], {"one_unit": 1, "two_units": 1, "three_units": 0})


if __name__ == "__main__":
    unittest.main()
