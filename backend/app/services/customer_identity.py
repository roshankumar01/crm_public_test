import re

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models import ConversionVerification, Customer, CustomerIdentity, Lead, Learner, LearnersCrmProfile, MainCrmLead, UpsellContactInfo, UpsellCourseCase


def normalize_email(value):
    value = str(value).strip().lower() if value is not None else ""
    return value or None


def normalize_phone(value):
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return (digits[-10:] if len(digits) >= 10 else digits) or None


def _merge_customer(db: Session, source_id: int, target_id: int):
    """A repeated board learner number proves these two contact records are one person."""
    if source_id == target_id:
        return
    source_info = db.get(UpsellContactInfo, source_id)
    target_info = db.get(UpsellContactInfo, target_id)
    if source_info:
        if target_info:
            target_info.overrides = {**source_info.overrides, **target_info.overrides}
            db.delete(source_info)
        else:
            source_info.customer_id = target_id
        db.flush()
    for model in (CustomerIdentity, MainCrmLead, LearnersCrmProfile, Learner, Lead, UpsellCourseCase, ConversionVerification):
        db.execute(update(model).where(model.customer_id == source_id).values(customer_id=target_id))
    source = db.get(Customer, source_id)
    if source:
        db.delete(source)
    from app.services.lead_workflow import mark_opportunities_dirty
    mark_opportunities_dirty(db)


def resolve_customer(db: Session, name=None, email=None, phone=None, preferred_customer_id=None):
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)
    customer = db.get(Customer, preferred_customer_id) if preferred_customer_id else None
    if normalized_email:
        identity = db.scalar(select(CustomerIdentity).where(CustomerIdentity.identity_type == "EMAIL", CustomerIdentity.normalized_value == normalized_email))
        if identity:
            if customer and identity.customer_id != customer.id:
                _merge_customer(db, identity.customer_id, customer.id)
            else:
                customer = db.get(Customer, identity.customer_id)
    if not customer and normalized_phone:
        identity = db.scalar(select(CustomerIdentity).where(CustomerIdentity.identity_type == "PHONE", CustomerIdentity.normalized_value == normalized_phone))
        if identity:
            if customer and preferred_customer_id and identity.customer_id != customer.id:
                _merge_customer(db, identity.customer_id, customer.id)
            elif not customer:
                customer = db.get(Customer, identity.customer_id)
    if not customer:
        customer = Customer(primary_name=name, primary_email=email, primary_phone=phone)
        db.add(customer); db.flush()
    else:
        if name: customer.primary_name = name
        if email: customer.primary_email = email
        if phone: customer.primary_phone = phone
    for identity_type, normalized, raw in (("EMAIL", normalized_email, email), ("PHONE", normalized_phone, phone)):
        if not normalized:
            continue
        existing = db.scalar(select(CustomerIdentity).where(CustomerIdentity.identity_type == identity_type, CustomerIdentity.normalized_value == normalized))
        if not existing:
            db.add(CustomerIdentity(customer_id=customer.id, identity_type=identity_type, normalized_value=normalized, raw_value=str(raw).strip()))
    db.flush()
    return customer


def customer_is_registered(db: Session, customer_id: int):
    return bool(
        db.scalar(select(LearnersCrmProfile.id).where(LearnersCrmProfile.customer_id == customer_id).limit(1))
        or db.scalar(select(Learner.learner_number).where(Learner.customer_id == customer_id).limit(1))
    )


def mark_customer_converted(db: Session, customer_id: int, learner_number=None):
    if learner_number:
        db.execute(update(MainCrmLead).where(MainCrmLead.customer_id == customer_id).values(
            matched_learner_number=learner_number
        ))
    db.execute(update(MainCrmLead).where(MainCrmLead.customer_id == customer_id).values(
        status_of_lead="CONVERTED"
    ))


def backfill_customer_links(db: Session):
    for lead in db.execute(select(MainCrmLead).where(MainCrmLead.customer_id.is_(None))).scalars().all():
        lead.customer_id = resolve_customer(db, lead.full_name, lead.email, lead.phone_number).id
    for profile in db.execute(select(LearnersCrmProfile).where(LearnersCrmProfile.customer_id.is_(None))).scalars().all():
        profile.customer_id = resolve_customer(db, profile.learner_name, profile.email_id, profile.phone_number).id
        mark_customer_converted(db, profile.customer_id)
    for learner in db.execute(select(Learner).where(Learner.customer_id.is_(None))).scalars().all():
        learner.customer_id = resolve_customer(db, learner.name, learner.email_id, learner.contact_number).id
        mark_customer_converted(db, learner.customer_id, learner.learner_number)
    db.commit()
