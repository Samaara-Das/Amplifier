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

## Acceptance Criteria — high level (prose)

(Reference only. The authoritative ACs for `/uat-task 66` are in the **Verification Procedure** section below, in `docs/uat/AC-FORMAT.md` table format.)

- HTMX 1.9 + Alpine.js 3 + Tailwind CDN + Chart.js loaded in `base.html`. HTMX sends Authorization header.
- Admin user table uses HTMX partial swaps + bulk actions.
- Company campaign wizard autosaves every keystroke to localStorage.
- SSE drives real-time KPI counters on `/admin/overview` and live campaign metrics on `/company/campaign_detail`.
- Chart.js charts on `/admin/financial`, `/admin/analytics`, `/company/dashboard`, `/company/stats`.
- Creator dashboard pages (`/user/dashboard`, `/user/campaigns`, `/user/campaign_detail`, `/user/posts`, `/user/earnings`, `/user/settings`, `/user/login`) exist and render.
- Creator dashboard does NOT host draft review — link to `localhost:5222/drafts/{id}`.
- Cmd+K / Ctrl+K command palette in admin.
- No JS build step (no npm, no node_modules, no package.json in server repo).
- Status label renames per #24, Copy URL buttons per #25, HTML5 native form validation per #26 — all consistent across admin/company/user surfaces.

---

## Verification Procedure — Task #66

