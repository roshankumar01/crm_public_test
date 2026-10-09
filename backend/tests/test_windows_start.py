import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AuthSession, Course, User
from app.services.auth import verify_password
from run_windows import initialize_from_env


class WindowsStartupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_new_database_and_password_change(self):
        with patch.dict(os.environ, {"ADMIN_USERNAME": "Admin", "ADMIN_PASSWORD": "first-secret"}):
            initialize_from_env(self.db)
        admin = self.db.scalar(select(User))
        self.assertEqual(admin.username, "admin")
        self.assertTrue(verify_password("first-secret", admin.password_hash))
        self.assertEqual(self.db.scalar(select(func.count(Course.id))), 4)
        self.db.add(AuthSession(token_hash="old-session", user_id=admin.id,
                                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        self.db.commit()

        with patch.dict(os.environ, {"ADMIN_USERNAME": "Admin", "ADMIN_PASSWORD": "second-secret"}):
            initialize_from_env(self.db)
        self.assertEqual(self.db.scalar(select(func.count(User.id))), 1)
        self.assertTrue(verify_password("second-secret", admin.password_hash))
        self.assertFalse(verify_password("first-secret", admin.password_hash))
        self.assertEqual(self.db.scalar(select(func.count(AuthSession.id))), 0)

    def test_rejects_placeholder_and_username_collision(self):
        with patch.dict(os.environ, {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "replace-with-a-long-admin-password"}):
            with self.assertRaisesRegex(RuntimeError, "ADMIN_PASSWORD"):
                initialize_from_env(self.db)
        self.db.add(User(username="admin", display_name="Counselor", password_hash="x", role="COUNSELOR", active=True))
        self.db.commit()
        with patch.dict(os.environ, {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "real-secret"}):
            with self.assertRaisesRegex(RuntimeError, "non-admin"):
                initialize_from_env(self.db)


if __name__ == "__main__":
    unittest.main()
