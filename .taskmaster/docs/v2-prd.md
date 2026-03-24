# Amplifier v2 — Task PRD

## Context
Amplifier is being rebuilt from a CLI+Flask prototype into a polished Tauri desktop app (users) + web dashboards (companies, admin). See docs/PRODUCT_SPEC_V2.md for full product spec, docs/TECHNICAL_ARCHITECTURE_V2.md for architecture, docs/DATABASE_SCHEMA_V2.md for schema, docs/API_SPEC_V2.md for API, docs/IMPLEMENTATION_PLAN_V2.md for detailed gap analysis.

Each task follows TDD: write tests first, build feature, UAT via Chrome DevTools MCP, fix bugs.

---

## Phase 1: Server Foundation Updates

### Task: Database schema migration for v2
Modify server database models and run migrations on Supabase. Changes:
- CampaignAssignment: add invitation lifecycle states (pending_invitation, accepted, rejected, expired), add invited_at, responded_at, expires_at columns
- User: add scraped_profiles (JSON), ai_detected_niches (JSON), last_scraped_at columns
- Campaign: add company_urls (JSON), ai_generated_brief (boolean), budget_exhaustion_action (enum: auto_pause/auto_complete), invitation counters (invitation_count, accepted_count, rejected_count, expired_count)
- Create new table: CampaignInvitationLog (campaign_id, user_id, event, metadata, timestamp)
- Create new table: ContentScreeningLog (campaign_id, flagged, flagged_keywords, reviewed_by_admin, review_result, created_at)
- Payout: remove multiplier from billing formula (earnings = pure metrics)
- Run ALTER TABLE migrations on Supabase PostgreSQL
- Update local_db.py: add scraped_profile table, post_schedule table, modify local_campaign for invitation fields
Reference: docs/DATABASE_SCHEMA_V2.md

### Task: Campaign invitation system (replace auto-assign)
Replace the current auto-assignment flow with an invitation system:
- When a company activates a campaign, server runs matching and creates CampaignAssignment records with status=pending_invitation
- New API endpoints: GET /api/campaigns/invitations (user gets pending invitations), POST /api/campaigns/invitations/{id}/accept, POST /api/campaigns/invitations/{id}/reject
- Invitations expire after 3 days (expires_at = invited_at + 3 days)
- Max 5 active campaigns per user enforced on accept
- Expired/rejected slots can be re-offered to other users
- Companies see invitation status (sent, accepted, rejected, expired counts) in campaign detail
- Log all invitation events to CampaignInvitationLog
- Modify matching.py: create invitations instead of assignments, add invitation count tracking
Reference: docs/API_SPEC_V2.md sections 3 and 5, docs/USER_FLOWS_V2.md flows 2 and 9

### Task: Remove payout multiplier from billing
Simplify billing: earnings = pure engagement metrics * company rates * 80% (Amplifier keeps 20%). Remove all payout_multiplier logic from:
- server/app/services/billing.py (remove multiplier from earnings calculation)
- server/app/routers/campaigns.py (remove payout_multiplier from assignment creation)
- Assignment model (deprecate payout_multiplier field, default to 1.0)
- Update all billing-related tests
Reference: docs/PRODUCT_SPEC_V2.md billing section

### Task: Prohibited content screening
Automated keyword screening when campaigns are created:
- Create screening service: check campaign brief + content guidance against prohibited categories (adult, gambling, drugs, weapons, financial fraud, hate speech)
- Keyword dictionary for each category
- If flagged: campaign status stays draft, entry added to ContentScreeningLog, requires admin review
- New admin API endpoints: GET /api/admin/flagged-campaigns, POST /api/admin/flagged-campaigns/{id}/approve, POST /api/admin/flagged-campaigns/{id}/reject
- New admin web page: campaign review queue
Reference: docs/API_SPEC_V2.md section 7-8

### Task: Campaign management improvements
- Campaign cloning: POST /api/company/campaigns/{id}/clone — duplicates campaign with new dates/budget
- Campaign deletion: DELETE /api/company/campaigns/{id} — only if draft or cancelled
- Budget top-up: POST /api/company/campaigns/{id}/budget-topup — increase budget for active campaigns
- Budget exhaustion action: per-campaign choice of auto_pause or auto_complete
- Budget alerts: flag when campaign hits 80% spent (store in campaign, show in dashboard)
- Minimum campaign budget: $50 enforced on creation
- Campaign edit propagation: when company edits active campaign, set a version/updated_at flag that user app detects on next poll. Posts approved but not yet posted get flagged for re-review.
Reference: docs/API_SPEC_V2.md section 5, docs/PRODUCT_SPEC_V2.md company dashboard section

