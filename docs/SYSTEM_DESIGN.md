# Amplifier System Design

This document captures the key architectural decisions, their rationale, trade-offs, and alternatives considered. It also documents the security model.

---

## Decision 1: User-Side Compute

**Problem:** The system needs to generate AI content, post to social media platforms, and scrape engagement metrics. Where should this compute run?

**Decision:** All posting, content generation, and metric scraping happen on the user's device. The server is a lightweight coordination layer that only handles campaign matching, billing, and trust scoring.

**Implications:**
- The server stays simple and cheap to operate -- no browser instances, no AI API costs, no stored credentials.
- Users bear the cost of AI generation (Claude CLI subscription) and the compute cost of running Playwright browsers.
- Social media credentials never leave the user's device. Browser profiles are stored locally in `profiles/{platform}-profile/`.
- The server must trust metric data reported by users, creating a fraud surface. This is mitigated by the trust and fraud detection system (Decision 7).
- Scaling is inherently distributed -- each user is their own compute node.

**Alternative Considered:** Cloud-based posting (server runs browsers). Rejected because: (a) storing user credentials server-side is a security and liability risk, (b) running headless browsers at scale is expensive, (c) platform anti-detection is harder when many accounts originate from the same IP ranges.

---

## Decision 2: Pull-Based Polling

**Problem:** How does the user app learn about new campaigns?

**Decision:** The user app polls the server every 5-15 minutes (default: 10 minutes via `CAMPAIGN_POLL_INTERVAL_SEC=600`) using `GET /api/campaigns/mine`. The server runs the matching algorithm on each poll and returns matched campaigns.

**Implications:**
- **Offline resilience** -- If the server is unreachable, the client retries with exponential backoff (5s, 10s, 20s, up to 3 attempts per request). Campaigns cached locally continue to function.
- **No WebSocket infrastructure** -- The server is a stateless FastAPI app deployable to Vercel serverless. No persistent connections to maintain.
- **Acceptable latency** -- Campaigns are not time-critical to the minute. A 10-minute poll interval means a new campaign reaches users within 10 minutes on average.
- **Matching happens on-demand** -- The matching algorithm runs fresh on each poll, incorporating the user's latest trust score and profile data.

**Alternative Considered:** WebSockets or server-sent events for real-time push. Rejected because: (a) adds infrastructure complexity (connection management, reconnection logic), (b) the use case does not require sub-minute latency, (c) incompatible with serverless deployment targets like Vercel.

---

## Decision 3: Playwright Browser Automation

**Problem:** How does the system post content to 6 different social media platforms?

**Decision:** Use Playwright with persistent browser profiles (Chromium) to automate posting through each platform's web UI. Each platform gets its own browser profile directory.

**Implications:**
- **No API keys needed** -- Users authenticate once via `login_setup.py`, which opens a visible browser for manual login. The session cookies are persisted in the profile directory and reused for all subsequent automated posting.
- **Fragile to UI changes** -- Each platform has hardcoded CSS selectors and UI flow expectations. Platform updates can break posting. Key gotchas are documented in CLAUDE.md (X overlay div, LinkedIn shadow DOM, Reddit faceplate components, TikTok Draft.js editor, Instagram multi-step dialog, Facebook image upload flow).
- **Anti-detection required** -- Browser automation must emulate human behavior to avoid platform detection (see Decision 4).
- **Per-platform proxy support** -- `platforms.json` supports a `proxy` field per platform (e.g., `socks5://127.0.0.1:1080` for TikTok in geo-restricted regions).

**Alternative Considered:** Official platform APIs. Rejected because: (a) most platforms severely limit posting via API or require app review, (b) some platforms (TikTok, Instagram) have no public posting API for individual accounts, (c) API-based posting is easily identifiable as automated.

---

## Decision 4: Anti-Detection Strategy

**Problem:** Social media platforms detect and penalize automated posting. How does the system avoid detection?

**Decision:** A multi-layered anti-detection strategy implemented in `scripts/utils/human_behavior.py` and `scripts/post.py`:

### Browser-Level
- **Persistent profiles** -- Each platform uses a dedicated Chromium profile directory (`profiles/{platform}-profile/`), preserving cookies, localStorage, and browser fingerprint across sessions.
- **`--disable-blink-features=AutomationControlled`** -- Strips the `navigator.webdriver` flag that platforms check.
- **Non-headless by default** -- `HEADLESS=false` (configurable). Headless mode is only used for metric scraping.

