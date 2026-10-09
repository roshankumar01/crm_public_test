"""Small startup upgrades for databases created by earlier CRM versions."""

from sqlalchemy import inspect, text


def ensure_counselor_action_columns(engine):
    columns = {column["name"] for column in inspect(engine).get_columns("counselor_actions")}
    if "actor_name" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE counselor_actions ADD COLUMN actor_name VARCHAR(255) NOT NULL DEFAULT 'Unknown'"))
            connection.execute(text("UPDATE counselor_actions SET actor_name = COALESCE((SELECT display_name FROM users WHERE users.id = counselor_actions.user_id), 'Unknown')"))
    if "assigned_counselor_name" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE counselor_actions ADD COLUMN assigned_counselor_name VARCHAR(255)"))
            connection.execute(text("UPDATE counselor_actions SET assigned_counselor_name = (SELECT display_name FROM users WHERE users.id = counselor_actions.assigned_counselor_id) WHERE assigned_counselor_id IS NOT NULL"))