### Task: Fix user earnings endpoint
GET /api/users/me/earnings currently returns hardcoded zeros for pending and per_campaign. Fix:
- Calculate pending earnings from metrics not yet marked final
- Aggregate per-campaign breakdown from payouts table
- Add POST /api/users/me/payout endpoint for withdrawal requests
Reference: docs/API_SPEC_V2.md section 2

---

## Phase 2: Profile Scraping & AI Niche Detection

### Task: Profile scraping system
Build Playwright-based scrapers for each platform that extract user profile data:
- X: follower/following count, bio, display name, profile pic, recent tweets (last 30-60), engagement per tweet
- LinkedIn: connections count, headline, about text, recent posts, engagement per post
- Facebook: friends count, bio/intro, recent posts, engagement per post
- Reddit: karma, cake day, recent posts/comments, post karma per post
- Each scraper runs headlessly using the user's existing persistent browser profile
- Store results in local scraped_profile table
- Sync aggregate data (follower counts, engagement rates, niches) to server via PATCH /api/users/me
- Runs: on platform connect (immediate), weekly refresh by background agent, manual refresh
Reference: docs/PRODUCT_SPEC_V2.md profile scraping section, docs/TECHNICAL_ARCHITECTURE_V2.md section 4

### Task: AI niche classification
After scraping a user's posts, feed them to an LLM to classify niches:
- Collect recent post text from all platforms
- Send to Gemini (or fallback): "Based on these posts, classify this user's content niches from: [finance, tech, beauty, fashion, fitness, gaming, food, travel, education, lifestyle, business, health, entertainment, crypto]"
- Store AI-detected niches in user profile (local + server)
- During onboarding, show detected niches for user confirmation/adjustment
- Re-run weekly when profiles are refreshed
Reference: docs/PRODUCT_SPEC_V2.md onboarding step 4

---

## Phase 3: AI-Powered Server Features

### Task: AI campaign creation wizard
Server-side API for the step-by-step campaign creation wizard:
- POST /api/company/campaigns/ai-wizard endpoint
- Accepts: product description, goal, company/product URLs, target audience, content direction preferences
- Scrape provided URLs using webcrawler (company description, product details, brand voice, selling points)
- Feed all context to Gemini to generate: campaign title, brief, content guidance, suggested payout rates, suggested budget
- Return generated campaign for company to review/edit
- Integrate reach estimation: count matching users based on targeting criteria, estimate impressions
- GET /api/company/campaigns/{id}/reach-estimate — live estimate that updates as targeting changes
Reference: docs/PRODUCT_SPEC_V2.md company dashboard section, docs/API_SPEC_V2.md section 5

### Task: AI-powered matching algorithm
Upgrade matching from simple niche overlap scoring to AI-powered relevance scoring:
- Hard filters unchanged: required platforms, follower minimums, region, niche match, not suspended, not already invited
- New: feed campaign brief + user profile (scraped posts, bio, niches, engagement rate) to LLM
- LLM scores relevance 0-100 for each candidate
- Combine AI score + trust bonus + engagement bonus for final ranking
- Top N users get invitations
- Cache AI scores to avoid re-computing for the same campaign-user pair
Reference: docs/PRODUCT_SPEC_V2.md matching section, docs/TECHNICAL_ARCHITECTURE_V2.md section 6

### Task: Content quality improvements
Enhance the existing quality scoring to check campaign brief adherence:
- Compare generated content against campaign brief, content guidance, must-include phrases
- Score brief adherence 0-100
- Combined quality score: (existing rules + brief adherence) / 2
- Content below 60/100 gets warning shown to user
- Ensure company brand guidelines from content_guidance are enforced
Reference: docs/PRODUCT_SPEC_V2.md content quality section

### Task: Reporting and export
- GET /api/company/campaigns/{id}/export endpoint
- Generate CSV with: campaign details, per-user breakdown (display name, platforms, post URLs, impressions, likes, reposts, comments, earned), per-platform stats, timeline, spend summary
- Optional: PDF generation (use a lightweight library like reportlab or weasyprint)
- Filterable by date range
Reference: docs/PRODUCT_SPEC_V2.md reporting section

---

## Phase 4: Tauri Desktop App

### Task: Tauri project setup and Python sidecar
Set up the Tauri project structure:
- Initialize Tauri project with Rust backend + WebView frontend
- Set up Python sidecar: bundle existing Python scripts (post.py, content_generator.py, metric_scraper.py, etc.) as a subprocess
- Implement JSON-RPC over stdin/stdout communication between Rust and Python
- System tray integration with context menu (Open Dashboard, Pause/Resume, Quit)
- Auto-start on login option
- Local SQLite database access from both Rust (reads for UI) and Python (writes)
- Ensure Playwright browser binaries are bundled or installed on first run
Reference: docs/TECHNICAL_ARCHITECTURE_V2.md section 2