### Behavioral Emulation
- **Pre-post browsing** -- Before composing a post, `browse_feed()` spends 1-5 minutes (configurable via `BROWSE_MIN_DURATION_SEC` / `BROWSE_MAX_DURATION_SEC`) scrolling the feed, reading 2-4 posts (3-10 seconds each), clicking 1-2 user profiles, and moving the mouse randomly.
- **Character-by-character typing** -- `human_type()` types each character individually with 30-120ms delays between keystrokes. 5% chance of a "thinking pause" (300-800ms).
- **Random scrolling** -- `human_scroll()` scrolls 200-500px with 0.5-1.5s pauses.
- **Random mouse movement** -- `random_mouse_movement()` moves the mouse to random viewport positions in 5-15 intermediate steps.
- **Post-post browsing** -- After posting, another `browse_feed()` session runs on the platform.

### Engagement
- **Auto-engagement** -- `auto_engage()` likes, reposts, and upvotes other users' content during browsing sessions. Each platform has daily caps (e.g., X: 15 likes + 3 retweets, LinkedIn: 8 likes + 2 reposts, Reddit: 15 upvotes).
- **Content blocklist** -- Engagement skips posts containing blocked keywords (politics, NSFW, conspiracy, etc.).
- **Daily tracking** -- Engagement counts persist to `logs/engagement-tracker.json` and reset daily.

### Timing
- **Inter-platform delays** -- 30-90 seconds between posting to different platforms within a session.
- **Slot-based scheduling** -- Posts are spread across 6 daily time slots aligned with US hours, not batched.
- **Random platform order** -- Platforms within a slot are shuffled to avoid predictable patterns.

---

## Decision 5: Content Generation — Two Separate Pipelines

**Problem:** How is social media content generated? The system has two distinct use cases with different requirements.

**Decision:** Two separate content generation pipelines:

### Personal Brand Engine (generate.ps1)
`scripts/generate.ps1` calls `claude --dangerously-skip-permissions -p "<prompt>"` via PowerShell and writes draft JSON files to `drafts/review/`. Per-slot generation with pillar rotation, CTA rotation, and legal disclaimers. Windows-only.

### Campaign Content (content_generator.py)
`scripts/utils/content_generator.py` generates campaign content using free AI APIs with a fallback chain. Requires no Claude CLI subscription.

**Text providers (fallback order):** Gemini (`gemini-2.5-flash-lite`) → Mistral (`mistral-small-latest`) → Groq (`llama-3.3-70b`)

**Image providers (fallback order):** Gemini (500+ images/day) → Pollinations AI (free, no signup, URL-based) → PIL branded templates (last resort)

API keys are stored in `config/.env` (`GEMINI_API_KEY`, `MISTRAL_API_KEY`, `GROQ_API_KEY`). The generator auto-detects which keys are available and builds the provider chain at startup. All providers offer daily/monthly refreshing free limits — users do not permanently run out.

**Implications:**
- **Campaign generation is cross-platform** -- No PowerShell or Claude CLI required. Works on any OS.
- **Personal brand generation remains Windows-only** -- PowerShell is required for `generate.ps1`.
- **Users bear no AI cost for campaigns** -- Free API keys required, but no billing.
- **Graceful degradation** -- If one provider's rate limit is hit, the next is tried automatically.

**Alternative Considered:** Continuing to use Claude CLI for campaign content. Rejected because: (a) requires a paid Claude subscription per user — a barrier to adoption, (b) PowerShell dependency limits the user app to Windows only, (c) free API alternatives (Gemini, Groq) are sufficient quality for campaign briefs.

---

## Decision 6: Dual Database Architecture

**Problem:** The user app needs to track campaigns, posts, and metrics locally, but the server is the authoritative source for billing and trust. How do the databases coexist?

**Decision:** Two separate SQLite databases with a defined sync protocol:
- **Server DB** (`server/amplifier.db` or PostgreSQL in production) -- 8 tables: Company, Campaign, User, CampaignAssignment, Post, Metric, Payout, Penalty. Authoritative for billing, trust scores, and campaign state.
- **Local DB** (`data/local.db`) -- 5 tables: local_campaign, local_post, local_metric, local_earning, settings. Tracks user-side state with sync flags.

### Sync Model

| Data | Direction | Mechanism |
|------|-----------|-----------|
| Campaigns | Server to Client | Polling via `GET /api/campaigns/mine`. Client upserts using `INSERT OR REPLACE` on `server_id` |
| Posts | Client to Server | Batch `POST /api/posts`. Local `synced` flag (0/1). Server returns post IDs mapped back |
| Metrics | Client to Server | Batch `POST /api/metrics`. Local `reported` flag (0/1). Only posts with `server_post_id` are eligible |
| Earnings | Server to Client | `GET /api/users/me/earnings`. Server is authoritative; local table is a read cache |

