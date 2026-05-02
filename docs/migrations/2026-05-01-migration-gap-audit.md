# Phase D Migration Gap Audit

**Date**: 2026-05-02
**Author**: Claude (Opus 4.7) — autonomous gap-audit pass after `/update-docs`
**Scope**: Walk every feature spec'd in the 3 Phase D migration docs (`docs/migrations/2026-04-28-*.md`) AND every product feature bucket (Money Loop, AI Brain, Product Features, Business Launch, all 3 dashboards, daemon, onboarding) to surface gaps where the migration silently dropped or never re-spec'd a launch-essential feature.
**Trigger**: User asked "how many more things are broken that we don't know of?" after the onboarding flow was discovered broken during Task #74 launch UAT prep (last session).

## Executive summary

**Updated 2026-05-02 after second + third audit passes:** 8 launch-blocker gaps confirmed (6 from first pass + 2 new from deeper audits), 1 false-alarm gap retracted, 5 new tasks filed (#75 web onboarding, #76 pause/resume + dashboard health, #77 installer icon, #79 EULA, #80 admin financial buttons), Task #19 description updated for demo-keys-for-launch + real-keys-required-pre-launch, scripts/onboarding.py reference dropped from CLAUDE.md.

**Original first-pass summary (kept for reference):** 6 launch-blocker gaps confirmed. 2 already-tracked partials. The rest of Phase D ships intact.

Phase D was three concurrent rewrites that merged separately over two days (#66 dashboards, #67 creator-app-split, #70 BYOK). The seams between them dropped one feature wholesale (web-driven onboarding flow) and left two more in a half-shipped state (pause/resume agent control, Stripe Connect onboarding UI). Those are the failures the user will hit on first install.

The product feature buckets (Money Loop, AI Brain, Product Features) survived the migration intact — daemon code was preserved verbatim per #67's design, and pytest 303/303 confirms no regression on server services.

---

## Method

For each spec'd feature, I checked: (a) does the code exist where the spec says it should, (b) does the user-visible flow connect end-to-end, (c) would Task #74 launch UAT actually catch a bug here. Findings annotated with `file:line` for `EXISTS`, `MISSING` for genuine absences.

---

## Findings — by feature bucket

### 1. Onboarding flow — **3 LAUNCH BLOCKERS**

The migration shipped the auth-handoff endpoint but not the surrounding flow. The result: there is currently **no way for a new user to register** through any UI (web or local).

| Spec source | Spec'd feature | Code | Status |
|---|---|---|---|
| `migration-creator-app-split.md` lines 102–120 (Auth handoff sequence) | `https://amplifier.app/register?agent=true` (public registration page) | `server/app/routers/user/login.py:60` says "Don't have an account? Install the desktop app and complete onboarding to create one" — but no register HTML route exists | **MISSING — LAUNCH BLOCKER** |
| Same | Server route `GET /onboarding/step2` ("Connect your platforms") | not found in server routers | **MISSING — LAUNCH BLOCKER** |
| Same | Server route `GET /onboarding/step3` ("Set up AI keys") | not found | **MISSING — LAUNCH BLOCKER** |
| Same | Server route `GET /onboarding/step4` ("Done") | not found | **MISSING — LAUNCH BLOCKER** |
| Same | Server route `GET /user/onboarding` (target of local auth callback redirect) | not found | **MISSING — LAUNCH BLOCKER** |
| `local_server.py:177` | After receiving JWT, redirects browser to `{HOSTED}/user/onboarding` | `RedirectResponse(url=f"{HOSTED_BASE_URL}/user/onboarding", status_code=302)` | **DEAD-END — redirects to 404** |
| `CLAUDE.md` Commands section | `python scripts/onboarding.py` ("first-run setup (register, connect platforms, set mode)") | `scripts/onboarding.py` does not exist | **MISSING — and CLAUDE.md is wrong** |
| `migration-creator-app-split.md` line 75 | DELETE `scripts/templates/user/onboarding.html` | template deleted ✅ | EXISTS (deleted as spec'd) |

**Net effect**: a fresh user cannot register. The only register path that actually works is `POST /api/auth/register` via curl/JSON — useful for UAT seed scripts, useless for real users.

This is **gap #1** and it's the largest. The migration spec described a 16-step flow (register → token handoff → connect platforms → AI keys → done). Steps 1, 7–14 of that flow have no implementation.

### 2. Daemon control surface — **1 LAUNCH BLOCKER**

| Spec source | Spec'd feature | Code | Status |
|---|---|---|---|
| `migration-creator-app-split.md` AC11 | "Pause Agent" + "Resume Agent" buttons on `/user/settings` | grep across `server/app/templates` returns 0 matches for `Pause Agent` / `pause_agent` / `Resume Agent` | **MISSING — LAUNCH BLOCKER** |
| Same | When user clicks Pause: server inserts `AgentCommand` type=`pause_agent`, daemon picks up within 90s, status reflects via SSE | API endpoints exist (`/api/agent/commands` POST, `/api/agent/status` GET) — but no UI button to trigger them | **API READY, UI MISSING** |
| `migration-creator-app-split.md` AC11 | SSE-driven "Status: Paused" indicator | `sse.py:183 GET /sse/user/agent-status` exists | EXISTS (consumer side untested) |

**Net effect**: user can't pause the agent from the web. They have to kill the daemon process. Bad UX for production.

### 3. Stripe Connect onboarding — **1 LAUNCH BLOCKER (also tracked as #19)**

| Spec source | Spec'd feature | Code | Status |
|---|---|---|---|
| `batch-4-business-launch.md` Task #19 | Stripe Connect Express onboarding for users (UI + redirect to Stripe-hosted onboarding + return URL handling) | `server/app/services/payments.py` has `create_payout` and `process_payout` — but no `create_account_link` / Stripe-hosted onboarding redirect | **MISSING — LAUNCH BLOCKER** |
| `user/settings.html:125` | "Connect Bank Account" button | exists but `disabled title="Stripe Connect onboarding — coming soon"` | **PLACEHOLDER ONLY** |
| `user/settings.html:129` | Hint text: "Stripe Connect onboarding will be available in the next update (Task #19)." | the hint is honest — but Task #74 launch UAT can't pass without this flow shipping | **TRACKED — Task #19 pending** |
| `user/earnings.html:122` | "Connect Bank Account" button (alternate entry point) | links to `/user/settings#stripe-connect` which has the disabled button | **DEAD-END LINK** |
| `users.py:116` | Withdraw API rejects when `stripe_account_id IS NULL` with HTTP 400: "Stripe Connect bank account not linked" | exists ✅ | EXISTS (correct gate, no upstream onboarding) |

**Net effect**: users can earn money but can never receive it. This is the gating money-loop bug for the user side.

This is already tracked as **Task #19 (pending)**, blocked on user setting up Stripe Connect Express. But the UI + redirect plumbing also has to be built — that's not strictly a "Stripe setup" task, it's a real feature task that depends on Stripe being live.

### 4. Hosted `/user/*` dashboard — **NO GAP**

All 7 spec'd pages exist with HTML templates and routes:

| Spec'd page | Route | Template | Status |
|---|---|---|---|
| `/user/login` | `routers/user/login.py:21` | `templates/user/login.html` | EXISTS |
| `/user/dashboard` (and `/`) | `routers/user/dashboard.py:21,22` | `templates/user/dashboard.html` | EXISTS |
| `/user/campaigns` | `routers/user/campaigns.py:30` | `templates/user/campaigns.html` | EXISTS |
| `/user/campaigns/{id}` | `routers/user/campaigns.py:79` | `templates/user/campaign_detail.html` | EXISTS |
| `/user/posts` | `routers/user/posts.py:19` | `templates/user/posts.html` | EXISTS |
| `/user/earnings` | `routers/user/earnings.py:20` | `templates/user/earnings.html` | EXISTS |
| `/user/settings` | `routers/user/settings.py:12` | `templates/user/settings.html` | EXISTS |

Plus 5 partial-render routes (`/campaigns/_tab/{tab_name}`, etc.) for HTMX swaps. No gap.

`campaign_detail.html:54-56` has the spec'd "Open in Desktop App" button linking to `localhost:5222/drafts/{id}` ✅ (#66 AC8 + #67 AC5).

`settings.html:97` links to `localhost:5222/keys` ("Manage Keys (Desktop App)") ✅ (#67 AC10).

### 5. Local FastAPI surface — **NO GAP** (but auth callback target is broken — see #1)

`scripts/utils/local_server.py` has all 5 spec'd top-level routes:

| Route | local_server.py line | Status |
|---|---|---|
| `GET /healthz` | 150 | EXISTS |
| `GET /auth/callback` | 156 | EXISTS (redirects to dead `/user/onboarding` — see gap #1) |
| `GET /connect`, `POST /connect/{platform}` | 181, 192 | EXISTS |
| `GET /keys`, `POST /keys`, `POST /keys/test` | 220+ | EXISTS |
| `GET /drafts`, `GET /drafts/{id}` + sub-actions | per file docstring | EXISTS |

Old Flask routes (`/dashboard`, `/campaigns`, `/posts`, `/earnings`, `/settings`, `/login`, `/onboarding`) all return 404 ✅ (#67 AC4).

### 6. Server-side new endpoints from #67 — **NO GAP**

| Endpoint | File:line | Status |
|---|---|---|
| `GET /api/agent/commands` | `agent.py:64` | EXISTS |
| `POST /api/agent/commands` | `agent.py:80` | EXISTS |
| `POST /api/agent/commands/{id}/ack` | `agent.py:105` | EXISTS |
| `POST /api/agent/status` (push) | `agent.py:131` | EXISTS |
| `GET /api/agent/status` | `agent.py:176` | EXISTS |
| `POST /api/drafts` | `drafts.py:57` | EXISTS |
| `POST /api/drafts/upload-image` | `drafts.py:79` | EXISTS |
| `GET /api/drafts` | `drafts.py:115` | EXISTS |
| `PATCH /api/drafts/{id}` | `drafts.py:126` | EXISTS |
| `GET /sse/admin/overview` | `sse.py:36` | EXISTS |
| `GET /sse/campaign/{id}/metrics` | `sse.py:93` | EXISTS |
| `GET /sse/user/agent-status` | `sse.py:183` | EXISTS |

### 7. HTMX/Alpine/Tailwind/Chart.js (Migration #66) — **NO GAP**

| Feature | Verification | Status |
|---|---|---|
| Libraries loaded in `base.html` | `templates/base.html:141` shows alpine-helpers loaded before alpinejs | EXISTS |
| Cmd+K / Ctrl+K command palette | `templates/admin/_nav.html:16,34,70` + `static/js/alpine-helpers.js:109-125` define `commandPalette` Alpine component | EXISTS |
| Status label renames (#24) | absorbed into HTMX templates per migration spec section "Polish requirements absorbed from deferred tasks" | (assumed — spot-check during UAT) |
| Copy URL buttons (#25) | `alpine-helpers.js` has `copyButton` per line 7 | EXISTS |
| HTML5 native validation (#26) | per migration spec, `required`/`type=email`/`pattern=` on every form | (assumed — UAT will catch any miss) |

### 8. Stealth + packaging (Migration #68) — **PARTIAL (already tracked)**

| Spec'd | Code | Status |
|---|---|---|
| Patchright drop-in across 22 files | per `a4828de` doc-sync commit + CLAUDE.md "stealth_lib: Patchright (drop-in Playwright). All 22 daemon files swapped 2026-05-01. CreepJS 0% stealth detection." | DONE |
| Nuitka build script `scripts/build/build_windows.py` | EXISTS | DONE (scaffolding) |
| `build_mac.py`, `build_mac_installer.sh` | EXIST | DONE (scaffolding) |
| Inno Setup installer `installer/windows.iss` | EXISTS | DONE (scaffolding) |
| `auto_update.py` | `scripts/utils/auto_update.py` EXISTS | DONE |
| Tray "Check for Updates" item | `tray.py:168` | DONE |
| GHA matrix `.github/workflows/release.yml` | (not verified in this audit, but committed per `9fbb615`) | DONE (scaffolding) |

**Live verification deferred to v1.0.0 release tag** — known partial per `STATUS.md`. Not a launch blocker for app functionality, but **does block actual user-installable distribution**. The app currently ships as `git clone + pip install`, which is unshippable to paying users. If launch = "users can install Amplifier without a developer environment," then **this is a launch blocker**.

### 9. BYOK (Migration #70) — **NO GAP**

| Feature | Verification | Status |
|---|---|---|
| `company_api_keys` table (Alembic `b1c2d3e4f5a6`) | applied to prod 2026-05-01 | DONE |
| `services/api_keys.py` with `resolve_api_key` + `call_with_byok_fallback` | per CLAUDE.md | DONE |
| `/company/settings/api-keys` POST | `company/settings.py:86` | EXISTS |
| `/company/settings/api-keys/test` POST | `company/settings.py:142` | EXISTS |
| Settings UI shows "•••••• (configured)" never plaintext | per migration spec | (assumed — UAT will spot-check) |
| 15 BYOK tests in pytest suite | 303/303 baseline | DONE |

### 10. Money Loop, AI Brain, Product Features (Batches 1–3) — **NO REGRESSION**

The migration explicitly preserved daemon automation code verbatim per `migration-creator-app-split.md` line 21 ("Existing 6,500+ LOC of `background_agent.py`, `engine/`, `content_agent.py`, `metric_scraper.py`, `profile_scraper.py`, `local_db.py` — preserved verbatim").

303/303 pytest passing on `flask-user-app` HEAD covers all server services (matching, billing, trust, payments, quality_gate, BYOK, content screening, post URL dedup, ToS gate). No code path was deleted or rewired.

What I did NOT verify (deferred to `/uat-task 74` runs):
- Real LinkedIn/Facebook/Reddit posts still execute end-to-end after Patchright swap
- Profile scraping selectors still work post-Patchright
- Metric scraping selectors still work post-Patchright

These are integration concerns that pytest can't catch — they're exactly what `/uat-task 74.1` will exercise.

### 11. Documentation drift — **MINOR**

| Issue | Where | Severity |
|---|---|---|
| `CLAUDE.md` Commands section references `scripts/onboarding.py` which doesn't exist | `CLAUDE.md` Commands section | MINOR — fix when filing the onboarding task (#75) |
| `docs/specs/launch-uat.md` AC blocks for 74.1 assume a registered user already exists | spec authored in last session | OK (UAT seed helpers register via JSON API as workaround); but if launch UAT is supposed to mirror real user experience, the spec should drive the broken UI flow first |

---

## Triage proposal

| Gap | Bucket | Severity | Proposed task | Est effort |
|---|---|---|---|---|
| 1 | Public user register HTML page + 4 onboarding step pages on hosted server | Onboarding | LAUNCH BLOCKER | **#75 — Web onboarding flow** | 2–3 days |
| 2 | `scripts/onboarding.py` (CLI fallback) | Onboarding | NICE-TO-HAVE | (drop — web flow obsoletes it; remove from CLAUDE.md instead) | 5 min |
| 3 | local_server.py:177 redirect target | Onboarding | LAUNCH BLOCKER (subset of #75) | covered by #75 | — |
| 4 | Pause/Resume agent button on `/user/settings` | Daemon control | LAUNCH BLOCKER | **#76 — Pause/Resume agent UI + command flow** | 0.5 day |
| 5 | Stripe Connect Express onboarding flow (UI + redirect + return URL) | Money loop (user side) | LAUNCH BLOCKER (Task #19) | already tracked — needs Stripe live keys before code can ship | depends on user |
| 6 | Nuitka installer + GHA release tag | Distribution | LAUNCH BLOCKER if launch = "user-installable" | already tracked as #68 partial — deferred to v1.0.0 tag | 1 day post-launch-prep |

**Recommended sequencing:**

1. **Now**: file gap #1 as Task #75 (web onboarding) and gap #4 as Task #76 (pause/resume). Author AC blocks for both following `docs/uat/AC-FORMAT.md`. Both are pure server + template work, no external dependencies.
2. **Implement #75** → `/uat-task 75` with user monitoring first run.
3. **Implement #76** → `/uat-task 76` with user monitoring first run.
4. **Re-run `/uat-task 74.1`** (the task whose initial run uncovered gap #1). Should now pass the registration + onboarding sub-flow.
5. **Decide on Stripe**: user sets up Stripe Connect live keys → unblock Task #19 → file as #77 (or keep as #19 with new ACs).
6. **Decide on installer**: tag v1.0.0 → run GHA release → produce real installer → that closes the #68 partial.
7. Then `/uat-task 74.2` (company) and `/uat-task 74.3` (admin) which don't depend on onboarding fixes.

---

## What this audit deliberately does NOT cover

- Browser-driven UAT of the working features (that's what `/uat-task 74` is for — gap audit is grep-driven, UAT is real-product-driven)
- Performance regressions (Tailwind CDN size, SSE connection limits, etc.)
- Visual regressions (screenshot diffs against pre-migration baselines)
- Security audit of the new auth handoff (token in URL fragment vs query — separate task)
- Mobile responsiveness of new HTMX surfaces (deferred per `STATUS.md`)

If any of those domains is a concern beyond what UAT will catch, file separately.

---

## Confidence and limitations

- I grep'd 4 surface areas (server routers, server templates, local_server.py, daemon scripts/utils) and read 3 migration docs end-to-end. I did NOT exhaustively trace every conditional branch in every router.
- A feature could exist as documented but be broken in a way grep won't catch (e.g., correct route registered but always returns 500). UAT will catch those — gap audit will not.
- The onboarding gap is high-confidence (multiple spec references + multiple missing routes/pages + dead-end redirect, all corroborate). The pause/resume gap is high-confidence (zero matches across templates). The Stripe gap is acknowledged in code comments.
- I trust the migration docs to be the contract. If the Claude Desktop spec sheet you mentioned was different, this audit may not reflect it. (Per your message in this session, the Claude Desktop chat produced exactly the 3 migration docs + the STATUS.md edit — same scope.)

---

## Second-pass audit findings (2026-05-02 deep)

User asked for a thorough re-audit ("ensure that you've analyzed thoroughly") because the first-pass audit was grep-driven and shallow. Three parallel Explore agents read each migration AC verbatim and traced code wiring end-to-end. Findings below supplement (and in one case correct) the first-pass section above.

### Confirmed (no change to first-pass findings)

All 6 first-pass gaps remain valid as written. The deeper audit corroborated them with file:line evidence:

- Gap #1 (web onboarding) — corroborated. No `/register` HTML route, no `/onboarding/step*` routes. `local_server.py:177` redirects to `{HOSTED_BASE_URL}/user/onboarding` which is undefined. `user/login.html:60` says "Install the desktop app" but no `scripts/onboarding.py` exists.
- Gap #4 (pause/resume) — corroborated. Zero matches for "Pause Agent"/"Resume Agent" in any template under `server/app/templates/`. Daemon side at `scripts/background_agent.py:892-896` HAS `_handle_pause_agent()` + `_handle_resume_agent()`. UI is the only missing piece.
- Gap #5 (Stripe Connect) — corroborated by `templates/user/settings.html:125` `<button disabled title="Stripe Connect onboarding — coming soon">`.

### Retracted (false alarm — was not actually a gap)

**Gap #8 was withdrawn after re-verification.** Initial flag: AI matching service had no admin trigger UI and no worker cron. Re-check: matching is **pull-based** via `routers/campaigns.py:26 → services/matching.py:490 get_matched_campaigns()`. When a user's daemon polls the matched-campaigns endpoint, the server runs matching for THAT user inline and creates `CampaignAssignment` rows (`services/matching.py:589`) with `status='pending_invitation'`. Migration #66 AC22's "wait for next worker cron OR pull" — the pull path is operative. **No fix needed.**

### NEW Gap #7 — Windows installer icon.ico missing

| Field | Value |
|---|---|
| **Source** | `migration-stealth-and-packaging.md` line 85 |
| **Reality** | `scripts/build/installer/ICON_PLACEHOLDER.md` exists in place of `icon.ico` |
| **Impact** | Inno Setup build fails or installer ships without icon. Hard-blocks Task #68 closure. |
| **Severity** | LAUNCH BLOCKER (downstream of #68 partial) |
| **Filed as** | **Task #77** — multi-size .ico (16/32/48/64/128/256 px). User reviews final art. ~0.5–1 day. |

### NEW Gap #9 + #10 — Dashboard agent visibility (folded into Task #76)

Gap #9: `/user/dashboard` shows no live `agent_status` (last_seen, platform_health JSON). User can't tell if their daemon is alive — daemon dies silently.

Gap #10: `/user/dashboard` shows no "drafts ready" count — only links out to `localhost:5222/drafts`, forcing a context switch to know if drafts are pending review.

Both folded into **Task #76** per user decision (no defer post-launch). Task #76 now covers pause/resume button + agent_status badge + per-platform health badges + drafts-ready count widget — coherent agent-control surface, ~1–1.5 days.

### NEW Gap #11 — EULA placeholder text

| Field | Value |
|---|---|
| **Source** | `migration-stealth-and-packaging.md` line 84 ("placeholder EULA text (replace with real text before launch)") |
| **Reality** | `scripts/build/installer/eula.rtf` is placeholder content |
| **Impact** | Installer ships without legal protection. Cannot ship to public users. |
| **Severity** | LAUNCH BLOCKER (legal) |
| **Filed as** | **Task #79** — I draft from existing /terms + /privacy + standard installer EULA boilerplate. User reviews legal accuracy. ~0.5 day. |

### NEW Gap #12 — `/admin/financial` missing 2 manual cron buttons (third-pass audit)

Surfaced when user asked for a final admin-actions audit pass.

| Field | Value |
|---|---|
| **Source** | Migration #66 AC28 ("admin financial actions: run-billing, run-payout-processing, run-earning-promotion all functional") |
| **Reality** | Server routes EXIST at `routers/admin/financial.py:207` (`run-earning-promotion`) and `:238` (`run-payout-processing`). `templates/admin/financial.html` has NO buttons for them. |
| **Impact** | When ARQ worker has a hiccup, admins can't manually unstick a payout or promote pending earnings without curl. Bad incident-response posture for launch. |
| **Severity** | OPERATIONAL LAUNCH BLOCKER |
| **Filed as** | **Task #80** — 2 HTMX `<form hx-post>` blocks added to financial.html. Routes already work + audit logging in place. ~0.5 day. |

### Confirmed not-gaps (no follow-up needed)

| Item | Notes |
|---|---|
| Migration #66 AC1–AC34 | All 30 verifiable ACs have code backing per per-AC trace by Explore agent. AC5 wizard uses Alpine `x-show` instead of HTMX `hx-post per step` — functionally equivalent (no reload), spec drift only. |
| Tray menu | Has 7+ items including Pause/Resume Agent at `tray.py:176`. Downgrades urgency of Gap #4 (web UI still missing, but local fallback exists for power users). |
| BYOK (#70) | All deliverables present: model, migration, service, encryption, settings UI, quality_gate + wizard integration, 15 tests passing. |
| All product feature buckets | Money Loop, AI Brain (matching pull-based ✓, content agent preserved verbatim, quality gate wired at activation), Product Features (invitation UX, admin payout actions, repost campaigns), Business Launch (legal pages live), all present. |
| Patchright migration | Zero `from playwright` matches in `scripts/`. All 22 daemon files swapped. |
| `scripts/utils/draft_sync.py` | Spec'd as new module; sync logic was instead split between `background_agent.py:1019 sync_unsynced_drafts()` and `local_server.py:130 _sync_draft_to_server()`. Functional, structural drift only. Not a gap. |
| Draft uploads timing | Spec'd as immediate; actual is async every 30s. Functional, not a blocker. |
| Stripe via Stock Buddy sandbox | Sandbox account `acct_1TCGfuABBUrjm7YF` configured. Per user decision, ship demo for launch. Real keys MUST swap pre-public-launch. |

---

## Final triage table

| Gap | Decision | Task | Severity |
|---|---|---|---|
| 1. Web onboarding flow | DO | **#75** | LAUNCH BLOCKER |
| 2. CLI scripts/onboarding.py | DROP — remove from CLAUDE.md | (cleanup, no task) | — |
| 3. local_server.py:177 redirect | covered by #75 | (subset of #75) | LAUNCH BLOCKER |
| 4. Pause/Resume agent UI | DO | **#76** | LAUNCH BLOCKER |
| 5. Stripe Connect Express | demo for launch, real pre-launch | **#19** (updated) | LAUNCH BLOCKER |
| 6. Nuitka installer | ship for launch | **#68** (close via #77 + #79) | LAUNCH BLOCKER |
| 7. icon.ico | proper icon | **#77** | LAUNCH BLOCKER |
| 8. matching admin trigger | NOT-A-GAP (pull-based works) | — | — |
| 9. dashboard agent health | fold into #76 | **#76** | LAUNCH BLOCKER |
| 10. drafts-ready count | fold into #76 | **#76** | LAUNCH BLOCKER |
| 11. EULA real text | I draft from /terms | **#79** | LAUNCH BLOCKER |
| 12. admin financial buttons | DO | **#80** | OPERATIONAL LAUNCH BLOCKER |

**Total launch-blocker tasks: 6** (5 new + 1 existing #19 update). Estimated implementation effort: ~6–8 days sequential, or ~3–4 days parallelized via amplifier-coder + my own work.

---

## Pre-launch checklist (must complete before opening to public users)

- [ ] **#75 web onboarding** — register page + step2/3/4 + auth callback wiring
- [ ] **#76 agent control + dashboard visibility** — pause/resume + agent_status + drafts-ready count
- [ ] **#77 installer icon** — multi-size .ico in scripts/build/installer/
- [ ] **#79 installer EULA** — real legal text in scripts/build/installer/eula.rtf
- [ ] **#80 admin financial buttons** — UI for run-earning-promotion + run-payout-processing
- [ ] **#19 Stripe Connect Express** — onboarding UI shipped (demo keys OK for launch); **CRITICAL** before opening to public: real Stripe Connect live keys must replace sandbox `acct_1TCGfuABBUrjm7YF`. Update `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` in VPS systemd unit. Test live-mode end-to-end with a $1 transfer.
- [ ] **#68 packaging closure** — Nuitka build verified, GHA release tag pushed (e.g., v1.0.0), installers attached to GitHub Release, fresh-machine install test passed
- [ ] **`/uat-task 74.1` re-run** — full user app sweep after #75 + #76 land
- [ ] **`/uat-task 74.2`** — company dashboard sweep
- [ ] **`/uat-task 74.3`** — admin dashboard sweep (will exercise #80 buttons)

---

## Documentation actions taken alongside this audit

- **Task #19 description updated** in `.taskmaster/tasks/tasks.json` — calls out demo-keys-for-launch + real-keys-required-pre-launch
- **CLAUDE.md** — `python scripts/onboarding.py` line removed from Commands section (gap #2 decision)
- **`server/.env.example`** — banner added near `STRIPE_SECRET_KEY` warning about demo→live swap before public launch
- **`docs/STATUS.md`** — task counts bumped, "currently in flight" updated to point at #75/#76 first
- **5 new spec files** authored under `docs/specs/` (onboarding.md, agent-control.md, installer-assets.md, admin-actions.md, plus update to batch-4-business-launch.md) — see Step 4 of plan
