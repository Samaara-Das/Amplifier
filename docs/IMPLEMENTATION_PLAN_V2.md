# Amplifier v2 Implementation Plan

**Date**: 2026-03-24
**Scope**: Product Spec v2 — full gap analysis + phased implementation plan

---

## Section 1: Gap Analysis

### 1.1 User App — Onboarding

| Feature | Status | Notes |
|---------|--------|-------|
| Register/Login (email+password) | **EXISTS** | `scripts/onboarding.py` step_auth() + `server/app/routers/auth.py` |
| Connect Platforms (browser login) | **EXISTS** | `scripts/onboarding.py` step_platforms() + `scripts/login_setup.py` |
| Profile Scraping (follower count, bio, posts, engagement) | **NEW (L)** | Currently self-reported via CLI prompts in onboarding.py. Need Playwright scrapers per platform. |
| AI Niche Classification | **NEW (M)** | Currently manual checkbox selection. Need AI to classify from scraped content. |
| Niche Confirmation UI | **NEW (S)** | Need GUI multi-select with AI-suggested defaults. Currently CLI text input. |
| Audience Region Selection | **EXISTS** | `scripts/onboarding.py` step_profile(). CLI-only, needs GUI. |
| Operating Mode Selection | **EXISTS** | `scripts/onboarding.py` step_mode(). CLI-only, needs GUI. |
| API Key Setup | **MODIFY** | Spec says "Amplifier's own API keys (bundled)". Current onboarding asks user for Gemini key. Remove user-facing key step; bundle keys in app. |
| Profile Summary (done screen) | **EXISTS** | `scripts/onboarding.py` step_verify(). CLI-only, needs GUI. |

### 1.2 User App — Home/Dashboard

| Feature | Status | Notes |
|---------|--------|-------|
| Active Campaigns count | **MODIFY** | `scripts/campaign_dashboard.py` has Campaigns tab but not a home dashboard with summary cards. |
| Pending Invitations count | **NEW (M)** | No invitation system exists. Campaigns are auto-assigned in `matching.py`. |
| Posts Queued count | **MODIFY** | Local DB tracks posts but no "queued/approved" status. |
| Earnings Balance | **EXISTS** | Server tracks `earnings_balance` on User model. Dashboard shows it. |
| Platform Health indicators | **NEW (M)** | No session health checking exists. |
| Recent Activity feed | **NEW (S)** | No activity log exists locally or server-side. |

### 1.3 User App — Campaigns Tab

| Feature | Status | Notes |
|---------|--------|-------|
| Campaign Invitations (accept/reject) | **NEW (L)** | Current flow: `matching.py` auto-assigns. Need invitation system with accept/reject + 3-day expiry. Major change to matching + assignment flow. |
| Max 5 active campaigns limit | **NEW (S)** | No limit enforced server-side or client-side. |
| Active campaigns with per-platform status | **MODIFY** | Dashboard shows campaigns but status granularity is basic (assigned/content_generated/posted). |
| Completed campaigns with final metrics | **MODIFY** | Earnings tab exists but no "completed campaigns" archive view. |
| 3-day invitation expiry | **NEW (S)** | Server-side: add `invited_at` + expiry check. Client-side: display countdown. |

### 1.4 User App — Posts Tab

| Feature | Status | Notes |
|---------|--------|-------|
| Pending Review (per-platform preview) | **MODIFY** | Dashboard has a Posts tab but no per-platform editing or preview. |
| Edit per platform independently | **NEW (M)** | No per-platform editing. Content is generated as a batch. |
| Regenerate per platform | **NEW (M)** | No single-platform regeneration. |
| Image preview + regenerate | **MODIFY** | Image generation exists (`image_generator.py`) but no preview/regen UI. |
| Approve all / individual | **NEW (S)** | No approval flow. full_auto posts immediately; semi_auto has basic review. |
| Scheduled posts view | **NEW (M)** | No scheduling engine. Posts happen immediately on generation. |
| Posted with URLs + metrics | **EXISTS** | Local DB tracks post URLs + metrics. Dashboard shows them. |
| Failed posts with retry | **MODIFY** | Failures logged but no retry mechanism in UI. |

### 1.5 User App — Earnings Tab

| Feature | Status | Notes |
|---------|--------|-------|
| Balance + Total Earned | **EXISTS** | Server `User.earnings_balance` + `User.total_earned`. API at `/api/users/me/earnings`. |
| Pending earnings | **MODIFY** | API returns `pending: 0.0` with TODO. Need to calculate from unbilled metrics. |
| Per-Campaign Breakdown | **MODIFY** | API returns `per_campaign: []` with TODO. Need to aggregate from Payout records. |
| Per-Platform Breakdown | **NEW (S)** | Not tracked. Need to aggregate from Post + Payout by platform. |
| Payout History | **MODIFY** | Payout model exists but no user-facing endpoint to list history. |
| Withdraw Button ($10 min) | **MODIFY** | `payments.py` has skeleton. Need user-triggered endpoint + UI. |

### 1.6 User App — Settings Tab