### Task: Onboarding UI
Build the onboarding flow in the Tauri WebView:
- Step 1: Register/Login form (email + password)
- Step 2: Connect Platforms — for each platform, button opens browser window for login, shows connected/not connected status
- Step 3: Profile Scraping — automatic after each connect, show progress spinner, display scraped data (follower count, bio preview)
- Step 4: Niche Confirmation — show AI-detected niches as pre-selected checkboxes, user can adjust
- Step 5: Audience Region — dropdown select
- Step 6: Operating Mode — radio buttons (semi_auto, full_auto, manual) with descriptions
- Step 7: Done — profile summary, connection status
- Blue/white theme (#2563eb primary, DM Sans font)
Reference: docs/PRODUCT_SPEC_V2.md onboarding section

### Task: Home dashboard UI
Build the main dashboard screen:
- Active Campaigns count + total potential earnings
- Pending Invitations count
- Posts Queued count
- Earnings Balance (current withdrawable)
- Platform Health indicators (green/yellow/red per platform)
- Recent Activity feed (last 5 events)
- Blue/white theme
Reference: docs/PRODUCT_SPEC_V2.md home dashboard section

### Task: Campaigns tab UI
Three sections in the campaigns tab:
- Invitations: campaign cards with title, brief summary, payout rates, estimated earnings, platforms required, 3-day expiry countdown. Accept/Reject/View Details buttons. Show "max 5 active" warning if at limit.
- Active: campaign cards with status pipeline (generating → review → approved → scheduled → posted → paid). Expandable per-platform status.
- Completed: past campaigns with final metrics and earnings.
Reference: docs/PRODUCT_SPEC_V2.md campaigns tab section

### Task: Posts tab UI with per-platform editing
Build the posts management tab:
- Pending Review: per-platform content preview with inline editing (change X text without touching LinkedIn). Regenerate button per platform. Image preview + regenerate. Approve all / approve individual. Skip button. Campaign-updated flag for re-review.
- Scheduled: show scheduled post time, reschedule/cancel options
- Posted: post URL per platform (clickable), live engagement metrics, post status
- Failed: error message, retry button, session health link
Reference: docs/PRODUCT_SPEC_V2.md posts tab section

### Task: Earnings tab UI
Build the earnings screen:
- Balance, Total Earned, Pending amounts
- Per-Campaign Breakdown table
- Per-Platform Breakdown
- Payout History with status
- Withdraw Button (enabled when balance > $10)
Reference: docs/PRODUCT_SPEC_V2.md earnings tab section

### Task: Settings tab and statistics UI
Build settings and stats:
- Operating Mode switcher
- Connected Platforms with status + re-authenticate + disconnect
- Profile summary (scraped data, detected niches, refresh button)
- Notification toggles
- Account management (email, password, delete)
- Statistics: trust score, avg engagement rate, campaign completion rate, best platform, earnings trend chart, post success rate
Reference: docs/PRODUCT_SPEC_V2.md settings and statistics sections

### Task: Post scheduling engine
Build the scheduling engine in the Python sidecar:
- When user approves content, determine optimal posting time based on campaign target region
- Region-to-timezone mapping with peak engagement windows per platform
- Queue posts in post_schedule table with scheduled_at time
- Enforce 30-minute minimum spacing between posts
- Limit daily campaign posts based on user's active campaigns
- Randomize exact times within windows
- Background agent executes scheduled posts at their times via headless Playwright
Reference: docs/PRODUCT_SPEC_V2.md scheduling section, docs/TECHNICAL_ARCHITECTURE_V2.md section 7

### Task: Session health monitoring
Build session health checking in the background agent:
- Periodically attempt to load profile page for each connected platform
- Classify: Green (works), Yellow (expiring), Red (expired)
- Show status in dashboard (Platform Health indicators on home screen, Settings tab)
- Alert user on session expiry (system notification)
- When post fails due to session: mark failed, alert user, prompt re-auth
- Re-auth: open browser window for manual login (same as initial connect)
- Campaigns NOT blocked by session issues
Reference: docs/PRODUCT_SPEC_V2.md session health section

### Task: Background agent and system tray
Wire up the always-running background agent:
- System tray icon with status indicator
- Campaign polling every 10 minutes
- Execute scheduled posts at their times
- Metric scraping at T+1h, 6h, 24h, 72h
- Session health checks every 30 minutes
- Profile refresh weekly
- Post failure alerts (system notifications)
- New campaign invitation alerts
- Earnings received alerts
Reference: docs/PRODUCT_SPEC_V2.md background agent section

---

## Phase 5: Company Dashboard Rebuild

### Task: AI campaign wizard UI
Build the step-by-step wizard in the company web dashboard:
- Step 1: Campaign basics (product, goal, company/product URLs) — wizard-style with AI chat feel
- Step 2: Target audience (niche checkboxes, region checkboxes, platform checkboxes, follower sliders)
- Step 3: Content direction (tone select, must-include/avoid text inputs)
- Step 4: Budget & payout (AI-suggested values, editable, reach estimation shown live)
- Step 5: Review & edit (all fields editable, preview of invitation as users will see it)
- Step 6: Reach estimation displayed before activation
- Save as draft or activate buttons
- Blue/white theme
Reference: docs/PRODUCT_SPEC_V2.md campaign creation section

### Task: Enhanced campaign detail page
Upgrade the campaign detail view:
- Invitation Status section: sent/accepted/rejected/expired counts with visual breakdown
- Per-User Performance Table: display name, platforms, post URLs, metrics per post, total earned, assignment status
- Per-Platform Breakdown with ROI (cost per impression, cost per engagement)
- Timeline of when posts went out and metrics collected
- Budget progress bar with 80% alert indicator
- Campaign edit form (inline or modal) with propagation rules explained
Reference: docs/PRODUCT_SPEC_V2.md campaign detail section

### Task: Company dashboard improvements
Build remaining company features:
- Campaign cloning UI (button on campaign detail, pre-fills form)
- Campaign deletion (only draft/cancelled, confirmation dialog)
- Budget top-up for active campaigns
- Budget exhaustion action selector (auto-pause vs auto-complete)
- Company statistics page: total campaigns, total spend, avg cost per impression, avg cost per engagement, best campaign, best platform, total reach, user retention, spend trend chart
- Export button on campaign detail (download CSV/PDF)
- Blue/white theme applied to all company pages
Reference: docs/PRODUCT_SPEC_V2.md company statistics and budget management sections

---

## Phase 6: Admin Dashboard Updates & Theme

### Task: Admin campaign review queue
- New admin page: /admin/reviews — list of flagged campaigns awaiting review
- Show: campaign title, company name, flagged keywords, screening category, created date
- Actions: Approve (campaign goes live) or Reject (campaign cancelled, company notified)
- Platform stats page: total posts per platform, success rate, avg engagement
- Blue/white theme applied to all admin pages
Reference: docs/PRODUCT_SPEC_V2.md admin section

### Task: Apply blue/white theme across all apps
Update all templates and UI to use the new Amplifier theme:
- Primary: Blue (#2563eb), Accent: Light blue (#3b82f6)
- Background: White (#ffffff), Sections: Light gray (#f8fafc)
- Text: Dark gray (#1e293b)
- Success: Green (#10b981), Warning: Amber (#f59e0b), Error: Red (#ef4444)
- Font: DM Sans
- Apply to: company dashboard (all 6+ pages), admin dashboard (all 6+ pages), Tauri user app
- Replace all emerald green (#10b981) primary references with blue (#2563eb)
Reference: docs/PRODUCT_SPEC_V2.md theme section

---

## Phase 7: Integration Testing & Polish

### Task: End-to-end integration test
Full cycle test via Chrome DevTools MCP:
1. Company registers, creates campaign via AI wizard, activates
2. User opens Tauri app, onboards (register, connect platform, profile scraped)
3. User receives campaign invitation, accepts
4. Content generated, user reviews/edits per platform, approves
5. Post scheduled and executed at correct time
6. Metrics scraped at intervals
7. Earnings calculated and shown in user dashboard
8. Company sees per-user stats, invitation status, post URLs
9. Test campaign editing propagation (company edits → user sees re-review flag)
10. Test session expiry handling
11. Test invitation expiry after 3 days
12. Test max 5 campaigns enforcement
13. Test budget exhaustion (auto-pause and auto-complete)
14. Test prohibited content screening
Fix all bugs found during testing.

### Task: Bug fix and polish pass
After integration testing:
- Fix all bugs found during UAT
- Verify all error states have proper user-facing messages
- Ensure session health alerts work
- Verify posting works headlessly on all enabled platforms (X, LinkedIn, Facebook, Reddit)
- Verify metric scraping works for all platforms
- Performance check: dashboard loads fast, polling doesn't lag
- Final theme consistency check across all three apps
