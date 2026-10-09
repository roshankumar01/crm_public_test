# Learning CRM — Stage 1 Build Specification

## 1. Goal

Build a CRM-style learning platform for a teaching company using:

- React + Vite frontend
- FastAPI backend
- PostgreSQL database
- SQLAlchemy 2.x
- pandas/openpyxl for Excel imports

Stage 1 uses `learner_number` as the unique learner key.

Do **not** use ML/DL in Stage 1. Recommendations are rule-based and must stay in Python.

The system must preserve dated learner history and support different Excel formats for different courses.

---

## 2. Core Architecture

```text
Excel / CSV Upload
      ↓
React Upload Page
      ↓
FastAPI Upload Endpoint
      ↓
Course-specific Python Parser
      ↓
Normalized Course Records
      ↓
PostgreSQL
      ↓
FastAPI APIs
      ↓
React CRM
```

Responsibilities:

- PostgreSQL stores facts/history.
- Python contains recommendation and opportunity rules.
- React only displays data and sends user actions.
- React must never connect directly to PostgreSQL.

---

## 3. Stage 1 Pages

Build these pages:

1. Dashboard
2. Learners
3. Learner Detail / Learning Journey
4. IDP Opportunities
5. Data Uploads

---

## 4. Database Tables

### `learners`

One row per learner.

Fields:

- `learner_number` VARCHAR(50) PRIMARY KEY
- `name`
- `nationality`
- `contact_number`
- `email_id`
- `last_activity_date`
- `created_at`
- `updated_at`

For Stage 1, learner number is trusted as unique.

### `courses`

Generic course catalog.

Fields:

- `id` PK
- `code` UNIQUE
- `name`
- `program_code`
- `active`
- `display_order`

Seed initially:

| code | name | program_code |
|---|---|---|
| IGC | IGC | IGC |
| ID1 | ID1 | IDP |
| ID2 | ID2 | IDP |
| ID3 | ID3 | IDP |

Do not create new DB columns when future courses are added.

### `upload_batches`

Audit every imported file.

Fields:

- `id`
- `import_type`
- `filename`
- `status`: PROCESSING / COMPLETED / FAILED
- `rows_total`
- `rows_imported`
- `rows_skipped`
- `error_message`
- `uploaded_at`

### `learner_course_records`

This is the dated learning history.

Fields:

- `id`
- `learner_number` FK
- `course_id` FK
- `upload_batch_id` FK nullable
- `event_date`
- `event_type`
- `enrollment_status`
- `result`
- `details` JSON
- `raw_data` JSON
- `row_hash` UNIQUE
- `created_at`

Important rules:

- Never overwrite old learning history.
- Every event has a real date.
- Keep original source row in `raw_data`.
- Keep course-specific normalized information in `details`.
- Use `row_hash` to prevent duplicate imports.

Example IGC `details`:

```json
{
  "ig1_result": "75",
  "ig2_result": "100",
  "unit": "IG2, IG1",
  "registration": "ind"
}
```

Future course-specific fields should also go into `details` rather than forcing schema changes.

---

## 5. Backend Structure

```text
backend/
├── app/
│   ├── __init__.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── main.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   ├── learners.py
│   │   ├── opportunities.py
│   │   └── uploads.py
│   └── services/
│       ├── __init__.py
│       ├── importers.py
│       ├── opportunities.py
│       └── recommendation.py
├── seed_courses.py
├── requirements.txt
└── .env
```

Keep routing separate by CRM niche.

---

## 6. Backend Dependencies

`requirements.txt`:

```text
fastapi
uvicorn[standard]
SQLAlchemy
psycopg[binary]
python-dotenv
pandas
openpyxl
python-multipart
```

`.env` example:

```text
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/upsell_db
```

Never commit real production secrets.

---

## 7. Recommendation Rules

Keep them in `app/services/recommendation.py`.

### Rule 1 — IGC → IDP

If learner:

- passed IGC
- has no IDP activity at all

Then recommend:

- IDP Programme

### Rule 2 — ID2 → ID1

If learner:

- passed ID2
- has no history for ID1

Then recommend ID1.

### Rule 3 — ID2 → ID3

If learner:

- passed ID2
- has no history for ID3

Then recommend ID3.

Important: `has history` includes enrolled, in-progress, pass, fail, etc. Do not recommend a course the learner has already entered.

---

## 8. IDP Opportunity Rule

A learner appears in the IDP opportunity list when:

- at least one IGC record has `result = PASS`
- learner has no activity in any course where `program_code = IDP`

Return:

- learner_number
- name
- email_id
- contact_number
- igc_passed_on
- days_since_igc_pass

Sort oldest opportunity first by default.

---

## 9. Import Architecture

The frontend uploads files to FastAPI.

Backend chooses a course-specific parser.

Current parsers:

```text
parse_igc_row()
parse_idp_row()
```

