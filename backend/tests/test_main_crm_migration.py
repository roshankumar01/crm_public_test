import json
import unittest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch

from fastapi import BackgroundTasks, UploadFile
import pandas as pd
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Customer, MainCrmActivity, MainCrmLead, User
from app.routers import main_crm
from app.routers.main_crm import backfill_migration_statuses, get_main_crm_lead, lead_summary, list_leads, migration_progress, migration_status, preview_migration, start_migration, upload_migration


HEADER = "Name,Sales owner,Owner Email,Mobile,Course Name,Age,status of lead,Regions,Last assigned at,First assigned at,Created at,Updated at,Created by,Updated By,Other Phone numbers,Source,Recent note,Email,Email IDs,Message\n"


class MainCrmMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(username="admin", display_name="Admin", password_hash="x", role="ADMIN", active=True)
        self.counselor = User(username="neha", display_name="Neha Mahto", email="neha@example.com", password_hash="x", role="COUNSELOR", active=True)
        self.db.add_all([self.admin, self.counselor])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def file(self, body):
        return UploadFile(file=BytesIO(body.encode()), filename="legacy.csv")

    def test_preview_and_import_mixed_sources(self):
        body = HEADER + (
            "Ada,Neha Mahto,neha@example.com,9876543210,IGC,29,Follow up,India,,2024-01-01,2024-01-02,2024-01-03,Admin,Admin,,Older - Email,Call later,ada@example.com,,Please call\n"
            "Ben,,,9123456780,IDIP,,New,UK,,,,,,,,Inbound Call,,ben@example.com,,\n"
            "Cy,,,9988776655,Online Course,,Converted,India,,,,,,,,Live online,,cy@example.com,,\n"
            "No Contact,,,bad,IGC,,New,India,,,,,,,,Older - Email,,,,\n"
        )
        preview = preview_migration(self.file(body), self.admin)
        self.assertEqual(preview["rows_total"], 4)
        self.assertEqual({item["suggested_category"] for item in preview["sources"]}, {"INFO_EMAIL_LEADS", "DIRECT_CALLS", "LIVE_ONLINE_LEADS"})
        result = upload_migration(self.file(body), "CREATE", None, json.dumps({"Older - Email": "INFO_EMAIL_LEADS"}), self.admin, self.db)
        self.assertEqual((result["rows_imported"], result["rows_skipped"]), (3, 1))
        leads = self.db.scalars(select(MainCrmLead).order_by(MainCrmLead.id)).all()
        self.assertEqual([lead.source_category for lead in leads], ["INFO_EMAIL_LEADS", "DIRECT_CALLS", "LIVE_ONLINE_LEADS"])
        self.assertEqual(leads[0].assigned_to_user_id, self.counselor.id)
        self.assertEqual(leads[0].status_of_lead, "FOLLOW_UP")
        self.assertEqual(get_main_crm_lead(leads[0].id, self.admin, self.db)["lead"]["migration_updated_at"], "2024-01-03")
        activity = self.db.scalar(select(MainCrmActivity).where(MainCrmActivity.lead_id == leads[0].id))
        self.assertEqual(activity.full_user_reply, "Please call")
        self.assertEqual(activity.raw_data["firstassignedat"], "2024-01-01")
        self.db.expunge(activity)

        leads[0].status_of_lead = "IN_CONTACT"
        self.db.commit()
        replacement = upload_migration(self.file(HEADER + "Ada,Neha Mahto,neha@example.com,9876543210,IGC,29,New,India,,,,,,,,Older - Email,,ada@example.com,,\n"), "UPDATE", result["unique_number"], "{}", self.admin, self.db)
        self.assertEqual(replacement["rows_imported"], 1)
        self.assertEqual(self.db.scalar(select(MainCrmLead).where(MainCrmLead.email == "ada@example.com")).status_of_lead, "NEW")
        self.assertEqual(len(self.db.scalars(select(MainCrmActivity)).all()), 1)

    def test_excel_numeric_mobile_and_source_override(self):
        columns = HEADER.strip().split(",")
        row = dict.fromkeys(columns)
        row.update({"Name": "Dana", "Mobile": 9876543210, "Source": "Referral", "Email": "dana@example.com", "Created at": "2023-06-15"})
        buffer = BytesIO()
        pd.DataFrame([row]).to_excel(buffer, index=False)
        buffer.seek(0)
        upload = UploadFile(file=buffer, filename="legacy.xlsx")
        result = upload_migration(upload, "CREATE", None, json.dumps({"Referral": "DIRECT_CALLS"}), self.admin, self.db)
        self.assertEqual(result["categories"]["DIRECT_CALLS"], 1)
        lead = self.db.scalar(select(MainCrmLead))
        self.assertEqual(lead.normalized_phone, "9876543210")
        self.assertEqual(lead.created_at.year, 2023)

    def test_optional_legacy_columns_can_be_missing(self):
        body = "Name,Email,Source,Course Name\nEli,eli@example.com,Older - Email,IGC\n"
        self.assertEqual(preview_migration(self.file(body), self.admin)["rows_total"], 1)
        result = upload_migration(self.file(body), "CREATE", None, "{}", self.admin, self.db)
        self.assertEqual(result["rows_imported"], 1)

    def test_migrated_last_updated_uses_latest_excel_date_after_crm_edit(self):
        body = "Name,Email,Updated at,Source\nAda,ada@example.com,2024-01-03,Older - Email\nAda,ada@example.com,2024-05-06,Older - Email\n"
        upload_migration(self.file(body), "CREATE", None, "{}", self.admin, self.db)
        lead = self.db.scalar(select(MainCrmLead))
        lead.updated_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.db.commit()
        detail = get_main_crm_lead(lead.id, self.admin, self.db)
        self.assertEqual(detail["lead"]["migration_updated_at"], "2024-05-06")

    def test_all_legacy_statuses_and_blank(self):
        expected = {
            "New": "NEW", "No Response (RNR)": "NO_RESPONSE", "Follow up": "FOLLOW_UP",
            "Later": "LATER", "Converted": "CONVERTED", "Call me later": "CALL_ME_LATER",
            "Good": "GOOD", "Not interested": "NOT_INTERESTED", "Invalid": "INVALID",
            "Hot": "HOT", "Didn't Make Enquiry": "OTHERS", "Duplicate Lead": "OTHERS",
            "Different Course": "OTHERS", "Resit": "OTHERS", "Job Enquiry": "OTHERS",
            "Marketing Enquiry": "OTHERS", None: "BLANK", "": "BLANK",
        }
        for original, mapped in expected.items():
            with self.subTest(original=original):
                self.assertEqual(migration_status(original), mapped)

        body = "Name,Email,status of lead,Source\nEli,eli@example.com,,Older - Email\n"
        upload_migration(self.file(body), "CREATE", None, "{}", self.admin, self.db)
        lead = self.db.scalar(select(MainCrmLead))
        self.assertEqual(lead.status_of_lead, "BLANK")
        self.assertTrue(list_leads(self.admin, self.db, 1, 50, "ALL", "")["items"][0]["is_migrated"])
        lead.status_of_lead = "NEW"  # The previous importer used NEW for empty status.
        self.db.commit()
        backfill_migration_statuses(self.db)
        self.assertEqual(lead.status_of_lead, "BLANK")

    def test_background_import_batches_and_reports_progress(self):
        body = "Name,Email,Source\n" + "".join(f"Person {index},person{index}@example.com,Older - Email\n" for index in range(1100))
        body += "Person 0,person0@example.com,Older - Email\n"
        tasks = BackgroundTasks()
        factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with patch.object(main_crm, "SessionLocal", factory):
            started = start_migration(tasks, self.file(body), "CREATE", None, "{}", self.admin, self.db)
            reference = started["unique_number"]
            self.assertEqual(migration_progress(reference, self.admin, self.db)["status"], "PROCESSING")
            for task in tasks.tasks:
                task.func(*task.args, **task.kwargs)
            self.db.expire_all()
            finished = migration_progress(reference, self.admin, self.db)
        self.assertEqual(finished["status"], "COMPLETED")
        self.assertEqual(finished["processed"], 1101)
        self.assertEqual(finished["rows_imported"], 1101)
        self.assertEqual(self.db.query(MainCrmLead).count(), 1100)
        first_page = list_leads(self.admin, self.db, 1, 50, "ALL", "")
        self.assertEqual((first_page["total"], len(first_page["items"]), first_page["pages"]), (1100, 50, 22))
        self.assertEqual(list_leads(self.admin, self.db, 1, 50, "ALL", "person1099@example.com")["total"], 1)
        self.assertEqual(list_leads(self.admin, self.db, 2, 50, "DIRECT_CALLS", "")["total"], 0)
        summary = lead_summary(self.admin, self.db)
        self.assertEqual(summary["total"], 1100)
        self.assertEqual(summary["source_category_counts"]["INFO_EMAIL_LEADS"], 1100)
        self.assertEqual(list_leads(self.counselor, self.db, 1, 50, "ALL", "")["total"], 0)
        self.assertEqual(lead_summary(self.counselor, self.db)["total"], 0)

    def test_information_edits_have_actor_and_appear_only_in_edit_history(self):
        customer = Customer(primary_name="Ada", primary_email="old@example.com")
        self.db.add(customer)
        self.db.flush()
        lead = MainCrmLead(customer_id=customer.id, full_name="Ada", email="old@example.com",
                           source_category="INFO_EMAIL_LEADS", status_of_lead="NEW")
        self.db.add(lead)
        self.db.commit()

        main_crm.update_details(lead.id, main_crm.LeadEditPayload(email="new@example.com"), self.admin, self.db)
        detail = get_main_crm_lead(lead.id, self.admin, self.db)
        self.assertEqual(detail["lead"]["email"], "new@example.com")
        self.assertEqual(len(detail["changes"]), 1)
        self.assertEqual(detail["changes"][0]["raw_data"]["changes"]["email"],
                         {"from": "old@example.com", "to": "new@example.com"})
        self.assertEqual(detail["changes"][0]["raw_data"]["edited_by"]["name"], "Admin")
        self.assertFalse(any(item["activity_type"] == "EDIT" for item in detail["activities"]))
        self.assertFalse(any(item["title"] == "Edit" for item in detail["lifecycle"]["events"]))


if __name__ == "__main__":
    unittest.main()