| Feature | Status | Notes |
|---------|--------|-------|
| Operating Mode switch | **EXISTS** | Server API `PATCH /api/users/me` supports mode change. |
| Connected Platforms status | **MODIFY** | Platforms stored in JSON. No health status or re-auth button. |
| Profile (scraped data summary) | **NEW (M)** | No scraped data display. Currently shows self-reported data. |
| Posting Schedule view/adjust | **NEW (M)** | No scheduling engine exists. |
| Notifications toggles | **NEW (S)** | No notification system. |
| Account (change password, delete) | **NEW (S)** | No password change or account deletion endpoint. |

### 1.7 User App — Statistics

| Feature | Status | Notes |
|---------|--------|-------|
| Trust score display | **MODIFY** | Trust score exists on server. Not displayed to user in dashboard. |
| Avg engagement rate per platform | **NEW (S)** | Need to calculate from local metrics. |
| Campaign completion rate | **NEW (S)** | Need to calculate from local campaigns. |
| Earnings trend (30-day chart) | **NEW (M)** | Need charting library + historical data aggregation. |
| Post success rate per platform | **NEW (S)** | Data exists in local_post table. Need aggregation + display. |

### 1.8 User App — Background Agent

| Feature | Status | Notes |
|---------|--------|-------|
| Posting at scheduled times | **MODIFY** | `campaign_runner.py` posts immediately. Need scheduling engine. |
| Metric Scraping at T+1h/6h/24h/72h | **EXISTS** | `metric_scraper.py` does tier-based scraping. Works. |
| Session Health checking | **NEW (M)** | No session validity checks exist. |
| Campaign Polling (10 min) | **EXISTS** | `campaign_runner.py` polls every 10 min. |
| Post Failure Alerts | **NEW (S)** | Failures logged but no user notification. |
| Profile Refresh (weekly) | **MODIFY** | `profile_node.py` has weekly cache for agent pipeline. Need general profile refresh. |
| System Tray icon | **NEW (M)** | No system tray. Current app is CLI + Flask web dashboard. |

### 1.9 Post Scheduling

| Feature | Status | Notes |
|---------|--------|-------|
| Region-based optimal times | **NEW (M)** | Current posting uses fixed IST slots for personal brand. No region-based logic. |
| 30-min minimum spacing | **NEW (S)** | No spacing logic. Posts happen back-to-back with 30-90s delay. |
| Platform variety (no same-platform back-to-back) | **NEW (S)** | Platforms are shuffled randomly but not scheduled. |
| Daily campaign post limit | **NEW (S)** | No limit enforced. |
| Randomized times within windows | **NEW (S)** | No jitter. |

### 1.10 Company Dashboard — Campaign Creation (AI Wizard)

| Feature | Status | Notes |
|---------|--------|-------|
| Step 1: Campaign Basics (product, goal, URLs) | **MODIFY** | `campaign_create.html` exists but is a simple form. No AI wizard, no URL scraping. |
| URL scraping for brief enrichment | **NEW (M)** | Webcrawler exists (`crawl.py`) but not wired into server. |
| Step 2: Target Audience (niches, regions, platforms, min followers) | **MODIFY** | `CampaignCreate` schema has `targeting` field. Form has basic fields. No AI suggestions. |
| Step 3: Content Direction (tone, must-include, avoid) | **MODIFY** | `content_guidance` field exists. Form has text area. No AI conversation. |
| Step 4: Budget & Payout with AI suggestions | **MODIFY** | Budget + payout_rules exist. No AI-suggested amounts or reach estimation. |
| Step 5: Review & Edit with full preview | **NEW (M)** | No generated preview. Company fills form manually. |
| Step 6: Reach Estimation | **NEW (M)** | No reach estimation endpoint. Need to count matching users + estimate impressions. |

### 1.11 Company Dashboard — Campaign Management

| Feature | Status | Notes |
|---------|--------|-------|
| Campaign List with status badges | **EXISTS** | `company/campaigns.html` shows list with status. |
| Quick stats (users, posts, impressions) | **MODIFY** | Campaign detail page exists but limited stats. |
| Pause/Resume/Cancel actions | **EXISTS** | `update_campaign` endpoint supports status transitions. |
| Campaign Cloning | **NEW (S)** | No clone endpoint. |
| Filter by status | **MODIFY** | List exists but no client-side filtering. |
| Sort by date/budget/performance | **NEW (S)** | No sorting in list. |

### 1.12 Company Dashboard — Campaign Detail

| Feature | Status | Notes |
|---------|--------|-------|
| Overview stats (impressions, engagement, spend) | **MODIFY** | `campaign_detail.html` exists but with limited aggregation. |
| Budget Progress Bar | **NEW (S)** | Budget data exists. Need visual component. |
| Invitation Status (accepted/rejected/expired/pending) | **NEW (M)** | No invitation tracking. Currently auto-assigned. |
| Per-User Performance Table | **NEW (M)** | Assignment data exists but no per-user metrics aggregation endpoint. |
| Per-Platform Breakdown | **NEW (S)** | Data exists across Post + Metric tables. Need aggregation. |
| Timeline view | **NEW (S)** | Post timestamps exist. Need timeline visualization. |
| Edit active campaign | **MODIFY** | `CampaignUpdate` schema is limited. Need budget increase, payout rate changes. |
| Edit propagation to users | **NEW (M)** | No mechanism for flagging approved-but-unposted content when campaign changes. |

### 1.13 Company Dashboard — Budget Management

