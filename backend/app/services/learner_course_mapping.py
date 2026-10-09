import unicodedata
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AppSetting, LearnerCourseCategory, LearnerCourseMapping, LearnerCourseSubcategory

SEED_KEY = "learner_course_mapping_seeded_v2"
SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "learner_course_mapping_v2.tsv"


def normalize_course_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def seed_course_mapping(db: Session) -> None:
    if db.get(AppSetting, SEED_KEY):
        return
    rows = []
    seen_courses = set()
    for line in SEED_FILE.read_text(encoding="utf-8-sig").splitlines()[1:]:
        if not line.strip():
            continue
        main, sub, course_name = (part.strip() for part in line.split("\t", 2))
        normalized = normalize_course_name(course_name)
        if not main or not sub or not normalized or normalized in seen_courses:
            raise ValueError("The bundled learner course mapping contains an empty or duplicate entry.")
        seen_courses.add(normalized)
        rows.append((main, sub, course_name, normalized))

    # This v2 seed is an explicitly requested replacement of the old two-level map.
    db.execute(delete(LearnerCourseMapping))
    db.execute(delete(LearnerCourseSubcategory))
    db.execute(delete(LearnerCourseCategory))
    categories = {}
    subcategories = {}
    for main, sub, course_name, normalized in rows:
        main_key = normalize_course_name(main)
        if main_key not in categories:
            category = LearnerCourseCategory(name=main, normalized_name=main_key, display_order=len(categories))
            db.add(category)
            db.flush()
            categories[main_key] = category
        sub_key = (main_key, normalize_course_name(sub))
        if sub_key not in subcategories:
            subcategory = LearnerCourseSubcategory(
                category_id=categories[main_key].id, name=sub, normalized_name=sub_key[1],
                display_order=sum(key[0] == main_key for key in subcategories),
            )
            db.add(subcategory)
            db.flush()
            subcategories[sub_key] = subcategory
        db.add(LearnerCourseMapping(
            category_id=categories[main_key].id,
            subcategory_id=subcategories[sub_key].id,
            course_name=course_name, normalized_name=normalized,
        ))
    db.add(AppSetting(key=SEED_KEY, value="1"))
    db.commit()


def mapping_for_course_names(db: Session, course_names) -> dict[str, dict]:
    normalized_names = {normalize_course_name(name) for name in course_names if name}
    if not normalized_names:
        return {}
    rows = db.execute(
        select(LearnerCourseMapping.normalized_name, LearnerCourseCategory.name, LearnerCourseSubcategory.name)
        .join(LearnerCourseCategory, LearnerCourseMapping.category_id == LearnerCourseCategory.id)
        .outerjoin(LearnerCourseSubcategory, LearnerCourseMapping.subcategory_id == LearnerCourseSubcategory.id)
        .where(LearnerCourseMapping.normalized_name.in_(normalized_names))
    ).all()
    return {normalized: {"main_category": main, "sub_category": sub} for normalized, main, sub in rows}


def categories_for_course_names(db: Session, course_names) -> dict[str, str]:
    return {name: mapping["main_category"] for name, mapping in mapping_for_course_names(db, course_names).items()}
