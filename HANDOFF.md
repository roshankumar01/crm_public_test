# Learning CRM — New Chat Handoff

## Daily learner uploads and verification (October 2026)

- The existing Learners CRM upload is labeled **Learners migrated**. A separate **Daily learners** upload accepts `enrolment_id`, `learner_name`, `email`, `phone`, `course`, `created_date`, `enrolment_date`, `start_date`, and `counselor_name` (headers are normalized). Each row needs an ID, learner name, course, enrolment date, and email or phone.
- Daily rows are staged in `daily_learner_rows`. A row with a Main CRM email/phone match and a uniquely matched active counselor is verified automatically and becomes an enrolment. Other rows remain pending and cannot create Upsell opportunities until an admin corrects email/phone and counselor, then clicks Verify on the Learners CRM Verification page. Explicit admin verification can approve a learner even if no Main CRM lead matches.
- Daily enrolments retain the file counselor (`learners_crm_enrollments.counselor_user_id`); Upsell opportunities inherit that counselor ahead of the Main CRM assignment. Learner profiles display that ownership. Matching migrated enrolments show green ticks; unmatched migrated enrolments show red ticks and still contribute to Upsell. Pending daily rows show gray ticks on the verification page.
- The new upload uses the existing progress job and skipped-row download. Both full and selected data reset remove staged daily rows. Startup adds the counselor columns and creates the staging table/indexes. Restart the backend to apply schema changes; no data reset is required.
- Verified with 95 backend tests, including daily matching, pending/admin verification, migrated match status and Upsell counselor ownership, plus the frontend production build. Full replacement files: `outputs/daily-learners-verification-files.zip`.

## Unique counselor updates (October 2026)

- The Counselors dashboard now separates raw action totals from unique people updated within the selected date range. Identity uses the shared `customer_id` across Main and Upsell; an unlinked record falls back to its workspace lead ID. Team card unique counts deduplicate across counselors and both CRMs. Each counselor chart value deduplicates that counselor's updates; Main and Upsell unique breakdowns may overlap for someone contacted in both workspaces.
- The Overview cards show unique people alongside total/Main/Upsell update counts. The chart has Every update / Unique people counting controls plus its existing Overview, Leads given, Main CRM and Upsell views. Unique Overview uses one bar for the deduplicated total so overlapping CRM counts are not stacked as if additive.
- The Change log has All updates / Unique people filters. Unique mode shows the latest action per linked person with the count of that counselor's actions for that person; View all updates opens that person's complete filtered history. Date range and counselor filters still apply, with SQL pagination.
- Counts and deduplication are calculated in SQL with existing lead/action indexes; no audit records were rewritten. Verified with 91 backend tests, frontend production build, counselor dashboard browser test, and live PostgreSQL summary/log queries. Full replacement files: `outputs/unique-counselor-updates-files.zip`.

## Fix for Failed to fetch on status and notes (October 2026)

- Main CRM status changes and manual notes failed because an existing `counselor_actions` table was created before the `actor_name` and `assigned_counselor_name` columns were added to the model. ORM writes raised PostgreSQL `UndefinedColumn`, which surfaced as "Failed to fetch" in the browser.
- Startup now idempotently adds both missing columns to existing databases and backfills actor/counselor names for retained audit rows. The local PostgreSQL schema was upgraded. Fresh databases already get the full schema from `create_all`.
- The Main lead profile keeps its content visible after a write error and shows the error inline, so a failed note/status save can be retried. Successful attempts clear the error.
- Verified Main note and status writes, and Upsell note and status writes, against real PostgreSQL leads inside rollback-only transactions; no diagnostic changes remained. 90 backend tests, production frontend build and Main profile render check pass. Full replacement files: `outputs/status-note-fetch-fix-files.zip`.

## Counselor dashboard (October 2026)

- Admin-only Dashboard workspace now has `/dashboard/counselors` Overview and `/dashboard/counselors/changes` Change log. No separate sales-head account role was added. Cards show Main CRM leads given, total counselor-authored updates, and the Main/Upsell split. The vertical comparison includes every counselor, even those with zero actions, with Overview, leads, Main, and Upsell views. Clicking a counselor opens their log.
- Lead counts use the current Main CRM assignee and the date of the latest assignment. Main leads now store indexed `assigned_at`; manual reassignment and uploads set it. Migration uses old CRM `Last assigned at` when available, then its lead creation date. Existing assigned records with no stored assignment timestamp are backfilled with lead creation time on startup. Historical prior reassignment events cannot be reconstructed, so these are current-assignment counts, not an all-time transfer ledger.
- Update counts use the indexed append-only `counselor_actions` table and credit the actual counselor who saved the note/status/contact action, excluding admin edits. The log is admin-only, filters to one counselor and the chosen India-calendar date range, and paginates 50 rows. It shows actor, lead, course, status transition, previous/new note, and flags notes of 1–3 characters. Upsell status/conversion actions now retain the previous note in the audit fact too.
- Date controls provide Today, Yesterday, Last 7 days, Last 1 month, custom range, and All time. Both pages retain the selected range in the browser session. SQL groups counts without loading all leads/actions; the log uses indexed actor/time lookup.
- Restart backend for the `assigned_at` migration/index and refresh frontend. No CRM data reset is needed. Checks: 89 backend tests, production frontend build, counselor dashboard browser interaction test and visual review, and live PostgreSQL schema/route inspection. Full replacement contents: `outputs/counselor-dashboard-files.zip`.

