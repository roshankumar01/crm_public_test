import unittest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.database import Base
from app.models import CounselorAction, LeadActivity, MainCrmActivity, MainCrmLead, UpsellCourseActivity, UpsellCourseCase, User
from app.routers.main_crm import StatusUpdate as MainStatus, LeadNotePayload, add_note, update_status as update_main
from app.routers.leads import StatusUpdate as UpsellStatus, update_status as update_upsell
from app.routers.upsell_management import ActivityInput, CaseStatus, ConversionInput, case_status, convert_course, edit_activity, save_activity
from app.services.data_reset import clear_crm_data
import test_upsell_management as fixtures


class MainCounselorActivityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine, "connect")
        def keys(connection, _): connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine); self.db = Session(self.engine)
        self.owner = User(username="owner", display_name="Counselor", role="COUNSELOR", password_hash="x", active=True)
        self.other = User(username="other", display_name="Other", role="COUNSELOR", password_hash="x", active=True)
        self.admin = User(username="admin", display_name="Admin", role="ADMIN", password_hash="x", active=True)
        self.db.add_all([self.owner, self.other, self.admin]); self.db.flush()
        self.lead = MainCrmLead(full_name="Person", course="IGC", source="Web enquiry",
            source_category="INFO_EMAIL_LEADS", assigned_to_user_id=self.owner.id, status_of_lead="NEW")
        self.db.add(self.lead); self.db.commit()

    def tearDown(self): self.db.close(); self.engine.dispose()

    def actions(self): return self.db.scalars(select(CounselorAction).order_by(CounselorAction.id)).all()

    def test_status_requires_fresh_note_and_audit_is_atomic(self):
        for value in (None, "  "):
            with self.assertRaises(HTTPException) as error:
                update_main(self.lead.id, MainStatus(status="HOT", note=value), self.owner, self.db)
            self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.lead.status_of_lead, "NEW")
        self.assertEqual(len(self.actions()), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(MainCrmActivity)), 0)
        update_main(self.lead.id, MainStatus(status="HOT", note="Spoke about fees"), self.owner, self.db)
        action = self.actions()[0]
        self.assertEqual((action.action_type, action.before_status, action.after_status), ("STATUS_CHANGE", "NEW", "HOT"))
        self.assertEqual((action.after_note, action.user_id, action.assigned_counselor_id), ("Spoke about fees", self.owner.id, self.owner.id))
        self.assertEqual((action.actor_name, action.assigned_counselor_name), ("Counselor", "Counselor"))
        self.assertEqual((action.course_name, action.source), ("IGC", "Web enquiry"))
        self.assertIsNotNone(action.created_at)
        activity = self.db.scalar(select(MainCrmActivity))
        self.assertEqual(activity.raw_data["actor"]["name"], "Counselor")
        self.assertEqual(activity.notes, "Spoke about fees")
        with self.assertRaises(HTTPException):
            update_main(self.lead.id, MainStatus(status="FOLLOW_UP", note="Spoke about fees"), self.owner, self.db)
        self.assertEqual(self.lead.status_of_lead, "HOT")
        self.assertEqual(len(self.actions()), 1)

    def test_each_new_note_preserves_previous_note_and_actor(self):
        add_note(self.lead.id, LeadNotePayload(note="First call"), self.owner, self.db)
        add_note(self.lead.id, LeadNotePayload(note="Second call"), self.owner, self.db)
        self.assertEqual([(row.before_note, row.after_note) for row in self.actions()],
                         [(None, "First call"), ("First call", "Second call")])
        self.assertEqual(self.lead.notes, "Second call")
        with self.assertRaises(HTTPException): add_note(self.lead.id, LeadNotePayload(note="Second call"), self.owner, self.db)
        self.assertEqual(len(self.actions()), 2)
        update_main(self.lead.id, MainStatus(status="IN_CONTACT", note="Third call"), self.owner, self.db)
        self.assertEqual(self.actions()[-1].before_note, "Second call")
        self.assertEqual(self.actions()[0].after_note, "First call")

    def test_unchanged_status_no_fake_activity_and_counselor_scope(self):
        update_main(self.lead.id, MainStatus(status="NEW", note="No status change"), self.owner, self.db)
        self.assertEqual(len(self.actions()), 0)
        with self.assertRaises(HTTPException) as error:
            update_main(self.lead.id, MainStatus(status="HOT", note="Other note"), self.other, self.db)
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            update_main(self.lead.id, MainStatus(status="HOT"), self.admin, self.db)

    def test_total_reset_clears_activity_facts_but_keeps_users(self):
        add_note(self.lead.id, LeadNotePayload(note="Called"), self.owner, self.db)
        clear_crm_data(self.db); self.db.commit()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CounselorAction)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(User)), 3)


