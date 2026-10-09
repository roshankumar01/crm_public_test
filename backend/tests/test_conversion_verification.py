import unittest
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from app.models import (ConversionVerification, LearnersCrmEnrollment, LearnersCrmProfile, Learner, Course, LearnerCourseRecord,
    MainCrmLead, UpsellCourseCase, LearnerCourseCategory, LearnerCourseSubcategory, LearnerCourseMapping, Lead)
from app.routers.main_crm import converted_mismatch, verify_main_mismatch, export_converted_mismatch
from app.routers.upsell_management import mismatch, verify_upsell_mismatch, convert_course, export_mismatch, ConversionInput
from app.services.conversion_verification import verification_payloads
from app.services.customer_lifecycle import customer_lifecycle
from app.services.lead_workflow import mark_opportunities_dirty, sync_opportunity_leads
import test_upsell_management as fixtures


class ConversionVerificationTests(unittest.TestCase):
    setUp = fixtures.UpsellManagementTests.setUp
    tearDown = fixtures.UpsellManagementTests.tearDown
    choose = fixtures.UpsellManagementTests.choose

    def converted_case(self):
        id = self.choose()
        convert_course(self.lead.id, id, self.owner, self.db, ConversionInput(note="Conversion confirmed after discussion"))
        return self.db.get(UpsellCourseCase, id)

    def converted_main(self):
        self.main.status_of_lead = "CONVERTED"
        self.db.commit()
        return self.main

    def upload(self, course="IGC Version 2", status="Not Completed"):
        profile = LearnersCrmProfile(customer_id=self.customer.id, learner_name="Person", email_id="person@test.com", normalized_email="person@test.com")
        self.db.add(profile); self.db.flush()
        enrolment = LearnersCrmEnrollment(enrolment_id="E1", learner_id=profile.id, course_name=course, completion_status=status,
            enrolment_date=date.today(), completion_date=date.today() if status == "Completed" else None)
        self.db.add(enrolment); self.db.commit()
        return profile, enrolment

    def check(self, model, id):
        return verification_payloads(self.db, model, [id])[id]

    def test_admin_only_and_converted_only(self):
        item = self.converted_case()
        for fn, id in [(verify_upsell_mismatch, item.id), (verify_main_mismatch, self.main.id)]:
            with self.assertRaises(HTTPException) as error: fn(id, self.owner, self.db)
            self.assertEqual(error.exception.status_code, 403)
        with self.assertRaises(HTTPException) as error: verify_main_mismatch(self.main.id, self.admin, self.db)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ConversionVerification)), 0)

    def test_main_person_only_and_upsell_course_specific(self):
        item = self.converted_case(); self.converted_main(); self.upload("PSM")
        self.assertTrue(self.check(MainCrmLead, self.main.id)["verified"])
        self.assertFalse(self.check(UpsellCourseCase, item.id)["verified"])
        self.assertEqual(converted_mismatch("all", self.admin, self.db)["total"], 0)
        self.assertEqual(mismatch("all", 1, self.admin, self.db)["total"], 1)

    def test_uploaded_match_is_dynamic_and_does_not_create_admin_audit(self):
        item = self.converted_case(); self.converted_main()
        profile, enrolment = self.upload()
        for model, id in [(MainCrmLead, self.main.id), (UpsellCourseCase, item.id)]:
            self.assertTrue(self.check(model, id)["verified"])
            self.assertEqual(self.check(model, id)["verification_source"], "Uploaded registration")
        self.db.delete(enrolment); self.db.delete(profile); self.db.commit()
        self.assertFalse(self.check(MainCrmLead, self.main.id)["verified"])
        self.assertFalse(self.check(UpsellCourseCase, item.id)["verified"])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ConversionVerification)), 0)

    def test_admin_verification_is_idempotent_enrolment_never_pass(self):
        item = self.converted_case()
        before = customer_lifecycle(self.db, self.customer.id, self.admin)["events"]
        self.assertFalse(any(e["kind"] in {"ENROLMENT", "COMPLETION"} for e in before))
        result = verify_upsell_mismatch(item.id, self.admin, self.db)
        stamp = result["verified_at"]
        repeated = verify_upsell_mismatch(item.id, self.admin, self.db)
        self.assertEqual(repeated["verified_at"], stamp)
        self.assertEqual(result["verified_by"], "Admin")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ConversionVerification)), 1)
        events = customer_lifecycle(self.db, self.customer.id, self.admin)["events"]
        enrolments = [e for e in events if e["kind"] == "ENROLMENT"]
        self.assertEqual(len(enrolments), 1)
        self.assertEqual(enrolments[0]["status"], "Enrolled")
        self.assertTrue(enrolments[0]["verified"])
        self.assertEqual(enrolments[0]["fields"]["verified_by"], "Admin")
        self.assertFalse(any(e["kind"] == "COMPLETION" or e["status"] == "PASS" for e in events))
        self.assertEqual(self.main.status_of_lead, "NEW")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(LearnersCrmEnrollment)), 0)
        sync_opportunity_leads(self.db)
        self.assertFalse(self.db.scalar(select(Lead.id).where(Lead.stage == 3)))

    def test_upload_replaces_virtual_enrolment_and_retains_admin_audit(self):
        item = self.converted_case(); verify_upsell_mismatch(item.id, self.admin, self.db)
        profile, enrolment = self.upload(status="Completed")
        events = customer_lifecycle(self.db, self.customer.id, self.admin)["events"]
        self.assertEqual(len([e for e in events if e["kind"] == "ENROLMENT"]), 1)
        self.assertTrue(any(e["kind"] == "COMPLETION" for e in events))
        self.db.delete(enrolment); self.db.delete(profile); self.db.commit()
        self.assertTrue(self.check(UpsellCourseCase, item.id)["verified"])
        self.assertEqual(self.check(UpsellCourseCase, item.id)["verification_source"], "Admin verified enrolment")
        self.assertFalse(any(e["kind"] == "COMPLETION" for e in customer_lifecycle(self.db, self.customer.id, self.admin)["events"]))

    def test_verified_filters_and_exports_include_actor_and_owner(self):
        item = self.converted_case(); self.converted_main()
        verify_main_mismatch(self.main.id, self.admin, self.db); verify_upsell_mismatch(item.id, self.admin, self.db)
        self.assertEqual(converted_mismatch("all", self.admin, self.db)["total"], 0)
        self.assertEqual(mismatch("all", 1, self.admin, self.db)["total"], 0)
        self.assertEqual(converted_mismatch("all", self.admin, self.db, 1, "verified")["items"][0]["counselor"], "Counselor")
        self.assertEqual(mismatch("all", 1, self.admin, self.db, "verified")["items"][0]["verified_by"], "Admin")
        self.assertEqual(converted_mismatch("all", self.other, self.db, 1, "all")["total"], 0)
        self.assertEqual(mismatch("all", 1, self.other, self.db, "all")["total"], 0)
        self.assertEqual(export_converted_mismatch("all", self.admin, self.db, "verified").status_code, 200)
        self.assertEqual(export_mismatch("all", self.admin, self.db, "verified").status_code, 200)

    def test_course_edit_invalidates_main_snapshot_and_no_synthetic_enrolment(self):
        self.converted_main(); verify_main_mismatch(self.main.id, self.admin, self.db)
        self.main.course = "PSM"; self.db.commit()
        self.assertFalse(self.check(MainCrmLead, self.main.id)["verified"])
        events = customer_lifecycle(self.db, self.customer.id, self.admin)["events"]
        self.assertFalse(any(e["kind"] == "ENROLMENT" for e in events))
        verify_main_mismatch(self.main.id, self.admin, self.db)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ConversionVerification)), 1)
        self.assertEqual(self.db.scalar(select(ConversionVerification)).course_name, "PSM")

    def test_main_and_upsell_verified_same_subcategory_create_one_enrolment(self):
        item = self.converted_case(); self.converted_main()
        verify_main_mismatch(self.main.id, self.admin, self.db); verify_upsell_mismatch(item.id, self.admin, self.db)
        events = customer_lifecycle(self.db, self.customer.id, self.admin)["events"]
        self.assertEqual(len([e for e in events if e["kind"] == "ENROLMENT"]), 1)

    def test_verified_stage_one_enrolment_obeys_cooling_days(self):
        sub = LearnerCourseSubcategory(category_id=self.category.id, name="Diploma", normalized_name="diploma")
        self.db.add(sub); self.db.flush()
        self.converted_main(); self.main.course = "Diploma"; self.db.commit()
        verify_main_mismatch(self.main.id, self.admin, self.db)
        sync_opportunity_leads(self.db)
        self.assertFalse(self.db.scalar(select(Lead.id).where(Lead.target_code == "PSM")))
        audit = self.db.scalar(select(ConversionVerification)); audit.verified_at = datetime.now(timezone.utc) - timedelta(days=61)
        mark_opportunities_dirty(self.db); self.db.commit(); sync_opportunity_leads(self.db)
        self.assertTrue(self.db.scalar(select(Lead.id).where(Lead.target_code == "PSM", Lead.is_active.is_(True))))
        self.assertFalse(self.db.scalar(select(Lead.id).where(Lead.stage == 3)))

    def test_main_person_match_does_not_invent_recorded_course_enrolment(self):
        self.converted_main(); self.upload("PSM")
        events = customer_lifecycle(self.db, self.customer.id, self.admin)["events"]
        self.assertEqual([e["title"] for e in events if e["kind"] == "ENROLMENT"], ["Enrolled in PSM"])

    def test_main_mismatch_paginates(self):
        self.db.add_all([MainCrmLead(customer_id=self.customer.id, full_name=f"Test {i}", source_category="DIRECT_CALLS", status_of_lead="CONVERTED") for i in range(55)])
        self.db.commit()
        first = converted_mismatch("all", self.admin, self.db, 1)
        second = converted_mismatch("all", self.admin, self.db, 2)
        self.assertEqual(first["total"], 55); self.assertEqual(len(first["items"]), 50)
        self.assertEqual(len(second["items"]), 5)
        self.assertFalse({r["id"] for r in first["items"]} & {r["id"] for r in second["items"]})

    def test_retained_board_contact_after_reset_is_not_registration_evidence(self):
        self.converted_main()
        board = Learner(learner_number="B1", customer_id=self.customer.id, name="Person")
        self.db.add(board); self.db.commit()
        self.assertFalse(self.check(MainCrmLead, self.main.id)["verified"])

    def test_uploaded_board_results_supply_pass_after_admin_enrolment(self):
        item = self.converted_case(); verify_upsell_mismatch(item.id, self.admin, self.db)
        course = Course(code="IGC", name="IGC", program_code="IGC")
        board = Learner(learner_number="B1", customer_id=self.customer.id, name="Person")
        self.db.add_all([course, board]); self.db.flush()
        self.db.add(LearnerCourseRecord(learner_number="B1", course_id=course.id, event_date=date.today(),
            event_type="COURSE_RESULT", result="PASS", row_hash="unique-pass"))
        mark_opportunities_dirty(self.db); self.db.commit(); sync_opportunity_leads(self.db)
        self.assertEqual(self.check(UpsellCourseCase, item.id)["verification_source"], "Uploaded registration")
        events = customer_lifecycle(self.db, self.customer.id, self.admin)["events"]
        self.assertTrue(any(e["kind"] == "RESULT" and e["status"] == "PASS" for e in events))
        self.assertFalse(any(e["key"].startswith("verified-enrolment") for e in events))
        self.assertTrue(self.db.scalar(select(Lead.id).where(Lead.opportunity_key == "IDP_ENTRY", Lead.is_active.is_(True))))
