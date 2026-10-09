import unittest

from sqlalchemy import create_engine, inspect, text

from app.services.schema_migrations import ensure_counselor_action_columns


class CounselorActionMigrationTests(unittest.TestCase):
    def test_existing_activity_table_gains_actor_columns_and_preserves_rows(self):
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, display_name VARCHAR(255))"))
                connection.execute(text("CREATE TABLE counselor_actions (id INTEGER PRIMARY KEY, user_id INTEGER, assigned_counselor_id INTEGER)"))
                connection.execute(text("INSERT INTO users (id, display_name) VALUES (1, 'Alex')"))
                connection.execute(text("INSERT INTO counselor_actions (id, user_id, assigned_counselor_id) VALUES (1, 1, 1)"))
            ensure_counselor_action_columns(engine)
            ensure_counselor_action_columns(engine)
            columns = {column["name"] for column in inspect(engine).get_columns("counselor_actions")}
            self.assertTrue({"actor_name", "assigned_counselor_name"} <= columns)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT actor_name, assigned_counselor_name FROM counselor_actions WHERE id = 1")).one(),
                                 ("Alex", "Alex"))
        finally:
            engine.dispose()
