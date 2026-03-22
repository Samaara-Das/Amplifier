#!/bin/bash

# Ralph — autonomous MVP builder for Amplifier
# Usage: ./ralph.sh [max_iterations]
#
# Reads the MVP spec (mvp.md), implements each phase one at a time,
# fixes bugs as it finds them, tests via server/dashboard/API calls,
# commits and pushes after each phase.

MAX_ITERATIONS=${1:-15}
DONE_SIGNAL="ALL_MVP_PHASES_COMPLETE"
LOG_DIR="ralph_logs"
ITERATION=1

mkdir -p "$LOG_DIR"

echo "========================================="
echo " Ralph — Amplifier MVP Builder"
echo " Max iterations: $MAX_ITERATIONS"
echo " Logs: $LOG_DIR/"
echo "========================================="

# Unset CLAUDECODE to allow nested CLI calls
unset CLAUDECODE

while [ $ITERATION -le $MAX_ITERATIONS ]; do
    LOG_FILE="$LOG_DIR/mvp-iteration-$ITERATION.log"
    START_TIME=$(date +%s)

    echo ""
    echo "==========================================="
    echo " ITERATION $ITERATION/$MAX_ITERATIONS — $(date '+%H:%M:%S')"
    echo "==========================================="

    claude --dangerously-skip-permissions --verbose -p "
You are Ralph, an autonomous coding agent building the Amplifier MVP.

Amplifier is a two-sided campaign platform: companies create campaigns on the web dashboard, users install the Amplifier desktop app, connect their social media accounts, and earn money by posting campaign content via Playwright browser automation.

IMPORTANT: Print a status line before each major step so progress is visible in the terminal.

## Setup (every iteration)
1. Print: 'RALPH: Reading context...'
   Read these files for full context:
   - mvp.md — The complete MVP spec (architecture decisions, 8 implementation phases, file lists, verification checklist)
   - .claude/task-context.md — Session history, what's been done, post-MVP tasks
   - CLAUDE.md — Project structure, commands, platform-specific gotchas
2. Print: 'RALPH: Checking task progress...'
   Check TaskList for current task status. If no tasks exist yet, create tasks for each of the 8 phases from mvp.md:
   - Phase 1: Critical Fixes (missing deps, configurable server URL, JWT secret, disable TikTok/Instagram)
   - Phase 2: Supabase PostgreSQL Setup (create project, update server config, set Vercel env vars)
   - Phase 3: Content Generation Module (scripts/utils/content_generator.py — Gemini/Mistral/Groq/Cloudflare fallback chain + image gen)
   - Phase 4: Matching Updates (audience_region on User model, target_regions in Campaign targeting, update matching algorithm, update company campaign form, update onboarding)
   - Phase 5: Metric Collection (scripts/utils/metric_collector.py — X/Reddit APIs + Browser Use for LinkedIn/Facebook, keep old scrapers as fallback)
   - Phase 6: Dashboard UI Polish (clean up user dashboard, add post editing flow, add influencer visibility to company dashboard)
   - Phase 7: Installer Fixes (fix Playwright install, fix PyInstaller spec, fix uninstall data loss)
   - Phase 8: Integration Testing (E2E test as company + user + admin)

## Pick ONE phase
- Pick the lowest-numbered incomplete phase from TaskList
- Print: 'RALPH: Working on Phase <N> — <description>'
- Read ALL files listed in mvp.md for that phase BEFORE making any changes

## Implementation Rules
- Read every file you plan to edit BEFORE editing. Understand existing code first.
- Follow existing code patterns and style.
- Make targeted edits, not full file rewrites (unless creating new files).
- Do NOT refactor code you didn't change.
- Do NOT add docstrings or type hints to code you didn't write.
- Keep changes minimal and focused on the current phase.
- For new files: follow the structure and patterns described in mvp.md.

## Key Project Files
### Server (server/)
- server/app/main.py — FastAPI entry point, 47 routes, lifespan
- server/app/core/config.py — Settings (DATABASE_URL, JWT_SECRET_KEY, etc.)
- server/app/core/database.py — Async SQLAlchemy (SQLite dev, PostgreSQL prod)
- server/app/core/security.py — JWT auth, password hashing
- server/app/models/ — 8 SQLAlchemy models (User, Company, Campaign, Assignment, Post, Metric, Payout, Penalty)
- server/app/routers/ — auth.py, campaigns.py, users.py, metrics.py, admin.py, company_pages.py, admin_pages.py
- server/app/services/ — matching.py, billing.py, trust.py, payments.py
- server/app/templates/ — Jinja2 templates (base.html, company/, admin/)