## Counselor activity facts and status notes (October 2026)

- No sales head dashboard has been built yet. Main and Upsell CRM now collect indexed, append-only `counselor_actions` facts for future counselor performance reporting. Each fact records action time, acting account and name, assigned counselor and name at that time, workspace lead/course, source where available, status before/after, note before/after and contact channel. These facts are kept separately from the learning journey and personal edit history.
- Manual status changes in both pipelines, the Main lead profile, the Upsell course panel and Upsell course conversion require a fresh, nonblank contact note. Changing a dropdown alone does not save. The API checks the note too, rejects an unchanged latest note and writes the status, conversation activity and audit fact in one transaction. Repeating the same status or already completed conversion does not create a fake activity fact. Upload-driven status updates remain automatic.
- Main CRM note additions and Upsell contact saves/edits also append audit facts with actor and note changes. The original contact history remains visible. Total data reset clears these new facts while keeping user accounts. Existing historical actions cannot have their actors reconstructed; new actions are tracked from this release onward.
- Restart the backend to create the table and refresh the frontend. No reset or re-upload is needed. Checks: 85 backend tests, production frontend build, Main pipeline and Upsell Manage browser workflows, and live PostgreSQL table/index inspection passed. Full replacement files: `outputs/sales-activity-tracking-files.zip`.

## Counselor reminders (September 2026)

- Both Main CRM and Upsell have separate Reminders pages (`/crm/reminders`, `/upsell/reminders`) and Set reminder controls in every pipeline row and lead profile. Counselors choose N calendar days (including Today), optionally add a contact note, mark done or reschedule. There is one current reminder per lead per workspace; rescheduling reopens a completed reminder.
- Reminders follow the lead's current assigned counselor. Counselors can only list/read/change reminders for their assigned leads. Admins can view/filter all counselors and schedule reminders; an unassigned lead's reminder is attributed to the admin who created it.
- Countdown uses India company dates. Zero days means Contact today; past dates remain highlighted with overdue days until marked done or rescheduled. The page has Due / Upcoming / Done counts and filters, profile links and stable 50-row pagination. An open tracker refreshes at the company-day change, without per-lead polling or daily database writes. Pipeline controls fetch reminder details only when opened.
- New indexed `lead_reminders` table and `/reminders` API are created/registered on startup. Reminder actions are separate from lead status, personal edit history and learning journey. Deleting a lead cascades to its reminder; Total data reset and both reset CLI scripts also clear reminders.
- Checks: 78 backend tests passed; Main/Upsell reminder browser flows, the existing Upsell manage/verification browser flow, production build and live PostgreSQL reminder queries passed. The database remains empty after the previous reset; tests did not insert real leads or reminders.
- Restart the backend and refresh the frontend; no data reset or re-upload is needed. Full replacement contents: `outputs/counselor-reminder-files.zip`.


## Complete CRM data reset (September 2026)

- The previous selected-upload reset deliberately retained manual activity and shared contacts, which left two Main CRM leads after uploads were gone. Old inactive Upsell leads/contact identities also remained.
- Data reset now offers Total data reset (default) or Selected upload files only. Total reset works even with zero uploads, requires the existing admin account and typed `RESET ALL CRM DATA`, and clears all business records across the three CRMs: uploads, leads, contacts/identities, enrolments/results, notes, edits, course cases/activities and verifications. Accounts, sessions, course catalog/mappings and configuration are preserved. Selected mode keeps its original file-specific behavior.
- `POST /uploads/reset-all` and both reset CLI scripts share `services/data_reset.py`. Records are removed in foreign-key-safe order in one transaction; active uploads block the reset, and recommendation revision invalidation prevents old opportunities from reappearing.
- At the user's request, local PostgreSQL `upsell_db` was cleared: two Main CRM leads, five Main activities, 10,247 old Upsell leads, 67,892 contacts and 127,167 identities. All CRM business tables and all three overview responses were verified empty/zero. User accounts/sessions/catalog/mappings were verified preserved.
- Checks: 69 backend tests passed; production frontend build passed; total-reset browser flow passed, including reset with no remaining upload files. Restart the backend for the new endpoint; refresh the browser for cleared values. Full updated files: `outputs/data-reset-fix-files.zip`.


## Conversion verification (September 2026)