> Format: `docs/uat/AC-FORMAT.md`. Heavy use of **Chrome DevTools MCP** to drive the live product as a real user/company/admin. Every UI surface gets exercised. Critical-path regression ACs ensure the migration did not break campaign creation, AI matching, profile scraping, content generation, posting, billing, earnings, ToS gate, or post URL dedup.

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `/health` returns 200.
- Worker live (`amplifier-worker.service` per Task #44). 4 cron jobs registered.
- Alembic at head — no schema drift (`alembic current` matches `server/alembic/versions/` head). No new model changes in this migration.
- Local user app installable on `flask-user-app` branch. Daemon (`scripts/background_agent.py`) operational.
- LinkedIn, Facebook, Reddit profiles connected on the test user account (`scripts/utils/local_db.get_user_profiles(['linkedin','facebook','reddit'])` returns non-empty per platform). X disabled (Task #40).
- Test fixtures: company `uat-task66-co@uat.local` (balance $0, no campaigns), user `uat-task66-user@uat.local` (no active assignments, profile scraped, $0 earnings).
- Stripe MCP authed (Stock Buddy sandbox is fine — test-mode work only for #66 billing AC).
- pytest suite (Task #18) baseline green: `pytest tests/ -v` → 194 passing on `flask-user-app` HEAD before migration begins.
- Repo on a `phase-d-htmx` worktree branch, isolated from `flask-user-app`.

### Test data setup

1. Seed company + user on prod:
   ```bash
   python scripts/uat/seed_stripe_fixtures.py \
     --company-email uat-task66-co@uat.local \
     --user-email uat-task66-user@uat.local \
     --user-available-balance-cents 1500 \
     --output data/uat/task66_fixtures.json
   ```
2. Seed 1 active campaign with the test company (so company dashboard has data):
   ```bash
   python scripts/uat/seed_campaign.py \
     --as-company uat-task66-co@uat.local \
     --title "UAT Task66 HTMX Smoke" \
     --goal brand_awareness --tone casual \
     --brief "$(python -c "print('x'*310)")" \
     --guidance "Be casual, mention you tested it." \
     --company-urls "https://example.com" \
     --output-id-to data/uat/task66_campaign_id.txt
   ```
3. Force-accept invitation as test user (so user-side surfaces have an active assignment):
   ```bash
   python scripts/uat/accept_invitation.py --campaign-id $(cat data/uat/task66_campaign_id.txt)
   ```
4. Capture pre-migration baseline: `curl https://api.pointcapitalis.com/admin/overview` (admin login required) → save HTML to `data/uat/task66_pre_overview.html` for visual diff.

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_UAT_INTERVAL_SEC=120` | Shortens content-gen + research-cache TTL (already documented in AC-FORMAT.md) | AC22, AC25 |
| `AMPLIFIER_UAT_DRY_STRIPE=1` | Logs Transfer kwargs without Stripe call (Task #44 inheritance) | AC23 (when Stripe MCP unavailable) |
| `AMPLIFIER_UAT_POST_NOW=1` | Schedules approved drafts ~1 min out instead of next slot | AC25 |
| **NEW** `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=500` | Forces SSE heartbeat to 500ms (default 30s) so AC11 verifies in <5s instead of >30s. Defaults to production behavior when unset. | AC11 |

(`AMPLIFIER_UAT_SSE_HEARTBEAT_MS` is a new flag; document in AC-FORMAT.md when added.)

---

## Features to verify end-to-end (Task #66)

**New HTMX/Alpine/SSE features (the migration itself):**
1. HTMX + Alpine + Tailwind + Chart.js loaded via CDN — AC1
2. Admin user table HTMX partial swap (filter, sort, paginate) — AC2
3. Admin user table bulk actions via Alpine modal — AC3
4. Campaign wizard autosaves to localStorage — AC4
5. Multi-step wizard uses HTMX `hx-post` per step (no full reloads) — AC5
6. SSE drives real-time KPI counters on admin overview — AC11
7. SSE drives live campaign metrics on company campaign_detail — AC12
8. Chart.js charts render on admin financial + company dashboard — AC6
9. Cmd+K command palette functional in admin — AC9
10. No JS build step in server repo — AC10
11. All 7 creator `/user/*` pages exist and render — AC7
12. Creator dashboard does NOT host draft review (links to localhost:5222) — AC8
13. Status label renames consistent across all 3 surfaces (#24) — AC13
14. Copy URL button next to every post URL (#25) — AC14
15. HTML5 native validation on every form (#26) — AC15

**Critical-path regression sweep (the migration must not break these):**
16. Public /terms + /privacy still 200, ToS checkbox + register flow blocks without checkbox — AC16
17. Company register + login + landing on dashboard — AC17
18. Admin login + landing on /admin/overview with KPI cards rendering — AC18
19. Manual campaign creation flow E2E (form → activate → quality gate score >=85 → audit_log entry) — AC19
20. AI campaign wizard flow E2E (URL → Gemini brief → screen → activate) — AC20
21. Billing top-up via Stripe Checkout test mode (idempotent on duplicate webhook) — AC21
22. AI matching: profile scrape → matching service → invitation logged — AC22
23. Invitation list with countdown timer + decline reason + expired badge (Task #5) — AC23
24. Content agent 4 phases produce drafts in `agent_draft` for LI/FB/Reddit — AC24
25. Posting via JSON engine: real LinkedIn post + URL captured + cleanup deletes it — AC25
26. Metric scraping: post URL → scraper → metric row → billing → payout pending — AC26
27. Earnings page shows pending + available balances; withdraw blocked without Stripe Connect — AC27
28. Admin financial actions: run-billing, run-payout-processing, run-earning-promotion all functional — AC28
29. Admin payout void + force-approve actions create audit_log entries (Task #8) — AC29
30. Server-side post URL dedup still returns `skipped_duplicate=1` on repeat (Task #27) — AC30
31. Console error scan: every page across admin + company + user has zero JS errors on load — AC31
32. Network 5xx scan: every page has zero 5xx responses on load — AC32
33. Visual regression: 24 page screenshots on desktop + mobile compared against pre-migration captures — AC33
34. pytest suite still 194/194 passing (no regressions) — AC34

---

### AC1 — HTMX, Alpine, Tailwind, Chart.js loaded in base.html via CDN

| Field | Value |
|-------|-------|
| **Setup** | Server live. `base.html` updated. |
| **Action** | DevTools MCP: `new_page("https://api.pointcapitalis.com/admin/login")` → `evaluate_script("[typeof htmx, typeof Alpine, typeof Chart, !!document.querySelector('script[src*=\"tailwindcss\"]')]")`. |
| **Expected** | Returns `["object", "object", "function", true]`. View source contains `htmx.org/dist/htmx.min.js@1.9` (or pinned 1.9.x), `alpinejs@3`, `cdn.tailwindcss.com`, `chart.js`. HTMX `hx-headers` includes `Authorization: Bearer <token>` when token present in localStorage. |
| **Automated** | yes |
| **Automation** | DevTools MCP eval + `pytest scripts/uat/uat_task66.py::test_ac1_cdn_loaded` |
| **Evidence** | eval result; view-source grep |
| **Cleanup** | `close_page` |

### AC2 — Admin user table: filter changes do partial swap, no full reload

| Field | Value |
|-------|-------|
| **Setup** | Admin logged in. `/admin/users` open with seeded users (>20). |
| **Action** | DevTools MCP: `take_snapshot` → record document.documentElement.outerHTML hash → click "Status: Active" filter → wait for HTMX request → `list_network_requests` → re-hash. |
| **Expected** | Network log shows ONE request to `/admin/users?status=active&hx=1` (or similar) returning HTML partial (Content-Type: text/html, body length < full page). URL bar shows `?status=active` (hx-push-url). Document hash differs ONLY in `<tbody>`, not in `<head>` or sidebar. No window `load` event fired (page didn't reload). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac2_admin_users_partial_swap` |
| **Evidence** | network requests dump; before/after document hashes |
| **Cleanup** | reset filter |

### AC3 — Admin user table: bulk-suspend 5 users via Alpine modal

| Field | Value |
|-------|-------|
| **Setup** | 5 seeded users with `status=active`. |
| **Action** | DevTools MCP: navigate `/admin/users` → check 5 row checkboxes → click "Bulk: Suspend" button → Alpine modal appears → click "Confirm" → wait. |
| **Expected** | One HTMX `POST /admin/users/bulk/suspend` with payload `{ids: [...5...]}`. 5 rows update in place to show "suspended" badge (no full reload). audit_log has +5 rows `event='user_suspended'`. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac3_bulk_suspend` |
| **Evidence** | network log; 5 audit_log rows; badge text in DOM snapshot |
| **Cleanup** | un-suspend the 5 users via SQL: `UPDATE users SET status='active' WHERE id IN (...)` |

### AC4 — Campaign wizard step 2 autosaves to localStorage

| Field | Value |
|-------|-------|
| **Setup** | Company logged in. Navigate to `/company/campaigns/create` step 2. |
| **Action** | DevTools MCP: type "test brief" into Brief field → wait 600ms → `evaluate_script("localStorage.getItem('amplifier_wizard_draft')")` → reload page → `take_snapshot`. |
| **Expected** | localStorage value contains `"brief":"test brief"`. After reload, Brief field still contains "test brief". |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac4_wizard_autosave` |
| **Evidence** | localStorage value; DOM snapshot post-reload |
| **Cleanup** | clear localStorage |

### AC5 — Wizard multi-step navigation via HTMX (no full reloads)

| Field | Value |
|-------|-------|
| **Setup** | Company logged in, on wizard step 1. |
| **Action** | DevTools MCP: fill step 1 → click "Next" → fill step 2 → click "Next" → fill step 3 → click "Next" → record full document load events count via `evaluate_script("performance.getEntriesByType('navigation').length")` before and after. |
| **Expected** | Navigation entries count unchanged (1) — no full page reloads. Each "Next" triggers `POST /company/campaigns/wizard/step{N}` HTMX request. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac5_wizard_no_reload` |
| **Evidence** | navigation entries count; network log |
| **Cleanup** | abandon wizard |

### AC6 — Chart.js renders on /admin/financial and /company/dashboard

| Field | Value |
|-------|-------|
| **Setup** | Admin logged in (seed prior payouts so chart has data). Company logged in (seed budget burn). |
| **Action** | DevTools MCP: navigate `/admin/financial` → `evaluate_script("document.querySelectorAll('canvas[data-chart]').length")` → screenshot. Then `/company/dashboard` → same eval. |
| **Expected** | Both pages have `>= 1` canvas with `data-chart` attribute. Canvas has non-zero `width` + `height`. Screenshot shows rendered chart (manual eyeball). |
| **Automated** | partial |
| **Automation** | `scripts/uat/uat_task66.py::test_ac6_charts_render` (auto count) + manual screenshot review |
| **Evidence** | canvas count; 2 screenshots |
| **Cleanup** | none |

### AC7 — Creator /user/* pages all reachable + render with data

| Field | Value |
|-------|-------|
| **Setup** | Test user logged in via `/user/login` (seed JWT). Active assignment exists per Test data setup step 3. |
| **Action** | DevTools MCP: navigate to each of `/user/dashboard`, `/user/campaigns`, `/user/campaign_detail/<id>`, `/user/posts`, `/user/earnings`, `/user/settings` → for each: `take_snapshot`, `take_screenshot(filePath="data/uat/screenshots/task66_ac7_<page>.png")`, `list_console_messages`, capture HTTP status. |
| **Expected** | All 6 pages return HTTP 200. Each renders the test campaign / activity data (not an empty state). Console error count = 0 per page. Same DM Sans + blue `#2563eb` design system as company/admin. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac7_user_pages_reachable` |
| **Evidence** | 6 screenshots; status codes; console message dumps |
| **Cleanup** | `close_page` for each |

### AC8 — Creator campaign_detail does NOT host draft review

| Field | Value |
|-------|-------|
| **Setup** | Test user on `/user/campaign_detail/<id>` for the seeded active campaign. |
| **Action** | DevTools MCP: `take_snapshot` → grep for "Open in Desktop App" → click that button → capture URL. |
| **Expected** | Page contains text "Draft review happens in the desktop app for offline access and instant editing" AND a button "Open in Desktop App" that links to `http://localhost:5222/drafts/<id>`. NO inline draft editor on this page. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac8_no_draft_review_in_web` |
| **Evidence** | snapshot text; button href |
| **Cleanup** | none |

### AC9 — Cmd+K command palette opens, filters, executes

| Field | Value |
|-------|-------|
| **Setup** | Admin logged in, anywhere on `/admin/*`. |
| **Action** | DevTools MCP: `press_key("Control+k")` → `take_snapshot` → type "suspend" → `take_snapshot` → press Enter on top result. |
| **Expected** | First snapshot: command palette overlay visible (z-index >= 100, role="dialog"). Second snapshot: filtered list shows only items matching "suspend" (e.g., "Suspend user...", "Suspend campaign..."). Enter triggers the corresponding action (verify by checking URL change or modal appearance). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac9_command_palette` |
| **Evidence** | 2 snapshots |
| **Cleanup** | press Escape |

### AC10 — No JS build step in server repo

| Field | Value |
|-------|-------|
| **Setup** | Repo at HEAD post-migration. |
| **Action** | `find server -name 'package.json' -o -name 'node_modules' -o -name 'webpack.config.js' -o -name 'vite.config.ts' -o -name 'next.config.*' 2>/dev/null` |
| **Expected** | Empty output. (`find` returns no matches.) |
| **Automated** | yes |
| **Automation** | bash command above; `pytest scripts/uat/uat_task66.py::test_ac10_no_npm_artifacts` |
| **Evidence** | command stdout (empty) |
| **Cleanup** | none |

### AC11 — SSE drives real-time KPI counters on /admin/overview

| Field | Value |
|-------|-------|
| **Setup** | `AMPLIFIER_UAT_SSE_HEARTBEAT_MS=500`. Admin logged in on `/admin/overview`. Capture initial "Active users" counter value as N. |
| **Action** | DevTools MCP: open `/admin/overview` in tab 1. In a terminal: register a NEW user via curl. Watch tab 1 counter via `evaluate_script("document.querySelector('[data-kpi=active_users]').textContent")` polled every 1s up to 5s. |
| **Expected** | Counter transitions from N to N+1 within 5s (with heartbeat 500ms). `list_network_requests` shows one EventSource connection to `/sse/admin/overview` with `Content-Type: text/event-stream`. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac11_sse_overview` |
| **Evidence** | counter values pre/post; EventSource request log |
| **Cleanup** | delete the seeded user; close EventSource |

### AC12 — SSE drives live campaign metrics on /company/campaign_detail

| Field | Value |
|-------|-------|
| **Setup** | Company on `/company/campaigns/<id>`. Capture initial "Total Posts" value. |
| **Action** | DevTools MCP: leave page open. Insert a new metric row via SQL (`INSERT INTO metric ... ` for the seeded campaign's post). Watch UI counter via `evaluate_script` poll. |
| **Expected** | Counter increments within 5s. EventSource connected to `/sse/campaign/<id>/metrics`. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac12_sse_campaign_metrics` |
| **Evidence** | counter values; EventSource log |
| **Cleanup** | delete seeded metric row |

### AC13 — Status label rename consistency across surfaces (#24)

| Field | Value |
|-------|-------|
| **Setup** | Test data has at least one row in each status: `pending_invitation`, `content_generated`, `posted`, `paid`. |
| **Action** | DevTools MCP: visit `/user/campaigns`, `/company/campaigns/<id>` (post list), `/admin/payouts` (payout list). For each page, snapshot the status badge column. |
| **Expected** | NO occurrences of raw enum strings (`pending_invitation`, `content_generated`, `posted`, `paid`) in user-visible badge text. ALL badges show display labels: "Invited", "Draft Ready", "Live", "Earned" respectively. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac13_status_labels` (regex grep DOM text) |
| **Evidence** | snapshot text per page |
| **Cleanup** | none |

### AC14 — Copy URL button next to every post URL (#25)

| Field | Value |
|-------|-------|
| **Setup** | Posts exist with valid URLs in DB. |
| **Action** | DevTools MCP: visit `/user/posts`, `/company/campaigns/<id>` (post list), `/admin/users/<id>` (user post history). For each, find post URL row → click Copy button → `evaluate_script("navigator.clipboard.readText()")`. |
| **Expected** | Each surface has a Copy button next to URL. Clicking it copies the URL to clipboard. "Copied!" tooltip appears for ~1.5s (Alpine state). |
| **Automated** | partial — clipboard read requires DevTools clipboard permission |
| **Automation** | `scripts/uat/uat_task66.py::test_ac14_copy_url` |
| **Evidence** | clipboard contents; tooltip screenshot |
| **Cleanup** | none |

### AC15 — HTML5 native form validation on every form (#26)

| Field | Value |
|-------|-------|
| **Setup** | Identify every `<form>` in admin/company/user templates. |
| **Action** | DevTools MCP: visit each form page → `evaluate_script("Array.from(document.forms).map(f => Array.from(f.elements).map(e => ({name:e.name,type:e.type,required:e.required,pattern:e.pattern,min:e.min,max:e.max})))")`. |
| **Expected** | Every required field has `required` attr. Email inputs have `type="email"`. Numeric inputs have `type="number"` with appropriate `min`/`max`. URL inputs have `pattern=` or `type="url"`. Submitting an empty required field triggers browser native validation tooltip (no JS error). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac15_form_validation` |
| **Evidence** | per-form attribute dump; submission attempt screenshot |
| **Cleanup** | none |

### AC16 — REGRESSION: ToS gate + /terms + /privacy still functional (Task #28)

| Field | Value |
|-------|-------|
| **Setup** | Server live. |
| **Action** | (a) `curl -s https://api.pointcapitalis.com/terms \| grep -o "Terms of Service"` and same for `/privacy`. (b) DevTools MCP: navigate `/company/login?register=1` → leave ToS unchecked → submit → screenshot. (c) Check ToS → submit different email → screenshot. |
| **Expected** | (a) Both grep hits non-empty (HTTP 200). (b) Error banner "You must accept the Terms of Service and Privacy Policy to register" visible. (c) Redirect to `/company/`. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac16_tos_gate_regression` |
| **Evidence** | curl output; 2 screenshots |
| **Cleanup** | delete throwaway company row |

### AC17 — REGRESSION: Company register → login → dashboard E2E

| Field | Value |
|-------|-------|
| **Setup** | Fresh email `uat-task66-fresh@uat.local`. |
| **Action** | DevTools MCP: register (with ToS) → log in → land on `/company/`. Verify all sidebar links work (Dashboard, Campaigns, Billing, Influencers, Stats, Settings) without 5xx. |
| **Expected** | Each of 6 nav links opens its page with HTTP 200 and console errors = 0. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac17_company_full_nav` |
| **Evidence** | 6 page screenshots; status codes |
| **Cleanup** | delete the test company row |

### AC18 — REGRESSION: Admin login + all 14 admin pages render

| Field | Value |
|-------|-------|
| **Setup** | Admin password `admin`. |
| **Action** | DevTools MCP: log in → visit each: `/admin/overview`, `/users`, `/users/<id>`, `/companies`, `/companies/<id>`, `/campaigns`, `/campaigns/<id>`, `/financial`, `/payouts`, `/fraud`, `/analytics`, `/audit_log`, `/review_queue`, `/settings`. For each: HTTP 200, console errors=0, screenshot. |
| **Expected** | 14 pages × HTTP 200, 0 console errors, no broken images, sidebar nav present. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac18_admin_full_nav` |
| **Evidence** | 14 screenshots |
| **Cleanup** | none |

### AC19 — REGRESSION: Manual campaign creation E2E (form → activate → quality gate)

| Field | Value |
|-------|-------|
| **Setup** | Test company logged in, balance $50 (top-up via AC21 if needed). |
| **Action** | DevTools MCP: `/company/campaigns/create` → fill all required fields with quality content (brief 300+ chars, guidance 50+ chars, target_regions/niche_tags set, budget $20, payout rates set) → click "Save Draft" → click "Activate". |
| **Expected** | Campaign saved as draft (DB row with `status=draft`). On Activate: server runs `score_campaign()` rubric → score ≥ 85 → AI review returns `safe` → status flips to `active`. audit_log row `event='campaign_activated'`. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac19_manual_campaign_e2e` |
| **Evidence** | DB row dump; audit_log row; screenshot of "Active" badge |
| **Cleanup** | void the test campaign |

### AC20 — REGRESSION: AI campaign wizard E2E (URL → Gemini → activate)

| Field | Value |
|-------|-------|
| **Setup** | Test company logged in, balance $50. |
| **Action** | DevTools MCP: `/company/campaigns/wizard` → enter URL `https://example.com/product` → click "Generate" → wait for Gemini brief → review → click "Activate". |
| **Expected** | Within 60s: brief generated (length > 200 chars). Content screening returns `caution` or `safe` (not `reject` for example.com). Activate succeeds, campaign live. |
| **Automated** | partial — Gemini call is real |
| **Automation** | `scripts/uat/uat_task66.py::test_ac20_ai_wizard_e2e` |
| **Evidence** | brief text; campaign row; screenshot |
| **Cleanup** | void campaign |

### AC21 — REGRESSION: Stripe Checkout top-up (test mode, idempotent)

| Field | Value |
|-------|-------|
| **Setup** | Test company, balance $0. Stripe MCP test mode. |
| **Action** | DevTools MCP: `/company/billing` → "Add Funds" → $50 → Stripe test card 4242... → "Pay" → wait redirect. Then via MCP: `mcp__stripe__trigger_event(event_type="checkout.session.completed", checkout_session=<id>)` to replay. |
| **Expected** | First flow: balance becomes 5000 cents. Webhook log shows event received. After replay: balance STILL 5000 (idempotent). audit_log has 1 `balance_credited` row, second replay creates `webhook_duplicate_ignored` (or no new row). |
| **Automated** | partial |
| **Automation** | `scripts/uat/uat_task66.py::test_ac21_stripe_topup_idempotent` |
| **Evidence** | balance before/after both replays; audit_log diff |
| **Cleanup** | reset balance |

### AC22 — REGRESSION: AI matching E2E (profile → match → invitation)

| Field | Value |
|-------|-------|
| **Setup** | Test user with scraped profile (LinkedIn niches set). New campaign just activated with niche_tags overlapping user's niches. |
| **Action** | Trigger matching: `curl -X POST https://api.pointcapitalis.com/admin/run-matching -H "Authorization: Bearer <admin>"` (or wait for next worker cron). |
| **Expected** | `CampaignAssignment` row created for user × campaign with `status=pending_invitation`. `CampaignInvitationLog` row exists. matching_cache has a hit on subsequent run. Gemini AI scoring score >= 60. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac22_matching_e2e` |
| **Evidence** | SQL row dumps; cache hit log line |
| **Cleanup** | reject the assignment |

### AC23 — REGRESSION: Invitation list — countdown, decline reason, expired badge (Task #5)

| Field | Value |
|-------|-------|
| **Setup** | Seed 3 invitations for test user: one expiring in 25h (default), one expiring in 2h (warning), one already-expired 1h ago. |
| **Action** | DevTools MCP: `/user/campaigns` (or local app `/campaigns`) → `take_snapshot`. Click Reject on a non-expired one → modal shows reason picker → choose "Payout too low" → submit. |
| **Expected** | All 3 invitations visible. 25h shows "1d 1h remaining" default color. 2h shows "2h Xm remaining" warning color (yellow/amber). Expired shows red EXPIRED badge, dimmed card, disabled buttons. Decline reason flows to server (`assignment.decline_reason='Payout too low'`). |
| **Automated** | partial |
| **Automation** | `scripts/uat/uat_task66.py::test_ac23_invitation_ux` |
| **Evidence** | snapshot DOM text per invitation; SQL row showing decline_reason |
| **Cleanup** | reset the 3 invitations |

### AC24 — REGRESSION: Content agent 4 phases produce drafts for LI/FB/Reddit

| Field | Value |
|-------|-------|
| **Setup** | Active assignment for test user × test campaign. `agent_research` + `agent_draft` empty for this campaign. `AMPLIFIER_UAT_INTERVAL_SEC=120`. |
| **Action** | `python scripts/background_agent.py --once --campaign-id <id> 2>&1 \| tee data/uat/task66_ac24_agent.log` |
| **Expected** | Within 5 min: agent.log has lines `Phase 1 (Research) complete`, `Phase 2 (Strategy) complete`, `Phase 3 (Creation) complete: 3 platform(s)`, `Phase 4 (Review) complete`. agent_draft has 3 rows (linkedin, facebook, reddit), all non-empty. Reddit row has caveat language. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac24_content_agent_e2e` |
| **Evidence** | log excerpts; SQL rows |
| **Cleanup** | none |

### AC25 — REGRESSION: Real LinkedIn post via JSON engine + URL captured

| Field | Value |
|-------|-------|
| **Setup** | LinkedIn profile session valid. Approved draft exists from AC24. `AMPLIFIER_UAT_POST_NOW=1`. |
| **Action** | Approve draft via local UI, then run `python scripts/post.py --slot 1`. Wait up to 3 min. |
| **Expected** | Post appears on LinkedIn (verify via Playwright or manual URL visit). Local DB `agent_draft` row updated to `status=posted`, `post_url` populated with `/feed/update/urn:li:activity:` URL. Server `posts` table has the row. |
| **Automated** | partial — manual confirmation that LI post is real |
| **Automation** | `scripts/uat/uat_task66.py::test_ac25_linkedin_post_real` (DB checks) + manual y/n on LinkedIn URL |
| **Evidence** | LinkedIn URL; DB rows; screenshot of live post |
| **Cleanup** | **DELETE the LinkedIn post** via `python scripts/uat/delete_post.py --url <url>` (autonomous Playwright deletion). Mark local row `status=deleted`. |

### AC26 — REGRESSION: Metric scrape → metric row → billing → payout pending

| Field | Value |
|-------|-------|
| **Setup** | Posted LI post from AC25 with at least 1 hour elapsed (or use a fixture URL with known-good metrics). |
| **Action** | `python scripts/utils/metric_scraper.py --post-url <url>` (one-shot). Then check server: `curl -s https://api.pointcapitalis.com/api/users/me/earnings -H "Authorization: Bearer <token>"`. |
| **Expected** | scraper logs `Scraped 1 post: likes=N, comments=N`. Server `metric` table has new row. Server `payouts` table has new row with `status=pending`, `available_at` 7 days out, amount > 0. Earnings endpoint shows pending_balance > 0. |
| **Automated** | partial |
| **Automation** | `scripts/uat/uat_task66.py::test_ac26_metric_billing_e2e` |
| **Evidence** | scraper log; SQL rows; earnings JSON |
| **Cleanup** | void the test payout |

### AC27 — REGRESSION: Earnings page + withdraw flow

| Field | Value |
|-------|-------|
| **Setup** | Test user with `earnings_balance_cents=1500` (available). `stripe_account_id=NULL` (no Connect yet). |
| **Action** | DevTools MCP: `/user/earnings` → snapshot. Click "Withdraw $15". |
| **Expected** | Page shows "Available: $15.00", "Pending: $0.00". Withdraw button shows "Connect your bank account first" toast/inline. No Stripe API call. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac27_earnings_no_connect` |
| **Evidence** | screenshots |
| **Cleanup** | none |

### AC28 — REGRESSION: Admin financial actions all functional

| Field | Value |
|-------|-------|
| **Setup** | Admin logged in. Seed 1 ready-to-promote payout. |
| **Action** | DevTools MCP: `/admin/financial` → click "Run earning promotion" → wait → click "Run payout processing" → wait → click "Run billing reconciliation" → wait. |
| **Expected** | Each button POSTs to its endpoint, returns 200, shows toast/banner with row counts. audit_log has 3 new rows. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac28_admin_financial_actions` |
| **Evidence** | toasts; audit_log rows |
| **Cleanup** | none |

### AC29 — REGRESSION: Admin payout void + force-approve (Task #8)

| Field | Value |
|-------|-------|
| **Setup** | Seed 1 pending payout + 1 available payout. Admin logged in. |
| **Action** | DevTools MCP: `/admin/payouts` → on pending row click "Void" → enter reason "UAT void test" → confirm. On available row click "Void" → enter reason → confirm. On a third pending row click "Force Approve". |
| **Expected** | Pending → voided: status flip, campaign budget +amount, audit_log row. Available → voided: status flip, user earnings_balance −amount, campaign budget +amount, audit_log row. Pending → approved: status='available' immediately, audit_log row. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac29_admin_payout_actions` |
| **Evidence** | SQL row diffs; 3 audit_log rows |
| **Cleanup** | none |

### AC30 — REGRESSION: Server-side post URL dedup still works (Task #27)

| Field | Value |
|-------|-------|
| **Setup** | Test user JWT. Active assignment. |
| **Action** | POST same URL twice via curl: `curl -X POST .../api/posts -H "Authorization: Bearer $TOKEN" -d '{"posts":[{"assignment_id":<ID>,"platform":"linkedin","post_url":"https://linkedin.com/posts/uat-task66-dedup","content_hash":"x","posted_at":"2026-04-30T20:00:00Z"}]}'`. Repeat. |
| **Expected** | First call: `count=1, skipped_duplicate=0`. Second: `count=0, skipped_duplicate=1`. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac30_post_dedup_regression` |
| **Evidence** | both JSON outputs |
| **Cleanup** | DELETE the row from posts table |

### AC31 — REGRESSION: Console error scan — every page across admin/company/user

| Field | Value |
|-------|-------|
| **Setup** | Admin, company, user all logged in. |
| **Action** | DevTools MCP: visit each of the 14 admin pages, 10 company pages, 7 user pages (31 total) → `list_console_messages` per page → grep for `error` level. |
| **Expected** | 31/31 pages report ZERO console errors. Warnings OK. (Tailwind CDN warning about production usage is acceptable; document it.) |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac31_console_error_sweep` |
| **Evidence** | per-page console message dump |
| **Cleanup** | none |

### AC32 — REGRESSION: Network 5xx scan — every page

| Field | Value |
|-------|-------|
| **Setup** | Same as AC31. |
| **Action** | DevTools MCP: per-page `list_network_requests` → filter `status >= 500`. |
| **Expected** | 31/31 pages report ZERO 5xx responses. 4xx OK only when expected (e.g., auth probe). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task66.py::test_ac32_network_5xx_sweep` |
| **Evidence** | per-page network log |
| **Cleanup** | none |

### AC33 — Visual regression: 24 page screenshots desktop + mobile

| Field | Value |
|-------|-------|
| **Setup** | All test data seeded per Test data setup. Pre-migration baselines captured in `data/uat/baselines/task66_pre/`. |
| **Action** | DevTools MCP: per page (24 dashboard + 7 user = 31), capture desktop (1280x720) + mobile (375x812) screenshots → `data/uat/screenshots/task66_<page>_<viewport>.png`. |
| **Expected** | All 62 screenshots captured. **Manual eyeball:** for each, the new HTMX version maintains layout integrity (no broken layout, no overlapping elements, no missing nav, fonts load). User reviews 5 random sampled screenshots and confirms y/n. |
| **Automated** | partial |
| **Automation** | DevTools MCP loop + manual y/n |
| **Evidence** | 62 screenshots; user confirmation |
| **Cleanup** | none |

### AC34 — REGRESSION: pytest suite still 194/194 passing

| Field | Value |
|-------|-------|
| **Setup** | Repo at HEAD post-migration. |
| **Action** | `cd /c/Users/dassa/Work/Auto-Posting-System && pytest tests/ -v 2>&1 \| tee data/uat/task66_ac34_pytest.log` |
| **Expected** | `194 passed` (or higher if new tests added for HTMX features). Zero `FAILED` lines. Zero `ERROR` lines. Suite < 60s wall clock. |
| **Automated** | yes |
| **Automation** | command above |
| **Evidence** | pytest log |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #66

Task #66 is marked done in task-master ONLY when:
1. AC1–AC34 all PASS (AC6/AC23/AC25/AC33 manual y/n confirmations from user)
2. Zero `FAILED`/`ERROR` in pytest suite (AC34)
3. Zero console errors across all 31 pages (AC31)
4. Zero 5xx responses across all 31 pages (AC32)
5. No `error|exception|traceback` in `journalctl -u amplifier-web` during the UAT window
6. No new rows in `audit_log` with `severity='error'` during UAT
7. UAT report `docs/uat/reports/task-66-<yyyy-mm-dd>-<hhmm>.md` written with all 62 screenshots embedded, all evidence captured
8. All cleanup steps completed (test campaigns voided, throwaway users deleted, LinkedIn UAT posts deleted via Playwright, localStorage cleared, fixtures removed)
9. `mcp__stripe__list_checkout_sessions(limit=10)` shows no orphan UAT sessions in test mode after AC21
10. Server `/health` returns 200 at end of run; `amplifier-web.service` and `amplifier-worker.service` both `active (running)`

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

## Polish requirements absorbed from deferred tasks (2026-04-30)

These three task-master items were deferred at the same time the user-app split was committed, because polishing the soon-to-be-deleted Flask templates is wasted work. Each requirement must land in the HTMX migration so the new creator/company/admin surfaces ship with them on day 1.

- **#24 — Status label rename** (originally targeted `scripts/templates/user/`). In every new HTMX surface that displays a status badge, the user-facing label must be: `pending_invitation` → "Invited", `content_generated` → "Draft Ready", `posted` → "Live", `paid` → "Earned". Apply consistently across user app `/user/*`, company `/company/*` (campaign assignment lists), and admin `/admin/*` (post status, payout status). Internal DB enum values stay the same — this is a presentation-layer rename only.
- **#25 — Copy URL button** (originally Posts tab in user app). Every new surface that renders a post URL (creator dashboard Posts page, company campaign-detail post list, admin posts table) must include a Copy button next to the URL. Use the standard Tailwind/HTMX clipboard pattern (`navigator.clipboard.writeText` + a 1.5s "Copied!" tooltip via Alpine).
- **#26 — Client-side form validation** (originally user app forms). Every form in every new HTMX surface must use HTML5 native validation: `required` on all required fields, `type="email"` on email inputs, `type="number"` with `min`/`max` on numeric inputs, `pattern=` on URL fields. No custom JS validation — native HTML5 + the existing Pydantic server-side validation is enough.

Each of these is small but easy to forget. Adding them to the migration's Acceptance Criteria block (when the AC block is expanded for #66 implementation) ensures they ship.
