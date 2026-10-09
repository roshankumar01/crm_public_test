import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.docker_start import initialize_defaults
from app.models import Course, User
from app.services.auth import verify_password


class DockerStartupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_first_start_and_restart_preserve_accounts_and_course_edits(self):
        initialize_defaults(self.db, " ADMIN ", "first-password", "Administrator", "admin@example.com")
        admin = self.db.scalar(select(User))
        original_hash = admin.password_hash
        self.assertEqual(admin.username, "admin")
        self.assertTrue(verify_password("first-password", original_hash))
        igc = self.db.scalar(select(Course).where(Course.code == "IGC"))
        igc.name = "Custom IGC name"
        self.db.commit()
        initialize_defaults(self.db, "another-admin", "replacement-password")
        self.assertEqual(self.db.scalar(select(func.count(User.id))), 1)
        self.assertEqual(self.db.scalar(select(func.count(Course.id))), 4)
        self.assertEqual(admin.password_hash, original_hash)
        self.assertEqual(igc.name, "Custom IGC name")

    def test_first_start_rejects_missing_password_or_existing_counselor_username(self):
        with self.assertRaisesRegex(RuntimeError, "ADMIN_PASSWORD"):
            initialize_defaults(self.db, "admin", "")
        self.db.rollback()
        self.db.add(User(username="admin", display_name="Existing counselor", password_hash="existing",
                         role="COUNSELOR", active=True))
        self.db.commit()
        with self.assertRaisesRegex(RuntimeError, "existing account"):
            initialize_defaults(self.db, "admin", "new-password")
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(User)).password_hash, "existing")


if __name__ == "__main__":
    unittest.main()