- Main CRM and Upsell mismatch pages have admin-only Verify enrolment controls, Pending / Verified / All filters, counselor details, 50-row pagination and Excel exports with verification provenance and actor/date.
- Thick gray ticks identify unverified conversions; green ticks mean an uploaded registration match or explicit admin verification. Ticks also appear on converted pipeline rows, profiles and converted course blocks.
- Main CRM matches the person only against actual uploaded Learners CRM enrolments or result records. Upsell matches the person plus mapped course subcategory (including alternate variants) or the corresponding board result course. Retained contact shells after reset do not establish registration evidence.
- Admin verification always means Enrolled, never Completed or PASS. IGC/IDIP passing still requires uploaded evidence. A manual verification stores the person/course snapshot, admin and verification time in `conversion_verifications`; repeated clicks preserve the original audit.
- Unverified course conversions cannot manufacture enrolment/completion journey events. Verified enrolments appear in the shared journey without writing fake upload rows. Actual uploaded enrolment/result events supersede duplicate virtual enrolments; the admin audit remains. Main person-only matches do not invent enrolment in an unrelated Main lead course.
- Verified mapped subcategories participate in enrolment/cooling eligibility and prevent repeat recommendations, without unlocking pass-dependent stages. Main course/status edits invalidate the appropriate cached recommendation state. Customer merges preserve verification links.
- Startup creates the indexed verification table automatically. Restart the backend (or rebuild Docker); no reset or re-upload is required.
- Verification: 67 backend tests, production frontend build, Main/Upsell browser verification flows and live PostgreSQL report queries pass. Full replacement files are in `outputs/conversion-verification-files.zip`.


## Upsell Manage course workflow (September 2026)

- Manage displays suggestions, personal information, three course selectors (main category/subcategory/course), course status/contact history, converted course blocks and the expandable edit history at the bottom.
- Any mapped course can be selected. A conversion closes that course panel and opens an empty next panel. Existing unfinished panels can be resumed. Contact notes can be edited until conversion; completed blocks preserve their history, conversion date, category, course and counselor.
- Personal information inherits Main CRM fields, with local Upsell overrides stored separately. Later Main CRM changes supersede the affected local values. Upsell personal edits/status never write to Main CRM or change registration identity keys. The last 10 information edits per lead record actor and before/after values; these edits are excluded from learning journey/contact activity.
- Course conversions appear in the shared learning journey across workspaces. Existing Main CRM converted leads are shown separately for reference in Manage. A counselor-reported conversion does not manufacture an uploaded registration or overwrite Main CRM lead status.
- `/upsell/mismatch` checks converted course panels against the same customer and mapped subcategory in Learners CRM or IGC/IDIP results. Course variants within one subcategory match. The report has counselor details, date filtering, pagination and Excel export.
- New tables: `upsell_contact_info`, `upsell_info_edits`, `upsell_course_cases`, `upsell_course_activities`. Startup also backfills an indexed normalized enrolment course name without altering its update date and preserves legacy conversions without inventing a course variant.
- Upsell analytics and company dashboard count persistent course conversions so starting another panel cannot erase earlier conversions. Upsell Excel exports include course conversations and their contact history.
- Backend restart applies schema/index updates automatically; no data reset or re-upload is needed. Docker users rebuild with `docker compose up -d --build`.
- Tests: `backend/tests/test_upsell_management.py` and `frontend/tests/upsellManagementInteractions.test.mjs`.

## Main CRM counselor inheritance (September 2026)

- Learners CRM and Upsell learner lists/profiles display the Main CRM counselor for their shared customer ID (normalized email/phone matching).
- Upsell opportunities inherit the actual counselor account, so pipeline filters, analytics and counselor access use the same assignment.
- If a contact has multiple assigned Main CRM records, the most recently updated record wins; ties use the highest lead ID. Only active counselor accounts qualify.
- Main CRM imports and assignment changes reconcile existing opportunities. Opportunity creation reconciles newly generated leads. Unmatched manual assignments remain intact; removing the Main CRM owner clears only inherited assignments.
- Restart the backend after updating: startup adds `leads.counselor_from_main`, creates the contact/date lookup index and reconciles existing assignments. No reset or re-upload is needed.
- Synchronization lives in `backend/app/services/counselor_sync.py`; page-level owner lookups are batched. Tests: `backend/tests/test_counselor_sync.py`, `frontend/tests/counselorDisplay.test.mjs`.

## Read this first

> **Current-state note (September 2026):** The original Stage 1 sections below remain useful for the Upsell CRM, but the application has since expanded into two connected workspaces. The "Full CRM expansion" section near the end of this file supersedes older route and limitation notes.

This repository is the latest agreed snapshot of a teaching-company CRM project. Inspect this file and the repository before changing code.

When changing code for the user:

1. explain what changed
2. explain why
3. give the **full replacement content** of each changed file, not only a diff
4. mention any DB/setup/migration step
5. keep explanations beginner-friendly
6. preserve working architecture unless there is a real reason to change it

---

## Business model

Current courses:

- IGC
- ID1
- ID2
- ID3

Important:

