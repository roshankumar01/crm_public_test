"""Start the Windows/Caddy deployment and synchronize its .env admin."""

import os

import uvicorn
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import AuthSession, Course, User
from app.services.auth import hash_password, verify_password
from seed_courses import COURSES


def initialize_from_env(db):
    username = os.getenv("ADMIN_USERNAME", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not username or not password or password == "replace-with-a-long-admin-password":
        raise RuntimeError("Set ADMIN_USERNAME and a real ADMIN_PASSWORD in backend/.env before starting.")

    for data in COURSES:
        if db.scalar(select(Course.id).where(Course.code == data["code"])) is None:
            db.add(Course(**data))

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        if db.scalar(select(User.id).where(User.role == "ADMIN", User.active.is_(True)).limit(1)) is not None:
            raise RuntimeError("An active admin already exists under another username. Keep ADMIN_USERNAME unchanged.")
        user = User(username=username, role="ADMIN", active=True, password_hash=hash_password(password))
        db.add(user)
    elif user.role != "ADMIN":
        raise RuntimeError("ADMIN_USERNAME belongs to a non-admin account. Choose another username.")
    elif not verify_password(password, user.password_hash):
        user.password_hash = hash_password(password)
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))

    user.display_name = os.getenv("ADMIN_DISPLAY_NAME", "Admin")
    user.email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    user.active = True
    db.commit()


def main():
    # Importing the app creates or migrates the schema before inserting the admin.
    import app.main  # noqa: F401

    with SessionLocal() as db:
        initialize_from_env(db)

    # Caddy exposes /api and strips that prefix before forwarding to this port.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, workers=1, root_path="/api")


if __name__ == "__main__":
    main()
