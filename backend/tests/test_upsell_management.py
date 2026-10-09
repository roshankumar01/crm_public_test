import unittest
from datetime import date
from io import BytesIO

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (Course, Customer, Lead, Learner, LearnerCourseRecord, LearnerCourseCategory,
    LearnerCourseMapping, LearnerCourseSubcategory, LearnersCrmEnrollment, LearnersCrmProfile,
    MainCrmLead, UpsellCourseActivity, UpsellCourseCase, UpsellInfoEdit, User)
from app.routers.upsell_management import (ActivityInput, CourseChoice, InfoEdit, CaseStatus,
    choose_course, convert_course, ConversionInput, edit_activity, edit_info, management, mismatch, save_activity, case_status)
from app.routers.main_crm import LeadEditPayload, update_details
from app.services.customer_lifecycle import customer_lifecycle
from app.services.lead_analytics import build_lead_analytics
from app.services.lead_workflow import mark_opportunities_dirty, sync_opportunity_leads
from app.services.opportunities import get_all_opportunities
from app.services.upsell_management import preserve_legacy_conversions
from app.routers.upsell_management import contact_history, export_mismatch
from app.routers.leads import StatusUpdate, update_status
from app.routers.leads import get_lead
from app.routers.learners import get_contacts


class UpsellManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine); self.db = Session(self.engine)
        self.admin = User(username="admin", display_name="Admin", password_hash="x", role="ADMIN", active=True)
        self.owner = User(username="owner", display_name="Counselor", password_hash="x", role="COUNSELOR", active=True)
        self.other = User(username="other", display_name="Other", password_hash="x", role="COUNSELOR", active=True)
        self.customer = Customer(primary_name="Person", primary_email="person@test.com")
        self.category = LearnerCourseCategory(name="Safety", normalized_name="safety")
        self.db.add_all([self.admin, self.owner, self.other, self.customer, self.category]); self.db.flush()
        self.igc_sub = LearnerCourseSubcategory(category_id=self.category.id, name="IGC", normalized_name="igc")
        self.psm_sub = LearnerCourseSubcategory(category_id=self.category.id, name="Nebosh PSM", normalized_name="nebosh psm")
        self.db.add_all([self.igc_sub, self.psm_sub]); self.db.flush()
        self.igc = LearnerCourseMapping(category_id=self.category.id, subcategory_id=self.igc_sub.id,
                                       course_name="IGC Version 1", normalized_name="igc version 1")
        self.igc2 = LearnerCourseMapping(category_id=self.category.id, subcategory_id=self.igc_sub.id,
                                        course_name="IGC Version 2", normalized_name="igc version 2")
        self.psm = LearnerCourseMapping(category_id=self.category.id, subcategory_id=self.psm_sub.id,
                                       course_name="PSM", normalized_name="psm")
        self.main = MainCrmLead(customer_id=self.customer.id, full_name="Main Person", email="main@test.com",
                               source_category="DIRECT_CALLS", course="IGC", assigned_to_user_id=self.owner.id)
        self.lead = Lead(customer_id=self.customer.id, opportunity_key="IGC", target_code="IGC",
                         assigned_to_user_id=self.owner.id, status="NEW")
        self.db.add_all([self.igc, self.igc2, self.psm, self.main, self.lead]); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def choose(self, mapping=None):
        return choose_course(self.lead.id, CourseChoice(mapping_id=(mapping or self.igc).id), self.owner, self.db)["case_id"]

    def test_one_way_info_edits_and_main_updates(self):
        edit_info(self.lead.id, InfoEdit(full_name="Upsell Person", email="local@test.com", age=42), self.owner, self.db)
        self.assertEqual(self.main.full_name, "Main Person")
        self.assertEqual(self.customer.primary_email, "person@test.com")
        self.assertEqual(management(self.lead.id, self.owner, self.db, 1)["info"]["full_name"], "Upsell Person")
        update_details(self.main.id, LeadEditPayload(full_name="Main changed", email="newmain@test.com"), self.admin, self.db)
        info = management(self.lead.id, self.owner, self.db, 1)["info"]
        self.assertEqual(info["full_name"], "Main changed")
        self.assertEqual(info["email"], "newmain@test.com")
        self.assertEqual(info["age"], 42)

    def test_upsell_personal_edits_are_used_in_upsell_lists_and_profiles(self):
        self.choose()
        edit_info(self.lead.id, InfoEdit(full_name="Local name", email="local@test.com"), self.owner, self.db)
        self.assertEqual(get_lead(self.lead.id, self.owner, self.db)["learner"]["name"], "Local name")
        profile = LearnersCrmProfile(customer_id=self.customer.id, learner_name="Person", email_id="person@test.com", normalized_email="person@test.com")
        self.db.add(profile); self.db.commit()
        contacts = get_contacts(search=None, admin_user=self.admin, db=self.db, page=1)
        self.assertEqual(contacts["items"][0]["name"], "Local name")
        self.assertEqual(self.main.email, "main@test.com")

    def test_same_subcategory_registration_for_another_person_does_not_match(self):
        first = self.choose(); convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        other = Customer(primary_name="Someone else")
        self.db.add(other); self.db.flush()
        profile = LearnersCrmProfile(customer_id=other.id, learner_name="Someone else", email_id="else@test.com", normalized_email="else@test.com")
        self.db.add(profile); self.db.flush()
        self.db.add(LearnersCrmEnrollment(enrolment_id="OTHER", learner_id=profile.id, course_name="IGC Version 1")); self.db.commit()
        self.assertEqual(mismatch("all", 1, self.admin, self.db)["total"], 1)

    def test_last_ten_info_edits_only_with_before_after_and_actor(self):
        for i in range(12): edit_info(self.lead.id, InfoEdit(full_name=f"Edit {i}"), self.owner, self.db)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(UpsellInfoEdit)), 10)
        edits = management(self.lead.id, self.owner, self.db, 1)["changes"]
        latest = edits[0]["raw_data"]
        self.assertEqual(latest["changes"]["full_name"], {"from": "Edit 10", "to": "Edit 11"})
        self.assertEqual(latest["edited_by"]["name"], "Counselor")
        self.assertFalse(any("Edit 11" in str(event) for event in customer_lifecycle(self.db, self.customer.id, self.admin)["events"]))

    def test_course_history_is_isolated_and_editable_until_converted(self):
        first = self.choose(); second = self.choose(self.psm)
        save_activity(self.lead.id, first, ActivityInput(notes="IGC conversation"), self.owner, self.db)
        save_activity(self.lead.id, second, ActivityInput(notes="PSM conversation"), self.owner, self.db)
        row = self.db.scalar(select(UpsellCourseActivity).where(UpsellCourseActivity.case_id == first))
        edit_activity(self.lead.id, first, row.id, ActivityInput(notes="IGC edited"), self.owner, self.db)
        cases = {c["id"]: c for c in management(self.lead.id, self.owner, self.db, 1)["cases"]}
        self.assertEqual(cases[first]["activities"][0]["notes"], "IGC edited")
        self.assertEqual(cases[second]["activities"][0]["notes"], "PSM conversation")
        self.assertEqual(cases[first]["activities"][0]["edited_by"], "Counselor")
        convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        with self.assertRaises(HTTPException): edit_activity(self.lead.id, first, row.id, ActivityInput(notes="change"), self.owner, self.db)

    def test_conversion_is_idempotent_and_not_a_registration_or_main_status_edit(self):
        first = self.choose()
        convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        timestamp = self.db.get(UpsellCourseCase, first).converted_at
        convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        self.assertEqual(self.db.get(UpsellCourseCase, first).converted_at, timestamp)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(UpsellCourseCase)), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(LearnersCrmEnrollment)), 0)
        self.assertEqual(self.main.status_of_lead, "NEW")
        events = customer_lifecycle(self.db, self.customer.id, self.admin)["events"]
        conversions = [e for e in events if e["key"].startswith("course-conversion")]
        self.assertEqual(len(conversions), 0)
        self.assertFalse(any(e["kind"] == "ENROLMENT" for e in events))

    def test_mismatch_matches_same_person_and_subcategory_across_course_versions(self):
        first = self.choose(); convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        self.assertEqual(mismatch("all", 1, self.admin, self.db)["total"], 1)
        profile = LearnersCrmProfile(customer_id=self.customer.id, learner_name="Person", email_id="person@test.com", normalized_email="person@test.com")
        self.db.add(profile); self.db.flush()
        enrolment = LearnersCrmEnrollment(enrolment_id="E1", learner_id=profile.id, course_name="PSM")
        self.db.add(enrolment); self.db.commit()
        self.assertEqual(mismatch("all", 1, self.admin, self.db)["total"], 1)
        enrolment.course_name = " IGC   Version 2 "; self.db.commit()
        self.assertEqual(mismatch("all", 1, self.admin, self.db)["total"], 0)

    def test_result_registration_only_matches_the_correct_subcategory(self):
        first = self.choose(self.psm); convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        learner = Learner(learner_number="L1", name="Person", customer_id=self.customer.id)
        course = Course(code="IGC", name="IGC", program_code="IGC")
        self.db.add_all([learner, course]); self.db.flush()
        self.db.add(LearnerCourseRecord(learner_number="L1", course_id=course.id, event_date=date(2026, 1, 1), result="REFER", row_hash="result"))
        self.db.commit()
        self.assertEqual(mismatch("all", 1, self.admin, self.db)["total"], 1)
        second = self.choose(self.igc); convert_course(self.lead.id, second, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        self.assertEqual(mismatch("all", 1, self.admin, self.db)["total"], 1)

    def test_conversions_survive_next_course_and_recommendation_refresh_in_analytics(self):
        first = self.choose(); convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        second = self.choose(self.psm)
        self.assertEqual(self.lead.status, "NEW")
        summary = build_lead_analytics(self.db, self.admin)["summary"]
        self.assertEqual((summary["converted"], summary["new"]), (1, 1))
        convert_course(self.lead.id, second, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        mark_opportunities_dirty(self.db); self.db.commit(); sync_opportunity_leads(self.db)
        self.assertEqual(build_lead_analytics(self.db, self.admin)["summary"]["converted"], 2)
        self.assertEqual(get_all_opportunities(self.db, self.admin)["summary"]["converted"], 2)

    def test_access_and_cross_course_activity_validation(self):
        first = self.choose(); second = self.choose(self.psm)
        with self.assertRaises(HTTPException): choose_course(self.lead.id, CourseChoice(mapping_id=self.igc.id), self.other, self.db)
        save_activity(self.lead.id, first, ActivityInput(notes="First course"), self.owner, self.db)
        row = self.db.scalar(select(UpsellCourseActivity).where(UpsellCourseActivity.case_id == first))
        with self.assertRaises(HTTPException): edit_activity(self.lead.id, second, row.id, ActivityInput(notes="Wrong course"), self.owner, self.db)
        with self.assertRaises(HTTPException): case_status(self.lead.id, first, CaseStatus(status="CONVERTED"), self.owner, self.db)
        convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        self.assertEqual(mismatch("all", 1, self.other, self.db)["total"], 0)

    def test_pipeline_status_updates_the_selected_course_panel(self):
        first = self.choose(); second = self.choose(self.psm)
        update_status(self.lead.id, StatusUpdate(status="IN_CONTACT", note="Discussed course options"), self.owner, self.db)
        self.assertEqual(self.db.get(UpsellCourseCase, first).status, "NEW")
        self.assertEqual(self.db.get(UpsellCourseCase, second).status, "IN_CONTACT")
        with self.assertRaises(HTTPException): update_status(self.lead.id, StatusUpdate(status="CONVERTED"), self.owner, self.db)
        convert_course(self.lead.id, second, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        self.assertIsNone(self.db.get(UpsellCourseCase, second).current_slot)
        data = management(self.lead.id, self.owner, self.db, 1)
        self.assertFalse(any(c["is_current"] for c in data["cases"]))

    def test_contact_history_is_paged_without_dropping_older_contacts(self):
        first = self.choose()
        self.db.add_all(UpsellCourseActivity(case_id=first, user_id=self.owner.id, activity_type="NOTE", notes=f"Contact {i}") for i in range(65))
        self.db.commit()
        case = management(self.lead.id, self.owner, self.db, 1)["cases"][0]
        self.assertEqual((len(case["activities"]), case["activity_count"]), (50, 65))
        older = contact_history(self.lead.id, first, 2, self.owner, self.db)
        self.assertEqual(len(older["items"]), 15)
        self.assertFalse({a["id"] for a in case["activities"]} & {a["id"] for a in older["items"]})

    def test_legacy_conversion_keeps_subcategory_without_inventing_variant(self):
        self.lead.status = "CONVERTED"; self.db.commit()
        preserve_legacy_conversions(self.db); self.db.commit()
        preserve_legacy_conversions(self.db); self.db.commit()
        case = self.db.scalar(select(UpsellCourseCase))
        self.assertEqual(case.normalized_subcategory, "igc")
        self.assertIsNone(case.mapping_id)
        self.assertIn("not recorded", case.course_name)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(UpsellCourseCase)), 1)

    def test_mismatch_export_is_readable_excel_with_counselor_and_course(self):
        import asyncio
        first = self.choose(); convert_course(self.lead.id, first, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        response = export_mismatch("all", self.admin, self.db)
        async def read():
            return b"".join([chunk async for chunk in response.body_iterator])
        frame = pd.read_excel(BytesIO(asyncio.run(read())))
        self.assertEqual(frame.iloc[0]["Subcategory"], "IGC")
        self.assertEqual(frame.iloc[0]["Counselor"], "Counselor")


if __name__ == "__main__": unittest.main()