- `IDP` is **not a course**.
- IDP is a program/family containing `ID1`, `ID2`, `ID3`.
- ID1/ID2/ID3 are independent courses and have no fixed order.
- Stage 1 trusts `learner_number` as the unique learner key.
- No ML/DL yet. Everything is rule-based Python.

---

## Current opportunity/recommendation rules

Single source of truth:

```text
backend/app/services/course_rules.py
```

Do not duplicate these rules in React or importer files.

### IGC → IDP Entry

If learner completed/passed IGC and has **no activity** in ID1, ID2 or ID3:

```text
IDP Entry lead
```

### Cross-sell within IDP

Once a learner completes any ID course, every other ID course they have **never entered** becomes an opportunity.

Examples:

```text
ID1 PASS -> ID2 + ID3
ID2 PASS -> ID1 + ID3
ID3 PASS -> ID1 + ID2
ID1 PASS + ID3 PASS -> ID2
ID1 PASS + ID2 PASS -> ID3
ID2 PASS + ID3 PASS -> ID1
ID1 + ID2 + ID3 complete -> no current ID opportunity
```

Existing activity prevents recommending the same target again.

Example:

```text
ID1 PASS
ID2 ENROLLED
```

Expected:

```text
ID3 only
```

---

## Main pages

```text
/                     Dashboard
/learners             Learners/search
/learners/:id         Learner profile + learning journey
/opportunities        Generic Opportunities page
/uploads              Excel/CSV uploads
```

Compatibility route:

```text
/opportunities/idp
```

currently opens the generic Opportunities page.

---

## Opportunities page

Sections:

1. IDP Entry
2. ID1 Opportunities
3. ID2 Opportunities
4. ID3 Opportunities

One learner can produce more than one opportunity.

Example:

```text
ID1 PASS
```

means:

```text
1 opportunity learner
2 opportunities (ID2 and ID3)
```

---

## Database

Main tables:

```text
learners
courses
learner_course_records
upload_batches
```

### learners

Current learner profile. Key:

```text
learner_number
```

### courses

Current seed:

```text
IGC  -> program_code IGC
ID1  -> program_code IDP
ID2  -> program_code IDP
ID3  -> program_code IDP
```

There is no IDP course row.

### learner_course_records

Immutable dated learning history.

Important fields:

```text
learner_number
course_id
event_date
event_type
enrollment_status
result
details JSON
raw_data JSON
row_hash
```

Do not overwrite old history.

### upload_batches

Tracks each uploaded file and its import status/counts.

---

## Learner journey

The learner profile should visually show chronological learning history and recommendations.

Example:

```text
01 May 2026
IGC - FAIL
IG1 48
IG2 60

20 May 2026
IGC - PASS
IG1 75
IG2 100

10 Jun 2026
ID1 - PASS
```

Course-specific `details` JSON is rendered dynamically in the frontend, so many new display-only fields require no frontend change.

---

## Upload architecture

Course-specific importer files live in:

```text
backend/app/services/importers/
```

Current files:

```text
common.py
registry.py
service.py
igc.py
idp.py
```

### common.py

Shared logic:

- value cleaning
- header normalization
- date parsing
- result/status normalization
- learner upsert
- duplicate row hash
- database save

### registry.py

Automatically discovers importer files.

Every course importer must expose:

```python
IMPORT_TYPE
DISPLAY_NAME
DESCRIPTION

def validate_columns(df):
    ...

def parse_row(row):
    ...
```

### service.py

Generic upload coordinator. It must **not** contain course-specific Excel mapping.

### igc.py

Only IGC Excel knowledge.

### idp.py

Only ID1/ID2/ID3 Excel knowledge.

---

## Current IGC Excel expectations

Headers are normalized by removing capitalization, spaces, `_`, `-`, etc.

Examples:

```text
Learner number
Learner_Number
LEARNER-NUMBER
```

all become:

```text
learnernumber
```

Required IGC headers after normalization:

```text
learnernumber
date
overallresult
```

Optional/currently supported:

```text
name
nationality
contactnumber
emailid
ig1result
ig2result
unit
bilingualdictionary
reg
```

IGC currently creates a `COURSE_RESULT` event.

---

## Current IDP Excel expectations

Here `IDP Excel` means one file containing activity/results for the ID course family.

Supported preliminary formats:

### Format A

```text
Learner number | Course | Result | Status | date
```

Course-like header may be:

```text
Course
Course Code
Module
Unit
```

Course values can include ID1, ID2, ID3.

### Format B

```text
Learner number | ID1 Result | ID2 Result | ID3 Result | date
```

One spreadsheet row may create multiple DB records.

When a real IDP spreadsheet is supplied, normally update only:

```text
backend/app/services/importers/idp.py
```

---

## Adding a future course

Example: IELTS.

### 1. Add course catalog entry

Update:

```text
backend/seed_courses.py
```

then run:

```powershell
python .\seed_courses.py
```

### 2. Add importer

Create:

```text
backend/app/services/importers/ielts.py
```

with metadata, `validate_columns()` and `parse_row()`.

The importer registry discovers it automatically, and the frontend upload dropdown reads available importers from:

