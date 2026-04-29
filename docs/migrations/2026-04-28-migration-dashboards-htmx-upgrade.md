# Migration: Dashboards HTMX Upgrade

**Date**: 2026-04-28
**Status**: Planned
**Phase**: D (Business Launch + Tech Stack Migration)
**Estimated effort**: 5-7 days

---

## Why this migration exists

Three independent code reviews (one Claude Desktop, one Grok, one synthesis) converged on the same conclusion: the company and admin dashboards do NOT need a Next.js + React rewrite. Server-rendered Jinja2 + HTMX + Alpine.js + Tailwind CDN closes ~90% of the UX gap with React for a 24-page internal SaaS tool, with a fraction of the maintenance cost.

The previous plan (Tauri + Next.js + shadcn) was rejected because:
- Adding a second runtime, npm, build pipeline, separate deploy, CORS surface, and JS framework cognitive load is not earned at this scale.
- HTMX + SSE handles the listed pain points (real-time metrics, sortable tables, multi-step wizards with autosave, optimistic updates, command palettes) with <50 LOC per feature.
- Solo founder + AI assistants ship faster on a single-language stack.

This migration adds HTMX + Alpine + Tailwind CDN to the existing dashboards instead of rewriting them. It also adds the new creator-facing dashboard pages (campaigns, posts, earnings, settings) on the same server using the same pattern.

## Decisions and rationale

| Decision | Choice | Why |
|---|---|---|
| UI framework | Jinja2 + HTMX 1.9 + Alpine.js 3 + Tailwind CDN | Zero build step, single language, single deploy. Matches the pattern that works. |
| Chart library | Chart.js (CDN) | Drop-in, no build step, sufficient for analytics needs in Phase D. |
| Real-time updates | Server-Sent Events (SSE) via FastAPI `EventSourceResponse` | Native FastAPI support, works through Caddy reverse proxy, no WebSocket complexity. |
| Component primitives | Alpine.js (modals, drawers, command palette, dropdowns) + custom HTMX templates | Alpine handles client-side state; HTMX handles server-fetched HTML swaps. |
| Form validation | HTMX `hx-validate` + server-side schema validation | No Zod equivalent needed; FastAPI Pydantic schemas already validate. |
| Creator dashboard location | Same FastAPI server, new routes under `/user/*` | Mirrors existing `/company/*` and `/admin/*` structure. |
| Hosting | Same Hostinger VPS, served by Caddy | No infra change. |

## What changes

### Existing files modified

| File | Change |
|---|---|
| `server/app/templates/base.html` | Add HTMX 1.9 + Alpine.js 3 + Tailwind CDN + Chart.js script tags. Set up HTMX defaults (`hx-headers`, error handling). |
| `server/app/templates/admin/_nav.html` | No structural change, may add command palette trigger. |
| `server/app/templates/company/_nav.html` | Same. |
| `server/app/templates/admin/users.html` | Convert pagination + filters to HTMX partial swaps. Add bulk-action checkboxes via Alpine. |
| `server/app/templates/admin/campaigns.html` | Same — partial swaps for sort/filter, bulk actions. |
| `server/app/templates/admin/companies.html` | Same. |
| `server/app/templates/admin/payouts.html` | Same. Add real-time payout status updates via SSE. |
| `server/app/templates/admin/financial.html` | Same. Add Chart.js revenue/payout charts. |
| `server/app/templates/admin/analytics.html` | Add Chart.js charts for per-platform stats. |
| `server/app/templates/admin/overview.html` | Add SSE for live KPI counters (active users, active campaigns, posts/day). |
| `server/app/templates/admin/audit_log.html` | HTMX partial pagination. |
| `server/app/templates/admin/fraud.html` | HTMX partial pagination + appeal action via HTMX POST. |
| `server/app/templates/admin/review_queue.html` | HTMX approve/reject without full reload. |
| `server/app/templates/company/dashboard.html` | Add SSE for live campaign metrics. Chart.js for budget burn-down. |
| `server/app/templates/company/campaigns.html` | HTMX partial swaps for sort/filter. |
| `server/app/templates/company/campaign_create.html` | Convert multi-step wizard to HTMX `hx-post` per step + Alpine for autosave to localStorage. |
| `server/app/templates/company/campaign_wizard.html` | AI wizard preview rendered via HTMX (server streams partial as Gemini generates). |
| `server/app/templates/company/campaign_detail.html` | Add SSE for live metric updates. Chart.js for engagement timeline. |
| `server/app/templates/company/billing.html` | HTMX top-up flow. |
| `server/app/templates/company/influencers.html` | HTMX partial pagination + filters. |
| `server/app/templates/company/stats.html` | Chart.js charts. |

### New files created

| File | Purpose |
|---|---|
| `server/app/routers/user.py` | Creator-facing routes (web dashboard for users). Mirrors `routers/company/` structure. |
| `server/app/templates/user/_nav.html` | Creator nav (dashboard, campaigns, posts, earnings, settings). |
| `server/app/templates/user/login.html` | User login page. |
| `server/app/templates/user/dashboard.html` | Creator overview — stats, platform health, recent activity, alerts. |
| `server/app/templates/user/campaigns.html` | List of accepted/active campaigns + invitations tabs. |
| `server/app/templates/user/campaign_detail.html` | Campaign detail. (Note: draft review is local, NOT here — link out to `localhost:5222/drafts`.) |
| `server/app/templates/user/posts.html` | Post history with metrics. |
| `server/app/templates/user/earnings.html` | Earnings breakdown, payout history, withdraw button. |
| `server/app/templates/user/settings.html` | Mode toggle, region, AI key status (read-only — actual entry is local), connected platforms. |
| `server/app/routers/sse.py` | New SSE endpoints: `/sse/campaign/{id}/metrics`, `/sse/admin/overview`, `/sse/user/agent-status`. |
| `server/app/static/js/htmx-defaults.js` | HTMX global config (auth headers, error toast, loading indicators). |
| `server/app/static/js/alpine-helpers.js` | Reusable Alpine components (command palette, multi-select, autosave). |

