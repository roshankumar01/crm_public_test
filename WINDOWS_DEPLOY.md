# Windows VPS deployment

This deployment uses PostgreSQL, a React production build, FastAPI, and Caddy. The public API lives at `/api` on the same origin as the frontend.

## First deployment

These commands use the actual VPS checkout at `C:\crm_new`. The included `Caddyfile` serves `C:\crm_new\frontend\dist`. Keep using this path so Caddy does not serve a build from another folder.

Before updating, `git remote -v` in `C:\crm_new` should show `https://github.com/roshankumar01/crm_public_test.git`. This is the repository containing this deployment setup.

1. Create an empty PostgreSQL database and login for this CRM. Keep PostgreSQL reachable from the VPS at `127.0.0.1:5432`, or adjust the settings below.
2. From PowerShell, configure the backend:

   ```powershell
   cd C:\crm_new\backend
   Copy-Item .env.example .env
   notepad .env
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

   Set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `ADMIN_USERNAME`, and a strong `ADMIN_PASSWORD` in `backend/.env`. This file is ignored by Git. The database password and CRM admin password are different settings.

3. Build the frontend:

   ```powershell
   cd C:\crm_new\frontend
   npm.cmd ci
   npm.cmd run build
   ```

   The build is served from `frontend\dist`. You do not run `npm run dev` or `npm run preview` on the VPS. Production API requests always go to `/api` on the same host through Caddy; no `VITE_API_URL` setting is needed.

4. Start the backend from its directory:

   ```powershell
   cd C:\crm_new\backend
   .\.venv\Scripts\python.exe .\run_windows.py
   ```

   This creates or updates the database schema, ensures the built-in courses exist, and creates the admin automatically. No seed command is needed. On later starts, the admin password is synchronized with `backend/.env`. Keep `ADMIN_USERNAME` the same after first startup. Other users can be created in CRM settings after logging in.

5. Use the included `Caddyfile` as your Caddy configuration. After installing Caddy, validate and start it from PowerShell (adjust the path to `caddy.exe` if needed):

   ```powershell
   & C:\caddy\caddy.exe validate --config C:\crm_new\Caddyfile
   & C:\caddy\caddy.exe run --config C:\crm_new\Caddyfile
   ```

   `run` stays in the foreground and stops if that window closes. For reboot startup, install Caddy as a Windows service as described in the [official Caddy instructions](https://caddyserver.com/docs/running#windows-service). Open `http://YOUR_SERVER_IP:8080/login` and log in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `backend/.env`. Allow inbound TCP port 8080 in the VPS firewall. For a domain with HTTPS, replace `:8080` with your domain and allow ports 80 and 443.

Keep the backend process running with your Windows service manager. Its working directory must be `C:\crm_new\backend` so the `.env` file is found. The backend listens only on `127.0.0.1:8000`; Caddy handles public traffic.

## Starting again after a reboot

You do not need to rebuild or reinstall on every start. PostgreSQL, the backend, and Caddy must be running. If the backend and Caddy are installed as services, start or check them through Windows Services. Otherwise, start the backend with the command in step 4 and Caddy with the command in step 5, each in its own PowerShell window. Check these URLs on the server:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://localhost:8080/api/health
```

Both should report `status` as `ok`. Then open `http://localhost:8080/login`. Do not add `/api` when contacting port 8000 directly; Caddy adds that public route on port 8080.

## Updating

From the VPS checkout, pull changes, then rebuild the frontend and update backend packages:

```powershell
cd C:\crm_new
git pull --ff-only
cd frontend
npm.cmd ci
npm.cmd run build
cd ..\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then restart the existing backend process or service if backend code changed. If it is not installed as a service, stop the old backend window and run `cd C:\crm_new\backend` followed by `.\.venv\Scripts\python.exe .\run_windows.py` in a new window. The frontend build is served directly from `dist`, so Caddy does not need a restart for JavaScript changes. **This release changes `Caddyfile`; reload Caddy once** from `C:\crm_new`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\reload-caddy.ps1
```

The script finds the running `caddy.exe`, validates `C:\crm_new\Caddyfile`, and reloads it. If Caddy is installed at a location it cannot detect, pass `-CaddyExe 'C:\path\to\caddy.exe'`.

Finally run the deployment check from `C:\crm_new`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\check-windows.ps1
```

It verifies that Caddy is serving the build in this checkout, `/api/health` reaches the backend, and the login request reaches the database. A check failure means the deployment is not ready; do not diagnose it from the login page alone.

## API routing

The production frontend calls `/api/auth/login` on the same host that served the page. Caddy strips `/api` and forwards `/auth/login` to FastAPI. The old `/crm/*` proxy rule conflicted with frontend URLs such as `/crm/leads`. A production bundle calling `127.0.0.1:8000` instead tries to reach each visitor's own computer. A cross-origin `VITE_API_URL` set during an earlier build can produce this failure; rebuilding from the updated source fixes it.
