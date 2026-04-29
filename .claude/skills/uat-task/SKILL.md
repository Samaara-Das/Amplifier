---
name: uat-task
description: "Run end-to-end User Acceptance Testing for an Amplifier task by ID. Use this skill ANY time the user invokes it as `/uat-task <id>` or asks to verify, UAT, acceptance-test, or end-to-end test a task — never improvise UAT without this skill. Drives the real product (real server, real DB, real Chrome DevTools MCP browser, real AI calls), reads the task's Verification Procedure block from docs/specs/, executes each AC, captures evidence, writes a report to docs/uat/reports/, and refuses to mark the task done unless every AC passes."
---

# uat-task — Real-Product UAT Verifier

Verify Amplifier task-master tasks against their `## Verification Procedure` block in `docs/specs/*.md` (search both `batch-*.md` for product tasks and `infra.md` for server-side infra tasks like #44/#45). Drive the real product. Capture evidence. Write a report. Refuse to mark done unless every AC passes.

This skill is the single entry point for verifying any task. It compounds: every mistake the user catches becomes a learning in `LEARNINGS.md` that future runs read first.

---

## STEP 0 — Read these files in this exact order, every invocation

Before doing anything else:

1. `docs/uat/skills/uat-task/LEARNINGS.md` — past corrections from the user. Apply them. They override default behavior. If the file is empty, that's fine — it grows over time.
2. `docs/uat/AC-FORMAT.md` — the format spec for `## Verification Procedure` blocks. The contract this skill executes against.
3. `docs/specs/*.md` (glob both `batch-*.md` and `infra.md`) — locate the requested task's `## Verification Procedure — Task #<id>` block. Use Grep with pattern `## Verification Procedure — Task #<id>` across the whole `docs/specs/` directory. If not found, abort: "No Verification Procedure block exists for Task #<id>. Backfill it in docs/specs/ first, then re-run."

If the user says "learning: <something>" at any point during a run, immediately append a new entry to `LEARNINGS.md` in the format below, then continue. Do not wait until the end.

```markdown
## YYYY-MM-DD — short title

**Mistake**: what the skill did wrong
**Correction**: what the skill should do instead
**Trigger**: when this learning applies (e.g., "any AC that involves background agent")
```

---

## Hard rules

These are non-negotiable. Violating any of them is a critical bug — surface it immediately.

**0. Screenshots are proof. Take them everywhere.** The user reviews screenshots as evidence that UAT actually happened. Without them the report is just text claiming success — which is exactly the failure mode this skill exists to prevent. Rules:

- **Every AC that touches a UI must produce at least one screenshot** via `mcp__chrome-devtools__take_screenshot` saved to `data/uat/screenshots/task<id>_ac<n>_<descriptor>.png`. Multiple screenshots when state changes (before action, after action, after wait).
- **Every AC that produces a DB-level artifact (drafts, research rows) must screenshot the relevant UI rendering of that artifact** — i.e., AC6 generated drafts → take a screenshot of the campaign detail page in the user app showing those drafts; AC8 day-5 drafts → screenshot the drafts panel showing them.
- **Phase boundaries get screenshots too** — after Phase 2 setup, after each agent run completes, before final cleanup. These prove environment state at each transition.
- **Every screenshot is embedded in the report** as `![AC<n> — <descriptor>](../../data/uat/screenshots/<file>.png)`. Relative path so the report renders correctly in any markdown viewer (GitHub, VS Code, Obsidian).
- **Screenshot naming convention**: `task<id>_ac<n>_<state>.png` where `<state>` is one of `before`, `after`, `final`, `error`, `precondition`, `setup`, plus a short suffix when multiple are needed (e.g., `task14_ac14_drafts_visible.png`, `task14_ac14_login_page.png`).
- **If a UI screenshot literally cannot be taken** (the AC is purely DB or log state, no UI rendering exists), the report's Evidence field for that AC must say `screenshots: N/A — <reason>`. Default is screenshots ARE possible; the burden of proof is on the skill to justify their absence.
- **Manual ACs include the screenshot in chat too**, not just the report. When asking the user yes/no, render the screenshot inline so they can see what they're approving.

1. **Real product testing only.** No mocks except where the AC's `Automation` field explicitly names a mocked test (e.g., AC12 "the only AC with controlled mocking"). All other ACs must use real Gemini calls, real DB writes, real Chrome DevTools MCP browser automation against real running servers/apps.

2. **Two browser tools, two jobs.** Chrome DevTools MCP (`mcp__chrome-devtools__*`) drives the **verifier** — testing the product as a user. Playwright drives the **product** itself (the agent's own posting/scraping). Never use Playwright for verification. Never use Chrome DevTools MCP for product automation.

3. **No X testing.** X (Twitter) is disabled (Task #40, since 2026-04-14). If any AC references `platform=x` in a posting/scraping context, skip it and write `SKIPPED: X disabled` in the report. Do not enable X to "test it once."

4. **No production writes without `--allow-prod`.** By default, the skill operates against local SQLite + a UAT-marked test campaign on the live server (which gets voided in cleanup). Cleanup steps that would alter non-UAT data (delete real campaigns, modify real users, drop tables, run migrations) require the user to have invoked the skill with `--allow-prod`. If you encounter a step that needs prod write access without the flag, abort and ask explicitly.

5. **Test-mode flags are real code.** The flags listed in the AC block's "Test-mode flags" section (e.g., `AMPLIFIER_UAT_INTERVAL_SEC=120`, `AMPLIFIER_UAT_BYPASS_AI=1`, `AMPLIFIER_UAT_FORCE_DAY=<n>`) must be set as environment variables on the relevant subprocess. Never comment out code, never `time.sleep(0)` something, never edit a constant temporarily. If a flag the AC requires isn't supported in code yet, abort with: "AC<n> requires `<flag>` which the code doesn't read yet. Add the env-var read in <file>:<line>, then re-run."

6. **Cleanup is mandatory and unconditional.** Even on partial fail, even on abort, run the AC's Cleanup steps and the task-level cleanup (kill background agent process, kill user app on port 5222, void the test campaign, close DevTools pages). Use `try/finally`-style execution. Never accumulate test data.

7. **Stop on AC1 failure unless ACs are independent.** Most ACs build on each other (research cache from AC1 is needed for AC5, etc.). If AC<n> fails and downstream ACs depend on its state, mark them `BLOCKED` rather than running them on a broken substrate. The AC block's Setup field tells you what state each AC requires.

8. **Manual ACs are bounded.** When an AC is `Automated: partial` or `manual`, surface the artifact (screenshot embedded as image, generated text in a code block, JSON dump in a fence) directly in chat with a single clear yes/no question. Never make the user dig through files. If they answer 'n', mark FAIL, save the artifact, continue.

---

## Execution flow

Walk through these phases in order. Communicate clearly at each phase boundary so the user can interrupt if needed.

### Phase 1 — Parse inputs and locate the AC block

- Parse the task ID from the user's invocation. Accept `14`, `#14`, `task 14`, `task #14`. Reject anything else with a usage message.
- Parse optional flags: `--allow-prod`, `--skip-cleanup` (debugging only, warn loudly), `--ac <n>` (run a single AC for fast iteration).
- Read LEARNINGS.md, AC-FORMAT.md, then locate the spec block via Grep: `## Verification Procedure — Task #<id>` across `docs/specs/*.md` (covers `batch-*.md` for product tasks and `infra.md` for infra tasks).
- Parse the block: extract Preconditions, Test data setup, Test-mode flags, every AC table, Aggregated PASS rule.
- State plan in chat: "Found Task #<id> spec with N ACs. Preconditions: <count>. Test-mode flags: <list>. Proceeding with Phase 2 — Preconditions."

### Phase 2 — Preconditions

Execute every precondition check. Each is a Bash command or a Python one-liner. If any fails, abort with the specific failure and the precondition's source line. Do not auto-fix preconditions (don't auto-start a server, don't auto-connect platforms) — those are environment problems for the user to handle.

### Phase 3 — Test data setup

Run each setup step in order. Capture outputs to `data/uat/`. If a setup step's script doesn't exist (e.g., `scripts/uat/seed_campaign.py` not yet written), pause and ask the user:

> AC setup requires `<script>` which doesn't exist. Options:
> - **Skip** — abort UAT, don't mark task done
> - **Create now** — delegate to `amplifier-coder` to write the script per the AC block's command signature, then continue
> - **Stub** — create a minimal stub that does just enough to proceed (warn this may invalidate later ACs)

Default to **Create now** if the user says "go ahead" without specifying.

### Phase 4 — Run ACs in order

For each AC table:

1. Print `▶ Running AC<n>: <criterion>` to chat.
2. Verify the AC's Setup state (e.g., DB rows expected to exist do exist).
3. Run the Action. For:
   - **pytest / python script / curl / sqlite3** → use Bash, capture stdout+stderr to `data/uat/ac<n>_run.log`
   - **chrome-devtools-mcp** → execute the tool sequence described in the AC's Action field. Common pattern: `new_page` → `take_snapshot` → identify UID by visible text → `click`/`fill_form` → `wait_for` → `take_screenshot` → `list_console_messages` → `list_network_requests` → `close_page`. The AC's Action field describes the sequence in plain English; translate it to the tool calls.
4. Check the Expected field. Each item is an assertion. Evaluate every one. Capture evidence files listed in the Evidence field.
5. Mark PASS / FAIL / INCONCLUSIVE / BLOCKED / SKIPPED:
   - **PASS** — all expected assertions hold
   - **FAIL** — at least one expected assertion fails on observable evidence
   - **INCONCLUSIVE** — external dependency failed (Gemini rate limit, network timeout). Retry up to 3x with exponential backoff before marking INCONCLUSIVE.
   - **BLOCKED** — a prior AC's failure left the substrate broken; this AC can't run meaningfully
   - **SKIPPED** — explicit reason (X disabled, --ac filter excluded it)
6. Print `<AC<n>: PASS/FAIL — <one-line summary>` to chat.
7. Run the AC's Cleanup if specified.

For partial/manual ACs: render the artifact in chat, ask one yes/no question, capture the answer to the report.

### Phase 5 — Aggregated PASS rule

Run every check in the Aggregated PASS rule (log error grep, audit_log query, row count, cleanup verification). Compute the overall result:
- **PASS** = every AC PASS AND every aggregate check passes
- **PARTIAL** = some PASS some not, no critical errors
- **FAIL** = any AC FAIL or critical aggregate check fail

### Phase 6 — Write the report

Write `docs/uat/reports/task-<id>-<yyyy-mm-dd>-<hhmm>.md`. Include the `<hhmm>` so multiple runs in a day don't overwrite. Format per the template below.

**Every screenshot taken during the run must be embedded in this report.** Each AC's section embeds its own screenshots inline. The report's first section ("Screenshot index") lists every file with its path and one-line caption — so the user can scan all evidence at a glance without scrolling through every AC.

### Phase 7 — Mandatory cleanup

Run task-level cleanup unconditionally:
- Kill background agent (capture PID at Phase 3 start, `kill -INT $PID`)
- Free port 5222 (kill any python.exe owning it)
- Void the test campaign on the server (call `scripts/uat/cleanup_campaign.py --id <id>`)
- **Delete any UAT-published social-media posts** (see below)
- Close all Chrome DevTools MCP pages
- Unset any UAT env vars from this session

If any cleanup step fails, log it loudly and continue — but flag in the report's Cleanup section.

#### Deleting UAT-published posts (AC17 and similar)

When an AC publishes a real post to a real platform (e.g., AC17 posts to LinkedIn under the test user), the skill MUST delete it during cleanup. The captured `post_schedule.posted_url` is the source of truth. For each such URL:

1. `mcp__chrome-devtools__new_page(url=<posted_url>)` then `resize_page(1920, 1080)` (per LEARNINGS).
2. `take_snapshot` to find the post's overflow / "..." menu UID. Per platform:
   - **LinkedIn**: button labeled "Open control menu" or visible icon next to the post timestamp; opens a dropdown with "Delete post"
   - **Facebook**: three-dot menu on the post card; "Move to trash" or "Delete"
   - **Reddit**: meatball menu on the post; "Delete"
3. `click(uid)` on the menu trigger, take another `take_snapshot`, find "Delete" item, click.
4. Handle the confirmation dialog (Delete confirmation modal, "Delete" button) via another snapshot + click.
5. `take_screenshot` of the post-deletion state (e.g., a "this post has been deleted" or 404) as proof.
6. `close_page`.

### Introspection-driven selector discovery (use ANY time named selectors miss)

When you need to click/find/interact with an element on a third-party page (delete posts, dismiss dialogs, drive an external app) and your named selectors don't match — DO NOT keep guessing. Inspect the live DOM, then write the selector that matches what's actually there. This applies anywhere you'd otherwise stab in the dark.

How to do it in ~10 seconds:

1. Open the target URL with the right authenticated session (Chrome DevTools MCP if logged in there, OR a Playwright persistent profile if the session lives in `profiles/`).
2. Run `page.evaluate(<JS>)` (Playwright) or use a small inspection script that lists every candidate element with its tag, role, aria-label, visible text, and `aria-haspopup`. Filter to elements whose label/text contains keywords related to your goal (`menu|action|more|delete|edit|...`).
3. Print the list. Find the element whose label matches your intent (e.g. `aria-label="Actions for this post"`).
4. Update your selector to use the exact attributes from the dump.
5. Re-run.

Reusable inspection snippet (paste into any one-shot Playwright script):

```python
elements = await page.evaluate("""
    () => Array.from(document.querySelectorAll('[role="button"],[role="menuitem"],[aria-haspopup]'))
        .slice(0, 100).map(e => ({
            tag: e.tagName.toLowerCase(),
            role: e.getAttribute('role'),
            aria_label: e.getAttribute('aria-label'),
            aria_haspopup: e.getAttribute('aria-haspopup'),
            text: (e.innerText || '').slice(0, 60),
        })).filter(e => e.aria_label || (e.text && e.text.length < 50));
""")
for e in elements:
    label = e['aria_label'] or e['text']
    if any(k in (label or '').lower() for k in ['delete', 'menu', 'action', 'edit']):
        print(e)
```

This is faster than reading product source code, more reliable than guessing CSS selectors from screenshots, and works on any platform that renders DOM.

---

If the platform's UI has changed and the named affordance isn't there:
- Do NOT ask the user. The skill figures this out on its own.
- Take a `take_snapshot`. Look for any element whose visible text or aria-label matches `delete|trash|remove|move to trash`. Click the most likely candidate.
- If that opens a menu/dialog, snapshot again and look for the same patterns one level deeper. Repeat until the post is gone (verified by reloading the URL — should be 404 or "this post was deleted").
- If the post is in a feed and clicking opens a permalink, navigate to the permalink first; the overflow menu lives on the permalink page on most platforms.
- If you've tried 5 distinct snapshot+click attempts and the post is still live, capture all snapshots/screenshots to `data/uat/cleanup_failed_<platform>_<timestamp>/`, log the failure in the report, and move on. Do not block forever.
- After the post is gone (or you give up), append a learning describing what UID pattern worked (or didn't) for that platform so the next run is faster.

This deletion logic runs even if the AC that produced the post FAILED. The post existing on a real social-media account is the side effect that matters; aborting cleanup leaves UAT noise on the user's public feed.

### Phase 8 — Report and propose next action

Print a concise summary in chat:

```
UAT Task #<id> — <PASS/PARTIAL/FAIL>
ACs: <X>/<Y> passed, <Z> failed, <W> blocked
Report: docs/uat/reports/task-<id>-<date>-<time>.md
```

If PASS: propose `task-master set-status --id=<id> --status=done`. Do not auto-execute. Wait for user confirmation.

If FAIL or PARTIAL: do NOT propose marking done. Instead, summarize the most likely root causes (file:line references where possible) and suggest next debugging step.

---

## Report template

```markdown
# UAT Report — Task #<id> — YYYY-MM-DD HH:MM IST

**Result**: PASS / PARTIAL / FAIL
**Skill version**: <git rev-parse HEAD on the .claude/skills/uat-task/ directory>
**Learnings applied**: <count of entries in LEARNINGS.md>
**--allow-prod**: yes / no
**Total duration**: <seconds>

## Summary
- ACs passed: X/Y
- ACs failed: <list of AC numbers>
- ACs blocked: <list>
- ACs skipped: <list with reason>

## Screenshot index — review these in order to confirm the run is real

| # | File | AC | Caption |
|---|------|----|---------|
| 1 | data/uat/screenshots/task<id>_setup.png | setup | Test campaign created on server |
| 2 | data/uat/screenshots/task<id>_ac1_research_complete.png | AC1 | agent.log showing Phase 1 complete + agent_research row |
| ... | ... | ... | ... |

(every screenshot taken during the run is listed here, in chronological order)

## ACs

### AC<n> — <PASS/FAIL/INCONCLUSIVE/BLOCKED/SKIPPED>
- **Action**: <command or DevTools sequence summary>
- **Expected**: <copy from spec>
- **Actual**: <observed result>
- **Evidence**:
  - Files: <relative paths in fenced block>
  - Log excerpt: <fenced block>
  - **Screenshots**:
    ![AC<n> — before](../../data/uat/screenshots/task<id>_ac<n>_before.png)
    ![AC<n> — after](../../data/uat/screenshots/task<id>_ac<n>_after.png)
- **Duration**: <seconds>

(repeat for every AC)

## Aggregated PASS rule
- All ACs pass: <yes/no>
- agent.log error count: <n> (must be 0)
- audit_log error rows: <n> (must be 0)
- <other rule items from spec>
- Cleanup ran: <yes/no, with details if partial>

## Recommendation
<one of:>
- "All checks pass. Safe to mark Task #<id> done. Run: task-master set-status --id=<id> --status=done"
- "Do NOT mark task done. Fix AC<n> first — likely cause: <root-cause hypothesis with file:line>"
- "Inconclusive — <external dep> failed. Re-run after <fix>."

## Notes
<any anomalies, learnings captured during the run, manual AC user responses>
```

---

## Failure modes and how to handle them

| Failure | Handle by |
|---------|-----------|
| AC's pytest/script doesn't exist yet | Pause, offer Skip/Create now/Stub. Default Create now via `amplifier-coder`. |
| Chrome DevTools MCP can't find an element by visible text | `take_snapshot` again, dump visible UIDs to chat, ask user "which UID is the target?" Add a learning: "for <page> the <element> has UID pattern <X>". |
| Real Gemini call returns 429 / network error | Retry 3x with 2s, 4s, 8s backoff. After 3, mark AC INCONCLUSIVE — never FAIL on external infrastructure. |
| Background agent doesn't start within 30s | Tail last 50 lines of agent.log, ABORT the run with the diagnostic. |
| User answers 'n' to a manual AC | Mark FAIL, save artifact, continue with remaining ACs. The aggregate rule will reflect the failure. |
| Test campaign already exists on server (previous run didn't clean up) | Find it via name pattern `UAT *`, void it, log the orphan in the report's Notes. |
| Cleanup script errors out | Continue cleanup of other items. Flag in report. Never let one cleanup failure block another. |
| Spec block missing fields the format requires | Abort with: "Task #<id> Verification Procedure block missing required field: <field>. Update the relevant file under docs/specs/ (batch-*.md or infra.md) per docs/uat/AC-FORMAT.md, re-run." |

---

## File and directory expectations

The skill reads/writes these locations. Create them on first run if missing.

| Path | Purpose | Source |
|------|---------|--------|
| `docs/uat/AC-FORMAT.md` | Format spec | Pre-existing, read-only for skill |
| `docs/uat/skills/uat-task/LEARNINGS.md` | Persistent corrections | Skill creates on first run if missing, appends entries |
| `docs/uat/reports/` | Per-run reports (committed to git) | Skill creates dir, writes one MD per run |
| `data/uat/` | Per-run evidence (gitignored) | Skill creates dir, writes screenshots/logs/JSON |
| `data/uat/fixtures/` | Static fixtures (product images for seed_campaign) | User-managed; skill warns if missing |
| `scripts/uat/` | UAT helper scripts referenced by AC blocks | User-managed; skill offers to create missing ones via amplifier-coder |

On first run, before parsing any spec block:
- `mkdir -p docs/uat/skills/uat-task docs/uat/reports data/uat data/uat/fixtures scripts/uat`
- If `docs/uat/skills/uat-task/LEARNINGS.md` doesn't exist, create it with a one-line header: `# UAT Skill Learnings — appended over time, oldest first`

---

## Safety reminders for the model running this skill

- **Don't trust your own narration.** When you say "AC1 passes," verify by actually running the assertion command and reading the output. The user is monitoring; "I think it passed" is not acceptable.
- **Don't optimize for speed over correctness.** A 5-minute UAT that catches a real bug is infinitely more valuable than a 30-second run that says "all good" and ships a broken feature.
- **When uncertain, ask the user.** They are watching the first run specifically to correct mistakes. A question now becomes a learning that prevents 50 future bugs.
- **The product is the source of truth.** If the AC says "log line `Phase 1 complete`" and the log has `Phase 1 (Research) complete: 5 angles`, that's a pass. If it has nothing, that's a fail — don't infer success from the absence of an error.
- **One AC, one decision.** Don't mark an AC pass because "the others passed and this one looks fine." Each AC is independent verification.
- **The report is the deliverable.** Even if everything fails, a clean, accurate report is the win — it tells the user exactly what to fix.
