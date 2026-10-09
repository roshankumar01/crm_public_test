import os

from dotenv import load_dotenv
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import User
from app.services.auth import hash_password

load_dotenv()

USERS = [
    {
        "username": os.getenv("ADMIN_USERNAME", "admin"),
        "display_name": os.getenv("ADMIN_DISPLAY_NAME", "Admin"),
        "email": os.getenv("ADMIN_EMAIL", "admin@gmail.com"),
        "password": os.getenv("ADMIN_PASSWORD", "admin123"),
        "role": "ADMIN",
    },
    {
        "username": os.getenv("COUNSELOR_A_USERNAME", "person_a"),
        "display_name": os.getenv("COUNSELOR_A_DISPLAY_NAME", "Person A"),
        "email": os.getenv("COUNSELOR_A_EMAIL", "person_a@gmail.com"),
        "password": os.getenv("COUNSELOR_A_PASSWORD", "personA123"),
        "role": "COUNSELOR",
    },
    {
        "username": os.getenv("COUNSELOR_B_USERNAME", "person_b"),
        "display_name": os.getenv("COUNSELOR_B_DISPLAY_NAME", "Person B"),
        "email": os.getenv("COUNSELOR_B_EMAIL", "person_b@gmail.com"),
        "password": os.getenv("COUNSELOR_B_PASSWORD", "personB123"),
        "role": "COUNSELOR",
    },
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for data in USERS:
            username = data["username"].strip().lower()
            existing = db.scalar(select(User).where(User.username == username))
            if existing:
                existing.display_name = data["display_name"]
                existing.email = data["email"]
                existing.role = data["role"]
                existing.active = True
                existing.password_hash = hash_password(data["password"])
            else:
                db.add(User(
                    username=username,
                    display_name=data["display_name"],
                    email=data["email"],
                    password_hash=hash_password(data["password"]),
                    role=data["role"],
                    active=True,
                ))
        db.commit()
        print("CRM users seeded successfully.")
        print("Change the default passwords in backend/.env before production use.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
