# Amplifier Admin Dashboard — Changelog

## v2.0.0 — Complete Admin System Rebuild (2026-04-02)

### Overview
Full rebuild of the admin dashboard from a single 706-line file with 8 templates and 17 routes to a modular package with 11 router modules, 15 templates, and 34 routes. Every page now has search, filter, pagination, and audit logging.

### New Pages
- **Companies** (`/admin/companies`) — Full company management with list, detail, fund add/deduct, and suspend/unsuspend. Previously there was no way to manage companies from the admin dashboard.
- **Settings** (`/admin/settings`) — Read-only system configuration display. Shows platform cut, JWT settings, database connection, and integration status.
- **Audit Log** (`/admin/audit-log`) — Complete audit trail of every admin action with timestamp, action type, target entity, details, and IP address. Filterable by action and target type.

### New Features
- **Company fund management** — Admin can add or deduct funds directly from a company's balance without Stripe
- **Company suspension** — Suspending a company automatically pauses all their active campaigns
- **User banning** — New permanent ban action in addition to temporary suspend
- **Trust score adjustment** — Manual trust score override from user detail page
- **Campaign cancellation with refund** — Cancelling a campaign automatically refunds remaining budget to the company
- **Appeal processing** — Approve or deny user penalty appeals directly from the fraud page
- **Top performing posts** — Analytics page now shows a leaderboard of the 10 highest-engagement posts
- **Campaign detail page** — Full drill-down with brief, assigned users, post metrics, and configuration tabs
- **User detail page** — Full profile with tabbed views of assignments, posts, payouts, and penalties
- **Company detail page** — Profile with fund management and campaign list

### Infrastructure Changes
- **Router package** — Single `admin_pages.py` replaced with `app/routers/admin/` package (11 files)
- **Shared navigation** — Inline nav HTML in every template replaced with `_nav.html` include
- **Pagination** — All list pages use server-side pagination (25-30 items per page)
- **Search & filter** — All list pages support search by primary field and filter by status
- **Audit logging** — Every admin mutation creates an `AuditLog` entry with IP tracking

### New Models
- **AuditLog** (`audit_log` table) — Stores all admin actions with action type, target, details, IP, timestamp
- **ContentScreeningLog** (`content_screening_logs` table) — Content screening records for campaigns. Was referenced in code but never created, causing the review queue to crash.
- **Company.status** — New `VARCHAR(20)` column on companies table (values: active, suspended)

### Bug Fixes
- **Review queue crash** — Fixed `NameError: ContentScreeningLog is not defined` that caused 500 on `/admin/review-queue`. Created the missing model.
- **Platform JSON crash** — Fixed `AttributeError: 'bool' object has no attribute 'get'` on user pages when `platforms` JSON contained boolean values instead of dicts.
- **No pagination** — Previous version had no pagination. Pages with many records would time out or consume excessive memory. All list pages now paginate at 25-30 items.
- **No company management** — There was no way to view, manage, or add funds to companies from the admin dashboard. Now fully supported.

### Removed / Replaced
- `payouts.html` template → replaced by `financial.html`
- `platform_stats.html` template → replaced by `analytics.html`
- `admin_pages.py` monolith → replaced by `routers/admin/` package (old file preserved as `_admin_pages_old.py`)

---

## v1.0.0 — Initial Admin Dashboard (2026-03-18)

### Pages
- Overview dashboard with 7 stat cards
- Users list with status filter and suspend/unsuspend
- Campaigns list (view only)
- Fraud detection with trust check trigger
- Payouts with billing and payout cycle triggers
- Platform stats with per-platform metrics
- Review queue (broken — ContentScreeningLog model missing)

### Known Issues (all fixed in v2.0.0)
- Review queue crashed due to missing ContentScreeningLog model
- No pagination on any page
- No search or filter on any page
- No company management
- No audit logging
- No detail pages for users, companies, or campaigns
- No appeal processing
- No fund management for companies
- Navigation duplicated across all 8 templates
