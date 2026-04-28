# Deployment Guide

> **Status (2026-04-25):** Production server is **LIVE at `https://api.pointcapitalis.com`** — Hostinger KVM 1 VPS (Mumbai, Ubuntu 24.04), Caddy reverse proxy, systemd `amplifier-web.service`. See `docs/HOSTING-DECISION-RECORD.md` and `docs/MIGRATION-FROM-VERCEL.md` for full details. The Vercel instructions below are preserved as historical reference for the connection/pgbouncer settings, which carry over.

How to run the Amplifier Server locally and deploy to the Hostinger VPS.

## Local Development

### Prerequisites

```bash
cd server
pip install -r requirements.txt
```

Key dependencies: `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `aiosqlite` (local), `asyncpg` (production), `python-jose`, `passlib`, `jinja2`, `google-genai`, `stripe`, `supabase`, `numpy>=1.24.0`, `piexif>=1.1.3`.

### Running Locally

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

| Endpoint | URL |
|----------|-----|
| Swagger docs | http://localhost:8000/docs |
| Company dashboard | http://localhost:8000/company/login |
| Admin dashboard | http://localhost:8000/admin/login (password: `admin`) |
| Health check | http://localhost:8000/health |
| Version check | http://localhost:8000/api/version |

### Local Database

By default, the server uses SQLite (`sqlite+aiosqlite:///./amplifier.db`). No setup required -- tables are auto-created on startup via `init_tables()` in the FastAPI lifespan handler (`app/main.py`).

The SQLite file is created in the `server/` directory. On Vercel, if SQLite is used accidentally, it falls back to `/tmp/amplifier.db` (ephemeral -- data lost between cold starts).

---

## Production Deployment (Hostinger KVM VPS + Supabase)

> **Current production host** — see `docs/HOSTING-DECISION-RECORD.md` for the full decision record and `docs/MIGRATION-FROM-VERCEL.md` for the migration runbook.

### Architecture

| Component | Technology |
|-----------|------------|
| Server runtime | uvicorn (1 worker, `127.0.0.1:8000`) managed by systemd `amplifier-web.service` |
| Reverse proxy | Caddy with auto-TLS via Let's Encrypt |
| Database | Supabase PostgreSQL (transaction pooler on port 6543) |
| Connection pooling | pgbouncer via Supabase transaction pooler |
| SQLAlchemy pool | `NullPool` (no persistent connections — required for pgbouncer) |
| SSL | Auto-configured with `ssl.CERT_NONE` (Supabase requires SSL) |
| SSH access | `ssh -i ~/.ssh/amplifier_vps sammy@31.97.207.162` (key-only). NOPASSWD sudo for `sammy`. |

### Step 1: Supabase PostgreSQL Setup

1. Create a Supabase project
2. Go to Supabase Dashboard > Settings > Database > Connection String > **Transaction Pooler** (port 6543)
3. Format the connection string for asyncpg:

```
postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
```

**Important**: Use the **transaction pooler** endpoint (port 6543), not the direct connection (port 5432). The codebase sets `prepared_statement_cache_size=0` and `statement_cache_size=0` in `server/app/core/database.py` for pgbouncer compatibility.

### Step 2: Set Environment Variables on VPS

SSH into the VPS and set env vars in `/etc/systemd/system/amplifier-web.service` under `[Service]` → `Environment=`:

```bash
ssh -i ~/.ssh/amplifier_vps sammy@31.97.207.162
sudo systemctl edit amplifier-web.service  # or edit unit file directly
sudo systemctl daemon-reload && sudo systemctl restart amplifier-web.service
```

#### Required Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Supabase PostgreSQL connection string (asyncpg format) | `sqlite+aiosqlite:///./amplifier.db` |
| `JWT_SECRET_KEY` | Secret key for JWT token signing | `change-me-to-a-random-secret` |
| `ADMIN_PASSWORD` | Password for the admin dashboard at `/admin/login` | `admin` |
| `GEMINI_API_KEY` | Google Gemini API key (used by campaign wizard for brief generation) | (none) |
| `ENCRYPTION_KEY` | AES-256-GCM encryption key for server-side data encryption. Without it, a dev fallback key is used (not secure for production). | Dev fallback key |

#### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis URL for background jobs (ARQ worker: billing every 6h, trust checks 2x/day) | `redis://localhost:6379/0` |
| `STRIPE_SECRET_KEY` | Stripe secret key for user payouts and company top-ups | (none) |
| `SUPABASE_URL` | Supabase project URL for campaign asset file uploads | (none) |
| `SUPABASE_SERVICE_KEY` | Supabase service role key for storage | (none) |
| `PLATFORM_CUT_PERCENT` | Platform cut on user earnings (0-100) | `20` |
| `MIN_PAYOUT_THRESHOLD` | Minimum payout amount in USD | `10.00` |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server bind port | `8000` |
| `DEBUG` | Enable SQLAlchemy echo logging | `true` |

### Step 3: Deploy (VPS)

```bash
# Push changes to server then pull on VPS
git push origin main
ssh -i ~/.ssh/amplifier_vps sammy@31.97.207.162 "cd ~/amplifier && git pull && sudo systemctl restart amplifier-web.service"
```

### Step 4: Verify

