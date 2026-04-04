# Amplifier Admin Dashboard — Concept Document

## 1. Purpose

The Admin Dashboard is the central control plane for the Amplifier marketplace. It gives platform operators full visibility and control over every entity in the system — users, companies, campaigns, finances, trust, and content moderation — through a single web interface.

## 2. Problem Statement

Amplifier is a two-sided marketplace where **companies** create advertising campaigns and **users** earn money by posting campaign content on social media. Operating this marketplace requires:

- **Oversight** — Knowing what's happening across the platform at any moment
- **Moderation** — Reviewing flagged content, managing trust scores, processing appeals
- **Financial control** — Running billing cycles, processing payouts, managing company balances
- **Fraud prevention** — Detecting anomalies, flagging suspicious accounts, penalizing bad actors
- **User management** — Suspending, banning, or adjusting users and companies as needed

Without an admin dashboard, these operations would require direct database access, which is slow, error-prone, and leaves no audit trail.

## 3. Target Users

The sole target user is the **platform operator** (admin). There is one admin account, authenticated via a shared password. The admin has full read and write access to every entity in the system.

## 4. Core Principles

### 4.1 Zero Internal Server Errors
Every page must handle edge cases gracefully — empty tables, missing relationships, null values, and corrupt data (e.g., a `bool` where a `dict` is expected in JSON fields). No user action should ever produce a 500 error.

### 4.2 Full Audit Trail
Every admin action that mutates data is logged to the `audit_log` table with the action type, target entity, details, and the admin's IP address. This creates an immutable record of who did what, when, and why.

### 4.3 Search, Filter, Paginate Everything
No table dumps all records at once. Every list view supports:
- **Search** — Free-text search on the most useful field (email, name, title)
- **Filters** — Dropdown filters on status, type, or category
- **Pagination** — Server-side pagination (25-30 items per page) with query string preservation
- **Sorting** — Sort by creation date, numeric fields, or alphabetical

### 4.4 Drill-Down Navigation
Every entity in a list view links to a detail page. Detail pages link to related entities. The admin can follow the chain: Company → Campaign → Assigned User → User Posts → Post Metrics — without leaving the dashboard.

### 4.5 Design Consistency
All pages use the same design system: dark theme (`#0f172a` background), `DM Sans` font, `#2563eb` primary blue, gradient cards, Heroicon SVGs, and a consistent badge color language (green = good, yellow = caution, red = alert, blue = info, gray = neutral).

## 5. Feature Scope

### 5.1 Overview Dashboard
Real-time system health: key metrics with weekly trends, health indicators for items needing attention (pending reviews, pending payouts, low trust users), and quick-action buttons for common admin tasks.

### 5.2 User Management
Full user lifecycle management: list with search/filter/sort, individual detail pages with tabbed views (assignments, posts, payouts, penalties), trust score adjustment, and account status management (suspend, unsuspend, ban).

### 5.3 Company Management
Company oversight with fund management: list with search/filter, detail pages with campaign views, direct fund add/deduct (for manual corrections, refunds, or testing), and company suspension (which cascades to pause all active campaigns).

### 5.4 Campaign Management
Campaign oversight with full drill-down: list with search/filter by status, detail pages with brief preview, assigned users, post metrics, and configuration. Actions include pause, resume, and cancel (with automatic budget refund to company).

### 5.5 Financial Dashboard
Revenue overview with billing controls: platform revenue calculation, pending/paid/failed payout totals, and the ability to trigger billing and payout cycles on demand. Paginated transaction table with expandable payout breakdowns.

### 5.6 Fraud & Trust Center
Fraud detection and penalty management: run trust checks (anomaly detection, deletion fraud), view penalties with search, and process appeals (approve with partial trust restoration or deny). Stats show total penalties, pending appeals, and users with dangerously low trust scores.

### 5.7 Platform Analytics
Engagement analytics per platform: post counts, success rates, average and total impressions, and a leaderboard of top-performing posts by engagement.

### 5.8 Content Review Queue
Campaign content moderation: flagged campaigns are surfaced with their flagged keywords and categories. Admin can approve or reject with notes. Rejected campaigns are cancelled and their budget is refunded. A "Reviewed" tab shows the history of past decisions.

### 5.9 System Settings
Read-only display of system configuration: platform cut percentage, payout threshold, JWT settings, database connection (masked), debug mode, and integration status (Stripe, Supabase).

### 5.10 Audit Log
Complete record of all admin actions: filterable by action type and target entity, paginated, with clickable links to the affected entities. Each entry shows timestamp, action, target, details, and the admin's IP.

## 6. Security

- **Authentication**: Cookie-based, single password. Cookie is `httponly` and `samesite=lax`.
- **Authorization**: All routes check the admin cookie before processing. Invalid cookies redirect to login.
- **Audit logging**: Every mutation is logged with IP address for accountability.
- **Confirmation dialogs**: Destructive actions (ban, cancel, deduct funds) require browser confirmation before executing.
- **No client-side secrets**: All data fetching and mutations happen server-side via form submissions.

## 7. Technical Architecture

- **Backend**: FastAPI with async SQLAlchemy (SQLite dev / PostgreSQL production)
- **Frontend**: Server-rendered Jinja2 templates with vanilla CSS and JavaScript (no frameworks)
- **Router structure**: Modular package (`app/routers/admin/`) with 11 sub-modules
- **Data models**: 10 SQLAlchemy models (8 existing + 2 new: `AuditLog`, `ContentScreeningLog`)
- **Template structure**: Shared nav partial (`_nav.html`), all pages extend `base.html`

## 8. Non-Goals

- **Real-time updates**: The dashboard is request-response. No WebSocket push or auto-refresh.
- **Multi-admin accounts**: Single shared password. No role-based access control.
- **Settings editing**: Settings are read-only. Configuration changes require environment variable updates and a restart.
- **Data export**: No CSV/PDF export functionality in V1.
- **Mobile optimization**: Basic responsive support (sidebar hides on narrow screens) but not a primary target.

## 9. Success Criteria

1. All 10 pages load without errors with any combination of data (empty, 1 record, 10,000 records)
2. Every admin action is logged and visible in the audit log
3. An admin can find any user, company, or campaign within 3 clicks from the overview
4. Financial operations (billing, payouts) can be triggered and monitored from a single page
5. Flagged campaigns can be reviewed and resolved without database access
