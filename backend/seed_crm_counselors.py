"""Create or refresh the agreed Main CRM counselor accounts.

Run from the backend directory:
    python seed_crm_counselors.py

The script is idempotent: usernames are created once and later runs update the
name, email, country, blank region, password, role, and active status.
"""

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import User
from app.services.auth import hash_password


PASSWORD = "test1234"
COUNSELORS = [
    ("counselor_megha", "Megha", "india", "megha.p@greenwgroup.com"),
    ("counselor_bhuvan", "Bhuvan", "india", "sales.india3@greenwgroup.com"),
    ("counselor_rina", "Rina", "india", "sales.india8@greenwgroup.com"),
    ("counselor_rimna", "Rimna", "india", "sales.india6@greenwgroup.com"),
    ("counselor_ashquar", "Ashquar", "india", "sales.india18@greenwgroup.com"),
    ("counselor_neha", "Neha", "india", "neha.m@greenwgroup.com"),
    ("counselor_priyanka", "Priyanka", "india", "priyanka.t@greenwgroup.com"),
    ("counselor_sandra", "Sandra", "india", "sales.india5@greenwgroup.com"),
    ("counselor_trisha", "Trisha", "india", "trisha.n@greenwgroup.com"),
    ("counselor_sujata", "Sujata", "india", "sujata.g@greenwgroup.com"),
    ("counselor_arul", "Arul", "india", "sales.india2@greenwgroup.com"),
    ("counselor_priya", "Priya", "uae", "sales.uae1@greenwgroup.com"),
    ("counselor_aswathi", "Aswathi", "uae", "sales.uae3@greenwgroup.com"),
    ("counselor_adarsh", "Adarsh", "uae", "sales.uae4@greenwgroup.com"),
    ("counselor_kiruthiga", "Kiruthiga", "uae", "kiruthiga.s@greenwgroup.com"),
    ("counselor_a_pandiyan", "A.Pandiyan", "ksa", "apandiyan.t@greenwgroup.com"),
    ("counselor_eshokh", "Eshokh", "uk", "eshokh.sp@greenwgroup.com"),
]


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for username, display_name, country, email in COUNSELORS:
            user = db.scalar(select(User).where(User.username == username))
            if not user:
                user = User(username=username, password_hash="", role="COUNSELOR")
                db.add(user)
            user.display_name = display_name
            user.email = email
            user.country = country
            user.region = None
            user.password_hash = hash_password(PASSWORD)
            user.role = "COUNSELOR"
            user.active = True
        db.commit()
    print(f"Created or updated {len(COUNSELORS)} counselor accounts.")


if __name__ == "__main__":
    main()
