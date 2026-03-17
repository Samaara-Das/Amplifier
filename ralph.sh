#!/bin/bash

# Ralph — autonomous task loop for Auto-Posting System
# Usage: ./ralph.sh [max_iterations]
#
# Runs Claude Code CLI in a loop, picking one task per iteration,
# implementing it, verifying it, committing, and moving to the next.

MAX_ITERATIONS=${1:-20}
DONE_SIGNAL="RALPH_ALL_TASKS_COMPLETE"
LOG_DIR="ralph_logs"
ITERATION=1

mkdir -p "$LOG_DIR"

echo "========================================="
echo " Ralph — Auto-Poster Task Runner"
echo " Max iterations: $MAX_ITERATIONS"
echo " Logs: $LOG_DIR/"
echo "========================================="

# Unset CLAUDECODE to allow nested CLI calls
unset CLAUDECODE

while [ $ITERATION -le $MAX_ITERATIONS ]; do
    LOG_FILE="$LOG_DIR/iteration-$ITERATION.log"
    START_TIME=$(date +%s)

    echo ""
    echo "==========================================="
    echo " ITERATION $ITERATION/$MAX_ITERATIONS — $(date '+%H:%M:%S')"
    echo "==========================================="

    claude --dangerously-skip-permissions --verbose -p "
You are Ralph, an autonomous coding agent for the Auto-Posting System.

IMPORTANT: Print a status line before each major step so progress is visible.

## Your Goal
Implement Task 17 (Updated Auto-Poster Workflow) one subtask at a time.
Each iteration you pick ONE subtask, implement it fully, verify it, commit it, and stop.

## Setup (every iteration)
1. Print: 'RALPH: Reading context...'
   Read .claude/task-context.md for full project context and task list.
2. Print: 'RALPH: Checking task progress...'
   Read .claude/ralph-tasks.md to see which subtasks are done and which are next.
3. Pick the first subtask with status '[ ]' (not done). If ALL are '[x]', output exactly: $DONE_SIGNAL

## Implementation Rules
- Read every file you plan to edit BEFORE editing it. Understand existing code first.
- Follow existing code patterns — match the style of post.py, generate.ps1, draft_manager.py.
- Do NOT create new files unless absolutely necessary. Prefer editing existing files.
- Do NOT add tests (no test suite exists). Verify by running: python -c 'import scripts.post' or similar import checks.
- Do NOT refactor code you didn't change.
- Do NOT add docstrings, comments, or type hints to code you didn't write.
- Keep changes minimal and focused on the subtask.
- All content must target US audience. No Indian references, IST in user-facing content, or rupees.

## Key Files Reference
- scripts/post.py — Main poster orchestrator + all 6 platform posting functions
- scripts/generate.ps1 — PowerShell content generator (calls Claude CLI)
- scripts/review_dashboard.py — Flask review app (localhost:5111)
- scripts/utils/draft_manager.py — Draft lifecycle management
- scripts/utils/human_behavior.py — Anti-detection behaviors
- scripts/utils/image_generator.py — Image/video generation (Pillow, moviepy)
- scripts/setup_scheduler.ps1 — Windows Task Scheduler registration
- config/platforms.json — Platform URLs, enable flags, proxy config, subreddits
- config/content-templates.md — Brand voice, pillars, format rules
- config/.env — Timing and behavior config
- docs/auto-poster-workflow.md — THE complete E2E workflow specification

## Platform Selector Gotchas (DO NOT CHANGE working selectors)
- X: dispatch_event('click') on post button (overlay intercepts pointer)
- LinkedIn: locator().wait_for() (pierces shadow DOM), NOT wait_for_selector()
- Reddit: Shadow DOM faceplate — Playwright locators pierce automatically
- TikTok: Draft.js editor — Ctrl+A → Backspace to clear, then type. Needs VPN.
- Instagram: force=True on all buttons (overlay intercepts)
- Facebook: Standard selectors work

## After Implementation
1. Print: 'RALPH: Verifying...'
   Run a quick verification (python syntax check, import check, or similar)
2. Print: 'RALPH: Updating task list...'
   Edit .claude/ralph-tasks.md — change the completed subtask from '[ ]' to '[x]'
   Add a one-line note of what was done.
3. Print: 'RALPH: Committing...'
   Stage only the files you changed (not ralph_logs/).
   Commit with message: 'feat(ralph): <what was done>'
   Push to origin main.
4. Print: 'RALPH: Iteration complete.'
   Stop. Do NOT start the next subtask — the loop handles that.
" 2>&1 | tee "$LOG_FILE"

    END_TIME=$(date +%s)
    ELAPSED=$(( END_TIME - START_TIME ))
    echo ""
    echo "--- Iteration $ITERATION finished in ${ELAPSED}s (log: $LOG_FILE) ---"

    if grep -q "$DONE_SIGNAL" "$LOG_FILE"; then
        echo ""
        echo "========================================="
        echo " All subtasks complete!"
        echo "========================================="
        break
    fi

    ((ITERATION++))
    sleep 5
done

echo ""
echo "========================================="
echo " Ralph finished after $((ITERATION)) iterations"
echo " Logs saved in $LOG_DIR/"
echo "========================================="
