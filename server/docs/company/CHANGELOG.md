# Amplifier Company Dashboard — Changelog

## v2.0.0 — Complete Dashboard Rebuild (2026-04-02)

### Overview
Full restructure of the company dashboard from a single 1,203-line monolith to a modular package with 7 router modules and 10 templates. Added new pages, search/filter/pagination, and shared navigation.

### New Pages
- **Dashboard** (`/company/`) — NEW overview page with 8 metric cards, smart alerts (low balance, draft campaigns, budget warnings), recent campaigns table, and quick action buttons. Previously `/company/` was just the campaigns list.
- **Influencers** (`/company/influencers`) — NEW cross-campaign influencer performance view. Shows every creator who's worked on any campaign with aggregated metrics: campaigns, posts, impressions, engagement, engagement rate, total paid. Search by email.

### Enhanced Pages
- **Campaigns List** (`/company/campaigns`) — Added search by title, filter by status (5 options), sort by date/budget/title, server-side pagination (15 per page), budget progress bars with color coding, screening status badges.
- **Campaign Detail** — Added budget deduction when activating from draft, automatic refund on cancellation, improved status transition validation with error messages.
- **Billing** — Added total_allocated and total_spent aggregate stats, campaign links in allocations table.

### Infrastructure Changes
- **Router package** — Single `company_pages.py` (1,203 lines) replaced with `app/routers/company/` package (7 modules: login, dashboard, campaigns, influencers, billing, stats, settings)
- **Shared navigation** — Inline nav HTML in all templates replaced with `company/_nav.html` include. Nav now includes Dashboard, Campaigns, Create Campaign, Influencers, Billing, Analytics, Settings, Logout.
- **Pagination** — Campaigns list uses server-side pagination (15 items per page)
- **Search & filter** — Campaigns searchable by title, filterable by status, sortable by date/budget/title
- **Query string persistence** — Search/filter/sort state preserved across pagination

### Bug Fixes
- **Draft→Active budget deduction** — Fixed: activating a draft campaign now properly checks balance and deducts budget
- **Cancel refund** — Fixed: cancelling an active/paused campaign refunds remaining budget to company balance
- **Platform JSON crash** — Inherited fix from admin dashboard: handles boolean values in `platforms` JSON gracefully

### Preserved (No Changes)
- Campaign wizard (4-step AI-powered creation flow)
- Campaign detail page analytics (platform ROI, influencer roster, invitation stats)
- Billing Stripe integration (checkout sessions, success callback, test mode)
- Statistics page (cross-campaign analytics, best performers, platform breakdown, monthly spend)
- Settings page (company profile update)
- Login/register/logout auth flow

---

## v1.0.0 — Initial Company Dashboard (2026-03-18)

### Pages
- Campaigns list (no search/filter/pagination)
- Campaign wizard (4-step AI-powered creation)
- Campaign detail with analytics
- Billing with Stripe integration
- Statistics page
- Settings page
- Login/register/logout

### Features
- JWT cookie-based authentication
- AI campaign brief generation (Gemini API with fallback chain)
- Deep URL crawling for product page analysis
- File uploads to Supabase Storage
- Stripe Checkout for payments (test mode fallback)
- Per-platform and per-influencer analytics
- Campaign lifecycle management (draft/active/paused/completed/cancelled)
- Budget allocation and tracking

### Known Issues (Fixed in v2.0.0)
- No dashboard/overview page (landing page was just campaigns list)
- No search or filter on campaigns list
- No pagination on campaigns list
- No cross-campaign influencer view
- Navigation duplicated in every template (6 copies)
- Draft→Active didn't deduct budget
- Cancel didn't refund remaining budget
