# Windows VPS deployment

This deployment uses PostgreSQL, a React production build, FastAPI, and Caddy. The public API lives at `/api` on the same origin as the frontend.

## First deployment

These commands assume the repository is cloned to `C:\crm\crm_public`, matching the included `Caddyfile`. If you use another directory, update Caddy's `root` path.

1. Create an empty PostgreSQL database and login for this CRM. Keep PostgreSQL reachable from the VPS at `127.0.0.1:5432`, or adjust the settings below.
2. From PowerShell, configure the backend:

   ```powershell
   cd C:\crm\crm_public\backend
   Copy-Item .env.example .env
   notepad .env
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

   Set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `ADMIN_USERNAME`, and a strong `ADMIN_PASSWORD` in `backend/.env`. This file is ignored by Git. The database password and CRM admin password are different settings.

3. Build the frontend:

   ```powershell
   cd C:\crm\crm_public\frontend
   npm ci
   npm run build
   ```

4. Start the backend from its directory:

   ```powershell
   cd C:\crm\crm_public\backend
   .\.venv\Scripts\python.exe .\run_windows.py
   ```

   This creates or updates the database schema, ensures the built-in courses exist, and creates the admin automatically. No seed command is needed. On later starts, the admin password is synchronized with `backend/.env`. Keep `ADMIN_USERNAME` the same after first startup. Other users can be created in CRM settings after logging in.

5. Use the included `Caddyfile` as your Caddy configuration and start or reload Caddy. Open `http://YOUR_SERVER_IP:8080/login` and log in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `backend/.env`. Allow inbound TCP port 8080 in the VPS firewall. For a domain with HTTPS, replace `:8080` with your domain and allow ports 80 and 443.

Keep the backend process running with your Windows service manager. Its working directory must be `C:\crm\crm_public\backend` (or your chosen backend directory) so the `.env` file is found. The backend listens only on `127.0.0.1:8000`; Caddy handles public traffic.

## Updating

From the repository directory, pull changes, then rebuild and restart the backend process:

```powershell
git pull
cd frontend
npm ci
npm run build
cd ..\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\run_windows.py
```

Run the final command through your service manager if one is configured. Restart Caddy only when you change its configuration.

## API routing

The production frontend calls `/api/auth/login` on the same host that served the page. Caddy strips `/api` and forwards `/auth/login` to FastAPI. The old `/crm/*` proxy rule conflicted with frontend URLs such as `/crm/leads`. A production bundle calling `127.0.0.1:8000` instead tries to reach each visitor's own computer.