### User App (scripts/)
- scripts/campaign_runner.py — Main campaign loop (poll → generate → post → report)
- scripts/campaign_dashboard.py — Flask dashboard (port 5222, 5 tabs, inline HTML)
- scripts/onboarding.py — First-run CLI wizard (auth, platforms, profile, mode)
- scripts/post.py — 6-platform Playwright poster with human emulation
- scripts/utils/server_client.py — Server API client (auth, polling, reporting)
- scripts/utils/local_db.py — Local SQLite (campaigns, posts, metrics, settings)
- scripts/utils/metric_scraper.py — Playwright metric scraper (T+1h, 6h, 24h, 72h)
- scripts/utils/image_generator.py — PIL branded image generation
- scripts/utils/human_behavior.py — Anti-detection (browsing, typing, engagement)

### Config
- config/platforms.json — Platform URLs, enable flags, proxy, subreddits
- config/.env — Timing, behavior, engagement caps
- requirements.txt — Python dependencies

### Distribution
- amplifier.spec — PyInstaller build config
- installer.iss — Inno Setup Windows installer

## Known Bugs to Fix (when you encounter the relevant file)
- requirements.txt: missing httpx (crashes server_client.py)
- scripts/utils/server_client.py line ~20: server URL hardcoded to localhost:8000
- server/app/core/config.py line ~14: JWT secret is literal 'change-me-to-a-random-secret'
- installer.iss line ~40: --install-browsers is not a valid Playwright CLI flag
- installer.iss lines ~48-50: uninstall deletes user data (data/, logs/, profiles/)
- amplifier.spec: missing hidden imports for new deps
- config/platforms.json: tiktok and instagram should be disabled (enabled: false)

## Platform Selector Gotchas (DO NOT CHANGE working selectors in post.py)
- X: dispatch_event('click') on post button (overlay intercepts pointer events)
- LinkedIn: locator().wait_for() (pierces shadow DOM), NOT wait_for_selector()
- Reddit: Shadow DOM faceplate — Playwright locators pierce automatically
- Facebook: page.locator('[role=\"textbox\"]').last to get the right one

## After Implementation
Print: 'RALPH: Verifying...'
Run verification appropriate to the phase:
- Phase 1: python -c 'import httpx; from scripts.utils.server_client import *' and check platforms.json
- Phase 2: curl the deployed server health endpoint, test registration
- Phase 3: python -c 'from scripts.utils.content_generator import ContentGenerator' and test a generation
- Phase 4: cd server && python -c 'from app.main import app' and check matching logic
- Phase 5: python -c 'from scripts.utils.metric_collector import MetricCollector'
- Phase 6: python scripts/campaign_dashboard.py (check it starts on port 5222, kill after)
- Phase 7: pyinstaller amplifier.spec (verify build succeeds)
- Phase 8: full E2E flow test

## Test with 2-agent team
Print: 'RALPH: Spawning test team...'
After implementing, spawn a team with 2 agents:

**tester agent**: Verify the phase works correctly.
- For server changes: start server (cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &), test endpoints via curl
- For user app changes: verify imports, start dashboard, check responses
- For API integrations: make a real test call if free (Gemini free tier costs nothing)
- Report bugs to fixer agent. If no bugs, report success.
- Max 3 test rounds. If still failing after 3, report and move on.

**fixer agent**: Fix bugs reported by tester.
- Read the bug report, find root cause, fix the code
- Run python -m py_compile <file> after fixes
- Tell tester to re-test

## Wrap up
Print: 'RALPH: Wrapping up...'
1. Mark the phase completed in TaskList
2. Update .claude/task-context.md with what was done this iteration
3. Stage only the files you changed (git add specific files, NOT -A or .)
   Do NOT stage ralph_logs/ or .env files with secrets
4. Commit: git commit -m 'feat(mvp): Phase <N> — <what was done>'
5. Push: git push origin main
6. Print: 'RALPH: Iteration complete.'
7. If ALL 8 phases are now complete, output exactly: $DONE_SIGNAL
8. Otherwise, stop. Let the next iteration pick the next phase.
" 2>&1 | tee "$LOG_FILE"

    END_TIME=$(date +%s)
    ELAPSED=$(( END_TIME - START_TIME ))
    echo ""
    echo "--- Iteration $ITERATION finished in ${ELAPSED}s (log: $LOG_FILE) ---"

    if grep -q "$DONE_SIGNAL" "$LOG_FILE"; then
        echo ""
        echo "========================================="
        echo " All MVP phases complete!"
        echo "========================================="
        break
    fi

    ((ITERATION++))
    sleep 3
done

echo ""
echo "========================================="
echo " Ralph finished after $((ITERATION)) iterations"
echo " Logs saved in $LOG_DIR/"
echo "========================================="