| Feature | Status | Notes |
|---------|--------|-------|
| Company Balance top-up (Stripe) | **EXISTS** | `payments.py` has `create_company_checkout()`. Skeleton only (Stripe optional). |
| Minimum $50 campaign budget | **NEW (S)** | No validation. Add to `CampaignCreate`. |
| Budget alert at 80% | **NEW (S)** | No alert system. |
| Budget exhaustion behavior (auto-pause/auto-complete) | **MODIFY** | `billing.py` auto-completes at <$1. No company choice between pause vs complete. |
| Budget top-up for active campaigns | **MODIFY** | `CampaignUpdate` doesn't allow budget changes. Need budget increase endpoint. |

### 1.14 Company Dashboard — Statistics

| Feature | Status | Notes |
|---------|--------|-------|
| Total campaigns, spend, reach | **MODIFY** | Admin stats exist but no company-specific stats endpoint. |
| Average cost per impression/engagement | **NEW (S)** | Need aggregation from Metric + Payout. |
| Best performing campaign/platform | **NEW (S)** | Need ranking logic. |
| User retention across campaigns | **NEW (M)** | Need cross-campaign user tracking. |
| Spend trend chart | **NEW (M)** | Need historical data + chart rendering. |

### 1.15 Reporting & Export

| Feature | Status | Notes |
|---------|--------|-------|
| CSV export | **NEW (M)** | No export functionality. |
| PDF export | **NEW (M)** | Needs PDF generation library. |
| Date range filtering | **NEW (S)** | Need query parameters for date filtering. |

### 1.16 Prohibited Content Screening

| Feature | Status | Notes |
|---------|--------|-------|
| Keyword screening at creation | **NEW (M)** | No content screening. Need banned keyword list + screening logic. |
| Flagged campaigns require admin review | **NEW (S)** | Need "flagged" status + admin review queue. |

### 1.17 Matching Algorithm Updates

| Feature | Status | Notes |
|---------|--------|-------|
| Use scraped data (verified followers, engagement) | **MODIFY** | `matching.py` uses self-reported `follower_counts` and `niche_tags`. Need to use scraped verified data. |
| AI scoring (brief + profile relevance) | **NEW (M)** | Current scoring is rule-based (niche overlap + trust). Need AI call. |
| Engagement rate bonus | **NEW (S)** | No engagement rate in scoring. Data needs to come from scraping. |
| Invitation flow (top N get invites, not auto-assigned) | **NEW (L)** | Complete rewrite of `get_matched_campaigns()`. Currently auto-assigns on poll. |
| Re-offer expired/rejected slots | **NEW (M)** | No re-offering logic. |

### 1.18 Admin Dashboard

| Feature | Status | Notes |
|---------|--------|-------|
| Campaign Review Queue (flagged) | **NEW (M)** | No flagged campaign concept. Need admin review page. |
| Platform Stats (aggregate) | **NEW (S)** | Need aggregation endpoint. |
| Existing: users, fraud, payouts, overview | **EXISTS** | Admin dashboard has 6 pages. Mostly sufficient. |

### 1.19 Billing Changes

| Feature | Status | Notes |
|---------|--------|-------|
| Remove payout multiplier | **MODIFY** | `billing.py` uses `assignment.payout_multiplier`. Spec says earnings depend purely on engagement, not mode. Need to remove multiplier from formula. |
| Earnings = metrics * rates * 80% | **MODIFY** | Formula is correct minus the multiplier. |

### 1.20 Theme Change

