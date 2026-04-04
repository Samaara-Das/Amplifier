# Amplifier Admin Dashboard — Deployment Guide

## 1. Local Development

### Prerequisites
- Python 3.11+
- pip packages: `fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `aiosqlite`, `jinja2`, `pydantic-settings`, `python-multipart`, `passlib[bcrypt]`

### Start the Server
```bash
cd server
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Access the Dashboard
- URL: `http://localhost:8000/admin/login`
- Password: `admin` (default)

### Database
SQLite file at `server/amplifier.db`. Created automatically on first startup via `init_tables()`. New tables (`audit_log`, `content_screening_logs`) and the `companies.status` column are created automatically by SQLAlchemy's `create_all`.

### LAN Access
To make the admin dashboard accessible to other devices on your network:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Access via `http://<your-lan-ip>:8000/admin/login`.

---

## 2. Production Deployment (Vercel + Supabase)

### Environment Variables
Set these in your Vercel project settings:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string. Format: `postgresql+asyncpg://user:pass@host:port/db` |
| `ADMIN_PASSWORD` | Yes | Admin dashboard password. Use a strong password in production. |
| `JWT_SECRET_KEY` | Yes | Secret key for JWT token generation. Use a random 32+ character string. |
| `STRIPE_SECRET_KEY` | No | Stripe API key for payment processing. Omit for test mode (instant credit). |
| `SUPABASE_URL` | No | Supabase project URL for file storage. |
| `SUPABASE_SERVICE_KEY` | No | Supabase service key for file storage. |

### Database Migration (Supabase)
When deploying the admin system for the first time on an existing database, run these SQL statements in the Supabase SQL Editor:

```sql
-- Create audit_log table
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    action VARCHAR(50) NOT NULL,
    target_type VARCHAR(30) NOT NULL,
    target_id INTEGER NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '{}',
    admin_ip VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create content_screening_logs table
CREATE TABLE IF NOT EXISTS content_screening_logs (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL UNIQUE REFERENCES campaigns(id),
    flagged BOOLEAN NOT NULL DEFAULT FALSE,
    flagged_keywords JSONB NOT NULL DEFAULT '[]',
    screening_categories JSONB NOT NULL DEFAULT '[]',
    reviewed_by_admin BOOLEAN NOT NULL DEFAULT FALSE,
    review_result VARCHAR(20),
    review_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_content_screening_logs_campaign_id
    ON content_screening_logs(campaign_id);

-- Add status column to companies (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'companies' AND column_name = 'status'
    ) THEN
        ALTER TABLE companies ADD COLUMN status VARCHAR(20) DEFAULT 'active';
    END IF;
END $$;
```

### Deploy to Vercel
```bash
vercel deploy --yes --prod --cwd server
```

### Production URLs
- Company dashboard: `https://<your-domain>/company/login`
- Admin dashboard: `https://<your-domain>/admin/login`
- API docs: `https://<your-domain>/docs`

---

## 3. Configuration Reference

### Server Config (via environment variables)

| Setting | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./amplifier.db` | Database connection string |
| `ADMIN_PASSWORD` | `admin` | Admin login password |
| `JWT_SECRET_KEY` | `change-me-to-a-random-secret` | JWT signing key |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | Token lifetime |
| `PLATFORM_CUT_PERCENT` | `20.0` | Platform's take from earnings (%) |
| `MIN_PAYOUT_THRESHOLD` | `10.0` | Minimum balance for payout ($) |
| `DEBUG` | `true` | SQLAlchemy echo and debug mode |
| `SERVER_URL` | `http://localhost:8000` | Public server URL |
| `STRIPE_SECRET_KEY` | (empty) | Stripe API key |
| `SUPABASE_URL` | (empty) | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | (empty) | Supabase service key |

---

## 4. Security Checklist

### Before Going Live
- [ ] Change `ADMIN_PASSWORD` from default `"admin"` to a strong password
- [ ] Change `JWT_SECRET_KEY` to a random 32+ character string
- [ ] Set `DEBUG=false` to disable SQLAlchemy query logging
- [ ] Restrict CORS origins in `main.py` (currently `allow_origins=["*"]`)
- [ ] Use HTTPS (Vercel provides this automatically)
- [ ] Set `DATABASE_URL` to production PostgreSQL (not SQLite)
- [ ] Run the SQL migration script on the production database
- [ ] Test all 10 admin pages return 200 after deployment

### Ongoing
- Review the audit log periodically for unexpected actions
- Monitor the fraud dashboard for anomalies
- Process pending reviews and appeals regularly
- Run billing and payout cycles on schedule (or set up background jobs)

---

## 5. Troubleshooting

### "Internal Server Error" on a page
Check the server logs for the full traceback. Common causes:
- **Missing database column**: Run the SQL migration script (Section 2)
- **JSON data type mismatch**: Some `platforms` JSON values may be booleans instead of dicts. The code handles this gracefully, but other JSON fields may have similar issues.

### "No such column: companies.status"
The `companies` table needs the `status` column added. Run:
```sql
ALTER TABLE companies ADD COLUMN status VARCHAR(20) DEFAULT 'active';
```

### Review queue crashes
Ensure the `content_screening_logs` table exists. Run the `CREATE TABLE` statement from Section 2.

### Audit log is empty
Audit entries are only created when admin actions are performed through the dashboard. Existing data from before v2.0.0 won't have audit entries.

### Pagination shows wrong total
The count query runs in parallel with the data query. If records are being actively created or deleted, the count may be slightly off. This is expected behavior.
