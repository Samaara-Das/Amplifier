# Amplifier Admin Dashboard — Architecture Document

## 1. System Architecture

```
Browser (Admin)
    │
    ▼
FastAPI (Uvicorn)
    │
    ├── /admin/login     → login.py     (auth)
    ├── /admin/          → overview.py   (dashboard)
    ├── /admin/users     → users.py      (user management)
    ├── /admin/companies → companies.py  (company management)
    ├── /admin/campaigns → campaigns.py  (campaign management)
    ├── /admin/financial → financial.py  (payouts/billing)
    ├── /admin/fraud     → fraud.py      (trust/penalties)
    ├── /admin/analytics → analytics.py  (platform stats)
    ├── /admin/review-queue → review.py  (content moderation)
    ├── /admin/settings  → settings.py   (system config)
    └── /admin/audit-log → audit.py      (audit trail)
    │
    ▼
SQLAlchemy (Async)
    │
    ├── SQLite (local development)
    └── PostgreSQL via Supabase (production)
```

## 2. File Structure

```
server/app/
├── routers/
│   └── admin/
│       ├── __init__.py      # Combined router, shared helpers (auth, pagination, audit)
│       ├── login.py         # Login/logout routes
│       ├── overview.py      # Dashboard with stats, trends, health indicators
│       ├── users.py         # User list, detail, suspend/ban/trust actions
│       ├── companies.py     # Company list, detail, fund management, suspend
│       ├── campaigns.py     # Campaign list, detail, pause/resume/cancel
│       ├── financial.py     # Payout stats, billing/payout cycle triggers
│       ├── fraud.py         # Penalties, trust checks, appeal processing
│       ├── analytics.py     # Platform metrics, top posts
│       ├── review.py        # Content screening review queue
│       ├── settings.py      # System config display (read-only)
│       └── audit.py         # Audit log viewer
│
├── models/
│   ├── audit_log.py         # AuditLog model (NEW)
│   ├── content_screening.py # ContentScreeningLog model (NEW)
│   ├── company.py           # Company model (MODIFIED: added status field)
│   ├── user.py              # User model
│   ├── campaign.py          # Campaign model
│   ├── assignment.py        # CampaignAssignment model
│   ├── post.py              # Post model
│   ├── metric.py            # Metric model
│   ├── payout.py            # Payout model
│   ├── penalty.py           # Penalty model
│   └── __init__.py          # Model registry
│
├── templates/
│   ├── base.html            # Shared layout (sidebar, CSS, responsive)
│   └── admin/
│       ├── _nav.html         # Shared navigation partial (10 pages + logout)
│       ├── login.html        # Login form
│       ├── overview.html     # Dashboard
│       ├── users.html        # User list
│       ├── user_detail.html  # User detail (tabbed)
│       ├── companies.html    # Company list
│       ├── company_detail.html # Company detail with fund management
│       ├── campaigns.html    # Campaign list
│       ├── campaign_detail.html # Campaign detail (tabbed)
│       ├── financial.html    # Financial dashboard
│       ├── fraud.html        # Fraud & trust center
│       ├── analytics.html    # Platform analytics
│       ├── review_queue.html # Content review queue
│       ├── settings.html     # System settings
│       └── audit_log.html    # Audit log viewer
│
└── core/
    ├── config.py             # Pydantic settings (env vars)
    └── database.py           # SQLAlchemy engine, session, Base
```

## 3. Authentication Architecture

```
Login Flow:
┌─────────────┐     POST /admin/login      ┌──────────────┐
│ Login Form  │ ──────────────────────────→ │ Verify       │
│             │     password (form data)    │ Password     │
└─────────────┘                            └──────┬───────┘
                                                  │
                                    ┌─────────────┴──────────────┐
                                    │                            │
                              password ==                  password !=
                              ADMIN_PASSWORD               ADMIN_PASSWORD
                                    │                            │
                                    ▼                            ▼
                           Set Cookie:              Redirect to login
                           admin_token=valid         with error param
                           httponly, samesite=lax
                                    │
                                    ▼
                           Redirect to /admin/

Protected Route Flow:
┌──────────────┐     admin_token cookie     ┌──────────────┐
│ Any Admin    │ ──────────────────────────→ │ _check_admin │
│ Page Request │                            │ (cookie)     │
└──────────────┘                            └──────┬───────┘
                                                   │
                                     ┌─────────────┴──────────────┐
                                     │                            │
                              cookie == "valid"            cookie != "valid"
                                     │                            │
                                     ▼                            ▼
                              Process request            Redirect to
                              normally                   /admin/login
```

## 4. Data Flow

### 4.1 Read Flow (List Pages)
```
Request → Auth Check → Build Query (with search/filter/sort)
    → Build Count Query → paginate() helper
    → Execute both queries → Format results → Render template
```

### 4.2 Write Flow (Actions)
```
Request → Auth Check → Load entity from DB
    → Validate state transition → Apply mutation → db.flush()
    → log_admin_action() → Redirect to detail/list page
    → Session auto-commits on success (via get_db dependency)
```

