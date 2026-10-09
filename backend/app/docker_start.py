"""Initialize a Docker deployment without replacing existing data or passwords."""

import os
import time

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.database import SessionLocal, engine
from app.models import Course, User
from app.services.auth import hash_password
from seed_courses import COURSES


def initialize_defaults(db, username, password, display_name="Admin", email=None):
    for data in COURSES:
        if db.scalar(select(Course.id).where(Course.code == data["code"])) is None:
            db.add(Course(**data))

    if db.scalar(select(User.id).where(User.role == "ADMIN", User.active.is_(True)).limit(1)) is None:
        if not username.strip() or not password:
            raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD are required for the first Docker startup.")
        username = username.strip().lower()
        if db.scalar(select(User.id).where(User.username == username)) is not None:
            raise RuntimeError("ADMIN_USERNAME already belongs to an existing account. Choose another username.")
        db.add(User(username=username, display_name=display_name, email=email,
                    password_hash=hash_password(password), role="ADMIN", active=True))
    db.commit()


def main():
    for attempt in range(60):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            break
        except OperationalError:
            if attempt == 59:
                raise RuntimeError("Database did not become available within 120 seconds.") from None
            print("Waiting for the database...", flush=True)
            time.sleep(2)

    # Run the application's existing schema and mapping initialization first.
    import app.main  # noqa: F401

    with SessionLocal() as db:
        initialize_defaults(db, os.getenv("ADMIN_USERNAME", "admin"), os.getenv("ADMIN_PASSWORD", ""),
                            os.getenv("ADMIN_DISPLAY_NAME", "Admin"), os.getenv("ADMIN_EMAIL"))

    # Upload-job progress lives in this process, so use exactly one worker.
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1",
                         "--root-path", os.getenv("API_ROOT_PATH", ""), "--proxy-headers", "--forwarded-allow-ips", "*"])


if __name__ == "__main__":
    main()
