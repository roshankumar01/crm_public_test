import unittest
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Course, Customer, Lead, Learner, LearnerCourseRecord, LearnersCrmProfile
from app.services.customer_identity import resolve_customer
from app.services.importers.common import upsert_learner
from app.services.lead_workflow import sync_opportunity_leads


class CustomerMatchingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_same_board_number_links_igc_and_idip_despite_changed_contact(self):
        igc = upsert_learner(self.db, "L-100", "Ada", None, "1112223333", "old@example.com", date(2025, 1, 1))
        original_id = igc.customer_id
        other = resolve_customer(self.db, "Ada", "new@example.com", None)
        self.db.add(LearnersCrmProfile(customer_id=other.id, learner_name="Ada", email_id="new@example.com", normalized_email="new@example.com"))
        self.db.commit()

        idip = upsert_learner(self.db, "L-100", "Ada", None, None, "new@example.com", date(2025, 6, 1))
        self.db.commit()
        self.assertEqual(idip.customer_id, original_id)
        self.assertEqual(self.db.scalar(select(LearnersCrmProfile.customer_id)), original_id)
        self.assertEqual(self.db.scalar(select(Customer.id).where(Customer.primary_email == "new@example.com")), original_id)

    def test_other_courses_match_email_or_phone_without_learner_number(self):
        board = upsert_learner(self.db, "L-200", "Ben", None, "9876543210", "ben@example.com", date(2025, 1, 1))
        by_email = resolve_customer(self.db, "Ben", "ben@example.com", None)
        by_phone = resolve_customer(self.db, "Ben", None, "+91 9876543210")
        self.assertEqual(board.customer_id, by_email.id)
        self.assertEqual(board.customer_id, by_phone.id)
        self.assertEqual(len(self.db.scalars(select(Learner)).all()), 1)

    def test_board_results_do_not_join_different_learner_numbers(self):
        igc_learner = upsert_learner(self.db, "IGC-1", "Ada", None, None, "ada@example.com", date(2025, 1, 1))
        idip_learner = upsert_learner(self.db, "IDIP-2", "Ada", None, None, "ada@example.com", date(2025, 2, 1))
        igc = Course(code="IGC", name="IGC", program_code="IGC")
        id1 = Course(code="ID1", name="IDIP 1", program_code="IDP")
        self.db.add_all([igc, id1])
        self.db.flush()
        self.db.add_all([
            LearnerCourseRecord(learner_number=igc_learner.learner_number, course_id=igc.id,
                                event_date=date(2025, 1, 1), result="PASS", row_hash="a" * 64),
            LearnerCourseRecord(learner_number=idip_learner.learner_number, course_id=id1.id,
                                event_date=date(2025, 2, 1), enrollment_status="ENROLLED", row_hash="b" * 64),
        ])
        self.db.commit()
        sync_opportunity_leads(self.db)
        leads = {lead.opportunity_key: lead for lead in self.db.scalars(select(Lead).where(Lead.is_active.is_(True)))}
        self.assertEqual(leads["IDP_ENTRY"].learner_number, "IGC-1")
        self.assertNotIn("ID2", leads)


if __name__ == "__main__":
    unittest.main()
