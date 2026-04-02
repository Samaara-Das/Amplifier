# Deployment Guide

How to deploy the Amplifier Server to Vercel with Supabase PostgreSQL, and how to run it locally.

## Local Development

### Prerequisites

```bash
cd server
pip install -r requirements.txt
```

Key dependencies: `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `aiosqlite` (local), `asyncpg` (production), `python-jose`, `passlib`, `jinja2`, `google-genai`, `stripe`, `supabase`.

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

## Production Deployment (Vercel + Supabase)

### Architecture

| Component | Technology |
|-----------|------------|
| Server runtime | Vercel Python serverless functions (`@vercel/python`) |
| Database | Supabase PostgreSQL (transaction pooler on port 6543) |
| Connection pooling | pgbouncer via Supabase transaction pooler |
| SQLAlchemy pool | `NullPool` (no persistent connections -- required for serverless) |
| SSL | Auto-configured with `ssl.CERT_NONE` (Supabase requires SSL) |
| Max lambda size | 50mb (set in `vercel.json`) |

### Step 1: Supabase PostgreSQL Setup

1. Create a Supabase project
2. Go to Supabase Dashboard > Settings > Database > Connection String > **Transaction Pooler** (port 6543)
3. Format the connection string for asyncpg:

```
postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
```

**Important**: Use the **transaction pooler** endpoint (port 6543), not the direct connection (port 5432). The codebase sets `prepared_statement_cache_size=0` and `statement_cache_size=0` in `server/app/core/database.py` for pgbouncer compatibility.

### Step 2: Set Vercel Environment Variables

Use `printf` (not `echo`) to avoid trailing newline corruption:

```bash
printf "postgresql+asyncpg://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres" | vercel env add DATABASE_URL production --cwd server

printf "your-random-secret-key" | vercel env add JWT_SECRET_KEY production --cwd server

printf "your-admin-password" | vercel env add ADMIN_PASSWORD production --cwd server

printf "your-gemini-api-key" | vercel env add GEMINI_API_KEY production --cwd server
```

#### Required Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Supabase PostgreSQL connection string (asyncpg format) | `sqlite+aiosqlite:///./amplifier.db` |
| `JWT_SECRET_KEY` | Secret key for JWT token signing | `change-me-to-a-random-secret` |
| `ADMIN_PASSWORD` | Password for the admin dashboard at `/admin/login` | `admin` |
| `GEMINI_API_KEY` | Google Gemini API key (used by campaign wizard for brief generation) | (none) |

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

### Step 3: Deploy

```bash
vercel deploy --yes --prod --cwd "C:/Users/dassa/Work/Auto-Posting-System/server"
```

### Step 4: Verify

```bash
# Health check (should return {"status": "ok"})
curl https://your-domain.vercel.app/health

# Version check (should return {"version": "0.1.0", ...})
curl https://your-domain.vercel.app/api/version
```

Then verify dashboards:
- Swagger docs: `https://your-domain.vercel.app/docs`
- Admin dashboard: `https://your-domain.vercel.app/admin/login`
- Company dashboard: `https://your-domain.vercel.app/company/login`

Current production deployment: `https://server-five-omega-23.vercel.app`

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
| Writable paths | Any directory | Only `/tmp/` on Vercel |
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

### 3. Lambda Size Exceeded

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

**Symptom**: Data disappears between requests on Vercel.

**Cause**: `DATABASE_URL` not set or still pointing to SQLite. On Vercel, SQLite uses `/tmp/` which is ephemeral (data lost on cold start).

**Fix**: Verify `DATABASE_URL` is set in Vercel environment variables and starts with `postgresql+asyncpg://`.

### 8. bcrypt / passlib Version Conflict

**Symptom**: `AttributeError` or hash verification failures during login.

**Cause**: `passlib` requires `bcrypt<4.1` for its internal API, but `bcrypt>=4.2` changed the interface.

**Fix**: The `requirements.txt` pins `bcrypt>=4.2.0` and `passlib[bcrypt]>=1.7.4`. If you see hash errors, ensure both are installed and compatible. Alternatively, set `passlib`'s bcrypt backend explicitly.
