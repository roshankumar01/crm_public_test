import unittest
from datetime import date, timedelta
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from app.database import Base
from app.models import User, MainCrmLead, Lead, LeadReminder
from app.routers.reminders import ReminderInput, set_reminder, get_reminder, list_reminders, complete_reminder
from app.services.data_reset import clear_crm_data


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine,"connect")
        def foreign_keys(connection,_): connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine); self.db=Session(self.engine)
        self.admin=User(username="admin",display_name="Admin",role="ADMIN",password_hash="x")
        self.owner=User(username="one",display_name="Counselor One",role="COUNSELOR",password_hash="x")
        self.other=User(username="two",display_name="Counselor Two",role="COUNSELOR",password_hash="x")
        self.db.add_all([self.admin,self.owner,self.other]);self.db.flush()
        self.main=MainCrmLead(full_name="Main contact",email="main@example.com",source_category="DIRECT_CALLS",assigned_to_user_id=self.owner.id)
        self.upsell=Lead(target_code="PSM",opportunity_key="PSM",assigned_to_user_id=self.owner.id)
        self.db.add_all([self.main,self.upsell]);self.db.commit()
        self.clock=patch("app.routers.reminders.company_today",return_value=date(2026,9,28));self.clock.start()

    def tearDown(self):
        self.clock.stop();self.db.close();self.engine.dispose()

    def schedule(self,workspace="main",days=3):
        return set_reminder(workspace,self.main.id if workspace=="main" else self.upsell.id,ReminderInput(days=days,notes="Call about fees"),self.owner,self.db)

    def listing(self,workspace="main",view="pending",user=None,page=1,owner=None):
        return list_reminders(workspace,view,page,owner,user or self.owner,self.db)

    def test_countdown_zero_and_overdue_use_calendar_days(self):
        item=self.schedule(days=3)
        self.assertEqual(item["due_date"],date(2026,10,1));self.assertEqual(item["remaining_days"],3)
        with patch("app.routers.reminders.company_today",return_value=date(2026,10,1)):
            row=self.listing()["items"][0]
            self.assertEqual(row["remaining_days"],0);self.assertTrue(row["due_now"])
            self.assertEqual(self.listing(view="due")["total"],1)
        with patch("app.routers.reminders.company_today",return_value=date(2026,10,4)):
            row=self.listing()["items"][0]
            self.assertEqual(row["overdue_days"],3);self.assertEqual(row["remaining_days"],0)

    def test_upsert_is_one_reminder_and_workspaces_are_separate(self):
        first=self.schedule();second=self.schedule(days=7);self.schedule("upsell",1)
        self.assertEqual(first["id"],second["id"]);self.assertEqual(self.db.query(LeadReminder).count(),2)
        self.assertEqual(self.listing()["items"][0]["remaining_days"],7)
        self.assertEqual(self.listing("upsell")["items"][0]["remaining_days"],1)
        self.assertEqual(self.main.status_of_lead,"NEW");self.assertEqual(self.upsell.status,"NEW")

    def test_counselor_cannot_view_edit_or_complete_someone_elses_lead(self):
        self.schedule()
        self.assertEqual(self.listing(user=self.other)["total"],0)
        self.assertEqual(self.listing(user=self.other,owner=self.owner.id)["total"],0)
        for operation in [lambda:get_reminder("main",self.main.id,self.other,self.db),
            lambda:set_reminder("main",self.main.id,ReminderInput(days=1),self.other,self.db),
            lambda:complete_reminder("main",self.main.id,self.other,self.db)]:
            with self.assertRaises(HTTPException) as error: operation()
            self.assertEqual(error.exception.status_code,403)

    def test_reminder_follows_assignment_and_admin_filters_counselors(self):
        self.schedule();self.main.assigned_to_user_id=self.other.id;self.db.commit()
        self.assertEqual(self.listing()["total"],0)
        self.assertEqual(self.listing(user=self.other)["total"],1)
        self.assertEqual(self.listing(user=self.admin,owner=self.owner.id)["total"],0)
        self.assertEqual(self.listing(user=self.admin,owner=self.other.id)["total"],1)

    def test_admin_can_schedule_unassigned_lead_and_owns_its_reminder(self):
        self.main.assigned_to_user_id=None;self.db.commit()
        set_reminder("main",self.main.id,ReminderInput(days=0),self.admin,self.db)
        self.assertEqual(self.listing(user=self.admin,owner=self.admin.id)["items"][0]["counselor"],"Admin")
        self.assertEqual(self.listing()["total"],0)

    def test_completed_is_idempotent_and_rescheduling_reopens(self):
        self.schedule(days=0)
        first=complete_reminder("main",self.main.id,self.owner,self.db)
        second=complete_reminder("main",self.main.id,self.owner,self.db)
        self.assertEqual(first["completed_at"],second["completed_at"])
        self.assertFalse(first["due_now"]);self.assertEqual(self.listing()["total"],0)
        self.assertEqual(self.listing(view="completed")["total"],1)
        self.schedule(days=2)
        self.assertEqual(self.listing(view="completed")["total"],0)
        self.assertEqual(self.listing(view="upcoming")["total"],1)

    def test_validation_and_missing_lead(self):
        for days in [-1,3651,1.5,"3"]:
            with self.assertRaises(ValidationError): ReminderInput(days=days)
        with self.assertRaises(HTTPException): get_reminder("unknown",self.main.id,self.owner,self.db)
        with self.assertRaises(HTTPException): get_reminder("main",999,self.owner,self.db)
        with self.assertRaises(HTTPException): self.listing(view="invalid")
        self.assertIsNone(get_reminder("main",self.main.id,self.owner,self.db)["reminder"])

    def test_total_reset_clears_reminders_and_lead_deletion_cascades(self):
        self.schedule();self.schedule("upsell")
        self.db.delete(self.main);self.db.commit()
        self.assertEqual(self.db.query(LeadReminder).count(),1)
        clear_crm_data(self.db);self.db.commit()
        self.assertEqual(self.db.query(LeadReminder).count(),0)
        self.assertEqual(self.db.query(User).count(),3)

    def test_stable_pagination_and_due_counts(self):
        rows=[MainCrmLead(full_name=f"Person {i}",source_category="DIRECT_CALLS",assigned_to_user_id=self.owner.id) for i in range(55)]
        self.db.add_all(rows);self.db.flush()
        self.db.add_all([LeadReminder(main_lead_id=lead.id,due_date=date(2026,9,28)+timedelta(days=i%2),created_by_id=self.owner.id) for i,lead in enumerate(rows)]);self.db.commit()
        first=self.listing();second=self.listing(page=2)
        self.assertEqual(first["total"],55);self.assertEqual(len(first["items"]),50);self.assertEqual(len(second["items"]),5)
        self.assertEqual(first["counts"],{"due":28,"upcoming":27,"completed":0})
        self.assertFalse({r["id"] for r in first["items"]}&{r["id"] for r in second["items"]})