**Implications:**
- **Offline capability** -- The user can generate and post content even when the server is unreachable. Posts and metrics queue locally and sync when connectivity returns.
- **No conflicts** -- Each direction is append-only or server-authoritative. There is no bidirectional merge. Campaigns flow down; posts and metrics flow up; earnings are read-only from the server.
- **Eventual consistency** -- Posts and metrics may lag behind the server by up to one poll interval (10 minutes). Billing uses the server's data, so delayed metric sync delays earnings calculation.

**Alternative Considered:** Single server database with the client as a thin API consumer. Rejected because offline operation is critical -- posting runs unattended via Task Scheduler and must not fail if the server is temporarily unreachable.

---

## Decision 7: Trust and Fraud System

**Problem:** Users self-report metrics. How does the platform prevent fraudulent engagement data?

**Decision:** A multi-layered trust system implemented in `server/app/services/trust.py`:

### Trust Score

Every user has a trust score ranging from 0 to 100 (default: 50). The score adjusts based on events:

| Event | Adjustment | Trigger |
|-------|-----------|---------|
| `post_verified_live_24h` | +1 | Post confirmed still live after 24 hours |
| `above_avg_engagement` | +2 | Engagement above campaign average |
| `campaign_completed` | +3 | Successfully completed a campaign |
| `user_customized_content` | +1 | Used semi_auto or manual mode |
| `post_deleted_24h` | -10 | Post deleted within 24 hours of posting |
| `content_flagged` | -15 | Content flagged for platform violation |
| `metrics_anomaly` | -20 | Engagement metrics flagged as statistical outlier |
| `confirmed_fake_metrics` | -50 | Confirmed fraudulent metrics |

### Fraud Detection (runs twice daily via background job)

1. **Deletion Monitoring** (`detect_deletion_fraud`) -- Finds posts marked as "live" that are older than 24 hours. These are candidates for spot-check verification (the admin reviews the list).

2. **Anomaly Detection** (`detect_metrics_anomalies`) -- Computes each user's average engagement across all final metrics, then compares against the overall average across all users. Users with engagement >3x the overall average are flagged. Requires at least 5 users and 3 metrics per user to trigger.

### Penalty Mechanics

- Negative trust events automatically create a Penalty record with `amount = abs(adjustment) * $0.50` per trust point lost.
- Penalty reasons: `content_removed`, `platform_violation`, `fake_metrics`.
- Penalties are visible in the admin fraud dashboard with appeal status tracking.
- If trust drops below 10, the user is flagged for ban review (no auto-ban).
- Trust score affects campaign matching: it contributes `trust_score * 0.5` to the match score, so low-trust users see fewer campaigns.

---

## Decision 8: Billing Model

**Problem:** How do users earn money from campaigns?

**Decision:** Pay-per-engagement with content mode multipliers and a platform cut.

### Earnings Formula

```
raw_earning = (impressions / 1000 * rate_per_1k_impressions)
            + (likes * rate_per_like)
            + (reposts * rate_per_repost)
            + (clicks * rate_per_click)

adjusted_earning = raw_earning * content_mode_multiplier

user_earning = adjusted_earning * (1 - platform_cut_percent / 100)
```

### Content Mode Multipliers

| Mode | Multiplier | Content Mode Label | Rationale |
|------|------------|-------------------|-----------|
| `full_auto` | 1.5x | `ai_generated` | Lower effort, AI does everything |
| `semi_auto` | 2.0x | `user_customized` | User reviews and edits AI content |
| `manual` | 2.0x | `user_customized` | User writes original content from brief |

Note: The base multiplier is 1.0x (implied in the formula). The multipliers above are the values stored on the assignment record, applied to the raw earning.

### Platform Cut

The platform (Amplifier) takes a 20% cut (configurable via `platform_cut_percent` in settings). The user receives 80% of the adjusted earning.

### Billing Cycle

- Runs every 6 hours via ARQ background worker (`cron(billing_cycle, hour={0, 6, 12, 18})`).
- Can also be triggered manually from the admin payouts page.
- Processes only posts with `is_final=True` metrics (the 72-hour scrape) and `status="live"`.
- Dedup: each metric ID is billed at most once by checking existing payout breakdowns.
- Budget capping: earnings are capped to the campaign's remaining budget. If `budget_remaining < $1.00`, the campaign auto-completes.

