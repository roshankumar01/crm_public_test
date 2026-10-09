# Learning CRM

For a new Windows VPS with Caddy and PostgreSQL, follow [WINDOWS_DEPLOY.md](WINDOWS_DEPLOY.md). It creates the admin from `backend/.env` automatically; no seed command is required.

Rule-based learner CRM using React + Vite, FastAPI, SQLAlchemy and PostgreSQL.

Read `HANDOFF.md` before making changes.

## Current business model

- IGC = course
- IDP = program/family, not a course
- ID1, ID2, ID3 = separate independent courses inside IDP
- Stage-1 unique learner key = `learner_number`
- Recommendations/opportunities are Python rules, not ML
- Every dated course event is preserved

## Local development

The following Vite and Uvicorn commands are for local development. Use [WINDOWS_DEPLOY.md](WINDOWS_DEPLOY.md) for the Windows VPS; that process does not require a seed command.

Backend:

```powershell
cd .\backend
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\seed_courses.py
python .\seed_users.py
uvicorn app.main:app --reload
```

Frontend in another PowerShell:

```powershell
cd .\frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

API docs: http://127.0.0.1:8000/docs

## Test the production build locally

With PostgreSQL running and `backend/.env` configured, start the backend in one PowerShell window:

```powershell
cd .\backend
.\.venv\Scripts\python.exe .\run_windows.py
```

In another PowerShell window, build and preview the frontend:

```powershell
cd .\frontend
npm.cmd ci
npm.cmd run build
npm.cmd run preview
```

Open http://localhost:4173/login. The preview server forwards `/api` to the local backend, so sign-in and data requests work without Caddy. Check http://localhost:4173/api/health for `{"status":"ok"}`. This preview command is for local testing; the Windows VPS uses Caddy to serve `frontend/dist`.

## Docker

For the complete frontend, backend, and PostgreSQL stack, see [Docker setup](docs/DOCKER.md).

```powershell
Copy-Item .env.example .env
# Edit .env and set your database and admin passwords.
docker compose up -d --build
```

Application: http://localhost:8080
