# Run Learning CRM with Docker

The stack contains PostgreSQL, the FastAPI backend, and the built React frontend served by Nginx. Open Docker Desktop with Linux containers enabled before starting.

## First start

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set your database password, admin password, and admin details. This root `.env` is separate from `backend/.env`; it is ignored by Git and excluded from both Docker images. Passwords containing URL characters such as `@` or `:` are supported. If a password contains `$` or `#`, enclose its value in single quotes in `.env` so Compose reads it literally.

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

- Application: **http://localhost:8080**
- API documentation: **http://localhost:8080/api/docs**
- API health: **http://localhost:8080/api/health**
- Login: the `ADMIN_USERNAME` and `ADMIN_PASSWORD` you configured.

`WEB_PORT` changes the application port if 8080 is already in use. Database and backend ports stay inside the Compose network.

Startup waits for PostgreSQL, applies the application's existing schema/mapping setup, inserts missing IGC/IDIP course records, and creates an administrator only if there is no active administrator. Restarts preserve existing users, passwords, course edits, and imported records. Sample counselors are not automatically created; add your counselors through Settings.

## Updating and stopping

After changing application files:

```powershell
docker compose up -d --build
```

To stop while keeping your data:

```powershell
docker compose down
```

PostgreSQL data is kept in the `learning-crm_postgres_data` volume. Do not add `--volumes` to the stop command when you want to keep the database. Changing `POSTGRES_PASSWORD` in `.env` does not change a password already stored in an initialized PostgreSQL database. Changing `ADMIN_PASSWORD` does not reset an existing account's password.

## Existing local data

Docker starts with its own database volume. Your current local PostgreSQL database is not automatically copied or changed. To use existing CRM data in Docker, back up the local database and restore the backup into the Docker PostgreSQL service before using the new deployment. Keep the original database until the restored records have been checked.

## Uploads and performance

- Nginx permits files up to 100 MB and uses extended API timeouts for previews and exports.
- The backend runs one worker because current upload and migration progress is held in process memory. Increasing workers or backend replicas would require moving job progress into shared storage first.
- Imported records and file history live in PostgreSQL. In-progress jobs and downloadable skipped-row reports are held in memory and do not survive an API restart. Allow active uploads to finish before rebuilding or stopping.
- The frontend calls `/api` on the same host, so it works from another computer without calling that computer's localhost API.
- The regular local development commands still work. `VITE_API_URL` can override the API address for a custom frontend build; Docker sets it to `/api`.

## Troubleshooting

```powershell
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 db
```

If the Docker engine cannot be reached, start Docker Desktop and wait for its engine to be ready. If Compose reports a missing password, fill in the root `.env`. First builds require internet access to download base images and dependencies.

The frontend reverse proxy strips `/api` before forwarding requests. API documentation uses the same prefix through FastAPI's `root_path` setting. The backend startup waits and Compose dependency health checks follow [Docker's startup guidance](https://docs.docker.com/compose/how-tos/startup-order/).

## Verification

Both images were built and started with PostgreSQL in an isolated Compose project. Checks passed for container health, Nginx configuration, Python dependency compatibility, admin login, API docs, dashboard date ranges, direct page refreshes, learner upload progress, skipped-row downloads, and learner retrieval. Restarting the backend preserved the admin login and imported learner. All 29 backend tests passed. The temporary test containers and database volume were removed after verification.