| Feature | Status | Notes |
|---------|--------|-------|
| Blue (#2563eb) + white theme | **MODIFY** | Current theme is emerald green (#10b981). All templates use green. Need global CSS change across all 12+ templates. |

### 1.21 Tauri Desktop App

| Feature | Status | Notes |
|---------|--------|-------|
| Tauri project (Rust + WebView) | **NEW (L)** | No Tauri setup. Currently Python Flask for user dashboard. |
| Python sidecar for Playwright | **NEW (L)** | Need to bundle Python runtime + Playwright as sidecar process. |
| System tray + background agent | **NEW (M)** | No system tray. Current app is foreground Flask process. |

---

## Section 2: Implementation Phases

### Phase 1: Server Foundation Updates
**Goal**: Fix the data model and core flows before building any UI.
**Dependencies**: None.

**What gets built**:
1. Campaign invitation system (replace auto-assign with invite + accept/reject)
2. `CampaignAssignment` status values updated: `invited` | `accepted` | `rejected` | `expired` | `content_generated` | `posted` | `metrics_collected` | `paid` | `skipped`
3. `invited_at` + `expires_at` columns on CampaignAssignment
4. Max 5 active campaigns enforcement (server-side check)
5. Invitation expiry cron/check (expire after 3 days)
6. Remove `payout_multiplier` from CampaignAssignment + billing formula
7. Remove `content_mode` from CampaignAssignment (or make informational only)
8. Campaign `budget_exhaustion_behavior` field (`auto_pause` | `auto_complete`)
9. Campaign minimum budget validation ($50)
10. Budget increase endpoint for active campaigns
11. Campaign clone endpoint
12. Add `target_regions` to Targeting schema (already partially in `_calculate_match_score`)
13. User profile: add `engagement_rates` JSON field, `bio_text`, `display_name`, `profile_picture_url`, `scraped_at` timestamp
14. Content screening service (keyword-based)
15. Campaign `flagged` status + admin review flow
16. Payout history endpoint for users
17. Pending earnings calculation
18. Per-campaign and per-platform earnings aggregation endpoints
19. Company stats endpoint
20. Reach estimation endpoint
21. Campaign edit propagation: `updated_since_approved` flag on assignments

**Files modified**:
- `server/app/models/assignment.py` — Remove `payout_multiplier`, `content_mode`. Add `invited_at`, `expires_at`. Change status enum.
- `server/app/models/campaign.py` — Add `budget_exhaustion_behavior`, `flagged_reason`.
- `server/app/models/user.py` — Add `engagement_rates`, `bio_text`, `display_name`, `profile_picture_url`, `scraped_at`.
- `server/app/schemas/campaign.py` — Update `CampaignBrief` (remove `payout_multiplier`), add `CampaignClone`, update `CampaignUpdate` (budget increase, payout rate changes), add `Targeting.target_regions`.
- `server/app/schemas/user.py` — Add scraped profile fields.
- `server/app/services/matching.py` — Rewrite: separate matching (find users) from assignment (create invitations). Add `send_invitations()` and `expire_invitations()`.
- `server/app/services/billing.py` — Remove multiplier from `calculate_post_earnings()`. Simplify formula.
- `server/app/routers/campaigns.py` — Add clone, accept/reject invitation, budget increase, reach estimation endpoints. Modify `get_my_campaigns` to return invitations instead of auto-assigning.
- `server/app/routers/users.py` — Add payout history, enhanced earnings breakdown endpoints.
- `server/app/routers/admin.py` — Add flagged campaign review queue endpoint.

**Files created**:
- `server/app/services/screening.py` — Prohibited content keyword screening.
- `server/app/services/reach_estimation.py` — Count matching users + estimate impressions.

**Estimated complexity**: ~15 files touched, 2 new. 3-4 days.

---

### Phase 2: Profile Scraping + AI Niche Detection
**Goal**: Replace self-reported user data with verified scraped data.
**Dependencies**: Phase 1 (user model has new profile fields).

**What gets built**:
1. Per-platform profile scraper (X, LinkedIn, Facebook, Reddit)
   - Navigate to logged-in user's profile page using existing Playwright sessions
   - Extract: follower count, following count, bio, display name, profile picture URL
   - Extract: last 30-60 recent posts with engagement metrics (likes, comments, shares)
   - Calculate engagement rate per platform
2. AI niche classification
   - Feed scraped bio + recent post text to Gemini
   - Return detected niches from predefined list
3. Local storage of scraped data
4. Server sync of scraped profile data (follower counts, niches, engagement rates, bio)
5. Weekly background refresh (integrate with background agent loop)
6. Manual refresh trigger

**Files modified**:
- `scripts/campaign_runner.py` — Add weekly profile refresh to poll loop.
- `scripts/utils/local_db.py` — Add `local_profile` table for scraped data.
- `scripts/utils/server_client.py` — Add `sync_profile_data()` function.

**Files created**:
- `scripts/utils/profile_scraper.py` — Per-platform Playwright scrapers (X, LinkedIn, Facebook, Reddit). Extracts follower count, bio, recent posts, engagement.
- `scripts/utils/niche_classifier.py` — AI niche detection from scraped content. Uses Gemini API.

**Estimated complexity**: ~5 files touched, 2 new. 3-4 days. Profile scraping is brittle (selectors break) but we have existing platform knowledge from `post.py`.

---

### Phase 3: AI-Powered Server Features
**Goal**: AI campaign wizard, AI matching, content quality, screening.
**Dependencies**: Phase 1 (server schema), Phase 2 (scraped profile data available).

**What gets built**:
1. AI campaign creation wizard (server-side)
   - URL scraping via webcrawler (reuse `crawl.py` logic or call it as subprocess)
   - AI generates: campaign title, brief, content guidance, suggested tone from scraped URL data
   - AI suggests budget + payout rates based on targeting scope + matching user count
   - Reach estimation: count matching users, estimate impressions from their engagement rates
2. AI matching scoring
   - Campaign brief + user profile (scraped posts, bio, niches) fed to Gemini
   - Returns relevance score 0-100
   - Replaces/augments rule-based `_calculate_match_score`
3. Content quality: brief adherence check
   - Compare generated content against campaign brief + content_guidance
   - Score adherence as part of quality pipeline
4. Prohibited content screening (server-side)
   - Run on campaign create/update
   - Flag for admin review if triggered

**Files modified**:
- `server/app/routers/company_pages.py` — Add AI wizard endpoints (step-by-step API).
- `server/app/routers/campaigns.py` — Wire screening into create/update.
- `server/app/services/matching.py` — Add AI scoring call alongside rule-based scoring.
- `scripts/agents/quality_node.py` — Add brief adherence check to quality scoring.

**Files created**:
- `server/app/services/ai_wizard.py` — URL scraping, brief generation, budget suggestion, reach estimation AI logic.
- `server/app/services/ai_matching.py` — AI relevance scoring (campaign brief vs user profile).

**Estimated complexity**: ~6 files touched, 2 new. 3-4 days. AI API costs are a concern for matching (called per user per campaign). Can cache and batch.

---

### Phase 4: User App Rebuild (Tauri Desktop)
**Goal**: Replace CLI onboarding + Flask dashboard with a native Tauri desktop app.
**Dependencies**: Phase 1 (invitation API), Phase 2 (profile scraping), Phase 3 (AI features available).

**What gets built**:

**4A: Tauri Project Setup (L)**
- Initialize Tauri project (Rust backend + WebView frontend)
- Frontend: Vanilla HTML/CSS/JS or lightweight framework (Svelte recommended for Tauri)
- Python sidecar: bundle Python + Playwright as a subprocess that the Tauri app spawns
- IPC bridge: Tauri commands call Python sidecar for Playwright operations (posting, scraping, login)
- System tray icon with status indicator

**4B: Onboarding Flow (M)**
- Register/Login screen
- Platform connect: Tauri opens Playwright browser via sidecar, user logs in, session saved
- Profile scraping: after connect, sidecar scrapes profile, shows results
- Niche confirmation: multi-select checkboxes with AI-detected defaults
- Audience region + operating mode selection
- Done screen with profile summary

**4C: Dashboard Screens (L)**
- Home: summary cards (active campaigns, pending invitations, posts queued, earnings, platform health)
- Campaigns tab: invitations (accept/reject), active campaigns, completed campaigns
- Posts tab: pending review (per-platform preview + edit + regenerate), scheduled, posted, failed
- Earnings tab: balance, total, pending, per-campaign breakdown, per-platform breakdown, payout history, withdraw
- Settings tab: mode, platforms, profile, schedule, notifications, account
- Statistics: trust score, engagement rates, completion rate, trends

**4D: Post Scheduling Engine (M)**
- Region-based optimal time calculation
- 30-min minimum spacing
- Platform variety enforcement
- Daily campaign post limit
- Randomized jitter within posting windows
- Schedule display in Posts tab

**4E: Background Agent (M)**
- System tray process (runs when app is closed)
- Posting at scheduled times via Playwright sidecar
- Metric scraping at T+1h/6h/24h/72h
- Campaign polling every 10 min
- Session health checks (periodic cookie validation)
- Post failure notifications (native OS notifications via Tauri)
- Weekly profile refresh

**Files created**:
- `tauri/` — Entire Tauri project directory
  - `tauri/src-tauri/` — Rust backend (Tauri commands, sidecar management, system tray)
  - `tauri/src/` — Frontend (HTML/CSS/JS or Svelte components)
  - `tauri/src-tauri/Cargo.toml` — Rust dependencies
  - `tauri/package.json` — Frontend dependencies
- `scripts/sidecar/` — Python sidecar entry points
  - `scripts/sidecar/main.py` — Sidecar IPC server (receives commands from Tauri, executes Playwright operations)
  - `scripts/sidecar/scheduler.py` — Post scheduling engine (region-based, spacing rules)
  - `scripts/sidecar/health.py` — Session health checker (per-platform cookie validation)

**Files modified**:
- `scripts/campaign_runner.py` — Refactor to be callable from sidecar (not just standalone script).
- `scripts/utils/metric_scraper.py` — Refactor for sidecar integration.
- `scripts/post.py` — Refactor platform functions to be importable from sidecar without full module load.

**Estimated complexity**: ~20+ new files, 3-5 modified. 2-3 weeks. This is the biggest phase. The Python sidecar adds significant complexity.

**Shortcut option**: Skip Tauri initially. Rebuild the Flask dashboard with all the new features (invitations, scheduling, per-platform editing) and add a system tray icon via `pystray`. This gets 80% of the UX with 20% of the effort. Tauri becomes a Phase 7 polish item.

---

### Phase 5: Company Dashboard Rebuild
**Goal**: AI wizard, improved campaign detail, cloning, budget management, export.
**Dependencies**: Phase 1 (server APIs), Phase 3 (AI wizard backend).

**What gets built**:
1. AI Campaign Creation Wizard (6-step UI)
   - Step-by-step flow with AI conversation
   - URL input + auto-scraping results preview
   - Auto-generated brief/guidance/tone
   - Budget suggestions with reach estimation
   - Full preview before activation
2. Campaign Detail page improvements
   - Budget progress bar
   - Invitation status (invited/accepted/rejected/expired)
   - Per-user performance table with post URLs + metrics
   - Per-platform breakdown
   - Timeline visualization
3. Campaign Cloning button
4. Budget Management improvements
   - Budget top-up for active campaigns
   - Budget exhaustion behavior selection (auto-pause / auto-complete)
   - Budget alert indicator at 80%
5. Company Statistics page
6. Reporting/Export (CSV download, PDF stretch goal)
7. Blue/white theme across all company templates

**Files modified**:
- `server/app/templates/company/campaign_create.html` — Rewrite as multi-step AI wizard.
- `server/app/templates/company/campaign_detail.html` — Add per-user table, budget bar, invitation status.
- `server/app/templates/company/campaigns.html` — Add filtering, sorting, clone button.
- `server/app/templates/company/billing.html` — Budget top-up improvements.
- `server/app/templates/company/settings.html` — Company stats.
- `server/app/templates/base.html` — Blue/white theme.
- `server/app/routers/company_pages.py` — Wire new endpoints, stats, export.

**Files created**:
- `server/app/templates/company/statistics.html` — Company stats page.
- `server/app/routers/export.py` — CSV/PDF export endpoints.

**Estimated complexity**: ~8 files modified, 2 new. 1-2 weeks.

---

### Phase 6: Admin Updates + Theme
**Goal**: Campaign review queue, platform stats, consistent theme.
**Dependencies**: Phase 1 (flagged campaigns), Phase 5 (theme established).

**What gets built**:
1. Campaign review queue page (flagged campaigns from screening)
2. Admin approve/reject flagged campaign
3. Platform-level aggregate stats
4. Blue/white theme applied to admin templates

**Files modified**:
- `server/app/routers/admin_pages.py` — Add campaign review page.
- `server/app/routers/admin.py` — Add approve/reject flagged campaign endpoint.
- `server/app/templates/admin/campaigns.html` — Add review queue section.
- `server/app/templates/admin/overview.html` — Add platform stats.
- `server/app/templates/admin/login.html` — Blue theme.
- `server/app/templates/admin/users.html` — Blue theme.
- `server/app/templates/admin/fraud.html` — Blue theme.
- `server/app/templates/admin/payouts.html` — Blue theme.

**Estimated complexity**: ~8 files modified. 2-3 days.

---

### Phase 7: Integration & Polish
**Goal**: End-to-end testing, bug fixes, consistency.
**Dependencies**: All previous phases.

**What gets built**:
1. End-to-end flow testing: company creates campaign (AI wizard) -> screening -> activation -> matching -> invitations sent -> user accepts -> content generated -> user reviews/edits -> approved -> scheduled -> posted -> metrics scraped -> billing -> earnings -> withdrawal
2. Campaign edit propagation verification (already-posted vs approved-unposted vs not-generated)
3. Session health + re-auth flow testing per platform
4. Budget exhaustion behavior testing (auto-pause + resume, auto-complete)
5. Invitation expiry testing (3-day timeout + re-offer to other users)
6. Theme consistency audit across all 3 apps
7. Bug fixes from integration testing
8. Performance: batch AI matching (avoid per-user API calls on large user bases)

**Estimated complexity**: 1 week.

---

## Section 3: Files to Create

### Server
| File | Description |
|------|-------------|
| `server/app/services/screening.py` | Prohibited content keyword screening for campaigns |
| `server/app/services/reach_estimation.py` | Count matching users + estimate impressions for reach estimation |
| `server/app/services/ai_wizard.py` | AI campaign wizard: URL scraping, brief generation, budget suggestions |
| `server/app/services/ai_matching.py` | AI relevance scoring for campaign-user matching |
| `server/app/routers/export.py` | CSV/PDF export endpoints for campaign reports |
| `server/app/templates/company/statistics.html` | Company statistics dashboard page |

### User App (Python/Sidecar)
| File | Description |
|------|-------------|
| `scripts/utils/profile_scraper.py` | Per-platform Playwright profile scrapers (followers, bio, posts, engagement) |
| `scripts/utils/niche_classifier.py` | AI niche classification from scraped content (Gemini) |
| `scripts/sidecar/main.py` | Python sidecar IPC server for Tauri (receives commands, runs Playwright) |
| `scripts/sidecar/scheduler.py` | Region-based post scheduling engine with spacing and variety rules |
| `scripts/sidecar/health.py` | Platform session health checker (cookie validation per platform) |

### Tauri App (if pursuing native desktop)
| File/Dir | Description |
|----------|-------------|
| `tauri/` | Tauri project root |
| `tauri/src-tauri/src/main.rs` | Rust entry point with Tauri commands and system tray |
| `tauri/src-tauri/Cargo.toml` | Rust dependencies |
| `tauri/src-tauri/tauri.conf.json` | Tauri configuration (window, permissions, sidecar) |
| `tauri/src/index.html` | Main app shell |
| `tauri/src/pages/` | Page components (onboarding, home, campaigns, posts, earnings, settings) |
| `tauri/src/lib/api.js` | API client for server communication |
| `tauri/src/lib/sidecar.js` | Sidecar IPC bridge (invoke Python commands) |
| `tauri/package.json` | Frontend dependencies |

---

## Section 4: Files to Modify

### Server Models
| File | Changes |
|------|---------|
| `server/app/models/assignment.py` | Remove `payout_multiplier`, `content_mode`. Add `invited_at`, `expires_at`, `updated_since_campaign_edit` flag. Update status enum to: invited/accepted/rejected/expired/content_generated/posted/metrics_collected/paid/skipped. |
| `server/app/models/campaign.py` | Add `budget_exhaustion_behavior` (String), `flagged_reason` (Text, nullable), `tone` (String, nullable). Add `flagged` to status options. |
| `server/app/models/user.py` | Add `engagement_rates` (JSON), `bio_text` (Text), `display_name` (String), `profile_picture_url` (Text), `scraped_at` (DateTime). |
| `server/app/models/company.py` | No changes needed for v2. |

### Server Schemas
| File | Changes |
|------|---------|
| `server/app/schemas/campaign.py` | Remove `payout_multiplier` from `CampaignBrief`. Add `target_regions` to `Targeting`. Add `budget_exhaustion_behavior` to `CampaignCreate`. Update `CampaignUpdate` to allow budget increase + payout rate changes. Add `CampaignClone` schema. Add `InvitationResponse` schema. |
| `server/app/schemas/user.py` | Add scraped fields to `UserProfileUpdate` and `UserProfileResponse`. |
| `server/app/schemas/metrics.py` | No changes needed. |

### Server Services
| File | Changes |
|------|---------|
| `server/app/services/matching.py` | Major rewrite. Split into: `find_matching_users()` (returns ranked user list), `create_invitations()` (creates invited assignments), `expire_invitations()` (marks expired). Remove auto-assignment from `get_matched_campaigns()`. Add engagement rate bonus to scoring. |
| `server/app/services/billing.py` | Remove `multiplier` from `calculate_post_earnings()`. Formula becomes: `earning = raw_earning * (1 - platform_cut)`. |
| `server/app/services/trust.py` | No major changes. May add campaign completion tracking. |
| `server/app/services/payments.py` | Add user-initiated withdrawal request endpoint logic. |
| `server/app/services/background_jobs.py` | Add invitation expiry job. |

### Server Routers
| File | Changes |
|------|---------|
| `server/app/routers/campaigns.py` | Add: clone endpoint, accept/reject invitation endpoints, budget increase endpoint, reach estimation endpoint. Modify `get_my_campaigns` to return invitations (not auto-assign). Add screening call on create/update. |
| `server/app/routers/users.py` | Add: payout history endpoint, enhanced earnings breakdown (per-campaign, per-platform), user statistics endpoint, password change endpoint, account deletion endpoint. |
| `server/app/routers/admin.py` | Add: flagged campaign review/approve/reject, platform aggregate stats. |
| `server/app/routers/company_pages.py` | Add AI wizard step endpoints, stats page, export endpoints. |
| `server/app/routers/admin_pages.py` | Add campaign review queue page. |

### Server Templates
| File | Changes |
|------|---------|
| `server/app/templates/base.html` | Change theme from emerald green (#10b981) to blue (#2563eb). |
| `server/app/templates/company/campaign_create.html` | Rewrite as multi-step AI wizard form. |
| `server/app/templates/company/campaign_detail.html` | Add budget bar, invitation status, per-user table, per-platform breakdown. |
| `server/app/templates/company/campaigns.html` | Add filtering, sorting, clone button, status badges. |
| `server/app/templates/company/billing.html` | Budget top-up improvements, budget exhaustion settings. |
| `server/app/templates/company/login.html` | Blue theme. |
| `server/app/templates/company/settings.html` | Company stats, blue theme. |
| `server/app/templates/admin/*.html` (all 6) | Blue theme, campaign review queue. |

### User App Scripts
| File | Changes |
|------|---------|
| `scripts/campaign_runner.py` | Add weekly profile refresh, integrate scheduling engine, refactor for sidecar callable. |
| `scripts/campaign_dashboard.py` | Major updates if keeping Flask approach: add invitation accept/reject, per-platform editing, scheduling view, statistics. (May be fully replaced by Tauri.) |
| `scripts/onboarding.py` | Replace CLI with GUI calls if Tauri, or improve Flask-based onboarding. |
| `scripts/post.py` | Refactor posting functions to be cleanly importable. Add scheduling-aware entry point. |
| `scripts/utils/local_db.py` | Add `local_profile` table, `local_schedule` table, `local_invitation` table. Update `local_campaign` status values. |
| `scripts/utils/server_client.py` | Add: `accept_invitation()`, `reject_invitation()`, `get_invitations()`, `sync_profile_data()`, `request_withdrawal()`, `get_payout_history()`. |
| `scripts/utils/content_generator.py` | No major changes (legacy fallback). |
| `scripts/utils/metric_scraper.py` | Minor refactor for sidecar integration. |
| `scripts/agents/quality_node.py` | Add brief adherence check to scoring. |

---

## Section 5: Files to Delete/Deprecate

| File | Action | Reason |
|------|--------|--------|
| `scripts/onboarding.py` | **Deprecate** | CLI onboarding replaced by Tauri GUI. Keep for dev/debugging but not shipped to users. |
| `scripts/generate_campaign.ps1` | **Delete** | Already unused ("preserved but unused"). Replaced by `content_generator.py` and agent pipeline. |
| `scripts/generate.ps1` | **Deprecate** | Personal brand generation via Claude CLI. Not part of campaign platform. Keep for personal use but not relevant to v2. |
| `scripts/review_dashboard.py` | **Deprecate** | Personal brand review dashboard. Replaced by campaign dashboard or Tauri app. Keep for personal use. |
| `scripts/setup_scheduler.ps1` | **Deprecate** | Windows Task Scheduler for personal posting slots. Campaign scheduling is handled by the new scheduling engine. |
| `scripts/utils/draft_manager.py` | **Deprecate** | Personal brand draft lifecycle manager. Not used by campaign flow. |
| `amplifier.spec` | **Delete** | PyInstaller build spec. Replaced by Tauri build. |
| `installer.iss` | **Delete** | Inno Setup installer. Replaced by Tauri installer. |
| `scripts/app_entry.py` | **Delete** | PyInstaller entry point. Replaced by Tauri. |

---

## Section 6: Risk & Open Questions

### Technical Risks

1. **Tauri + Python sidecar complexity (HIGH)**
   - Tauri is designed for Rust + WebView. Python sidecar requires spawning a subprocess, managing its lifecycle, and IPC.
   - Playwright needs a full Python environment (~500MB with chromium). Bundling this is non-trivial.
   - **Mitigation**: Consider the Flask dashboard shortcut (Phase 4 shortcut option). Ship faster with `pystray` for system tray + improved Flask app. Defer Tauri to a future version.

2. **Profile scraping reliability (MEDIUM)**
   - Platform selectors change frequently (Reddit already broke).
   - Some platforms aggressively detect scraping (X locked the account).
   - **Mitigation**: Scrape defensively (try/except per field), cache aggressively (weekly), fall back to self-reported data if scraping fails. Consider official APIs where available (X API for public profile data).

3. **AI API costs for matching (MEDIUM)**
   - AI scoring per user per campaign could be expensive at scale. If 100 users and 10 campaigns activate per day = 1000 AI calls/day.
   - **Mitigation**: Rule-based pre-filter to narrow candidates to ~20 before AI scoring. Cache AI scores for user-niche pairs. Use cheapest model (Gemini Flash).

4. **AI wizard URL scraping on Vercel (MEDIUM)**
   - Vercel serverless has execution time limits (10s default, 60s max on Pro). URL scraping + AI generation in a single request may timeout.
   - **Mitigation**: Make wizard steps async. Step 1 kicks off URL scraping as a background task, frontend polls for results. Or use Vercel's streaming responses.

5. **Invitation system migration (MEDIUM)**
   - Moving from auto-assign to invite-accept changes the fundamental user flow. Existing data (auto-assigned campaigns) needs migration.
   - **Mitigation**: Add `invited_at` with default value for existing records. Treat existing "assigned" status as equivalent to "accepted". New flow only applies to campaigns created after migration.

6. **Campaign edit propagation (LOW)**
   - Flagging approved-but-unposted content when a campaign changes is complex. User app needs to detect the flag on next poll.
   - **Mitigation**: Simple boolean flag `updated_since_campaign_edit` on assignment. User app checks on poll and shows "Campaign updated" banner. No forced content regeneration.

### Open Questions

1. **Tauri or Flask+pystray?**
   - Tauri gives a proper desktop app experience but adds 2-3 weeks of work and significant bundling complexity (Python + Playwright sidecar).
   - Flask + `pystray` gets 80% of the UX (web dashboard + system tray + background agent) with much less effort.
   - **Recommendation**: Start with Flask+pystray for v2. Build Tauri for v3 when the product is validated with real users.

2. **API keys bundled vs user-provided?**
   - Spec says "Amplifier's own API keys (bundled with the app)." This means all AI costs are borne by Amplifier.
   - At scale, this could be expensive. For MVP, this is fine (small user base).
   - Keys must be obfuscated in the binary (not plaintext in source).
   - **Decision needed**: What's the API key budget? When do we switch to server-side AI generation?

3. **AI matching: when to call?**
   - On campaign activation (batch all users) or on user poll (per-user)?
   - Batch on activation is better for consistency but slower for campaign activation.
   - **Recommendation**: Batch on activation. Run matching as a background task. Campaign goes to "matching" status briefly, then "active" when invitations are sent.

4. **How to handle X account locking?**
   - Playwright automation is detected by X. This blocks a core platform.
   - Options: official X API (costs $100/month for Basic), stealth browser (undetected-playwright), or drop X temporarily.
   - **Decision needed before Phase 4**.

5. **Real money flow timeline?**
   - Stripe integration is skeleton-only. When do we need real payments?
   - Product spec says "skeleton for now" for Stripe.
   - **Recommendation**: Keep skeleton through v2. Real Stripe integration is a separate project when first paying customer appears.

6. **Database migrations?**
   - Schema changes (Phase 1) affect production Supabase. Need migration strategy.
   - **Recommendation**: Use Alembic for migrations. Add `server/alembic/` setup. Run `alembic upgrade` on deploy.
   - Alternative: Since early stage with minimal data, can reset production DB if needed.

7. **Session health check mechanism?**
   - How to check if a platform session is valid without making a post?
   - Options: navigate to profile page and check for login redirect, check cookie expiry dates, make a lightweight API call.
   - **Recommendation**: Navigate to profile page, check for login wall/redirect. Simple and works for all platforms.

### Acceptable MVP Shortcuts

- **Skip PDF export** — CSV is sufficient for v2. PDF is a nice-to-have.
- **Skip spend/earnings trend charts** — Show numbers in tables. Charts can come later.
- **Skip notification toggles** — Always notify for failures and new campaigns. Fine-grained control later.
- **Skip user account deletion** — Manual process via admin for now.
- **Skip AI-generated campaign preview to users** — Show the raw brief/guidance. AI preview is polish.
- **Skip timeline visualization** — Show timestamped list instead of visual timeline.
- **Use Flask+pystray instead of Tauri** — Ship faster, validate product first.
- **Rule-based matching with AI as optional boost** — Don't block invitations on AI scoring. Use AI score as tiebreaker, not gatekeeper.
