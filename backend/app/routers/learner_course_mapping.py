from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LearnerCourseCategory, LearnerCourseMapping, LearnerCourseSubcategory, LearnersCrmEnrollment, User
from app.services.auth import require_admin
from app.services.learner_course_mapping import normalize_course_name
from app.services.lead_workflow import mark_opportunities_dirty

router = APIRouter(prefix="/learners-crm/course-mapping", tags=["Learner Course Mapping"])


class CategoryPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SubcategoryPayload(CategoryPayload):
    category_id: int


class CoursePayload(BaseModel):
    course_name: str = Field(min_length=1, max_length=500)
    subcategory_id: int


class CourseUpdate(BaseModel):
    course_name: str | None = Field(default=None, max_length=500)
    subcategory_id: int | None = None


def clean_name(value: str) -> tuple[str, str]:
    name = " ".join(value.split())
    normalized = normalize_course_name(name)
    if not name or not normalized:
        raise HTTPException(status_code=400, detail="Enter a name.")
    return name, normalized


def require_category(db: Session, category_id: int):
    category = db.get(LearnerCourseCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Course main category not found.")
    return category


def require_subcategory(db: Session, subcategory_id: int):
    subcategory = db.get(LearnerCourseSubcategory, subcategory_id)
    if not subcategory:
        raise HTTPException(status_code=404, detail="Course subcategory not found.")
    return subcategory


def require_course(db: Session, course_id: int):
    course = db.get(LearnerCourseMapping, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Mapped course not found.")
    return course


def changed(db):
    mark_opportunities_dirty(db)
    db.commit()


@router.get("")
def list_mapping(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    categories = db.scalars(select(LearnerCourseCategory).order_by(LearnerCourseCategory.display_order, LearnerCourseCategory.name)).all()
    subcategories = db.scalars(select(LearnerCourseSubcategory).order_by(LearnerCourseSubcategory.display_order, LearnerCourseSubcategory.name)).all()
    courses = db.scalars(select(LearnerCourseMapping).order_by(LearnerCourseMapping.course_name)).all()
    by_subcategory = {item.id: [] for item in subcategories}
    for course in courses:
        if course.subcategory_id in by_subcategory:
            by_subcategory[course.subcategory_id].append({"id": course.id, "course_name": course.course_name})
    by_category = {item.id: [] for item in categories}
    for subcategory in subcategories:
        by_category[subcategory.category_id].append({
            "id": subcategory.id, "name": subcategory.name,
            "courses": by_subcategory[subcategory.id],
        })
    enrolment_counts = db.execute(select(LearnersCrmEnrollment.course_name, func.count()).group_by(LearnersCrmEnrollment.course_name)).all()
    mapped_names = {course.normalized_name for course in courses}
    unmapped = [{"course_name": name, "enrolments": count} for name, count in enrolment_counts if normalize_course_name(name) not in mapped_names]
    return {
        "categories": [{"id": category.id, "name": category.name, "subcategories": by_category[category.id]} for category in categories],
        "unmapped_courses": sorted(unmapped, key=lambda item: item["course_name"].casefold()),
    }


@router.post("/categories", status_code=201)
def create_category(payload: CategoryPayload, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    name, normalized = clean_name(payload.name)
    if db.scalar(select(LearnerCourseCategory.id).where(LearnerCourseCategory.normalized_name == normalized)):
        raise HTTPException(status_code=409, detail="That main category already exists.")
    order = db.scalar(select(func.max(LearnerCourseCategory.display_order)))
    category = LearnerCourseCategory(name=name, normalized_name=normalized, display_order=(order or 0) + 1)
    db.add(category); changed(db)
    return {"id": category.id, "name": category.name}


@router.patch("/categories/{category_id}")
def update_category(category_id: int, payload: CategoryPayload, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    category = require_category(db, category_id)
    name, normalized = clean_name(payload.name)
    existing = db.scalar(select(LearnerCourseCategory.id).where(LearnerCourseCategory.normalized_name == normalized))
    if existing and existing != category_id:
        raise HTTPException(status_code=409, detail="That main category already exists.")
    category.name = name; category.normalized_name = normalized
    changed(db)
    return {"id": category.id, "name": category.name}


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    category = require_category(db, category_id)
    if db.scalar(select(LearnerCourseSubcategory.id).where(LearnerCourseSubcategory.category_id == category_id).limit(1)):
        raise HTTPException(status_code=400, detail="Move or remove this category's subcategories first.")
    db.delete(category); changed(db)
    return {"deleted": category_id}


@router.post("/subcategories", status_code=201)
def create_subcategory(payload: SubcategoryPayload, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    require_category(db, payload.category_id)
    name, normalized = clean_name(payload.name)
    if db.scalar(select(LearnerCourseSubcategory.id).where(
        LearnerCourseSubcategory.category_id == payload.category_id,
        LearnerCourseSubcategory.normalized_name == normalized,
    )):
        raise HTTPException(status_code=409, detail="That subcategory already exists in this main category.")
    order = db.scalar(select(func.max(LearnerCourseSubcategory.display_order)).where(LearnerCourseSubcategory.category_id == payload.category_id))
    subcategory = LearnerCourseSubcategory(category_id=payload.category_id, name=name, normalized_name=normalized, display_order=(order or 0) + 1)
    db.add(subcategory); changed(db)
    return {"id": subcategory.id, "name": subcategory.name, "category_id": subcategory.category_id}


@router.patch("/subcategories/{subcategory_id}")
def update_subcategory(subcategory_id: int, payload: SubcategoryPayload, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    subcategory = require_subcategory(db, subcategory_id)
    require_category(db, payload.category_id)
    name, normalized = clean_name(payload.name)
    existing = db.scalar(select(LearnerCourseSubcategory.id).where(
        LearnerCourseSubcategory.category_id == payload.category_id,
        LearnerCourseSubcategory.normalized_name == normalized,
    ))
    if existing and existing != subcategory_id:
        raise HTTPException(status_code=409, detail="That subcategory already exists in this main category.")
    subcategory.category_id = payload.category_id
    subcategory.name = name
    subcategory.normalized_name = normalized
    db.execute(LearnerCourseMapping.__table__.update().where(
        LearnerCourseMapping.subcategory_id == subcategory_id
    ).values(category_id=payload.category_id))
    changed(db)
    return {"id": subcategory.id, "name": subcategory.name, "category_id": subcategory.category_id}


@router.delete("/subcategories/{subcategory_id}")
def delete_subcategory(subcategory_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    subcategory = require_subcategory(db, subcategory_id)
    if db.scalar(select(LearnerCourseMapping.id).where(LearnerCourseMapping.subcategory_id == subcategory_id).limit(1)):
        raise HTTPException(status_code=400, detail="Move or remove this subcategory's courses first.")
    db.delete(subcategory); changed(db)
    return {"deleted": subcategory_id}


@router.post("/courses", status_code=201)
def create_course(payload: CoursePayload, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    subcategory = require_subcategory(db, payload.subcategory_id)
    name, normalized = clean_name(payload.course_name)
    if db.scalar(select(LearnerCourseMapping.id).where(LearnerCourseMapping.normalized_name == normalized)):
        raise HTTPException(status_code=409, detail="That course is already mapped.")
    course = LearnerCourseMapping(category_id=subcategory.category_id, subcategory_id=subcategory.id, course_name=name, normalized_name=normalized)
    db.add(course); changed(db)
    return {"id": course.id, "course_name": course.course_name, "subcategory_id": course.subcategory_id}


@router.patch("/courses/{course_id}")
def update_course(course_id: int, payload: CourseUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    course = require_course(db, course_id)
    if payload.subcategory_id is not None:
        subcategory = require_subcategory(db, payload.subcategory_id)
        course.subcategory_id = subcategory.id
        course.category_id = subcategory.category_id
    if payload.course_name is not None:
        name, normalized = clean_name(payload.course_name)
        existing = db.scalar(select(LearnerCourseMapping.id).where(LearnerCourseMapping.normalized_name == normalized))
        if existing and existing != course_id:
            raise HTTPException(status_code=409, detail="That course is already mapped.")
        course.course_name = name; course.normalized_name = normalized
    changed(db)
    return {"id": course.id, "course_name": course.course_name, "subcategory_id": course.subcategory_id}


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    course = require_course(db, course_id)
    db.delete(course); changed(db)
    return {"deleted": course_id}