class UpsellCounselorActivityTests(unittest.TestCase):
    setUp = fixtures.UpsellManagementTests.setUp
    tearDown = fixtures.UpsellManagementTests.tearDown
    choose = fixtures.UpsellManagementTests.choose

    def actions(self): return self.db.scalars(select(CounselorAction).order_by(CounselorAction.id)).all()

    def test_pipeline_status_requires_note_for_legacy_and_selected_case(self):
        with self.assertRaises(HTTPException): update_upsell(self.lead.id, UpsellStatus(status="IN_CONTACT"), self.owner, self.db)
        self.assertEqual(self.lead.status, "NEW")
        update_upsell(self.lead.id, UpsellStatus(status="IN_CONTACT", note="Discussed PSM"), self.owner, self.db)
        self.assertEqual(self.actions()[-1].after_note, "Discussed PSM")
        first = self.choose()
        with self.assertRaises(HTTPException): update_upsell(self.lead.id, UpsellStatus(status="REJECTED"), self.owner, self.db)
        update_upsell(self.lead.id, UpsellStatus(status="REJECTED", note="Not ready for IGC"), self.owner, self.db)
        case = self.db.get(UpsellCourseCase, first)
        self.assertEqual(case.status, "REJECTED")
        last = self.actions()[-1]
        self.assertEqual((last.before_status, last.after_status, last.upsell_case_id), ("NEW", "REJECTED", first))
        self.assertEqual(last.user_id, self.owner.id)
        self.assertTrue(self.db.scalar(select(UpsellCourseActivity).where(UpsellCourseActivity.case_id == first)))
        with self.assertRaises(HTTPException):
            case_status(self.lead.id, first, CaseStatus(status="IN_CONTACT", note="Not ready for IGC"), self.owner, self.db)
        self.assertEqual(case.status, "REJECTED")

    def test_each_contact_edit_preserves_old_and_new_note(self):
        first = self.choose()
        save_activity(self.lead.id, first, ActivityInput(notes="First contact"), self.owner, self.db)
        activity = self.db.scalar(select(UpsellCourseActivity).where(UpsellCourseActivity.case_id == first))
        edit_activity(self.lead.id, first, activity.id, ActivityInput(notes="Follow-up detail"), self.owner, self.db)
        self.assertEqual([(a.action_type, a.before_note, a.after_note) for a in self.actions()],
                         [("NOTE", None, "First contact"), ("CONTACT_EDIT", "First contact", "Follow-up detail")])
        edit_activity(self.lead.id, first, activity.id, ActivityInput(notes="Follow-up detail"), self.owner, self.db)
        self.assertEqual(len(self.actions()), 2)
        self.assertEqual(self.actions()[0].after_note, "First contact")

    def test_conversion_needs_fresh_note_and_is_counted_once(self):
        first = self.choose()
        save_activity(self.lead.id, first, ActivityInput(notes="Discussed price"), self.owner, self.db)
        with self.assertRaises(HTTPException): convert_course(self.lead.id, first, self.owner, self.db)
        with self.assertRaises(HTTPException):
            convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Discussed price"))
        self.assertEqual(self.db.get(UpsellCourseCase, first).status, "NEW")
        convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Agreed to enroll"))
        self.assertEqual(self.actions()[-1].after_status, "CONVERTED")
        count = len(self.actions())
        convert_course(self.lead.id, first, self.owner, self.db)
        self.assertEqual(len(self.actions()), count)
        self.assertEqual(self.actions()[-1].course_name, self.igc.course_name)