### 4.3 Audit Logging Flow
```
Admin Action → log_admin_action(db, request, action, target_type, target_id, details)
    → Create AuditLog entry with:
        - action: "user_suspended" | "company_funds_added" | etc.
        - target_type: "user" | "company" | "campaign" | "penalty" | "system"
        - target_id: ID of affected entity
        - details: JSON dict with context (email, amounts, scores, etc.)
        - admin_ip: Extracted from x-forwarded-for or request.client.host
    → db.flush()
    → Entry visible in /admin/audit-log
```

## 5. Pagination Architecture

```python
async def paginate(db, query, count_query, page=1, per_page=25):
    """
    1. Execute count_query for total
    2. Calculate total pages (ceil division)
    3. Clamp page to valid range [1, pages]
    4. Apply OFFSET/LIMIT to query
    5. Return: { items, page, per_page, total, pages, has_prev, has_next }
    """
```

Two variants:
- `paginate()` — For joined queries returning tuples `(Model1, Model2, ...)`
- `paginate_scalars()` — For single-model queries returning scalars

Query string persistence across pages:
```python
qs = build_query_string(search=search, status=status, sort=sort, order=order)
# → "search=test&status=active&sort=email"
# Template: /admin/users?page=2&{qs}
```

## 6. Template Architecture

```
base.html (shared layout)
├── <head>: DM Sans font, full CSS design system
├── <nav class="sidebar">: {% block nav %}{% endblock %}
├── <main class="main">: Flash messages + {% block content %}{% endblock %}
└── {% block scripts %}{% endblock %}

Each admin template:
├── {% extends "base.html" %}
├── {% block nav %}{% include "admin/_nav.html" %}{% endblock %}
├── {% block extra_css %} — Page-specific styles
├── {% block content %} — Page body
└── {% block scripts %} — Page-specific JavaScript

_nav.html:
├── Receives `active_page` variable from route handler
├── 10 nav items with SVG icons + conditional .active class
└── Logout link
```

## 7. Database Models (Admin-Specific)

### AuditLog
```sql
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    action      VARCHAR(50) NOT NULL,       -- action identifier
    target_type VARCHAR(30) NOT NULL,       -- entity type
    target_id   INTEGER NOT NULL DEFAULT 0, -- entity ID
    details     JSON NOT NULL DEFAULT '{}', -- context data
    admin_ip    VARCHAR(45),                -- source IP
    created_at  DATETIME DEFAULT NOW()      -- timestamp
);
```

### ContentScreeningLog
```sql
CREATE TABLE content_screening_logs (
    id                  INTEGER PRIMARY KEY,
    campaign_id         INTEGER NOT NULL UNIQUE REFERENCES campaigns(id),
    flagged             BOOLEAN NOT NULL DEFAULT FALSE,
    flagged_keywords    JSON NOT NULL DEFAULT '[]',
    screening_categories JSON NOT NULL DEFAULT '[]',
    reviewed_by_admin   BOOLEAN NOT NULL DEFAULT FALSE,
    review_result       VARCHAR(20),        -- approved | rejected
    review_notes        TEXT,
    created_at          DATETIME DEFAULT NOW()
);
```

### Company (modified)
```sql
-- Added column:
ALTER TABLE companies ADD COLUMN status VARCHAR(20) DEFAULT 'active';
-- Values: active | suspended
```

## 8. Design Decisions

### Why a Router Package Instead of a Single File?
The original `admin_pages.py` was 706 lines and growing. With 10 pages, detail views, and action endpoints, a single file would exceed 2000 lines. The package structure:
- Keeps each domain (users, companies, campaigns) in its own file
- Shares auth, pagination, and audit helpers via `__init__.py`
- Allows parallel development on different admin features
- Keeps `main.py` clean (single import, single `include_router`)

### Why Server-Side Pagination?
Client-side pagination loads all data into the browser, which breaks with 1000+ records. Server-side pagination with `OFFSET/LIMIT` is the correct approach for a database-backed admin panel. The `paginate()` helper runs a parallel `COUNT(*)` query for total, which is O(1) with proper indexes.

### Why Vanilla CSS/JS Instead of a Framework?
The existing codebase uses no JS frameworks. Adding React, Vue, or Tailwind would introduce build tooling complexity that doesn't match the project's simplicity. The design system in `base.html` provides all needed components. Vanilla JS handles the few interactive elements (tabs, toggles, confirmations).

### Why Audit Logging Instead of Just Git History?
Admin actions happen through the web UI, not through code changes. Git history tracks code deployments, not runtime mutations like "admin suspended user #42 at 3:15 PM from IP 192.168.1.8." The audit log provides accountability for runtime operations.

### Why `db.flush()` Instead of `db.commit()`?
The `get_db()` dependency handles commits automatically on success and rollbacks on exception. Using `flush()` within route handlers ensures changes are visible to subsequent queries within the same request (e.g., the audit log entry) without prematurely committing. The session lifecycle is managed at the dependency level.
