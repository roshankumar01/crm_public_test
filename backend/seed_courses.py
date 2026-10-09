from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Course

COURSES = [
    {"code": "IGC", "name": "IGC", "program_code": "IGC", "display_order": 1},
    {"code": "ID1", "name": "ID1", "program_code": "IDP", "display_order": 10},
    {"code": "ID2", "name": "ID2", "program_code": "IDP", "display_order": 20},
    {"code": "ID3", "name": "ID3", "program_code": "IDP", "display_order": 30},
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for data in COURSES:
            existing = db.scalar(select(Course).where(Course.code == data["code"]))
            if existing:
                existing.name = data["name"]
                existing.program_code = data["program_code"]
                existing.display_order = data["display_order"]
                existing.active = True
            else:
                db.add(Course(**data))
        db.commit()
        print("Courses seeded successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
