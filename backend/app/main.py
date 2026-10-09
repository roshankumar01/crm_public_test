from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import inspect, text, select, update
from app.database import Base, SessionLocal, engine
from app.models import LEARNERS_CRM_INDEXES, MAIN_CRM_INDEXES, UPSELL_INDEXES, MaintenanceRun, LearnersCrmEnrollment, UpsellCourseCase, UpsellCourseActivity
from app.routers import analytics, auth, campaigns, company_dashboard, counselor_dashboard, dashboard, learner_course_mapping, learners, learners_crm, leads, main_crm, opportunities, recommendation_rules, uploads, upsell_management, reminders
from app.services.schema_migrations import ensure_counselor_action_columns

Base.metadata.create_all(bind=engine)
ensure_counselor_action_columns(engine)
for table in (UpsellCourseCase.__table__, UpsellCourseActivity.__table__):
    for index in table.indexes:
        index.create(bind=engine, checkfirst=True)
if "subcategory_id" not in {column["name"] for column in inspect(engine).get_columns("upsell_course_cases")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE upsell_course_cases ADD COLUMN subcategory_id INTEGER REFERENCES learner_course_subcategories(id) ON DELETE SET NULL"))
if "current_slot" not in {column["name"] for column in inspect(engine).get_columns("upsell_course_cases")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE upsell_course_cases ADD COLUMN current_slot INTEGER"))
        connection.execute(text("CREATE UNIQUE INDEX uq_upsell_case_current ON upsell_course_cases (lead_id, current_slot)"))
if "normalized_course_name" not in {column["name"] for column in inspect(engine).get_columns("learners_crm_enrollments")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE learners_crm_enrollments ADD COLUMN normalized_course_name VARCHAR(500)"))
        connection.execute(text("CREATE INDEX ix_learners_crm_enrollments_normalized_course_name ON learners_crm_enrollments (normalized_course_name)"))
if "counselor_user_id" not in {column["name"] for column in inspect(engine).get_columns("learners_crm_enrollments")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE learners_crm_enrollments ADD COLUMN counselor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))
        connection.execute(text("CREATE INDEX ix_learners_crm_enrollments_counselor_user_id ON learners_crm_enrollments (counselor_user_id)"))
if "assigned_at" not in {column["name"] for column in inspect(engine).get_columns("main_crm_leads")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE main_crm_leads ADD COLUMN assigned_at TIMESTAMP WITH TIME ZONE"))
        connection.execute(text("UPDATE main_crm_leads SET assigned_at = created_at WHERE assigned_to_user_id IS NOT NULL"))
for index in (*MAIN_CRM_INDEXES, *LEARNERS_CRM_INDEXES):
    index.create(bind=engine, checkfirst=True)
if "marketing_type" not in {column["name"] for column in inspect(engine).get_columns("marketing_campaigns")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE marketing_campaigns ADD COLUMN marketing_type VARCHAR(100) NOT NULL DEFAULT 'Other'"))
if "email" not in {column["name"] for column in inspect(engine).get_columns("users")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(320)"))
if "region" not in {column["name"] for column in inspect(engine).get_columns("users")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN region VARCHAR(255)"))
if "country" not in {column["name"] for column in inspect(engine).get_columns("users")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN country VARCHAR(100)"))
if "customer_id" not in {column["name"] for column in inspect(engine).get_columns("main_crm_leads")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE main_crm_leads ADD COLUMN customer_id INTEGER"))
        connection.execute(text("CREATE INDEX ix_main_crm_leads_customer_id ON main_crm_leads (customer_id)"))
if "country" not in {column["name"] for column in inspect(engine).get_columns("main_crm_leads")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE main_crm_leads ADD COLUMN country VARCHAR(100)"))
        connection.execute(text("CREATE INDEX ix_main_crm_leads_country ON main_crm_leads (country)"))
if "customer_id" not in {column["name"] for column in inspect(engine).get_columns("learners_crm_profiles")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE learners_crm_profiles ADD COLUMN customer_id INTEGER"))
        connection.execute(text("CREATE INDEX ix_learners_crm_profiles_customer_id ON learners_crm_profiles (customer_id)"))
learner_profile_columns = {column["name"] for column in inspect(engine).get_columns("learners_crm_profiles")}
if "phone_number" not in learner_profile_columns:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE learners_crm_profiles ADD COLUMN phone_number VARCHAR(100)"))
if "normalized_phone" not in learner_profile_columns:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE learners_crm_profiles ADD COLUMN normalized_phone VARCHAR(40)"))
        connection.execute(text("CREATE INDEX ix_learners_crm_profiles_normalized_phone ON learners_crm_profiles (normalized_phone)"))
if "customer_id" not in {column["name"] for column in inspect(engine).get_columns("learners")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE learners ADD COLUMN customer_id INTEGER"))
        connection.execute(text("CREATE INDEX ix_learners_customer_id ON learners (customer_id)"))
if "unique_number" not in {column["name"] for column in inspect(engine).get_columns("upload_batches")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE upload_batches ADD COLUMN unique_number VARCHAR(50)"))
        connection.execute(text("CREATE UNIQUE INDEX ix_upload_batches_unique_number ON upload_batches (unique_number)"))
if "subcategory_id" not in {column["name"] for column in inspect(engine).get_columns("learner_course_mappings")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE learner_course_mappings ADD COLUMN subcategory_id INTEGER"))
        connection.execute(text("CREATE INDEX ix_learner_course_mappings_subcategory_id ON learner_course_mappings (subcategory_id)"))
if "customer_id" not in {column["name"] for column in inspect(engine).get_columns("leads")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE leads ADD COLUMN customer_id INTEGER"))
        connection.execute(text("CREATE INDEX ix_leads_customer_id ON leads (customer_id)"))
        connection.execute(text("CREATE INDEX ix_leads_customer_opportunity ON leads (customer_id, opportunity_key)"))
lead_columns = {column["name"]: column for column in inspect(engine).get_columns("leads")}
if "counselor_from_main" not in lead_columns:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE leads ADD COLUMN counselor_from_main BOOLEAN NOT NULL DEFAULT false"))
if "counselor_from_daily" not in lead_columns:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE leads ADD COLUMN counselor_from_daily BOOLEAN NOT NULL DEFAULT false"))
if "stage" not in lead_columns:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE leads ADD COLUMN stage INTEGER"))
if "reason" not in lead_columns:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE leads ADD COLUMN reason TEXT"))
if engine.dialect.name == "postgresql" and not lead_columns["learner_number"]["nullable"]:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE leads ALTER COLUMN learner_number DROP NOT NULL"))
for index in UPSELL_INDEXES:
    index.create(bind=engine, checkfirst=True)
with engine.begin() as connection:
    connection.execute(text("UPDATE users SET email = 'person_a@gmail.com' WHERE username = 'person_a' AND email IS NULL"))
    connection.execute(text("UPDATE users SET email = 'person_b@gmail.com' WHERE username = 'person_b' AND email IS NULL"))

from app.services.customer_identity import backfill_customer_links
from app.services.counselor_sync import sync_main_counselors
from app.services.upsell_management import preserve_legacy_conversions
from app.services.learner_course_mapping import seed_course_mapping, normalize_course_name
with SessionLocal() as session:
    seed_course_mapping(session)
    while True:
        rows = session.execute(select(LearnersCrmEnrollment.enrolment_id, LearnersCrmEnrollment.course_name, LearnersCrmEnrollment.updated_at)
            .where(LearnersCrmEnrollment.normalized_course_name.is_(None)).limit(500)).all()
        if not rows: break
        session.execute(update(LearnersCrmEnrollment), [{"enrolment_id": row.enrolment_id,
            "normalized_course_name": normalize_course_name(row.course_name), "updated_at": row.updated_at} for row in rows])
        session.commit()
    if session.get(MaintenanceRun, "customer_links_v1") is None:
        backfill_customer_links(session)
        session.add(MaintenanceRun(key="customer_links_v1"))
        session.commit()
    if session.get(MaintenanceRun, "migration_status_v2") is None:
        main_crm.backfill_migration_statuses(session)
        session.add(MaintenanceRun(key="migration_status_v2"))
        session.commit()

    sync_main_counselors(session)
    if session.get(MaintenanceRun, "upsell_course_conversions_v1") is None:
        preserve_legacy_conversions(session)
        session.add(MaintenanceRun(key="upsell_course_conversions_v1"))
    session.commit()

app = FastAPI(title="Learning CRM API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reminders.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(company_dashboard.router)
app.include_router(counselor_dashboard.router)
app.include_router(learners.router)
app.include_router(opportunities.router)
app.include_router(leads.router)
app.include_router(upsell_management.router)
app.include_router(analytics.router)
app.include_router(campaigns.router)
app.include_router(uploads.router)
app.include_router(main_crm.router)
app.include_router(learners_crm.router)
app.include_router(learner_course_mapping.router)
app.include_router(recommendation_rules.router)


@app.get("/health")
def health():
    return {"status": "ok"}
