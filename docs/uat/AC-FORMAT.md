# Acceptance Criteria & UAT Verification Format

**Purpose**: Every remaining task in `docs/specs/batch-*.md` gets a `### Verification Procedure` block in this format. The `/uat-task <id>` slash command reads that block and drives the **real product** — real server, real database, real Playwright browsers, real AI calls — to confirm each criterion. No mocks, no test-only shortcuts, no "if the unit test passes I'm done."

---

## Core principles

1. **Test the user's product, not the code.** The bar is: "if I followed these steps as a user, would the feature work?" — not "do the unit tests pass."
2. **Every AC has an observable result.** A log line, a DB row, a DOM element, a screenshot, an HTTP response, a console message, a network request. If you can't observe it, the AC is wrong.
3. **State the setup explicitly.** Don't say "given a campaign exists" — say "POST /api/campaigns with this exact payload."
4. **Test-mode overrides are allowed.** If a feature runs daily, ship a `--test-interval=120s` flag so UAT can exercise it in a few minutes. The override must be code, in the repo, reviewed at PR time. Not "comment out the sleep."
5. **Manual verification is allowed but bounded.** When subjective ("does this sound human?"), the skill surfaces the artifact (screenshot, generated text) in chat and asks the user a yes/no. The user spends 30 seconds, not 10 minutes.
6. **No X testing.** X is disabled (Task #40). UAT runs use LinkedIn, Facebook, Reddit only. The skill refuses any AC that touches `platform=x`.
7. **Cleanup after every run.** UAT creates a test campaign, runs, then voids it. No accumulated test data in production.
8. **Two browser tools, two jobs.** Chrome DevTools MCP drives the verifier (testing the product as a user). Playwright drives the product itself (posting, scraping, login). Never mix.

## Tool boundaries — what drives what

| Layer | Tool | Why |
|-------|------|-----|
| **Product automation** (posting to LinkedIn/FB/Reddit, scraping profiles, browser logins) | **Playwright** with persistent profiles | Anti-detection, human emulation, profile cookies, image upload — Playwright owns this. It IS the product. |
| **UAT verification of the product** (drive the user app at localhost:5222, drive company dashboard, drive admin dashboard, snapshot the DOM, read console errors, inspect network) | **Chrome DevTools MCP** (`mcp__chrome-devtools__*` tools) | Direct observational tools: `take_snapshot` returns DOM with UIDs I can click, `list_console_messages` catches JS errors, `list_network_requests` proves what was fetched, `take_screenshot` is one call. No script to maintain — the AC text describes the action, the skill executes it via DevTools tools. |
| **Server API verification** (POST/GET against api.pointcapitalis.com) | `curl` or Python `httpx` | Faster than driving a browser when the AC is "endpoint returns this JSON". |
| **DB state verification** | Direct SQL via Python | The truth is in the rows, not the screen. |
| **Log inspection** | `grep` / `tail` on log files | Phase-completion log lines are the contract. |

---

## Block structure

Every task spec ends with one block exactly like this:

```markdown
## Verification Procedure — Task #<id>

**Preconditions** (must hold before any AC runs):
- <e.g., server running at https://api.pointcapitalis.com>
- <e.g., test company seeded with email test-company@uat.local>
- <e.g., user app installed at C:\Users\dassa\Work\Auto-Posting-System with .venv set up>

**Test data setup** (run once at start of UAT for this task):
- <exact API call or SQL or CLI command to seed the state>
- <e.g., `python scripts/uat/seed_campaign.py --goal=brand_awareness --tone=casual`>

**Test-mode flags** (env vars / CLI flags introduced for UAT only):
- <e.g., `AMPLIFIER_UAT_INTERVAL_SEC=120` shortens content-gen loop from daily to every 2 min>

---

### AC<n>: <one-sentence criterion>

| Field | Value |
|-------|-------|
| **Setup** | <exact state to reach before action — bullet list> |
| **Action** | <exact command, click, or API call to perform> |
| **Expected** | <exact observable result> |
| **Automated** | yes / no / partial |
| **Automation** | <pytest path::name> OR <Playwright script path> OR `manual` |
| **Evidence** | <screenshot path>, <log file + grep>, <SQL query + expected rows>, or <curl + expected JSON> |
| **Cleanup** | <state to revert after this AC, if any> |

---

### Aggregated PASS rule

A task is marked done in task-master ONLY when:
- Every AC reports PASS
- No errors in `~/.amplifier/logs/agent.log` or `server/server.log` during the UAT window
- No new rows in `audit_log` with `severity='error'` during the window
- All cleanup steps executed
```

---

## Worked example — Task #14 Phase 1 (Research)

This is what a complete AC block looks like in practice. The full Task #14 spec will have ~12 ACs covering all 4 phases, but here are 3 that demonstrate the format covering all three verification styles (full automated, partial, manual).

```markdown
## Verification Procedure — Task #14

**Preconditions**:
- Server live at https://api.pointcapitalis.com (verify: `curl https://api.pointcapitalis.com/health` → `{"status":"ok"}`)
- Local user app on flask-user-app branch with config/.env containing GEMINI_API_KEY
- LinkedIn, Facebook, Reddit profiles connected (verify: `python -c "from scripts.utils.local_db import get_user_profiles; print(get_user_profiles(['linkedin','facebook','reddit']))"` returns non-empty list per platform)
- Local SQLite has zero rows in agent_research and agent_draft for the test campaign id (will be created in setup)

**Test data setup**:
1. Create UAT campaign on server with known-good payload:
   ```bash
   python scripts/uat/seed_campaign.py \
     --title "UAT Trading Indicator Test" \
     --goal brand_awareness \
     --tone casual \
     --brief "A TradingView indicator that shows institutional order flow on SPY and QQQ. Built for day traders who want to see what smart money is doing before the move happens. Free for the first 100 users." \
     --guidance "Mention you've been testing it for a week. Be casual, not salesy." \
     --company-urls "https://www.tradingview.com/script/example/" \
     --product-images "data/uat/product1.jpg,data/uat/product2.jpg" \
     --output-id-to data/uat/last_campaign_id.txt
   ```
2. Force-accept the invitation as the test user (skips the matching delay):
   ```bash
   python scripts/uat/accept_invitation.py --campaign-id $(cat data/uat/last_campaign_id.txt)
   ```
3. Truncate research cache so we test cold path:
   ```bash
   python -c "from scripts.utils.local_db import _get_db; c=_get_db(); c.execute('DELETE FROM agent_research WHERE campaign_id=?',(int(open('data/uat/last_campaign_id.txt').read()),)); c.commit()"
   ```

**Test-mode flags**:
- `AMPLIFIER_UAT_INTERVAL_SEC=120` — overrides the 24h research-cache TTL and the daily content-gen interval. Set in scripts/uat/run_agent.sh. Code-side: `content_agent.py` reads this env var, falls back to 7-day TTL when unset.
- Background agent loop interval drops from 120s to 30s when this flag is set.

---

### AC1: Phase 1 (Research) successfully scrapes company URL and synthesizes structured research

| Field | Value |
|-------|-------|
| **Setup** | Test data setup completed. Background agent NOT running yet. |
| **Action** | Start background agent: `python scripts/background_agent.py --once --campaign-id $(cat data/uat/last_campaign_id.txt) 2>&1 | tee data/uat/agent.log` |
| **Expected** | Within 60s: log contains `Phase 1 (Research) complete: N angles` where N >= 3. agent_research table has exactly 1 row with `research_type='full_research'` and content is valid JSON with non-empty keys: product_summary, key_features (>=3), target_audience, content_angles (>=3), emotional_hooks (>=3). |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task14.py::test_ac1_research_phase --campaign-id $(cat data/uat/last_campaign_id.txt)` |
| **Evidence** | data/uat/agent.log (grep "Phase 1"), SQL: `SELECT length(content), created_at FROM agent_research WHERE campaign_id=? AND research_type='full_research'` (expect 1 row, length > 500) |
| **Cleanup** | none (research cache valid for downstream ACs) |

### AC2: Phase 1 fetches recent niche news via Gemini grounded search

| Field | Value |
|-------|-------|
| **Setup** | AC1 passed. agent_research row exists with full_research content. |
| **Action** | Read the cached research JSON: `python -c "import json,sqlite3; c=sqlite3.connect('data/local.sqlite'); r=c.execute('SELECT content FROM agent_research WHERE campaign_id=?',(int(open('data/uat/last_campaign_id.txt').read()),)).fetchone(); print(json.loads(r[0]).get('recent_niche_news'))"` |
| **Expected** | Returns a JSON array with 3-5 string elements. Each element is a plausible-looking headline (not empty, not a fence error, contains words like "market"/"trading"/"stock"/"Fed"/"earnings" — niche-appropriate). |
| **Automated** | partial — automated checks for shape (3-5 strings, non-empty); manual eyeball check for plausibility |
| **Automation** | `pytest scripts/uat/uat_task14.py::test_ac2_niche_news` (shape only) |
| **Evidence** | Console output of the python one-liner, captured to data/uat/ac2_news.txt. Manual review: user reads the headlines and confirms they're real-niche, not random or AI-fabricated. The slash command shows the headlines and asks: "Are these plausible niche headlines? (y/n)" |
| **Cleanup** | none |

### AC3: Phase 3 generates Reddit content with mandatory caveat (real human authenticity rule)

| Field | Value |
|-------|-------|
| **Setup** | AC1 passed. Strategy phase has run (cached). agent_draft has zero reddit rows for this campaign (`DELETE FROM agent_draft WHERE campaign_id=? AND platform='reddit'`). |
| **Action** | Force a daily content-gen cycle: `python scripts/background_agent.py --task=generate_content --campaign-id $(cat data/uat/last_campaign_id.txt) --day-number 1` |
| **Expected** | agent_draft has 1 reddit row. The draft_text is a JSON string parseable to `{"title": str, "body": str}`. title length 60-120 chars. body length 500-2500 chars. body contains at least one of: "didn't love", "not perfect", "one thing", "downside", "limitation", "wish", "missing", "but" used in a caveat sense (regex: `(?i)(didn't love|wasn't a fan|one (downside|drawback|thing)|to be fair|not perfect|the only|that said)`). |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task14.py::test_ac3_reddit_caveat` |
| **Evidence** | SQL row content, grep result of caveat regex, full draft body printed to data/uat/ac3_reddit.txt for human eyeball |
| **Cleanup** | none |

### AC4: Full E2E — campaign accepted on web, drafts appear in user app within 5 min

| Field | Value |
|-------|-------|
| **Setup** | All prior ACs passed. Local Flask user app running at http://localhost:5222 (started by `python scripts/user_app.py` in background). Background agent running with `AMPLIFIER_UAT_INTERVAL_SEC=120`. |
| **Action** | Drive the user app via Chrome DevTools MCP: `new_page("http://localhost:5222/campaigns")` → `take_snapshot` to get DOM UIDs → `click(uid_of_login_button)` if redirected → `fill_form(login fields with test creds)` → `take_snapshot` again, find the UAT campaign card by title text → `click(uid_of_campaign_card)` → `wait_for(text="Drafts", timeout=300_000)` → `take_screenshot(filePath="data/uat/screenshots/task14_ac4_campaign_detail.png")` |
| **Expected** | Within 5 min wall-clock, the campaign detail page shows 3 draft cards (one per active platform: linkedin, facebook, reddit). Each draft card shows non-empty content. Reddit draft renders title + body separately. No "Generation failed" badge. `list_console_messages` returns zero error-level messages. `list_network_requests` shows no 5xx responses from /api/. |
| **Automated** | yes |
| **Automation** | `chrome-devtools-mcp` (no script file needed — skill executes the tool sequence based on this AC block) |
| **Evidence** | data/uat/screenshots/task14_ac4_campaign_detail.png embedded in report. data/uat/agent.log grep "Phase 3 (Creation) complete: 3 platform(s)". Console messages JSON dump. Network requests JSON dump showing only 2xx/3xx for /api/. |
| **Cleanup** | Stop background agent (kill -INT). Stop user app. Mark UAT campaign as completed: `python scripts/uat/cleanup_campaign.py --id $(cat data/uat/last_campaign_id.txt)`. `close_page` on all DevTools-opened pages. |

---

### Aggregated PASS rule for Task #14

- AC1, AC2 (auto), AC3, AC4 PASS
- AC2 manual: user confirms "y" on plausibility prompt
- agent.log contains zero lines matching `(?i)error|exception|traceback` (warnings are OK)
- agent_research has exactly 2 rows (full_research + strategy)
- agent_draft has 3 rows (one per active platform), all with `approved=0` (semi_auto mode default)
- No exceptions in server.log during the UAT window
```

---

## What the slash command does (preview)

`/uat-task 14` will:

1. Parse `docs/specs/batch-2-ai-brain.md` for the `## Verification Procedure — Task #14` block
2. Run **Preconditions** checks — abort if any fail
3. Run **Test data setup** — abort if any step errors
4. For each AC in order:
   a. Run the **Automation** command (pytest, python script, or Playwright script)
   b. Capture **Evidence** files and log excerpts
   c. For partial/manual ACs, render the artifact (screenshot, generated text) in the chat and ask the user yes/no
5. Run the **Aggregated PASS rule**
6. Write `docs/uat/reports/task-14-2026-04-25.md` with PASS/FAIL per AC, screenshot embeds, log excerpts
7. Run **Cleanup** unconditionally (even on partial fail)
8. If all PASS, propose: `task-master set-status --id=14 --status=done`. Does NOT auto-mark — user confirms.

---

## What lives where

| File | Purpose |
|------|---------|
| `docs/specs/batch-N-*.md` | Per-task spec for product batches (Money Loop, AI Brain, Product Features, Business Launch). Each task ends with `## Verification Procedure — Task #<id>` block. |
| `docs/specs/infra.md` | Per-task spec for server-side infra tasks outside the 4 batches (e.g. #44 ARQ worker, #45 Alembic baseline). Same Verification-Procedure format. The skill should glob `docs/specs/*.md` (not just `batch-*.md`) when locating a task's spec. |
| `docs/uat/AC-FORMAT.md` | This file. Rules for the AC block. |
| `docs/uat/reports/task-<id>-<yyyy-mm-dd>.md` | Generated UAT report per run. Committed to git so we have a history. |
| `scripts/uat/uat_task<id>.py` | pytest file with the automated AC checks. One per task. |
| `scripts/uat/seed_campaign.py` | Reusable test-data seeder (creates a campaign on the server). |
| `scripts/uat/accept_invitation.py` | Force-accept a campaign invitation as the test user. |
| `scripts/uat/cleanup_campaign.py` | Mark a UAT campaign completed + delete local drafts. |
| ~~`scripts/uat/playwright_drive_user_app.py`~~ | Removed — Chrome DevTools MCP replaces these. UI verification logic lives in the AC block itself, executed by the skill. |
| `scripts/uat/run_agent.sh` | Helper that exports `AMPLIFIER_UAT_INTERVAL_SEC=120` then launches the background agent. |
| `data/uat/` | All UAT outputs: screenshots, logs, artifact files. Gitignored. |

---

## Test-mode flags — the rule

These are **production code**, behind env vars or CLI flags, reviewed at PR time. They are NOT comments-out, NOT branches, NOT one-off scripts. The principle:

- The flag exists for UAT and for nothing else
- The flag is named `AMPLIFIER_UAT_*` so it's grep-able and obvious
- The flag's effect is documented in the test-mode flags section of every task that uses it
- Default behavior (flag unset) is the production behavior

Approved flags:
- `AMPLIFIER_UAT_INTERVAL_SEC` — shortens any "every N hours" loop to N seconds
- `AMPLIFIER_UAT_BYPASS_AI` — forces the fallback path in any AI-call function (proves fallback works)
- `AMPLIFIER_UAT_FAKE_METRICS` — injects a metric row directly without scraping (proves billing without waiting for real engagement)

Adding a new flag requires updating this file.
