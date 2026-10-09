# Learning CRM — Stage 2 Future Updates Specification

## 1. Purpose

This is the future expansion plan after Stage 1 is stable.

Do not implement everything in this document at once.

Codex must first read `STAGE_1_BUILD_SPEC.md` and preserve its architecture and behavior unless a requested update explicitly changes it.

---

## 2. Future Product Direction

Expand the system into a full learning CRM supporting:

- many programs and courses
- advanced learner filters
- multiple opportunity types
- admin/sales workflow
- learner notes
- follow-up management
- recommendation tracking
- conversion analytics
- authentication and roles
- better import validation
- exports
- audit history
- eventual ML readiness

Keep the existing separation:

```text
PostgreSQL = facts and history
Python = business rules
FastAPI = application/API layer
React = presentation and user interaction
```

---

## 3. Generic Opportunity Engine

Current Stage 1 has only IDP opportunity logic.

Future examples:

```text
IGC PASS -> IDP
IELTS Foundation PASS -> IELTS Advanced
Business English 1 PASS -> Business English 2
```

Initially keep these business rules in Python.

Possible future organization:

```text
services/
  recommendations/
    igc.py
    idp.py
    ielts.py
    business_english.py
```

Do not move rules to DB unless explicitly required later.

---

## 4. Advanced Filtering

Add server-side filters to learner and opportunity APIs.

Potential filters:

- program
- course
- passed course
- enrollment status
- result
- date range
- last activity range
- days since pass
- nationality
- region
- registration type
- recommendation type

Example:

```text
Passed IGC
AND no IDP
AND pass was > 30 days ago
AND nationality = India
```

Filtering should happen in SQL/FastAPI, not by downloading the full table to React.

---

## 5. Pagination and Sorting

Add server-side pagination.

Example:

```text
GET /learners?page=1&page_size=50&sort=last_activity_date&direction=desc
```

Suggested response:

```json
{
  "items": [],
  "page": 1,
  "page_size": 50,
  "total": 0,
  "pages": 0
}
```

Use the same pattern for opportunity lists, uploads, and other large CRM tables.

---

## 6. CRM Interactions

Add admin/sales interaction tracking.

Suggested table: `learner_interactions`

Fields:

- id
- learner_number
- interaction_type
- interaction_date
- admin_user_id
- target_course_code nullable
- status nullable
- note
- created_at

Interaction types may include:

- CALL
- EMAIL
- WHATSAPP
- SMS
- MEETING
- NOTE

Possible sales status values:

- NEW
- CONTACTED
- INTERESTED
- FOLLOW_UP
- NOT_INTERESTED
- CONVERTED

Keep CRM interactions separate from learning history.

Learner detail can eventually show tabs:

```text
Overview
Learning Journey
Recommendations
CRM Activity
Source / Upload History
```

---

## 7. Recommendation Tracking

Add a `recommendation_events` table.

Fields:

- id
- learner_number
- recommendation_code
- event_type
- occurred_at
- admin_user_id nullable
- metadata JSON

Possible events:

- GENERATED
- SHOWN
- CONTACTED
- CLICKED
- ACCEPTED
- DISMISSED
- CONVERTED

Purpose: measure whether rule-based recommendations work and create future ML training data.

---

## 8. Conversion Funnel

Create analytics for:

```text
IGC Passed
  ->
IDP Recommended
  ->
Contacted
  ->
Interested
  ->
Enrolled
  ->
Completed
```

Potential metrics:

- IGC to IDP conversion %
- average/median days from IGC pass to IDP enrollment
- stale opportunity count
- opportunities created this month
- learners contacted this week
- conversion by admin
- conversion by nationality/region
- conversion by course/program

---

## 9. Better Learner Profile

Future learner profile may contain:

### Overview

- current active course
- last activity
- courses completed
- active recommendations
- opportunity status
- days inactive

### Learning Journey

Current dated course timeline.

### Recommendations

Current and historical recommendations.

### CRM Activity

Calls, emails, notes, follow-ups.

### Source History

Which upload batches created/updated learner history.