### Files NOT touched

- All `server/app/services/*` — business logic unchanged
- All `server/app/models/*` — data models unchanged (except 2 additions in the creator-app-split migration)
- All `server/app/routers/*` JSON API endpoints — unchanged

## Acceptance Criteria

### AC-1: HTMX added to base template
**Given** the existing `base.html` is rendered
**When** I view the page source
**Then** HTMX 1.9, Alpine.js 3, Tailwind CDN, and Chart.js are loaded via CDN
**And** HTMX is configured to send the `Authorization` header with every request

### AC-2: Admin user table uses HTMX partial swaps
**Given** I am on `/admin/users` with 100+ users
**When** I change the status filter dropdown
**Then** only the table body is replaced (HTMX partial swap)
**And** the URL updates to reflect the filter (`hx-push-url`)
**And** the page does not full-reload

### AC-3: Admin user table supports bulk actions
**Given** I am on `/admin/users`
**When** I check 5 user rows and click "Bulk: Suspend"
**Then** an Alpine confirmation modal appears
**And** confirming triggers a single HTMX request to `POST /admin/users/bulk/suspend`
**And** the affected rows update in place to show "suspended" status

### AC-4: Company campaign wizard supports autosave
**Given** I am on `/company/campaigns/create` step 2
**When** I edit any input field
**Then** the value is persisted to localStorage within 500ms of the last keystroke
**And** if I refresh the page, my edits are restored

### AC-5: Real-time KPI counters via SSE
**Given** I am on `/admin/overview`
**When** a new user signs up or a new campaign goes active
**Then** the corresponding KPI counter updates within 2 seconds without a page reload
**And** the SSE connection auto-reconnects if the server restarts

### AC-6: Charts render on Chart.js
**Given** I am on `/admin/financial` or `/company/dashboard`
**When** the page loads
**Then** revenue/budget charts render using Chart.js (canvas elements)
**And** charts are responsive and dark-mode-aware

### AC-7: Creator dashboard pages exist and are reachable
**Given** I log in as a user at `/user/login`
**When** I navigate to `/user/dashboard`, `/user/campaigns`, `/user/posts`, `/user/earnings`, or `/user/settings`
**Then** each page renders correctly with data from the existing JSON API
**And** each page uses the same blue/DM Sans design system as company/admin

### AC-8: Creator dashboard does NOT host draft review
**Given** I am on `/user/campaigns/{id}` for an active campaign with pending drafts
**When** I look for a draft review section
**Then** I see an explanation: "Draft review happens in the desktop app for offline access and instant editing"
**And** there is a button: "Open in Desktop App" that opens `http://localhost:5222/drafts/{campaign_id}`

### AC-9: Command palette in admin
**Given** I am anywhere on `/admin/*`
**When** I press `Cmd+K` (Mac) or `Ctrl+K` (Windows)
**Then** an Alpine-powered command palette overlay appears
**And** typing filters available actions (suspend user, run billing, view campaign, etc.)
**And** Enter executes the selected action

### AC-10: No JS build step required
**Given** the dashboards have been migrated
**When** the server is deployed
**Then** there is no `npm install`, no `npm run build`, no `node_modules/`, no `package.json` in the server repo
**And** all JS dependencies load from CDN

## Out of scope

- React/Next.js migration (rejected)
- Component library (shadcn/ui, MUI, etc.)
- TypeScript on the frontend
- WebSocket (SSE is sufficient)
- Mobile apps
- Internationalization

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Tailwind CDN is large and slow on first paint | Acceptable for v1 (internal-leaning audience). If launch reveals performance issues, switch to a precompiled Tailwind CSS file served from FastAPI static. |
| HTMX behavior differs from React expectations | Document HTMX patterns in `docs/development-setup.md` for future reference. Stick to canonical patterns from htmx.org. |
| SSE connections accumulate on Caddy | Caddy default is fine for <1000 concurrent connections. Monitor in production; switch to dedicated SSE worker if needed. |
| Some browsers throttle SSE on background tabs | Accept — user will see updates when they refocus the tab. Don't try to work around it. |

## Test plan

1. Manual smoke test of every modified page after migration.
2. Add Playwright tests for: bulk actions, multi-step wizard autosave, SSE reconnect, command palette.
3. Run pytest suite (Task #18 prerequisite — must be done before this migration starts).

## Dependencies

- **Task #18 (pytest suite)** — must be complete before this migration. Without tests, every HTMX change risks breaking something invisibly.
- **Task #44 (ARQ worker)** — independent of this migration but recommended before launch.
- **Task #45 (Alembic baseline)** — independent.

## Followups

- Migrate one specific admin page to React if a future feature genuinely needs it (e.g., real-time collaborative draft editing). Until that triggers, stay on HTMX.
