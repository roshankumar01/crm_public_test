# Windows VPS deployment

This deployment uses PostgreSQL, a React production build, FastAPI, and Caddy. The public API lives at `/api` on the same origin as the frontend.

## First deployment

These commands assume the repository is cloned to `C:\crm\crm_public`, matching the included `Caddyfile`. If you use another directory, make a copy of the Caddyfile outside the Git checkout and change its `root` path there. Start Caddy with `--config` pointing to that copy, so future pulls do not conflict with your server-specific path.

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

   The build is served from `frontend\dist`. You do not run `npm run dev` or `npm run preview` on the VPS. Production API requests always go to `/api` on the same host through Caddy; no `VITE_API_URL` setting is needed.

4. Start the backend from its directory:

   ```powershell
   cd C:\crm\crm_public\backend
   .\.venv\Scripts\python.exe .\run_windows.py
   ```

   This creates or updates the database schema, ensures the built-in courses exist, and creates the admin automatically. No seed command is needed. On later starts, the admin password is synchronized with `backend/.env`. Keep `ADMIN_USERNAME` the same after first startup. Other users can be created in CRM settings after logging in.

5. Use the included `Caddyfile` as your Caddy configuration. After installing Caddy, validate and start it from PowerShell (adjust the path to `caddy.exe` if needed):

   ```powershell
   & C:\caddy\caddy.exe validate --config C:\crm\crm_public\Caddyfile
   & C:\caddy\caddy.exe run --config C:\crm\crm_public\Caddyfile
   ```

   `run` stays in the foreground and stops if that window closes. For reboot startup, install Caddy as a Windows service as described in the [official Caddy instructions](https://caddyserver.com/docs/running#windows-service). Open `http://YOUR_SERVER_IP:8080/login` and log in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `backend/.env`. Allow inbound TCP port 8080 in the VPS firewall. For a domain with HTTPS, replace `:8080` with your domain and allow ports 80 and 443.

Keep the backend process running with your Windows service manager. Its working directory must be `C:\crm\crm_public\backend` (or your chosen backend directory) so the `.env` file is found. The backend listens only on `127.0.0.1:8000`; Caddy handles public traffic.

## Starting again after a reboot

You do not need to rebuild or reinstall on every start. PostgreSQL, the backend, and Caddy must be running. If the backend and Caddy are installed as services, start or check them through Windows Services. Otherwise, start the backend with the command in step 4 and Caddy with the command in step 5, each in its own PowerShell window. Check these URLs on the server:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://localhost:8080/api/health
```

Both should report `status` as `ok`. Then open `http://localhost:8080/login`. Do not add `/api` when contacting port 8000 directly; Caddy adds that public route on port 8080.

## Updating

From the repository directory, pull changes, then rebuild the frontend and update backend packages:

```powershell
git pull
cd frontend
npm ci
npm run build
cd ..\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then restart the existing backend process or service. If it is not installed as a service, stop the old backend window and run `cd C:\crm\crm_public\backend` followed by `.\.venv\Scripts\python.exe .\run_windows.py` in a new window. Caddy does not need a restart for a new frontend build. Reload Caddy only if its configuration changes.

## API routing

The production frontend calls `/api/auth/login` on the same host that served the page. Caddy strips `/api` and forwards `/auth/login` to FastAPI. The old `/crm/*` proxy rule conflicted with frontend URLs such as `/crm/leads`. A production bundle calling `127.0.0.1:8000` instead tries to reach each visitor's own computer. A cross-origin `VITE_API_URL` set during an earlier build can produce this failure; rebuilding from the updated source fixes it.