---

## 10. Authentication and Roles

Add only after core CRM is stable or when deployment requires it.

Potential roles:

- SUPER_ADMIN
- ADMIN
- SALES
- VIEWER

Example access:

### SUPER_ADMIN

Full access.

### ADMIN

- learner management
- uploads
- reports
- CRM actions

### SALES

- learners
- opportunities
- interactions
- follow-ups

### VIEWER

Read-only.

Use secure password hashing and production-grade auth. Prefer a clear JWT/session strategy rather than custom insecure auth.

---

## 11. Upload Validation and Error Review

Stage 1 tracks only batch totals.

Future table: `upload_row_errors`

Fields:

- id
- upload_batch_id
- row_number
- error_type
- message
- raw_data JSON
- created_at

Examples:

- missing learner number
- invalid date
- unknown course
- invalid result
- malformed workbook
- missing required column

Frontend should allow admin to inspect rejected rows.

Example:

```text
Upload: IGC_June.xlsx
2,000 rows
1,980 imported
20 rejected
[View errors]
```

---

## 12. Importer Contracts

Eventually move toward dedicated importer modules:

```text
importers/
  base.py
  igc.py
  idp.py
  ielts.py
  business_english.py
```

Each importer defines:

- expected headers
- required fields
- optional fields
- normalization rules
- parser
- validation

Do not allow one large importer file to become unmaintainable as course count grows.

---

## 13. Audit Logging

Suggested table: `audit_logs`

Fields:

- id
- admin_user_id
- action
- entity_type
- entity_id
- old_value JSON
- new_value JSON
- created_at

Audit important actions such as:

- manual profile edits
- deletion
- CRM status changes
- uploads
- role/user changes

Historical raw upload rows should remain immutable.

---

## 14. Manual Learner Editing

Allow authorized admins to update current profile fields:

- name
- email
- phone
- nationality

Important:

- current profile may change
- historical imported course records and `raw_data` remain unchanged

---

## 15. Course Catalog Management

Future Courses page:

- list courses
- activate/deactivate
- display order
- program grouping

Possible future hierarchy:

```text
Program
  -> Course
      -> Module
```

Do not add deeper hierarchy until business requirements require it.

---

## 16. More Programs

Future examples:

- IELTS
- Business English
- Teacher Training
- Kids English
- Corporate Training

Avoid hardcoding all program names into React. Prefer backend metadata for generic views while keeping recommendation eligibility rules in Python.

---

## 17. Export

Admin should eventually export filtered lists.

Examples:

- IDP opportunities
- inactive learners
- learners recommended ID3
- learners contacted this month

Formats:

- CSV
- XLSX

Generate exports on the backend so export data matches API filters exactly.

---

## 18. Bulk CRM Actions

Possible future actions:

- mark selected learners contacted
- assign learners to sales user
- set follow-up date
- bulk export
- update status

Only implement after single-record workflows are reliable.

---

## 19. Follow-Up Management

Add fields/events for:

- next_follow_up_at
- assigned_admin_user_id

Future pages/cards:

- Follow-ups Today
- Overdue Follow-ups
- Upcoming Follow-ups

This is a major step toward a true CRM.

---

## 20. Notifications

Possible future notifications:

- new opportunity generated
- opportunity older than 30 days
- learner completed prerequisite course
- follow-up overdue
- upload failed

Do not add complex async infrastructure until required.

---

## 21. Analytics

Once data quality is reliable, add:

- learners over time
- IGC pass rate
- IDP conversion rate
- course enrollments
- result distribution
- time to conversion
- recommendation conversion
- admin/sales activity

Use PostgreSQL aggregation rather than loading large datasets into the browser.

---

## 22. Data Quality Dashboard

Track:

- missing email
- missing phone
- invalid dates
- import errors
- stale learner profiles
- unknown course codes

Example:

```text
Missing email: 324
Missing phone: 98
Import errors: 12
Stale profiles: 1,201
```

---

## 23. Future Learner Identity Resolution

Stage 1 assumption:

```text
learner_number is unique
```