```bash
# Health check (should return {"status": "ok"})
curl https://api.pointcapitalis.com/health

# Version check
curl https://api.pointcapitalis.com/api/version
```

Then verify dashboards:
- Swagger docs: `https://api.pointcapitalis.com/docs`
- Admin dashboard: `https://api.pointcapitalis.com/admin/login`
- Company dashboard: `https://api.pointcapitalis.com/company/login`

---

## vercel.json Configuration

Located at `server/vercel.json`:

```json
{
  "builds": [
    {
      "src": "app/main.py",
      "use": "@vercel/python",
      "config": {
        "maxLambdaSize": "50mb"
      }
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app/main.py"
    }
  ]
}
```

**Important**: `rootDirectory` is a Vercel project-level setting (set via dashboard or CLI). Do NOT include it in `vercel.json` -- the CLI rejects it.

---

## Local vs Production Differences

| Aspect | Local (SQLite) | Production (Supabase PostgreSQL) |
|--------|---------------|----------------------------------|
| Database file | `server/amplifier.db` (auto-created) | Supabase managed PostgreSQL |
| Connection pool | `StaticPool` (single connection, `check_same_thread=False`) | `NullPool` (serverless-safe, no persistent connections) |
| SSL | Not required | Required (`ssl.create_default_context()` with `check_hostname=False`, `verify_mode=ssl.CERT_NONE`) |
| pgbouncer settings | N/A | `statement_cache_size=0`, `prepared_statement_cache_size=0` |
| Table creation | `init_tables()` on startup | `init_tables()` on startup (idempotent, logs warning if tables exist) |
| Debug logging | `echo=True` (default) | Set `DEBUG=false` to disable |
| Writable paths | Any directory | VPS home dir (no restriction) |
| CORS | `allow_origins=["*"]` | Same (restrict in production by editing `app/main.py`) |

The database backend is auto-detected from `DATABASE_URL` prefix in `server/app/core/database.py`:
- `sqlite` -- SQLite mode with `StaticPool` and `check_same_thread=False`
- `postgresql` -- PostgreSQL mode with `NullPool`, SSL, and pgbouncer-compatible settings

---

## Common Deployment Issues

### 1. `prepared_statement_cache_size` Error

**Symptom**: `asyncpg.exceptions.InterfaceError` about prepared statements.

**Cause**: Supabase uses pgbouncer in transaction pooling mode, which does not support prepared statements.

**Fix**: Already handled in `server/app/core/database.py`. Verify `DATABASE_URL` starts with `postgresql` (not `sqlite`), which triggers the pgbouncer-compatible engine kwargs.

### 2. SSL Connection Refused

**Symptom**: Connection refused or SSL handshake failure when connecting to Supabase.

**Fix**: The codebase creates an SSL context with `check_hostname=False` and `verify_mode=ssl.CERT_NONE`. Ensure `DATABASE_URL` uses the transaction pooler endpoint (port 6543).

### 3. (Vercel historical) Lambda Size Exceeded

> This issue only applies if deploying to Vercel. The production server is now on Hostinger KVM VPS — this error will not occur there.

**Symptom**: Vercel build fails with "Lambda exceeds maximum size."

**Fix**: `maxLambdaSize` is set to `50mb` in `vercel.json`. If dependencies push past this, audit `server/requirements.txt`. The heaviest packages: `google-genai`, `supabase`, `stripe`, `PyPDF2`, `python-docx`.

### 4. Tables Not Created

**Symptom**: 500 errors about missing tables on first deploy.

**Cause**: `init_tables()` runs on every cold start via the FastAPI lifespan handler. If the database user lacks `CREATE TABLE` permissions, tables won't be created.

**Fix**: Use a Supabase connection string with the default `postgres` user (has DDL permissions). Check the Vercel function logs for the `init_tables failed:` warning.

### 5. Environment Variable Corruption (Trailing Newlines)

**Symptom**: Auth failures, database connection errors, or "invalid JWT" after setting env vars.

**Cause**: `echo` adds a trailing newline on some shells, corrupting the value.

**Fix**: Always use `printf` (not `echo`) when piping values to `vercel env add`:
```bash
printf "your-value" | vercel env add VAR_NAME production --cwd server
```

### 6. CORS Errors from Frontend

**Symptom**: Browser console shows CORS errors when calling the API.

**Cause**: Current config allows all origins (`allow_origins=["*"]`). If this is changed, update the allowed origins list in `server/app/main.py`.

### 7. SQLite Used Accidentally in Production

**Symptom**: Server starts but data is missing — it's writing to a local SQLite file instead of Supabase PostgreSQL.

**Cause**: `DATABASE_URL` env var not set or not exported in the systemd unit file, so the server falls back to SQLite.

**Fix**: Verify `DATABASE_URL` is set in the systemd unit's environment and starts with `postgresql+asyncpg://`. Restart the service after adding it.

### 8. bcrypt / passlib Version Conflict

**Symptom**: `AttributeError` or hash verification failures during login.

**Cause**: `passlib` requires `bcrypt<4.1` for its internal API, but `bcrypt>=4.2` changed the interface.

**Fix**: The `requirements.txt` pins `bcrypt>=4.2.0` and `passlib[bcrypt]>=1.7.4`. If you see hash errors, ensure both are installed and compatible. Alternatively, set `passlib`'s bcrypt backend explicitly.