Future parsers:

```text
parse_ielts_row()
parse_business_english_row()
...
```

Every parser must output a common normalized shape:

```python
{
    "learner_number": "928504",
    "name": "Kawsar Ahmed",
    "nationality": None,
    "contact_number": "123",
    "email_id": "123@gmail.com",
    "course_code": "IGC",
    "event_date": date(...),
    "event_type": "COURSE_RESULT",
    "enrollment_status": None,
    "result": "PASS",
    "details": {...}
}
```

The rest of the system should not care what the original spreadsheet looked like.

---

## 10. IGC Import Rules

Expected columns may include:

- Learner number
- Name
- nationality
- Bi-lingual Dictionary
- Unit
- status
- contact number
- Email id
- IG1 Result
- IG2 Result
- Overall result
- date
- reg

Normalize column names before parsing.

Normalize results:

- PASS / PASSED → PASS
- FAIL / FAILED → FAIL
- TBA / PENDING / AWAITING → PENDING

Store:

- course = IGC
- event_type = COURSE_RESULT
- result from Overall result
- event_date from date
- IG1, IG2, Unit, Registration in `details`
- entire original row in `raw_data`

---

## 11. IDP Import Rules

IDP has a separate Excel format.

Keep all IDP-specific interpretation inside `parse_idp_row()`.

Initial parser may support:

### Format A

```text
Learner number | Course | Result | date
```

Course is ID1, ID2, or ID3.

### Format B

```text
Learner number | ID1 Result | ID2 Result | ID3 Result | date
```

When the real IDP spreadsheet is provided, update only the IDP importer and its tests/validation. Do not redesign unrelated APIs or the database.

---

## 12. Duplicate Import Handling

Generate a SHA-256 hash from normalized values including:

- learner_number
- course_code
- event_date
- result
- enrollment_status
- details

If the hash already exists:

- do not insert a duplicate course record
- count it as skipped

---

## 13. Learner Profile Update Rules

When importing:

### New learner

Create a learner using learner number as PK.

### Existing learner

Only update profile fields when the incoming event is as new or newer than `last_activity_date`.

Only replace name/email/phone/nationality when the incoming value is non-empty.

Do not use email or phone as identity keys in Stage 1.

---

## 14. API Endpoints

### Health

```text
GET /health
```

### Dashboard

```text
GET /dashboard/summary
```

Expected response:

```json
{
  "total_learners": 0,
  "igc_passed": 0,
  "idp_learners": 0,
  "idp_opportunities": 0
}
```

### Learners

```text
GET /learners
GET /learners?search=ankit
```

Search by:

- learner number
- name
- email

### Learner detail

```text
GET /learners/{learner_number}
```

Response shape:

```json
{
  "learner": {},
  "passed_courses": [],
  "recommendations": [],
  "timeline": []
}
```

Timeline is chronological and contains:

- id
- date
- event_type
- course_code
- program_code
- course_name
- result
- enrollment_status
- title
- details

### IDP Opportunities

```text
GET /opportunities/idp
```

### Uploads

```text
GET /uploads
POST /uploads
```

POST is multipart form data:

- `import_type`: IGC or IDP
- `file`: XLSX or CSV

---

## 15. Frontend Structure

```text
frontend/src/
├── components/
│   └── AppLayout.jsx
├── pages/
│   ├── DashboardPage.jsx
│   ├── LearnersPage.jsx
│   ├── LearnerDetailPage.jsx
│   ├── IdpOpportunitiesPage.jsx
│   └── UploadsPage.jsx
├── api.js
├── App.jsx
├── main.jsx
└── index.css
```

Routes:

```text
/                     Dashboard
/learners             Learners
/learners/:id         Learner Profile
/opportunities/idp    IDP Opportunities
/uploads              Data Uploads
```

---

## 16. Frontend Design Direction

Design should be:

- simple
- premium
- CRM-like
- spacious
- readable
- dark sidebar + light content area
- restrained colors
- responsive
- strong typography hierarchy
- visually polished learner timeline

Avoid unnecessary gradients, heavy animation, or large UI libraries unless explicitly requested.

---

## 17. Dashboard Page

Show four summary cards:

1. Total Learners
2. IGC Passed
3. In IDP
4. IDP Opportunities

Also show a prominent CTA to the IDP Opportunities page.

---

## 18. Learners Page

Show:

- search box
- learner name
- learner number
- email
- phone
- last activity
- View action

Clicking View opens Learner Detail.

---

## 19. Learner Detail Page

This is a high-priority visual page.

### Header

Show:

- name
- learner number
- email
- phone
- last activity

### Recommendations

Show rule-based recommendation cards with:

- course/program code
- name
- reason

### Learning Journey

Show vertical chronological timeline.

Example:

```text
01 Jun 2025
IGC - FAIL
IG1: 48
IG2: 70

20 Jun 2025
IGC - PASS
IG1: 75
IG2: 100

14 Aug 2025
ID2 - PASS
```

PASS should have positive visual treatment.
FAIL should have distinct negative treatment.
Pending/enrolled should have neutral treatment.

Render `details` dynamically so new future course-specific fields appear without hardcoding every field in React.

Also show completed/passed courses in a side panel.

---

## 20. IDP Opportunities Page

Show:

- learner
- learner number
- IGC passed date
- days waiting
- email
- phone
- link to learner profile

This is the admin's initial upsell/sales working list.

---

## 21. Data Uploads Page

Show:

- import type dropdown
- IGC Excel
- IDP Excel
- file picker
- upload button
- import result
- recent upload history

Recent upload table:

- filename
- import type
- status
- rows total
- imported
- skipped
- uploaded time

---

## 22. React API Client

Keep all API functions in `src/api.js`:

- `getDashboardSummary()`
- `getLearners(search)`
- `getLearner(learnerNumber)`
- `getIdpOpportunities()`
- `getUploads()`
- `uploadExcel(importType, file)`

Development backend URL:

```text
http://127.0.0.1:8000
```

FastAPI CORS must allow:

```text
http://localhost:5173
```

---

## 23. Seed Script

Create `seed_courses.py`.

It must insert/update:

- IGC
- ID1
- ID2
- ID3

It must be idempotent. Running it multiple times must not create duplicates.

---

## 24. PowerShell — First-Time Setup

Assume project root contains `backend` and `frontend`.

### Backend

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

### Frontend

Open a second PowerShell window:

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

## 25. PowerShell — Normal Daily Run

### Window 1 — Backend

```powershell
cd .\backend
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

### Window 2 — Frontend

```powershell
cd .\frontend
npm run dev
```

PostgreSQL must already be running.

---

## 26. Acceptance Criteria

Stage 1 is complete only when all of the following are true.

### Database

- PostgreSQL connects
- learners table exists
- courses table exists
- learner_course_records table exists
- upload_batches table exists
- IGC/ID1/ID2/ID3 seed successfully

### Uploads

- browser can upload IGC file
- learners are inserted/updated
- dated history is inserted
- duplicates are skipped
- upload batch is recorded
- failed upload records error state

### Learners

- learner list loads
- search works
- learner detail opens
- timeline is chronological
- IGC details render
- passed courses render

### Recommendations

- IGC PASS + no IDP => IDP recommendation
- ID2 PASS + no ID1 => ID1 recommendation
- ID2 PASS + no ID3 => ID3 recommendation
- existing activity suppresses duplicate recommendations

### IDP Opportunities

- IGC PASS + no IDP appears
- any IDP activity removes learner

### Frontend

- dashboard works
- learners works
- learner profile works
- opportunities works
- upload page works
- design feels simple and premium

---

## 27. End-to-End Business Test

### Scenario A

Learner 1001:

```text
IGC PASS
2026-01-10
```

Expected:

- learner appears in CRM
- IGC appears in journey
- IDP recommendation appears
- learner appears in IDP Opportunities

### Scenario B

Later upload:

```text
1001
ID2 ENROLLED
2026-02-01
```

Expected:

- generic IDP recommendation disappears
- learner disappears from IDP Opportunities
- ID2 appears in journey

### Scenario C

Later:

```text
1001
ID2 PASS
2026-03-01
```

Expected recommendations:

- ID1
- ID3

### Scenario D

Later:

```text
1001
ID1 ENROLLED
2026-03-15
```

Expected recommendation:

- ID3 only

---

## 28. Instructions for Codex

When modifying this project:

1. Read this file before editing.
2. Do not move recommendation rules into PostgreSQL.
3. Do not add ML/DL in Stage 1.
4. Preserve all dated learner history.
5. Never silently overwrite learner history.
6. Use learner number as unique learner key in Stage 1.
7. Keep course-specific import logic isolated.
8. Keep React separate from business/database logic.
9. Prefer SQL filtering/aggregation over client-side filtering for large data.
10. Preserve API response compatibility where practical.
11. If a file changes, show the full replacement file, not only a diff.
12. For every change explain briefly:
    - what changed
    - why it changed
    - any setup/migration command required
13. Keep code simple and readable.
14. Do not add infrastructure that is not needed yet.
15. Add/update tests when recommendation or importer logic changes.

---

## 29. Recommended Build Order

1. PostgreSQL connection
2. SQLAlchemy models
3. seed courses
4. IGC importer
5. upload API
6. learner APIs
7. recommendation service
8. IDP opportunity query/API
9. dashboard API
10. React layout
11. dashboard
12. learners page
13. learner detail + visual journey
14. IDP opportunities
15. upload page
16. real IDP importer
17. end-to-end business tests

Do not move to Stage 2 until this complete flow works reliably.