If this becomes unreliable, migrate deliberately to:

```text
learners
learner_identifiers
identity_review_queue
```

Identifiers may include:

- learner number
- email
- phone

Prefer deterministic matching and collision detection first.

Do not perform unsafe fuzzy auto-merging without admin review.

This should be a planned migration, not an ad-hoc code patch.

---

## 24. Database Migrations

Before production, move from:

```python
Base.metadata.create_all()
```

to Alembic migrations.

Typical commands:

```powershell
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Never drop the production database to apply a normal schema change.

---

## 25. Environment Configuration

Use separate configuration for:

- development
- staging
- production

Do not hardcode:

- DB passwords
- API URLs
- secrets

Frontend should eventually use:

```text
VITE_API_URL=...
```

Backend should use environment variables.

---

## 26. Testing

Add automated tests before major expansion.

### Backend tests

Prioritize:

- recommendation rules
- opportunity queries
- IGC importer
- IDP importer
- duplicate handling
- learner timeline ordering
- upload failures

### Frontend tests

Prioritize:

- search
- opportunity loading
- journey rendering
- uploads

Recommendation and importer tests are the highest-value tests.

---

## 27. Recommendation Rule Tests

Every business rule must have tests.

Examples:

```text
IGC PASS + no IDP => IDP
IGC PASS + ID1 enrolled => no generic IDP recommendation
ID2 PASS + no ID1 + no ID3 => ID1 + ID3
ID2 PASS + ID1 enrolled => ID3 only
ID2 PASS + ID1/ID3 activity => none
```

Never change a recommendation rule without updating tests.

---

## 28. Eventual ML Readiness

Do not add ML until the system has reliable behavioral history.

Collect first:

- course history
- results/scores
- event dates
- recommendation generated
- recommendation shown
- learner contacted
- recommendation accepted/dismissed
- enrollment/conversion
- conversion timing

Possible future ML question:

```text
Given this learner's history and available courses,
which course are they most likely to enroll in next?
```

A future hybrid design may be:

```text
Eligibility Rules
      +
ML Ranking
```

Business eligibility rules should still prevent recommending invalid/ineligible courses.

---

## 29. Future UI Direction

Preserve the Stage 1 simple/premium style.

Possible sidebar:

```text
Dashboard
Learners
Opportunities
  IDP
  IELTS
  Other
CRM
  Follow-ups
  Contacts
Courses
Uploads
Reports
Admin
```

Avoid turning the interface into a visually dense ERP.

Keep:

- whitespace
- clear page purpose
- polished tables
- readable cards
- strong learner journey visualization
- restrained colors

---

## 30. Recommended Future Priority

### Priority 1

- real IDP importer
- upload validation/error rows
- advanced opportunity filters
- pagination
- recommendation/importer tests

### Priority 2

- CRM interactions
- opportunity status
- follow-up dates
- recommendation tracking
- learner profile tabs

### Priority 3

- authentication and roles
- exports
- analytics
- data quality dashboard
- Alembic

### Priority 4

- course catalog admin
- bulk actions
- notifications
- production hardening

### Priority 5

- ML readiness
- ML ranking
- hybrid recommendation engine

---

## 31. Instructions for Codex

When using this future-updates file:

1. Read `STAGE_1_BUILD_SPEC.md` first.
2. Implement only the requested Stage 2 feature, not this entire roadmap.
3. Preserve Stage 1 behavior unless the request explicitly changes it.
4. Keep recommendation rules in Python unless explicitly told otherwise.
5. Preserve dated learner history.
6. Preserve original uploaded raw rows.
7. Keep course-specific importers isolated.
8. Keep React separate from database/business logic.
9. Prefer SQL for filtering and aggregation.
10. Avoid unnecessary dependencies and infrastructure.
11. For every changed file, provide:
    - what changed
    - why
    - the full replacement file
12. If DB schema changes, clearly state the required migration.
13. Do not silently reset or drop a real database.
14. Add tests for recommendation/importer behavior changes.
15. Do not introduce ML unless specifically requested.
