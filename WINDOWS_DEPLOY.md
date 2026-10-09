# Windows Server VPS deployment

This guide uses `C:\crm_new` for the Git checkout, PostgreSQL for data, FastAPI on `127.0.0.1:8000`, and Caddy on port 8080. The browser calls `/api` on the same host that serves the frontend. The tracked `Caddyfile` points to `C:\crm_new\frontend\dist`.

**Run each PowerShell command separately and wait for it to finish.** Do not paste a whole block as one long line. Use `npm.cmd` in PowerShell so its script execution policy does not block npm.

## A. First deployment on a new VPS

Do this section once. If `C:\crm_new` already exists and `git status` works there, use [section B](#b-update-an-existing-vps) instead.

### 1. Install the programs

Install [Git for Windows](https://git-scm.com/install/windows), [Python 3.13 x64](https://www.python.org/downloads/windows/), [Node.js LTS](https://nodejs.org/en/download) (the locked Vite build requires Node 22.12 or later), and [PostgreSQL for Windows](https://www.postgresql.org/download/windows/). Keep PostgreSQL running on `127.0.0.1:5432`.

Download [Caddy for Windows](https://caddyserver.com/docs/install) and place `caddy.exe` at `C:\caddy\caddy.exe`. Open a new PowerShell window and check the tools:

```powershell
git --version
py -3.13 --version
node --version
npm.cmd --version
& C:\caddy\caddy.exe version
```

### 2. Clone this project

```powershell
git clone https://github.com/roshankumar01/crm_public_test.git C:\crm_new
cd C:\crm_new
git remote -v
```

The remote should be `crm_public_test.git`. Future updates use `git pull`; do not clone again into this folder.

### 3. Create the database

Open **SQL Shell (psql)** from the PostgreSQL installation. Connect to the default host `localhost`, port `5432`, database `postgres`, as user `postgres`. At its `postgres=#` prompt, enter these lines one at a time:

```sql
CREATE ROLE learning_crm LOGIN;
\password learning_crm
CREATE DATABASE learning_crm OWNER learning_crm;
\q
```

The `\password` command prompts for a new database password. Save it for the next step. Do not repeat these creation commands for an existing database. [PostgreSQL database ownership documentation](https://www.postgresql.org/docs/current/sql-createdatabase.html).

### 4. Configure and install the backend

```powershell
Copy-Item C:\crm_new\backend\.env.example C:\crm_new\backend\.env
notepad C:\crm_new\backend\.env
```

Set `DB_PASSWORD` to the database password from step 3. Set a **different**, strong `ADMIN_PASSWORD` for CRM login. If you used the database commands above, keep `DB_HOST=127.0.0.1`, `DB_PORT=5432`, `DB_NAME=learning_crm`, and `DB_USER=learning_crm`. Keep `ADMIN_USERNAME` unchanged after first startup. `backend\.env` is ignored by Git and is not overwritten by a pull.

```powershell
cd C:\crm_new\backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 5. Build the frontend

```powershell
cd C:\crm_new\frontend
npm.cmd ci
npm.cmd run build
```

The build writes `frontend\dist` and then exits. No frontend process must remain running. Do not run `npm run dev` or `npm run preview` on the VPS.

### 6. Test the backend before installing services

In one PowerShell window:

```powershell
cd C:\crm_new\backend
.\.venv\Scripts\python.exe .\run_windows.py
```

First startup creates or updates the schema, adds built-in courses, and creates the admin from `backend\.env`. No seed command is needed. Leave this window open. In a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

It should report `status : ok`. Then press **Ctrl+C** in the backend window before installing the service, so only one backend listens on port 8000.

### 7. Install the backend service

Download the x64 executable from the [WinSW releases](https://github.com/winsw/winsw/releases) and save it as `C:\crm_new\deploy\backend-service.exe`. The repository includes `deploy\backend-service.xml` with the backend executable, working directory, automatic startup, and restart on failure.

In **PowerShell as Administrator**, run each line separately:

```powershell
& C:\crm_new\deploy\backend-service.exe install
& C:\crm_new\deploy\backend-service.exe start
Get-Service LearningCrmBackend
Invoke-RestMethod http://127.0.0.1:8000/health
```

The service should be `Running`, and health should report `ok`. [WinSW configuration documentation](https://github.com/winsw/winsw/blob/v3/docs/xml-config-file.md).

### 8. Install the Caddy service

In **PowerShell as Administrator**, run each line separately:

```powershell
& C:\caddy\caddy.exe validate --config C:\crm_new\Caddyfile
sc.exe create LearningCrmCaddy start= auto binPath= "C:\caddy\caddy.exe run --config C:\crm_new\Caddyfile"
sc.exe start LearningCrmCaddy
Get-Service LearningCrmCaddy
```

The service should be `Running`. If Caddy is already running in a PowerShell window, press **Ctrl+C** there before starting the service. [Caddy's Windows service instructions](https://caddyserver.com/docs/running#windows-service).

### 9. Check the app and sign in

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\crm_new\deploy\check-windows.ps1
```

Expect three `PASS` lines: Caddy serves this checkout's build, `/api/health` reaches FastAPI, and `/api/auth/login` reaches the database. Open `http://localhost:8080/login` **on the VPS** and sign in with the admin account from `backend\.env`.

These checks confirm operation on the VPS itself. Access from a different device also depends on the hosting provider and Windows firewall allowing the public port; that is separate from the app setup.

## B. Update an existing VPS

Use this section after changes have been pushed to `crm_public_test/main`. Run each line separately. Do not recreate the database, `.env`, or virtual environment.

### 1. Pull the code

```powershell
cd C:\crm_new
git status --short
git pull --ff-only
```

`git status --short` should be empty before the pull. If it shows changes or the pull fails, resolve that result before rebuilding. The repository URL is needed only for the first clone.

### 2. Update and restart the backend

If it runs as the WinSW service installed above:

```powershell
& C:\crm_new\deploy\backend-service.exe stop
& C:\crm_new\backend\.venv\Scripts\python.exe -m pip install -r C:\crm_new\backend\requirements.txt
& C:\crm_new\deploy\backend-service.exe start
```

If it runs in a PowerShell window instead, press **Ctrl+C** in that window, run the middle `pip install` command above, then start it again from `C:\crm_new\backend` with `.\.venv\Scripts\python.exe .\run_windows.py`.

### 3. Rebuild the frontend

```powershell
npm.cmd --prefix C:\crm_new\frontend ci
npm.cmd --prefix C:\crm_new\frontend run build
```

If `npm ci` reports `EPERM` on `rolldown-binding`, a leftover Vite `dev` or `preview` process may hold that file open. Identify it with `Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Select-Object ProcessId,CommandLine`, stop only that Vite process, and retry. Caddy does not use the Node process.

### 4. Reload Caddy and verify

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\crm_new\deploy\reload-caddy.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\crm_new\deploy\check-windows.ps1
```

The reload script validates and applies `C:\crm_new\Caddyfile`. If it cannot find Caddy, pass `-CaddyExe 'C:\your\path\caddy.exe'`. The check must print three `PASS` lines. Refresh `http://localhost:8080/login` with **Ctrl+Shift+R** and sign in.

## C. After a reboot

PostgreSQL, `LearningCrmBackend`, and `LearningCrmCaddy` should start as services. Check them without rebuilding:

```powershell
Get-Service *postgres*,LearningCrmBackend,LearningCrmCaddy
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\crm_new\deploy\check-windows.ps1
```

The frontend is static files in `dist`, not a service. A reboot alone does not require `git pull`, `npm ci`, or `npm run build`.

## If a check fails

| Result | What to check |
| --- | --- |
| Build missing | Run `npm.cmd --prefix C:\crm_new\frontend run build`. |
| Caddy serves a different build | Check `root * C:/crm_new/frontend/dist` in `Caddyfile`, then run `deploy\reload-caddy.ps1`. |
| `/api/health` fails | Check the backend service and `http://127.0.0.1:8000/health`. |
| Login check does not return 401 | Check PostgreSQL and the `DB_*` values in `backend\.env`; do not share that file or its passwords. |
| Real admin login returns 401 | Check `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `backend\.env`, then restart the backend so it synchronizes the admin. |

Port 8000 is the direct backend and uses `/health`. Port 8080 is Caddy and uses `/api/health`. The production frontend calls `/api/auth/login` on the same host, so it needs no `VITE_API_URL` override.
