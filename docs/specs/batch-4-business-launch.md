# Batch 4: Business & Launch Specifications

**Tasks:** #19 (Stripe live integration), #22 (landing page), #6 (metrics accuracy). Task #17 (Free/Pro tiers) deferred — see stub below.

---

## Task #17 — [DEFERRED] Free/Pro Tiers

**Status: Deferred to post-launch (2026-04-29).** Full spec preserved in the task-master task description (task #17). Reasoning: amplifiers with no earnings track record cannot rationally evaluate a $19.99/mo subscription; Pro converts post-traction users, which MVP hasn't produced yet. The 20% platform cut is sufficient monetization for MVP. The Free 4 posts/day cap is removed alongside Pro — it only made sense as upgrade friction. Reputation tier (seedling/grower/amplifier) still governs campaign count and earnings multiplier; no per-day post cap from a subscription axis remains. Revisit triggers: amplifier cohort earning $300+/month consistently, OR campaign-supply scarcity making match-priority valuable, OR feature demand that genuinely costs money to deliver.

---

## Task #19 — Stripe Live Integration (Company Checkout + User Connect)

### Overview

Stripe must work in both directions for real money to flow:
- **Companies pay IN** via Stripe Checkout (top up campaign budget)
- **Users get paid OUT** via Stripe Connect Express (receive earnings)

Currently: company Checkout exists in test mode. User payouts are a stub (always marks "paid" without sending money).

**Existing Stripe account:** Father's company has a live, working Stripe account that will be used for Amplifier. No need to create a new Stripe account.

### Company Side: Checkout (already built, needs live keys)

1. Company clicks "Add Funds" on the billing page
2. Enters amount (minimum $50)
3. Server creates a Stripe Checkout session
4. Company completes payment with real card
5. **Webhook** (`checkout.session.completed`) fires → server credits company balance
6. Company can now activate campaigns with that balance

**What needs to change for live:**
- Set real Stripe keys on the server (production environment)
- Use webhook for payment confirmation instead of redirect-based verification (more reliable)
- Add idempotency check: if the same Checkout session is verified twice, don't double-credit the balance

### User Side: Connect Express (not built yet)

Users need to onboard with Stripe Connect to receive real payouts.

**Onboarding flow:**
1. User navigates to Settings → "Connect Bank Account" (or Earnings page → "Set up payouts")
2. Server creates a Stripe Connect Express account for the user
3. User is redirected to Stripe's hosted onboarding form (collects bank details, identity, tax info)
4. After completing onboarding, user is redirected back to the app
5. Server stores the user's Stripe account ID
6. User can now receive payouts

**Payout flow (automated):**
1. User has available earnings >= $10.00 (past the 7-day hold)
2. User clicks "Withdraw" on the Earnings page OR payouts run on a schedule
3. Server creates a Stripe Transfer from Amplifier's account to the user's Connect account
4. Payout status: available → processing → paid (or failed)
5. User sees the payout in their bank account (typically 2-3 business days)

**What happens without Stripe Connect:**
- User can still earn and see their balance
- Withdrawal button shows "Connect your bank account first"
- Earnings accumulate until the user completes Stripe onboarding

### Webhook Endpoints

The server needs a webhook endpoint that handles events from both Checkout and Connect:

| Event | Action |
|-------|--------|
| checkout.session.completed | Credit company balance (with idempotency check) |
| transfer.paid | Confirm user payout successful |
| transfer.failed | Mark payout as failed, return funds to user's available balance |
| account.updated | Track user's Stripe account verification status |

### Edge Cases

- Company clicks success page twice → balance only credited once (idempotency)
- User completes Stripe onboarding but bank details are invalid → transfer fails, funds return to available balance
- User requests withdrawal of $15 but only $12 is available → reject with "Insufficient available balance"
- User has no Stripe account → can't withdraw, earnings accumulate safely
- Stripe is down → payouts fail gracefully, retry on next cycle

### Acceptance Criteria

1. Company tops up $100 using a real card. Balance increases by $100 after webhook fires. Balance does NOT increase if page is refreshed (idempotency).
2. User completes Stripe Connect onboarding. Their Stripe account ID is stored. "Connect your bank account" changes to "Connected."
3. User with $15 available balance clicks "Withdraw $15". Stripe Transfer is created. Payout status moves to "paid" after processing. User's available balance decrements.
4. User without Stripe Connect tries to withdraw. Error message: "Connect your bank account first."
5. Transfer fails (bad bank details). Payout status = "failed". Funds return to user's available balance.

---

## Verification Procedure — Task #19

> Format: `docs/uat/AC-FORMAT.md`. Heavy use of **Stripe MCP** (`https://docs.stripe.com/mcp?mcp-client=claudecode`) for autonomous setup work. Stripe **test mode** keys (`sk_test_...`) are used for ACs 1-12; live mode is only flipped for the final smoke after all ACs pass. **Do NOT run any AC against live Stripe except the final smoke (AC13).**

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `/health` returns 200.
- Worker live (`amplifier-worker.service` running per Task #44) — `services.payments.process_pending_payouts` will be invoked by the worker's hourly cron OR via the `/admin/financial/run-payout-processing` admin override.
- Stripe MCP server connected in Claude (one-time auth via the MCP install flow). Verify with: `mcp__stripe__authenticate` returns ok.
- Stripe test-mode account active (use the existing father's-company account in test mode — toggle via Stripe Dashboard top-left selector to "Test mode").
- Webhook endpoint reachable from Stripe — for local dev, use Stripe CLI's `stripe listen --forward-to https://api.pointcapitalis.com/api/stripe/webhook`. For prod, register the live URL in the Stripe Dashboard.
- VPS env vars set in `/etc/amplifier/server.env`: `STRIPE_SECRET_KEY=sk_test_...`, `STRIPE_PUBLISHABLE_KEY=pk_test_...`, `STRIPE_WEBHOOK_SECRET=whsec_...`, `STRIPE_CONNECT_CLIENT_ID=ca_...`. Confirm via `ssh sammy@31.97.207.162 "sudo cat /etc/amplifier/server.env | grep STRIPE_"`.
- `User.stripe_account_id` column exists on prod (added 2026-04-30 per `docs/migrations/2026-04-30-task18-stripe-account-id.md`).
- Test fixtures: company `uat-stripe-co@uat.local` with starting balance $0; user `uat-stripe-user@uat.local` with $15.00 in available payouts (past 7-day hold).

### Test data setup

1. **Provision Stripe webhook endpoint via MCP** (one-time, idempotent):
   ```
   mcp__stripe__create_webhook_endpoint(
     url="https://api.pointcapitalis.com/api/stripe/webhook",
     enabled_events=[
       "checkout.session.completed",
       "transfer.paid",
       "transfer.failed",
       "account.updated",
       "payment_intent.succeeded"
     ]
   )
   ```
   Capture the returned `whsec_...` signing secret and write to `/etc/amplifier/server.env`. Restart `amplifier-web.service`.

2. **Seed test company + user**:
   ```bash
   python scripts/uat/seed_stripe_fixtures.py \
     --company-email uat-stripe-co@uat.local \
     --user-email uat-stripe-user@uat.local \
     --user-available-balance-cents 1500 \
     --output data/uat/stripe_fixtures.json
   ```

3. **Stripe CLI listening** (only if testing webhooks from local — skip if prod webhook endpoint registered):
   ```bash
   stripe listen --forward-to https://api.pointcapitalis.com/api/stripe/webhook --skip-verify
   ```
   Capture `whsec_...` from the CLI banner — this is the webhook secret used during local-listen.

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_UAT_DRY_STRIPE=1` | Inherited from Task #44. `services.payments` logs `Transfer.create` kwargs without calling Stripe. Used when Stripe MCP is unavailable. | AC8 fallback path |
| `STRIPE_MODE=test` | Forces server to use `sk_test_...` even if `sk_live_...` is also present. Prevents accidental live-mode payouts during UAT. | All ACs |

---

### AC1 — Stripe MCP authenticated and live keys never leak into test runs

| Field | Value |
|-------|-------|
| **Setup** | Stripe MCP installed in Claude. `STRIPE_MODE=test` set. |
| **Action** | `mcp__stripe__list_products(limit=1)` — confirm MCP is connected. Then `ssh sammy@31.97.207.162 "sudo systemctl show -p Environment amplifier-web \| grep -oP 'STRIPE_SECRET_KEY=\K[^ ]+'"` — confirm secret key starts with `sk_test_`. |
| **Expected** | MCP returns ok (any test product or empty list). VPS env shows `sk_test_...`, NOT `sk_live_...`. If `sk_live_...` is present, ABORT all subsequent ACs and report. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task19.py::test_ac1_test_mode_only` |
| **Evidence** | MCP response; VPS env grep (key prefix only — never log full secret) |
| **Cleanup** | none |

### AC2 — Webhook endpoint registered and signs verify

| Field | Value |
|-------|-------|
| **Setup** | Webhook endpoint registered (test-mode) via MCP setup step. |
| **Action** | `mcp__stripe__list_webhook_endpoints()` — verify endpoint exists with the 5 events. Then trigger a synthetic event: `mcp__stripe__trigger_event(event_type="payment_intent.succeeded")`. Tail server logs: `ssh sammy@31.97.207.162 "sudo journalctl -u amplifier-web -n 50 --no-pager \| grep -i webhook"`. |
| **Expected** | MCP `list_webhook_endpoints` returns 1 entry matching `https://api.pointcapitalis.com/api/stripe/webhook` with all 5 events enabled. Server log contains `webhook_received event=payment_intent.succeeded sig_verified=True`. No `InvalidSignatureError` lines. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task19.py::test_ac2_webhook_signed` |
| **Evidence** | MCP response; server log lines |
| **Cleanup** | none |

### AC3 — Company top-up creates Checkout session with correct amount + metadata

| Field | Value |
|-------|-------|
| **Setup** | Test company logged into `/company/billing`. Capture company `balance_cents` before. |
| **Action** | Drive UI via Chrome DevTools MCP: navigate to `/company/billing` → click "Add Funds" → enter `$100` → click "Continue to Stripe" → on Stripe Checkout test page enter card `4242 4242 4242 4242` exp `12/34` cvc `123` ZIP `12345` → click "Pay". Wait for redirect back to `/company/billing?session_id=...`. |
| **Expected** | Stripe Checkout session created with `amount=10000` (cents) and `metadata.company_id=<test_company_id>`. Verify via `mcp__stripe__retrieve_checkout_session(id=...)`. Within 30s of redirect, `webhook_received event=checkout.session.completed` appears in server log. |
| **Automated** | partial — DevTools MCP for the UI; MCP for session retrieval |
| **Automation** | `scripts/uat/uat_task19.py::test_ac3_checkout_creates_session` |
| **Evidence** | session ID; metadata dump; webhook log line |
| **Cleanup** | reset balance for AC4 |

### AC4 — checkout.session.completed credits company balance, idempotent

| Field | Value |
|-------|-------|
| **Setup** | AC3 succeeded. `balance_cents` reset to 0. Capture `audit_log` count before. |
| **Action** | Replay the same session via MCP: `mcp__stripe__trigger_event(event_type="checkout.session.completed", checkout_session=<session_id_from_ac3>)`. Wait 5s. Trigger AGAIN (idempotency check). |
| **Expected** | After first replay: `balance_cents = 10000` (=$100). `audit_log` has +1 row `event='balance_credited'` with `metadata.session_id=<...>`. After second replay: `balance_cents` STILL `10000` (no double-credit). `audit_log` count UNCHANGED on second replay (or +1 row `event='webhook_duplicate_ignored'`). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac4_balance_credit_idempotent` |
| **Evidence** | balance before/after both replays; audit_log diff |
| **Cleanup** | reset company balance |

### AC5 — User Connect Express: onboarding link generated

| Field | Value |
|-------|-------|
| **Setup** | Test user logged into local user app. `users.stripe_account_id` is NULL. |
| **Action** | Drive UI via DevTools MCP: navigate to `/settings` (or `/earnings` — whichever has the Connect button per the implementation) → click "Connect Bank Account" → expect redirect to a `https://connect.stripe.com/express/onboarding/...` URL. Capture redirect URL. |
| **Expected** | Server creates a Stripe Connect Express account (verify via `mcp__stripe__list_accounts(limit=1)` — newest account is type `express`, country US). Returns `account.id` as `acct_...`. Server stores `users.stripe_account_id=acct_...`. Onboarding URL is valid (HTTP 200 head check, no 404). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac5_connect_onboard_link` |
| **Evidence** | redirect URL; `acct_...` ID; SQL row dump |
| **Cleanup** | none — account stays for AC6 |

### AC6 — account.updated webhook flips user.stripe_account_id "verified"

| Field | Value |
|-------|-------|
| **Setup** | AC5 succeeded. User has `stripe_account_id=acct_...` but `stripe_account_verified=False`. |
| **Action** | Skip the Stripe-hosted form by directly updating the test account via MCP: `mcp__stripe__update_account(account=acct_..., individual={...test data...}, business_profile={...})`. Trigger account.updated: `mcp__stripe__trigger_event(event_type="account.updated", account=acct_...)`. Wait 5s. |
| **Expected** | Server log shows `webhook_received event=account.updated`. `users.stripe_account_verified=True`. UI dashboard refresh shows "Connected" badge instead of "Connect your bank account". |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac6_account_updated_flips_verified` |
| **Evidence** | webhook log; SQL row; UI screenshot |
| **Cleanup** | none |

### AC7 — Withdrawal flow: $15 available, button enabled, transfer created

| Field | Value |
|-------|-------|
| **Setup** | Test user verified per AC6. `users.earnings_balance_cents=1500` (=$15). |
| **Action** | DevTools MCP: navigate to `/earnings` → "Withdraw $15" button enabled → click → confirm → wait. Watch server log + Stripe MCP. |
| **Expected** | Server creates `Transfer` via Stripe API (verify `mcp__stripe__list_transfers(limit=1)` returns newest with `amount=1500`, `destination=acct_...`). Local `payouts` row created with `status=processing`, `stripe_transfer_id=tr_...`. User's `available_balance_cents` immediately decremented to 0. UI shows "Processing..." badge on the payout history row. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac7_withdrawal_creates_transfer` |
| **Evidence** | Transfer ID; payout row; balance before/after; UI screenshot |
| **Cleanup** | none — payout stays for AC8 |

### AC8 — transfer.paid webhook moves payout to paid

| Field | Value |
|-------|-------|
| **Setup** | AC7 succeeded. Payout in `processing` state. |
| **Action** | `mcp__stripe__trigger_event(event_type="transfer.paid", transfer=tr_...)`. Wait 5s. |
| **Expected** | Server log `webhook_received event=transfer.paid`. Payout `status=paid`, `paid_at=NOW()`. User's `total_earned_cents` UNCHANGED (already counted at metric submission). UI payout history row shows "Paid" badge. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac8_transfer_paid_finalizes` |
| **Evidence** | webhook log; SQL row; UI screenshot |
| **Cleanup** | reset payout + balance for AC9 |

### AC9 — transfer.failed webhook returns funds to available balance

| Field | Value |
|-------|-------|
| **Setup** | Repeat AC7 setup with $15. New payout in `processing` state. |
| **Action** | `mcp__stripe__trigger_event(event_type="transfer.failed", transfer=tr_...)`. Wait 5s. |
| **Expected** | Server log `webhook_received event=transfer.failed`. Payout `status=failed`, `failure_reason` populated. User's `earnings_balance_cents` restored to 1500 (refunded). `audit_log` row `event='payout_failed_refunded'`. UI shows "Failed" badge with retry option. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac9_transfer_failed_refunds` |
| **Evidence** | webhook log; SQL rows; balance restored |
| **Cleanup** | reset payout |

### AC10 — Edge case: insufficient available balance rejected

| Field | Value |
|-------|-------|
| **Setup** | User with `earnings_balance_cents=1200` (=$12). |
| **Action** | DevTools MCP: navigate to `/earnings` → enter "$15" in withdraw amount → submit. |
| **Expected** | UI shows error toast/inline: "Insufficient available balance" (or equivalent). No Stripe `Transfer.create` call. No payout row created. Balance unchanged. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac10_insufficient_balance` |
| **Evidence** | UI screenshot of error; SQL row count diff (0 new payouts) |
| **Cleanup** | none |

### AC11 — Edge case: no Stripe Connect → withdrawal blocked with CTA

| Field | Value |
|-------|-------|
| **Setup** | User with `stripe_account_id=NULL` and `earnings_balance_cents=1500`. |
| **Action** | DevTools MCP: navigate to `/earnings` → click withdraw button. |
| **Expected** | UI shows "Connect your bank account first" with a CTA button linking to `/settings` Connect onboarding. Withdraw button disabled. No Stripe API call attempted. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac11_no_stripe_connect_blocks` |
| **Evidence** | UI screenshot |
| **Cleanup** | none |

### AC12 — Worker auto-promotes pending payouts past 7-day hold and processes them

| Field | Value |
|-------|-------|
| **Setup** | Seed user with `payouts` row `status=pending`, `available_at=NOW() - INTERVAL '1 minute'`, `amount_cents=1500`, `stripe_account_id` valid. Worker running with `AMPLIFIER_UAT_INTERVAL_SEC=30`. |
| **Action** | Wait up to 90s. Watch worker log. |
| **Expected** | Within first 30s: payout `status=available`, `earnings_balance_cents` incremented. Within 60s: worker `process_pending_payouts` picks it up, `status=processing`, Stripe Transfer created. After test `transfer.paid` event triggered manually: `status=paid`. Full pipeline runs without manual intervention. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task19.py::test_ac12_worker_full_pipeline` |
| **Evidence** | worker log; status timeline from SQL |
| **Cleanup** | reset payout |

### AC13 — Final smoke (LIVE mode) — single $1 real top-up

| Field | Value |
|-------|-------|
| **Setup** | All ACs 1-12 PASS in test mode. **User explicitly approves switching to live mode.** Live keys (`sk_live_...`) staged but not yet active on VPS. |
| **Action** | Swap VPS env to live keys via SSH: `sudo sed -i 's/^STRIPE_SECRET_KEY=sk_test_.*/STRIPE_SECRET_KEY=sk_live_.../' /etc/amplifier/server.env && sudo systemctl restart amplifier-web`. Run AC3 flow with **real card**, **$1 amount**. Then immediately refund: `mcp__stripe__create_refund(charge=ch_...)`. |
| **Expected** | $1 charge succeeds. Webhook fires. Company balance credited $1. Refund issued. Balance debited $1 within 60s of refund webhook. End state: $0 net change, real money flowed both directions. |
| **Automated** | partial — manual confirmation required from user before flipping to live |
| **Automation** | manual run with explicit user `y` confirmation |
| **Evidence** | Stripe Dashboard screenshot of charge + refund; balance audit_log; bank statement (next-day verification) |
| **Cleanup** | nothing to clean — refund completes the round-trip |

---

### Aggregated PASS rule for Task #19

Task #19 is marked done in task-master ONLY when:
1. AC1–AC12 all PASS in test mode (zero `sk_live_` exposure during test ACs)
2. AC13 PASS — live $1 round-trip succeeds and refunds cleanly
3. No `error|exception|traceback` lines in `journalctl -u amplifier-web` during the UAT window
4. No orphan Stripe objects: `mcp__stripe__list_transfers(status=pending)` empty after run
5. UAT report `docs/uat/reports/task-19-<yyyy-mm-dd>-<hhmm>.md` written with all evidence (webhook IDs, transfer IDs, screenshots) embedded
6. Live keys remain on VPS env after AC13 (staying in live mode is the goal — Task #19 done == live Stripe is on)

---

## Task #22 — Landing Page

### Overview

A public-facing website that explains Amplifier to both companies and users. Must convert visitors into signups (companies) and downloads (users).

### Two Audiences, One Page

| Section | For Companies | For Users |
|---------|-------------|-----------|
| Hero | "Get real people to post about your product" | "Earn money posting about products you love" |
| How it works | Create campaign → Set budget → Track results | Sign up → Get matched → Post & earn |
| Pricing | Pay per engagement (impressions, likes, reposts) | Free to join, earn per post |
| CTA | "Create Campaign" → links to company dashboard | "Download Amplifier" → links to installer download |

### Page Sections (top to bottom)

1. **Hero** — Split message for both audiences. Bold headline, short subtitle, two CTA buttons (Company / User)
2. **How it works** — 3-step visual flow for each audience
3. **For Companies** — Why use Amplifier: real people (not bots), pay only for results, AI-matched creators, campaign analytics
4. **For Users** — Why join: earn money from social media you already use, AI generates content for you, get matched to brands you care about, cash out anytime
5. **Pricing** — Companies: pay per engagement (show the rate types). Users: free, earn from day one
6. **Trust/Social Proof** — Platform stats (campaigns created, posts made, earnings paid). Placeholder for testimonials.
7. **FAQ** — Common questions: "How much can I earn?", "What platforms are supported?", "How does payment work?", "Is it free?"
8. **Footer** — Links to Terms, Privacy Policy, company dashboard, support email

### Technical Requirements

- Static site (no server rendering needed). Can be HTML + CSS or a simple framework (Next.js, Astro).
- Deployed to Vercel (same platform as the server)
- Loads in under 2 seconds
- Mobile responsive
- SEO: title tag, meta description, Open Graph tags for social sharing
- Download link for Windows installer (and Mac when ready)

### Acceptance Criteria

1. Navigate to the landing page URL. Page loads in under 2 seconds. Both company and user messaging is visible.
2. Click "Create Campaign". Redirects to company login/register page.
3. Click "Download Amplifier". Installer download starts.
4. Share the URL on LinkedIn/Facebook/Reddit. Preview card appears with title, description, and image (OG tags working).
5. View on mobile (375px width). All content is readable, CTAs are tappable, no horizontal scroll.
6. FAQ section answers the 4 key questions.

---

## Verification Procedure — Task #22

> Format: `docs/uat/AC-FORMAT.md`. Landing page is a static deliverable — most ACs use Chrome DevTools MCP to drive the live URL. Stripe MCP not needed. Hosting target TBD at implementation time (likely Hostinger static or Vercel free static — landing has no server-side logic so Vercel's commercial-use ban doesn't apply to this asset).

### Preconditions

- Landing page deployed to a public URL (capture as `LANDING_URL` env var, e.g., `https://amplifier.app` or temporarily `https://landing.pointcapitalis.com`).
- Windows installer artifact published to GitHub Releases at a known download URL (capture as `INSTALLER_URL`).
- Server live at `https://api.pointcapitalis.com` so the "Create Campaign" CTA links to a working `/company/login`.

### Test data setup

None — landing page is static.

### Test-mode flags

None.

---

### AC1 — Page loads in under 2 seconds (Lighthouse / DevTools performance)

| Field | Value |
|-------|-------|
| **Setup** | Cold cache (DevTools MCP fresh page). |
| **Action** | DevTools MCP: `new_page(LANDING_URL)` → `performance_start_trace` → reload → `performance_stop_trace`. Then `lighthouse_audit(LANDING_URL, categories=["performance"])`. |
| **Expected** | First Contentful Paint < 1.2s. Largest Contentful Paint < 2.0s. Lighthouse Performance score >= 85. Total page weight < 500KB (excluding fonts). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task22.py::test_ac1_load_perf` |
| **Evidence** | trace JSON; Lighthouse report HTML/JSON |
| **Cleanup** | `close_page` |

### AC2 — Hero shows BOTH company AND user messaging

| Field | Value |
|-------|-------|
| **Setup** | Page loaded. |
| **Action** | DevTools MCP: `take_snapshot` of the hero section → `take_screenshot(filePath="data/uat/screenshots/task22_ac2_hero.png")`. Grep snapshot for company-side keywords + user-side keywords. |
| **Expected** | Hero contains text matching `(?i)(post about your product\|real people\|create campaign)` (company side) AND `(?i)(earn money\|earn from social\|download)` (user side). Both CTA buttons visible above the fold (viewport 1280x720). Screenshot embedded in report. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task22.py::test_ac2_dual_audience_hero` |
| **Evidence** | snapshot; screenshot |
| **Cleanup** | none |

### AC3 — "Create Campaign" CTA navigates to company login

| Field | Value |
|-------|-------|
| **Setup** | Page loaded. |
| **Action** | DevTools MCP: `take_snapshot` → find UID of "Create Campaign" button by visible text → `click(uid)` → `wait_for(text="Sign in to your company account")` (or whatever the company login page shows). Capture final URL. |
| **Expected** | Final URL is `https://api.pointcapitalis.com/company/login` (or `/company/register`). Page renders the company login form (email field present). No 404, no redirect loops. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task22.py::test_ac3_company_cta` |
| **Evidence** | URL transition; final-page snapshot |
| **Cleanup** | navigate back |

### AC4 — "Download Amplifier" CTA starts installer download

| Field | Value |
|-------|-------|
| **Setup** | Page loaded. |
| **Action** | DevTools MCP: `take_snapshot` → find UID of "Download Amplifier" button → `click(uid)` → use `list_network_requests` filtered by URL containing `.exe` OR `.msi` OR a redirect to a `releases/download/` URL. |
| **Expected** | Network request fires with `Content-Disposition: attachment; filename=Amplifier-*.exe` (or installer URL is a redirect that resolves to an executable). HTTP 200. File size > 1 MB (sanity check it's a real binary, not a stub). |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task22.py::test_ac4_user_cta_download` |
| **Evidence** | network request dump; resolved URL; HEAD response headers |
| **Cleanup** | navigate back; cancel any pending download |

### AC5 — Open Graph + Twitter Card meta tags present

| Field | Value |
|-------|-------|
| **Setup** | Page loaded. |
| **Action** | DevTools MCP: `evaluate_script("Array.from(document.querySelectorAll('meta')).filter(m => m.getAttribute('property')?.startsWith('og:') || m.getAttribute('name')?.startsWith('twitter:')).map(m => [m.getAttribute('property') || m.getAttribute('name'), m.getAttribute('content')])")`. |
| **Expected** | Returns at least: `og:title`, `og:description`, `og:image` (absolute URL, HTTP 200 when fetched), `og:url`, `og:type=website`, `twitter:card=summary_large_image`. `og:image` dimensions >= 1200x630. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task22.py::test_ac5_og_tags` |
| **Evidence** | meta tag dump; HEAD on og:image URL |
| **Cleanup** | none |

### AC6 — Mobile responsive at 375px (iPhone viewport)

| Field | Value |
|-------|-------|
| **Setup** | Page loaded. |
| **Action** | DevTools MCP: `emulate(device="iPhone 15")` (or `resize_page(width=375, height=812)`) → `take_screenshot(filePath="data/uat/screenshots/task22_ac6_mobile.png", fullPage=true)` → check via JS: `document.documentElement.scrollWidth <= 375` (no horizontal scroll). |
| **Expected** | No horizontal scroll. All hero CTAs visible without zooming. FAQ accordion functional with tap. Font size >= 14px throughout. Screenshot reviewed manually for layout integrity. |
| **Automated** | partial — automated horizontal-scroll check; manual screenshot eyeball |
| **Automation** | `scripts/uat/uat_task22.py::test_ac6_mobile_responsive` (auto check) + manual y/n on screenshot |
| **Evidence** | screenshot embedded in report |
| **Cleanup** | reset viewport to desktop |

### AC7 — FAQ answers all 4 required questions

| Field | Value |
|-------|-------|
| **Setup** | Page loaded. |
| **Action** | DevTools MCP: scroll to FAQ section → `take_snapshot` of the FAQ block → grep for the 4 question patterns. |
| **Expected** | FAQ contains questions matching all four (case-insensitive): `(?i)how much can I earn`, `(?i)what platforms`, `(?i)how does payment work` (or "how do I get paid"), `(?i)is it free` (or "what does it cost"). Each has a non-empty answer at least 1 sentence long. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task22.py::test_ac7_faq_complete` |
| **Evidence** | snapshot text; per-question answer text |
| **Cleanup** | none |

### AC8 — Footer has Terms + Privacy links and they resolve

| Field | Value |
|-------|-------|
| **Setup** | Page loaded. |
| **Action** | DevTools MCP: scroll to footer → `take_snapshot` → find UIDs of "Terms" and "Privacy Policy" links → for each, fetch the URL via httpx HEAD. |
| **Expected** | Both links present in footer. Both URLs return HTTP 200. Each linked page contains a `<title>` matching `Terms` or `Privacy`. |
| **Automated** | yes |
| **Automation** | `scripts/uat/uat_task22.py::test_ac8_footer_legal_links` |
| **Evidence** | URLs; HEAD response codes |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #22

Task #22 is marked done in task-master ONLY when:
1. AC1–AC8 all PASS (AC6 manual confirmation = user `y` on the mobile screenshot)
2. Lighthouse score >= 85 in Performance, Accessibility, SEO categories
3. Console messages during page load: zero error-level (warnings OK)
4. UAT report `docs/uat/reports/task-22-<yyyy-mm-dd>-<hhmm>.md` includes embedded screenshots, Lighthouse report link, and OG tag preview from a real share-debug tool (Twitter Card Validator OR LinkedIn Post Inspector — manual paste of `LANDING_URL`)
5. Public installer download from AC4 actually launches on a clean Windows machine (one-time manual smoke before declaring done)

---

## Task #6 — Metrics Accuracy

### Overview

Metrics drive billing. Inaccurate metrics mean inaccurate payouts — users lose trust if underpaid, companies lose money if overpaid. This task adds validation and handles edge cases in the metric scraping pipeline.

### Deleted Post Detection

When the scraper visits a post URL and the post has been deleted, it must detect this and stop scraping. Without detection, deleted posts produce zero-metric rows that look like engagement dropped to zero — which is different from "this post no longer exists."

**Per-platform deletion signals:**

| Platform | Signs the post was deleted (verified against real deleted posts) |
|----------|--------------------------|
| X | "This post is unavailable", "This account doesn't exist", "This post was deleted", "Hmm...this page doesn't exist" (unicode-normalized), "Account suspended", "Page not found", HTTP 404 via API |
| LinkedIn | "This content isn't available", "This page doesn't exist", "This post has been removed", "This post cannot be displayed", "Content unavailable" |
| Facebook | "This content isn't available", "This page isn't available", "The link you followed may be broken", "Content not found", "This post is no longer available", "Content isn't available right now". Also detects author-deleted posts via permalink: if permalink URL loads but shows "No more posts" (empty feed), the post is gone. |
| Reddit | "Sorry, this post was removed", "Sorry, this post was deleted", "This post was removed by", "This post was deleted by", "This post has been removed", "This post is no longer available", "Page not found". Also checks `shreddit-post[removed="true"]` attribute for mod removals AND `shreddit-post[author="[deleted]"]` / `is-author-deleted` attribute for user-deleted posts. Note: `[deleted]`/`[removed]` in body text NOT used (causes false positives from deleted comments). |

**When a deleted post is detected:**
1. Mark the post as "deleted" in the local database
2. Do NOT record a zero-metric row (zeros would look like real engagement data)
3. Stop all future scraping for this post
4. Notify the server via `PATCH /api/posts/{id}/status` with `{"status": "deleted"}` — the server calls `void_earnings_for_post()` which voids pending payouts and returns funds to the campaign budget

### Rate Limit Handling

Platforms may block repeated automated visits with CAPTCHAs, login walls, or rate limit pages.

**When rate limiting is detected:**
1. Skip the current scrape (do NOT record zero metrics)
2. Track consecutive rate limits per platform
3. After 3 consecutive rate limits on a platform, pause all scraping for that platform for 1 hour
4. Resume automatically after the cooldown

### Duplicate Prevention

The same metric values should not be billed twice. The billing system must check if a metric has already been processed before creating a new earning record.

### Edge Cases

- Post gets 0 likes and 0 comments (brand new post) → store zeros, this IS valid data (different from deletion)
- Reddit score goes negative → store as-is, negative scores are valid
- Scraper finds engagement numbers but the page is still loading → wait for page to fully load before extracting
- Platform changes their UI → metric extraction returns all zeros. This should trigger a warning, not silent billing of $0.

### Acceptance Criteria

1. Delete a post on X. Run the scraper. The post is marked as "deleted" in the database. No zero-metric row is stored. Future scraping skips this post. _(N/A while X disabled; test equivalent on LinkedIn/Facebook/Reddit)_
2. A post with 0 likes and 0 comments (real post, just no engagement). Scraper stores the zeros correctly. This is valid data.
3. Platform rate limits the scraper 3 times in a row. Scraping for that platform pauses for 1 hour. Other platforms continue normally.
4. Same metric data submitted to the server twice. Only one earning record is created (no duplicates).
5. Server is notified about a deleted post. Pending earnings for that post are voided. Funds return to the campaign budget.
