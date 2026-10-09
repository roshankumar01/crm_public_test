from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    primary_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    primary_phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CustomerIdentity(Base):
    __tablename__ = "customer_identities"
    __table_args__ = (UniqueConstraint("identity_type", "normalized_value", name="uq_customer_identity_value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    identity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    normalized_value: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    raw_value: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Learner(Base):
    __tablename__ = "learners"

    learner_number: Mapped[str] = mapped_column(String(50), primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nationality: Mapped[str | None] = mapped_column(String(100))
    contact_number: Mapped[str | None] = mapped_column(String(100))
    email_id: Mapped[str | None] = mapped_column(String(320))
    last_activity_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    course_records: Mapped[list["LearnerCourseRecord"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    program_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    records: Mapped[list["LearnerCourseRecord"]] = relationship(back_populates="course")


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_type: Mapped[str] = mapped_column(String(50), nullable=False)
    unique_number: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PROCESSING", nullable=False)
    rows_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MaintenanceRun(Base):
    __tablename__ = "maintenance_runs"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LearnerCourseRecord(Base):
    __tablename__ = "learner_course_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_number: Mapped[str] = mapped_column(
        ForeignKey("learners.learner_number", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"), nullable=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), default="COURSE_RESULT", nullable=False)
    enrollment_status: Mapped[str | None] = mapped_column(String(50))
    result: Mapped[str | None] = mapped_column(String(50))
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    learner: Mapped["Learner"] = relationship(back_populates="course_records")
    course: Mapped["Course"] = relationship(back_populates="records")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("learner_number", "opportunity_key", name="uq_lead_learner_opportunity"),
        Index("ix_leads_customer_opportunity", "customer_id", "opportunity_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    learner_number: Mapped[str | None] = mapped_column(
        ForeignKey("learners.learner_number", ondelete="SET NULL"), nullable=True, index=True
    )
    opportunity_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30), default="NEW", nullable=False, index=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    counselor_from_main: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    counselor_from_daily: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    channel: Mapped[str | None] = mapped_column(String(30), index=True)
    campaign_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_number: Mapped[str] = mapped_column(
        ForeignKey("learners.learner_number", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    marketing_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Other", index=True)
    upload_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("upload_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


UPSELL_INDEXES = (
    Index("ix_leads_active_updated_id", Lead.is_active, Lead.updated_at.desc(), Lead.id.desc()),
    Index("ix_leads_active_key_stage_trigger", Lead.is_active, Lead.opportunity_key, Lead.stage, Lead.trigger_date),
    Index("ix_leads_owner_active_updated", Lead.assigned_to_user_id, Lead.is_active, Lead.updated_at.desc()),
    Index("ix_leads_customer_active", Lead.customer_id, Lead.is_active),
    Index("ix_lead_activities_lead_type", LeadActivity.lead_id, LeadActivity.activity_type),
    Index("ix_marketing_campaigns_learner_created", MarketingCampaign.learner_number, MarketingCampaign.created_at.desc(), MarketingCampaign.id.desc()),
    Index("ix_customers_updated_id", Customer.updated_at.desc(), Customer.id.desc()),
    Index("ix_learner_course_records_number_date", LearnerCourseRecord.learner_number, LearnerCourseRecord.event_date.desc()),
)


class MainCrmLead(Base):
    __tablename__ = "main_crm_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    normalized_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    course: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_of_lead: Mapped[str] = mapped_column(String(50), default="NEW", nullable=False, index=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sales_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_learner_number: Mapped[str | None] = mapped_column(
        ForeignKey("learners.learner_number", ondelete="SET NULL"), nullable=True, index=True
    )
    upload_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("upload_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MainCrmActivity(Base):
    __tablename__ = "main_crm_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("main_crm_leads.id", ondelete="CASCADE"), nullable=False, index=True)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id", ondelete="CASCADE"), nullable=True, index=True)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    activity_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    campaign_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campaign_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    course: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_user_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


MAIN_CRM_INDEXES = (
    Index("ix_main_crm_leads_customer_updated_id", MainCrmLead.customer_id, MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_created_id", MainCrmLead.created_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_status_updated_id", MainCrmLead.status_of_lead, MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_actual_source_updated_id", MainCrmLead.source, MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_course_updated_id", MainCrmLead.course, MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_created_status", MainCrmLead.created_at, MainCrmLead.status_of_lead),
    Index("ix_main_crm_leads_owner_status_course", MainCrmLead.assigned_to_user_id, MainCrmLead.status_of_lead, MainCrmLead.course),
    Index("ix_main_crm_leads_updated_id", MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_source_updated_id", MainCrmLead.source_category, MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_owner_updated_id", MainCrmLead.assigned_to_user_id, MainCrmLead.updated_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_owner_assigned_id", MainCrmLead.assigned_to_user_id, MainCrmLead.assigned_at.desc(), MainCrmLead.id.desc()),
    Index("ix_main_crm_leads_source_status", MainCrmLead.source_category, MainCrmLead.status_of_lead),
    Index("ix_main_crm_activities_lead_type", MainCrmActivity.lead_id, MainCrmActivity.activity_type),
    Index("ix_main_crm_activities_lead_date", MainCrmActivity.lead_id, MainCrmActivity.activity_date.desc(), MainCrmActivity.id.desc()),
)


class LearnersCrmProfile(Base):
    __tablename__ = "learners_crm_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    learner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_id: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class LearnersCrmEnrollment(Base):
    __tablename__ = "learners_crm_enrollments"

    enrolment_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners_crm_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_course_name: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    enrolment_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_status: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    upload_batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    counselor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DailyLearnerRow(Base):
    __tablename__ = "daily_learner_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    enrolment_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    learner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    normalized_email: Mapped[str | None] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(100))
    normalized_phone: Mapped[str | None] = mapped_column(String(40), index=True)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_date: Mapped[date | None] = mapped_column(Date)
    enrolment_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    counselor_name: Mapped[str | None] = mapped_column(String(255))
    counselor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    matched_main_lead_id: Mapped[int | None] = mapped_column(ForeignKey("main_crm_leads.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    verified_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


LEARNERS_CRM_INDEXES = (
    Index("ix_learners_crm_enrollments_learner_updated", LearnersCrmEnrollment.learner_id, LearnersCrmEnrollment.updated_at.desc()),
    Index("ix_learners_crm_enrollments_learner_date", LearnersCrmEnrollment.learner_id, LearnersCrmEnrollment.enrolment_date.desc()),
    Index("ix_learners_crm_profiles_updated_id", LearnersCrmProfile.updated_at.desc(), LearnersCrmProfile.id.desc()),
)


@event.listens_for(LearnersCrmEnrollment, "before_insert")
@event.listens_for(LearnersCrmEnrollment, "before_update")
def normalize_enrollment_course(mapper, connection, enrollment):
    from app.services.learner_course_mapping import normalize_course_name
    enrollment.normalized_course_name = normalize_course_name(enrollment.course_name)


class LearnerCourseCategory(Base):
    __tablename__ = "learner_course_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class LearnerCourseSubcategory(Base):
    __tablename__ = "learner_course_subcategories"
    __table_args__ = (UniqueConstraint("category_id", "normalized_name", name="uq_learner_course_subcategory"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("learner_course_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class LearnerCourseMapping(Base):
    __tablename__ = "learner_course_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("learner_course_categories.id", ondelete="RESTRICT"), nullable=False, index=True)
    subcategory_id: Mapped[int | None] = mapped_column(ForeignKey("learner_course_subcategories.id", ondelete="RESTRICT"), nullable=True, index=True)
    course_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)


class UpsellContactInfo(Base):
    __tablename__ = "upsell_contact_info"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UpsellInfoEdit(Base):
    __tablename__ = "upsell_info_edits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CounselorAction(Base):
    __tablename__ = "counselor_actions"
    __table_args__ = (
        Index("ix_counselor_actions_actor_time", "user_id", "created_at", "id"),
        Index("ix_counselor_actions_type_time", "action_type", "created_at", "id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    main_lead_id: Mapped[int | None] = mapped_column(ForeignKey("main_crm_leads.id", ondelete="CASCADE"), index=True)
    upsell_lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    upsell_case_id: Mapped[int | None] = mapped_column(ForeignKey("upsell_course_cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_counselor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    assigned_counselor_name: Mapped[str | None] = mapped_column(String(255))
    action_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    before_status: Mapped[str | None] = mapped_column(String(50))
    after_status: Mapped[str | None] = mapped_column(String(50))
    before_note: Mapped[str | None] = mapped_column(Text)
    after_note: Mapped[str | None] = mapped_column(Text)
    course_name: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str | None] = mapped_column(String(255))
    channel: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LeadReminder(Base):
    __tablename__ = "lead_reminders"
    __table_args__ = (Index("ix_lead_reminders_pending_due", "completed_at", "due_date", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    main_lead_id: Mapped[int | None] = mapped_column(ForeignKey("main_crm_leads.id", ondelete="CASCADE"), unique=True)
    upsell_lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), unique=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConversionVerification(Base):
    __tablename__ = "conversion_verifications"
    id = mapped_column(Integer, primary_key=True)
    main_lead_id = mapped_column(Integer, ForeignKey("main_crm_leads.id", ondelete="CASCADE"), unique=True)
    upsell_case_id = mapped_column(Integer, ForeignKey("upsell_course_cases.id", ondelete="CASCADE"), unique=True)
    customer_id = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    verified_by_id = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    verified_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    course_name = mapped_column(String(500), nullable=True)
    normalized_subcategory = mapped_column(String(255), nullable=True)


class UpsellCourseCase(Base):
    __tablename__ = "upsell_course_cases"
    __table_args__ = (
        UniqueConstraint("lead_id", "current_slot", name="uq_upsell_case_current"),
        Index("ix_upsell_cases_lead_status", "lead_id", "status"),
        Index("ix_upsell_cases_status_converted", "status", "converted_at", "id"),
        Index("ix_upsell_cases_customer_subcategory", "customer_id", "normalized_subcategory"),
        Index("ix_upsell_cases_customer_status_date", "customer_id", "status", "converted_at", "id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    mapping_id: Mapped[int | None] = mapped_column(ForeignKey("learner_course_mappings.id", ondelete="SET NULL"))
    subcategory_id: Mapped[int | None] = mapped_column(ForeignKey("learner_course_subcategories.id", ondelete="SET NULL"))
    main_category: Mapped[str] = mapped_column(String(255))
    sub_category: Mapped[str] = mapped_column(String(255))
    normalized_subcategory: Mapped[str] = mapped_column(String(255))
    course_name: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="NEW", nullable=False)
    current_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counselor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    converted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UpsellCourseActivity(Base):
    __tablename__ = "upsell_course_activities"
    __table_args__ = (Index("ix_upsell_course_activity_case_created", "case_id", "created_at", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("upsell_course_cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    activity_type: Mapped[str] = mapped_column(String(40))
    campaign_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