### Payout Cycle

- Minimum payout threshold: $10.00 (configurable via `min_payout_threshold`).
- Users with `earnings_balance >= $10.00` and `status=active` are eligible.
- Payouts are processed via Stripe Connect (Express accounts). Currently creates pending payout records; full Stripe transfer integration is in progress.

---

## Decision 9: Campaign Matching Algorithm

**Problem:** How does the server decide which campaigns to show to which users?

**Decision:** A two-stage filter-and-score algorithm in `server/app/services/matching.py`:

### Stage 1: Hard Filters (reject if any fail)

1. **Required Platforms** -- If the campaign targets specific platforms (e.g., `["x", "linkedin"]`), the user must have all of them connected.
2. **Minimum Followers** -- If the campaign requires minimum follower counts per platform (e.g., `{"x": 1000}`), the user must meet every threshold.
3. **Target Regions** -- If the campaign specifies `target_regions` (e.g., `["us", "uk"]`), the user's `audience_region` must match (or the user's region is `"global"`).
4. **Budget Check** -- Campaigns with `budget_remaining <= 0` are excluded.
5. **Already Assigned** -- Campaigns already assigned to this user are excluded.

### Stage 2: Soft Scoring (rank remaining candidates)

| Factor | Points | Notes |
|--------|--------|-------|
| Niche overlap | +30 per matching tag | Campaign tags vs. user tags |
| No niche targeting | +10 (base) | If campaign has no niche tags, everyone gets a base score |
| Trust score | +0.5 per point | User's trust score (0-100) contributes 0-50 points |
| Minimum guarantee | 1 | If hard filters pass, score is at least 1 |

### Selection

- Candidates are sorted by score descending.
- Top 10 are selected and assigned to the user.
- An assignment record (`CampaignAssignment`) is created with the user's content mode and payout multiplier.
- On subsequent polls, existing active assignments (status `assigned` or `content_generated`) are also returned alongside any new matches.

---

## Security Model

### Authentication

| Mechanism | Details |
|-----------|---------|
| **Password hashing** | bcrypt via `passlib` (in `app/core/security.py`) |
| **JWT tokens** | HS256 algorithm, configurable secret (`jwt_secret_key`), 24-hour expiry |
| **Token types** | Two JWT types distinguished by `type` claim: `"user"` and `"company"` |
| **User API auth** | Bearer token in `Authorization` header. Dependency: `get_current_user()` validates token, checks user exists, rejects banned/suspended |
| **Company API auth** | Bearer token in `Authorization` header. Dependency: `get_current_company()` validates token type is `"company"` |
| **Company web auth** | JWT stored as httpOnly cookie (`company_token`). Validated via `get_company_from_cookie()` |
| **Admin web auth** | Simple password comparison (env var `ADMIN_PASSWORD`, default "admin"). Cookie `admin_token` set to a static value "valid" |

### Authorization

- **Ownership verification** -- Company pages verify `Campaign.company_id == company.id` before allowing access or modification.
- **Campaign status transitions** -- Enforced server-side via a `valid_transitions` map: `draft->[active,cancelled]`, `active->[paused,cancelled]`, `paused->[active,cancelled]`.
- **User status enforcement** -- The `get_current_user()` dependency rejects tokens for `banned` or `suspended` users with 403 responses.

### Data Isolation

- **Users** can only see their own profile, their own campaign assignments, and their own earnings.
- **Companies** can only see and manage campaigns they created (filtered by `company_id` FK).
- **Admin** has read access to all data via the admin dashboard. Admin actions are limited to: suspend/unsuspend users, run billing, run fraud checks, run payouts.

### Known Security TODOs

| Issue | Risk | Status |
|-------|------|--------|
| **Admin API unprotected** | Admin pages use cookie auth, but `/admin/` routes only check a static cookie value, not a cryptographic token. No CSRF protection | Known limitation |
| **CORS open** | No CORS restrictions configured. In production, should restrict to known origins | TODO |
| **No rate limiting** | API endpoints have no rate limiting. Vulnerable to brute-force login attempts and poll flooding | TODO |
| **No email verification** | Users and companies can register with any email without verification | TODO |
| **Static admin token** | Admin authentication uses a static cookie value ("valid") rather than a signed token | Known limitation |
| **JWT secret default** | Default `jwt_secret_key` is `"change-me-to-a-random-secret"`. Must be changed in production via `.env` | Configuration |