```text
GET /uploads/import-types
```

Normally you do **not** update registry.py, service.py, uploads.py, api.js or UploadsPage.jsx for each new importer.

---

## Adding a new Excel column

### Display-only/course-specific field

Examples:

```text
Exam Centre
Teacher
Batch
```

Usually change only the relevant importer and add the value to `details`.

### Lifecycle date

Examples:

```text
Registered Date
Exam Date
Completion Date
Withdrawal Date
```

Prefer creating separate lifecycle records when it represents a real event.

The importer `parse_row()` returns a **list** intentionally, so one Excel row can create several timeline events.

Example:

```text
Registered Date = 01-05-2026
Exam Date       = 01-06-2026
PASS
```

could become:

```text
01-05-2026  IGC ENROLMENT / ENROLLED
01-06-2026  IGC COURSE_RESULT / PASS
```

### Important globally queried field

If a field becomes heavily used for filtering/reporting/business logic, consider a real database column. That would require a schema migration plus importer/API/query changes.

---

## Important file map

| Requirement | File |
|---|---|
| Progression rules | `backend/app/services/course_rules.py` |
| Learner recommendation adapter | `backend/app/services/recommendation.py` |
| Opportunity grouping | `backend/app/services/opportunities.py` |
| IGC Excel format | `backend/app/services/importers/igc.py` |
| IDP Excel format | `backend/app/services/importers/idp.py` |
| Common upload helpers | `backend/app/services/importers/common.py` |
| Importer auto-discovery | `backend/app/services/importers/registry.py` |
| Generic upload coordinator | `backend/app/services/importers/service.py` |
| Course catalog | `backend/seed_courses.py` |
| DB models | `backend/app/models.py` |
| Learner API | `backend/app/routers/learners.py` |
| Opportunity API | `backend/app/routers/opportunities.py` |
| Upload API | `backend/app/routers/uploads.py` |
| Dashboard API | `backend/app/routers/dashboard.py` |
| Frontend API client | `frontend/src/api.js` |
| Journey UI | `frontend/src/pages/LearnerDetailPage.jsx` |
| Opportunity UI | `frontend/src/pages/OpportunitiesPage.jsx` |
| Upload UI | `frontend/src/pages/UploadsPage.jsx` |

---

## PowerShell first-time backend setup

Create PostgreSQL database `upsell_db`, then create `backend\.env` from `.env.example`.

```powershell
cd .\backend
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\seed_courses.py
uvicorn app.main:app --reload
```

Backend:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

---

## PowerShell first-time frontend setup

Second PowerShell window:

```powershell
cd .\frontend
npm install
npm run dev
```

Frontend:

```text
http://localhost:5173
```

---

## Daily run

Backend terminal:

```powershell
cd .\backend
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Frontend terminal:

```powershell
cd .\frontend
npm run dev
```

---

## Testing reset

Delete learners/history/uploads but keep course catalog:

```powershell
cd .\backend
.\.venv\Scripts\Activate.ps1
python .\reset_test_data.py
```

Type:

```text
RESET
```

Full development reset:

```powershell
python .\reset_everything.py
```

then:

```powershell
python .\seed_courses.py
```

Do not use destructive resets in production.

---

## Business regression tests

Preserve these tests:

### A

```text
IGC PASS
```

Expected: IDP Entry lead + IDP recommendation.

### B

```text
IGC PASS
ID1 PASS
```

Expected: ID2 + ID3, no IDP Entry.

### C

```text
ID2 PASS
```

Expected: ID1 + ID3.

### D

```text
ID3 PASS
```

Expected: ID1 + ID2.

### E

```text
ID1 PASS
ID3 PASS
```

Expected: ID2 only.

### F

```text
ID1 PASS
ID2 ENROLLED
```

Expected: ID3 only.

### G

```text
ID1 PASS
ID2 PASS
ID3 PASS
```

Expected: no current ID-course opportunity.

---

## Current limitations / sensible next updates

Good next tasks:

1. update `idp.py` from a real IDP spreadsheet
2. row-level import error reporting
3. pagination
4. opportunity filters
5. CRM notes/contact history
6. follow-up workflow
7. recommendation shown/contacted/converted tracking
8. Alembic database migrations
9. automated tests
10. authentication and roles

Do not add ML yet unless explicitly requested.

---

# Full CRM expansion (September 2026)

## Workspace separation

The authenticated application now has three connected workspaces selected from the sidebar:

- **Main CRM (`/crm`)** manages people who have enquired but may not yet be registered.
- **Learners CRM (`/learners-crm`)** is the central workspace for viewing registered learner data; its uploads are managed from Main CRM.
- **Upsell CRM (`/upsell`)** preserves the original registered-learner and course-opportunity system.

Learners CRM now contains an active learner-import foundation:

- `/learners-crm` — overview with unique learner, enrolment, active, completed, and Main CRM match totals.
- `/learners-crm/learners` — shows 25 learners ordered by their most recently updated enrolment by default and supports search by email, phone number, or enrolment ID.
- `/crm/uploads?section=learners` — admin-only new/update learner Excel imports with upload references. The former `/learners-crm/uploads` URL redirects here.

Learner upload columns are `enrolment_id`, `learner_name`, `email_id`, optional `phone_number`, `course_name`, `enrolment_date`, `start_date`, `completion_date`, and `completion_status`. A person is uniquely identified by normalized `email_id`; `enrolment_id` uniquely identifies each course enrolment, allowing one learner to have multiple courses. New files receive an `LCRM-...` upload number, and Update mode replaces the selected upload transactionally. The overview counts each enrolment separately: `Not Completed` is active and `Completed` is completed.

The initial learner course mapping is bundled in `backend/app/data/learner_course_mapping.tsv` (146 course names in 15 categories from the supplied list). Startup seeds it once into `learner_course_categories` and `learner_course_mappings`, recording completion in `app_settings`. Later startup runs preserve admin edits. Course matching ignores case, Unicode compatibility differences, and repeated whitespace while preserving the uploaded course name. Learner search and overview resolve categories from the current mapping, so moving, renaming, adding, or removing a mapping changes the displayed category for existing enrolments without reuploading files. Unknown course names remain imported and appear as Unmapped. Admins manage categories and courses at `/crm/settings/course-mapping`.

Learners CRM stores data separately in `learners_crm_profiles` and `learners_crm_enrollments`. This avoids treating an enrolment ID as a person ID and keeps the existing Upsell CRM course-history tables intact.

Main CRM routes:

- `/crm` — enquiry overview and headline metrics.
- `/crm/leads` — searchable lead pipeline with status and counselor assignment.
- `/crm/leads/:leadId` — complete enquiry/call/campaign lifecycle.
- `/crm/campaigns` — redirects to the Main CRM overview; campaign events remain visible in lead lifecycles.
- `/crm/analytics` — source, conversion, registration, and assignment reporting.
- `/crm/uploads` — admin-only upload center for Main CRM, Learners CRM, and Upsell CRM files, with separate sections and one data reset control.
- `/crm/settings` — admin-only settings pages for counselor mapping and learner course mapping. The former `/crm/mapping` URL redirects here.

Upsell routes are prefixed with `/upsell`, including overview, learners, lead pipeline, and analytics. The lead pipeline opens on All leads, with Opportunities as the second view. The former `/upsell/campaigns` page redirects to the overview; campaign activity remains visible in lead records. Upsell course and marketing uploads are at `/crm/uploads?section=upsell`; the former `/upsell/uploads` URL redirects there.

## Main CRM identity and learner matching

Main CRM leads do not have learner numbers. The importer normalizes and matches by either:

- lowercase, trimmed email; or
- phone digits normalized to the final ten digits.

When a Main CRM lead matches an Upsell CRM learner by email or phone, `matched_learner_number` connects the two profiles. The Main CRM lifecycle page then links to the registered learner's Upsell lifecycle.

## Canonical customer connection across all CRMs

All three workspaces now connect through a shared customer identity layer:

- `customers` represents one real person independently of CRM workflow.
- `customer_identities` stores normalized `EMAIL` and `PHONE` values with a uniqueness rule per identity type.
- `main_crm_leads.customer_id` links enquiries and their activity timeline.
- `learners_crm_profiles.customer_id` links the registered learner and all enrolments.
- `learners.customer_id` links external-board IGC/IDP learner numbers and result history.

Matching checks normalized email first and then normalized phone. A customer may have multiple course enrolments and may also have one or more external-board learner records. `enrolment_id` remains a course-enrolment key and is never treated as a person identifier. A board `learner_number` remains specific to IGC/IDP assessment data and is never manufactured for other learners.

When a Learners CRM upload or an Upsell board-result upload resolves to the same customer as a Main CRM enquiry, that enquiry is automatically set to `CONVERTED`. Board-result imports also populate `matched_learner_number`, enabling the existing link to the Upsell learner journey. No new recommendation logic is inferred from general enrolments yet; future course and level mappings can extend the rule engine.

Upsell imports must flush the external-board `learners` row before setting `main_crm_leads.matched_learner_number`. This ordering is required by the foreign key and makes upload order across Main CRM, Learners CRM, and Upsell CRM independent.

Existing unlinked rows are backfilled idempotently during the current startup compatibility migration. The schema diagram is stored at `docs/connected-crm-schema.png`; its reproducible drawing script is `docs/generate_schema_diagram.ps1`.

## Main CRM upload types

Every new file receives one upload-level reference such as `CRM-20260901-A1B2`. This reference belongs to the entire Excel file, not an individual row.

The Data Uploads page supports:

- **New upload** — creates a new unique upload reference.
- **Update upload** — selects an existing reference and replaces its imported lifecycle data. Validation occurs transactionally so a failed replacement does not intentionally discard the previous valid import.

Supported upload types:

1. **Info email leads (`INFO_EMAIL_LEADS`)**
   - Umbrella source for web enquiries, live chat, landing pages, and social-media leads.
   - The row's `source` value retains the specific sub-source.
   - Core columns: `full_name`, `email`, `phone_number`, `whatsapp_number`, `source`, `course`, `region`, `age`, `status_of_lead`, `counselor`, `sales_owner`, `counsilor_email`, `note`.
2. **Direct calls (`DIRECT_CALLS`)**
   - Stores call enquiries as lifecycle activities.
   - Supports date, full name (including the supplied `Full Nmae` spelling), email, phone, WhatsApp, source, country/region, course, service type, status, counselor, counselor email, call type, test status, comment, and follow-up date.
3. **Campaign replies (`CAMPAIGN_REPLIES`)**
   - Columns: `date`, `email`, `campaign_type`, `course`, `full_user_reply`, `campaign name`, `campaign description`.
   - Appends the full reply to the matching email's lifecycle.
4. **Campaign data (`CAMPAIGN_DATA`)**
   - Columns: `date`, `email`, `campaign_type`, `campaign name`, `campaign description`, `course_campaign`.
   - Records marketing sent to the matching lead. Email is supported now; the channel model can later support WhatsApp and LinkedIn.

Original row data is retained in `main_crm_activities.raw_data` so more source-specific fields can be exposed later without losing the imported values.

## Main CRM data model

- `main_crm_leads` stores the current unified lead/contact profile, normalized identity fields, ownership, source, status, and optional learner link.
- `main_crm_activities` stores dated enquiries, direct calls, campaigns sent, and campaign replies.
- `upload_batches.unique_number` stores the upload-level reference used for replacement imports.
- `users` now includes `email`, `country`, and `region` for counselor mapping.

## Lead workflow

- Admins see all leads and may assign counselors.
- Counselors see only leads assigned to them.
- Lead status can be changed from the pipeline.
- Selecting a counselor displays the counselor's mapped email.
- Assignment applies the counselor's region to the lead; when region is blank, country is used as the fallback territory.
- Supported frontend statuses currently include New, In contact, Follow up, Converted, and Rejected.

## Counselor mapping

The Mapping page can create counselors and update their display name, email, country, region, and password. Usernames are fixed after creation. Passwords are securely hashed and never returned to the frontend. Changing a counselor password invalidates that counselor's existing sessions.

The agreed production-shaped test accounts are seeded by:

```powershell
cd backend
python seed_crm_counselors.py
```

The script is idempotent and creates or updates 17 counselor accounts. All currently use the temporary password `test1234`; regions are blank and countries are populated. `A.Pandiyan` uses the safely normalized username `counselor_a_pandiyan`; all others follow `counselor_{lowercase_name}`.

## Database initialization

The application currently uses `Base.metadata.create_all()` plus small startup column checks for compatibility with the existing database. Added tables are created on backend startup, and the `users.country`, `users.region`, `users.email`, and `upload_batches.unique_number` columns are added when absent. Alembic remains the recommended future production migration system.

## Large database performance

Main CRM lead lists now use server-side search and 50-row pages. The overview and analytics pages use grouped database counts rather than downloading every lead. Indexes support recent lead order, source and counselor filters, and lead activity lookups. The selected source, search, and page are kept in the URL so returning from a lead profile restores the same list.

The existing `customers` and `customer_identities` tables are the central person/contact entity. Main CRM leads, Learners CRM profiles, external-board learners, and upsell opportunities link through `customer_id`. An upsell lead's board `learner_number` is optional, so a customer imported only through Learners CRM can still receive recommendations. Learners CRM completion remains counted per enrolment. Legacy customer-link and migration-status backfills are recorded in `maintenance_runs` so they run once. New uploads create customer links directly.

Upsell opportunity generation now reads both Learners CRM enrolments and board results for each customer. The bundled three-level mapping in `backend/app/data/learner_course_mapping_v2.tsv` replaces the old mapping once at startup; admins can then edit main categories, subcategories, and courses in Settings. Stage 1 subcategories mature after the configurable cooling period (default 60 days) and offer IGC, PSM, and Incident Investigation. An IGC pass offers stage 3 PSM, Incident Investigation, and IDIP entry. A passed IDIP unit offers the remaining unenrolled units. Already enrolled target courses are excluded. The course revision, rules version, and next cooling eligibility date are tracked in `app_settings`; opportunity refreshes occur after an upload, a rule change, or an actual eligibility boundary. Bump `OPPORTUNITY_RULES_VERSION` when changing the opportunity rules. Tests use a local SQLite sample; production PostgreSQL timing still needs measurement after deployment.

Upsell pipeline rows are fetched through a 50-row paged `/leads` query with server-side search, filters and sorting. `/opportunities`, Upsell analytics, and the dashboard calculate grouped counts in SQL. PSM and Incident Investigation each have separate Stage 2 and Stage 3 sections, distinguished by `Lead.stage` while preserving the same lead through promotion. PostgreSQL opportunity refreshes use an advisory transaction lock so concurrent requests do not rebuild the same revision. Composite indexes for active stage lists, owner lists, recency, campaigns, and learner history are created on startup. Upsell learner lists are paged at 50; Learners CRM search is paged at 25 and returns a five-enrolment preview per learner, with full history on the detail page.

Data reset immediately reconciles generated Upsell opportunities after deleting selected upload data. The default Upsell “All leads” page filters to active opportunities, so deactivated historical rule rows do not reappear after a reset. Main CRM summary source counts use the actual row-level `source` values from normal and migrated uploads; `source_category_counts` remains available for the pipeline’s upload-type tabs. New and in-progress cards expose normal versus migrated counts inside each card.

IGC and IDIP board results use `learner_number` to join IGC to IDIP and IDIP units to each other. Recommendation rules evaluate each board learner number separately, even when two numbers share an email. Once a board number exists, a later board row with changed contact details keeps that same customer; conflicting contact identities are merged into it. All other course enrolments link to the customer through normalized email or phone, without using a learner number. Upsell leads retain a board number only for IDIP entry/unit opportunities backed by board history.

All upload forms now start a background job and poll `/uploads/jobs/{job_id}` for processed, imported, and skipped counts. Main CRM source files, Learners CRM enrolments, Upsell course results, and Upsell marketing campaigns report progress after each 500-row slice. The old CRM migration keeps its separate source-mapping preview and progress endpoint. The upload pages remember an active job in browser session storage, so the admin can leave the page and return while it runs. Job progress is held by the running API process; finished file history remains in `upload_batches`.

Each individual detail page in Main CRM, Learners CRM, and Upsell CRM now includes a live full customer journey. It is assembled from the shared `customer_id` on every request and includes main enquiry activity, individual enrolments and completions, board result records, marketing campaigns, and upsell opportunities and activities. Uploading a new linked result or enrolment changes the journey visible in all three workspaces without copying lifecycle rows between tables. Counselor-scoped enquiry and upsell activity respects the existing assignment rules. The endpoint data is generated only for the selected customer, not for whole lists.

The shared journey uses the vertical Learning journey design on all three detail pages. Each dated card can show its source, status, result fields, and the original uploaded Main CRM row. The former Upsell-only result timeline was removed to avoid presenting two competing journeys. On a migrated Main CRM lead, the detail page's Last updated field displays the original `Updated at` text from the migration activity row. When several old CRM rows match one lead, the latest valid source date is displayed; a missing source date is shown as not provided. This affects the detail display only and leaves the operational `main_crm_leads.updated_at` timestamp available for sorting and current edits.

---

# Quick prompt for the next chat

## Main CRM pipeline filters and result labels

Main CRM's lead pipeline now has searchable, multi-select counselor, status, actual lead-source, and course filters. A filter panel uses draft selections until Apply filters is pressed; option searches run locally in the browser. Group selections match any selected value, while different groups are combined. Unassigned counselors and empty source/course values are selectable. The API preserves counselor access restrictions for both list results and filter choices. Filters, submitted search, sort order, and pagination are stored in the URL for returning from a profile.

`GET /crm/leads/filter-options` groups visible lead rows to return options and counts. `GET /crm/leads` accepts repeated `counselor_ids`, `statuses`, `sources`, and `courses`, plus whitelisted `sort_by=created_at|updated_at` and `sort_direction=asc|desc`. Results remain paginated at 50 rows by default. The table displays created and updated dates, with clickable column headings and a date-sort control. Ties use lead ID for stable pagination. Added indexes support created-date ordering and status, actual-source, and course filtering with updated-date ordering; the existing startup code creates them automatically.

The shared customer journey labels assessment uploads as Result data IGC or Result data IDP using the upload batch's import type. Historical records without a batch fall back to their course family. This display change applies to every CRM using CustomerLifecycle and does not relabel, delete, or reclassify imported course records.

Verification: all 33 backend tests pass, the frontend builds, and the browser interaction check covers Apply behavior, local option search, date sorting, URL state, result labels, and horizontal table scrolling on smaller screens. New checks are in `backend/tests/test_main_crm_filters.py` and `frontend/tests/pipelineInteractions.test.mjs`.

Copy/paste:

> I am continuing a Learning CRM project. I uploaded `learning-crm.zip` and `HANDOFF.md`. Read `HANDOFF.md` first and inspect the repository before changing anything. The stack is React + Vite, FastAPI, SQLAlchemy and PostgreSQL. Stage 1 uses learner_number as the learner key. IGC is a course; IDP is a program containing independent courses ID1, ID2 and ID3. Recommendation/opportunity logic is rule-based and the single source of truth is `backend/app/services/course_rules.py`. Course-specific Excel importers are separate files under `backend/app/services/importers/` and are auto-discovered. Preserve all dated learner history. For every requested code change, explain what changed and why, then give the full replacement content of every changed file and mention any DB/setup step. Do not redesign working architecture unless necessary. First summarize your understanding of the current repository in 8–12 bullets, then wait for my requested change.
