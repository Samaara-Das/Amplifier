# Session: Phase D Gap Audit + Launch-Blocker Task Filing

**Date**: 2026-05-02
**Wing**: auto_posting_system
**Branch**: flask-user-app
**Commit**: `966a5a4`
**Note**: MemPalace MCP was offline this session — written to `docs/sessions/` for later `mempalace mine` ingestion.

---

## What was accomplished

### `/update-docs` (skill ran first, plan-mode discipline)
- `CLAUDE.md` — `scripts/uat/` paragraph expanded (Task #74 launch-UAT seeders documented: `seed_company_fixtures`, `seed_admin_fixtures`, `seed_stripe_fixtures`, `cleanup_admin_fixtures`, plus 8 previously-undocumented harnesses).
- `CLAUDE.md` — dropped the `python scripts/onboarding.py` line from Commands section (gap #2 decision; file doesn't exist).
- `.claude/skills/update-docs/references/doc-inventory.md` — date bumped to 2026-05-02; Alembic head corrected to `b1c2d3e4f5a6` (was stale at `a1b2c3d4e5f6`); test count corrected to 303 (was 194); 5 new doc rows added (launch-uat, onboarding, agent-control, installer-assets, admin-actions, gap-audit).
- `docs/deployment-guide.md` — Vercel-ectomy: removed `vercel.json` config section, removed Vercel Lambda issue, replaced `vercel env add` instructions with systemd unit edits, renumbered the 8 troubleshooting issues.
- `docs/specs/user-app-tech-stack.md` — added prominent SUPERSEDED banner pointing to the 3 Phase D migration docs.

### Phase D Gap Audit (THE main work this session)

User asked "how many more things are broken that we don't know of?" after we caught the broken onboarding flow during Task #74 prep last session. Did **3 audit passes** — first pass was grep-driven (shallow, found 6 gaps), second pass dispatched 3 parallel Explore agents reading each migration doc's AC verbatim against code (found 5 more gaps + 1 false alarm), third pass dispatched 1 Explore agent tracing every admin action button to its route + DB write (found 1 more gap).

**Final findings** (in `docs/migrations/2026-05-01-migration-gap-audit.md`, 336 lines):

| Gap | Decision | Task |
|---|---|---|
| 1. Web onboarding flow missing | DO | **#75** |
| 2. CLI `scripts/onboarding.py` | DROP — remove from CLAUDE.md | (cleanup, no task) |
| 3. `local_server.py:177` redirect dead-end | covered by #75 | — |
| 4. Pause/Resume agent UI missing | DO | **#76** |
| 5. Stripe Connect Express onboarding | demo-keys-for-launch, real keys pre-public | **#19 updated** |
| 6. Nuitka installer | ship for launch | **#68 partial** (closed via #77+#79) |
| 7. `icon.ico` missing | DO | **#77** |
| 8. matching admin trigger / cron | NOT-A-GAP (matching is pull-based via `services/matching.py:490 get_matched_campaigns()`) | — |
| 9. dashboard agent_status not shown | fold into #76 | **#76** |
| 10. drafts-ready count missing | fold into #76 | **#76** |
| 11. EULA placeholder text | DO (I draft from /terms) | **#79** |
| 12. admin financial UI missing 2 buttons | DO | **#80** |

Total: **6 launch-blocker tasks filed/updated**, 1 false-alarm retracted, 1 cleanup item.

### 5 spec files authored (via amplifier-coder, single Agent dispatch, all matching `docs/uat/AC-FORMAT.md`)
- `docs/specs/onboarding.md` — Task #75. **12 ACs** (266 lines).
- `docs/specs/agent-control.md` — Task #76. **8 ACs** (219 lines).
- `docs/specs/installer-assets.md` — Tasks #77 + #79. **8 ACs** (195 lines).
- `docs/specs/admin-actions.md` — Task #80. **4 ACs** (132 lines).
- `docs/specs/batch-4-business-launch.md` — Task #19 expanded with **AC14–AC17** for user-side Stripe Connect onboarding UI; launch-scope note added.

### tasks.json updates
- 5 new tasks: #75, #76, #77, #79, #80 (skipped #78 — gap #8 was retracted).
- Task #19 description updated to call out demo-Stripe-for-launch + real-keys-required-pre-launch.
- Task count: 74 → 79.

### Other doc updates
- `server/.env.example` — multi-line banner above `STRIPE_SECRET_KEY` with explicit pre-launch checklist (replace sandbox `acct_1TCGfuABBUrjm7YF` with live keys, test $1 transfer, update systemd unit).
- `docs/STATUS.md` — counts bumped (74→79); added rich Phase D Gap Audit COMPLETE callout pointing at audit doc + 5 spec files.
- `docs/uat/AC-FORMAT.md` — registered new test-mode flag `AMPLIFIER_UAT_SKIP_LOCAL_HANDOFF` (CI-safe path that skips `localhost:5222/auth/callback` redirect).

### Bonus catch
amplifier-coder caught pre-existing rot during AC authoring:
- `routers/admin/__init__.py:18` shows admin auth cookie value is `"valid"`, NOT `"admin"`. The existing `docs/specs/launch-uat.md` had `cookies={'admin_token':'admin'}` literals — those would have made AC18 of Task #74 fail mysteriously when run. Fixed in batch-4 AC17 cleanup. May want to grep `launch-uat.md` for the same string and fix before running `/uat-task 74.3`.
- Replaced `@uat.local` fixture emails with `@pointcapitalis.com` in batch-4 (Pydantic email-validator rejects `.local`).

### Commit
- `966a5a4 docs(phase-d-gap-audit): file 5 launch-blocker tasks (#75-#80) + spec ACs` — 14 files, +1365 / -65 lines. Pushed to `flask-user-app` AND `main`. **No auto-deploy** (no server-affecting code changed; .env.example is template only).

---

## Decisions made this session

### Decision: Plan-mode discipline applied to the audit itself
- **What**: User asked for a thorough re-audit after the first-pass was shallow. I entered plan mode, dispatched 3 parallel Explore agents to read each migration doc's ACs verbatim against code, used `AskUserQuestion` to triage the new findings, then `ExitPlanMode` for approval.
- **Why**: First-pass missed 5 gaps. Plan-mode forces thoroughness before declaring done. Aligns with user feedback `feedback_first_run_user_present.md` ("first run is exactly when corrections compound") + the "95% confidence rule" in CLAUDE.md.
- **Worth revisiting if**: a second-pass audit produces no new gaps, indicating the first pass is now reliable.

### Decision: Fold gaps #9 + #10 into Task #76 instead of separate task
- **What**: Pause/Resume agent UI + dashboard agent_status visibility + drafts-ready count are all bundled into Task #76 as a coherent "agent control surface."
- **Alternatives**: defer #9/#10 post-launch (user rejected), or file as separate Task #80.
- **Why**: All three touch `agent_status` model + `/sse/user/agent-status` endpoint + same template files (settings.html, dashboard.html). Splitting would mean two PRs editing the same files. Cohesion > separation here.
- **Worth revisiting if**: implementation balloons past 1.5 days, indicating the bundle was too big.

### Decision: Ship Stripe with demo sandbox keys for launch
- **What**: Task #19 ships with Stock Buddy sandbox account (`acct_1TCGfuABBUrjm7YF`) for v1.0.0. Real Stripe Connect live keys MUST replace before opening to public users.
- **Alternatives**: block launch on real Stripe setup, or skip Stripe entirely (no payouts).
- **Why**: User explicit decision. Sandbox lets us close the launch UAT loop with zero real-money risk. Documented in `server/.env.example` banner + audit doc pre-launch checklist + Task #19 description so the swap can't be forgotten.
- **Worth revisiting if**: sandbox transfer behavior diverges from live Connect Express (rare, but Stripe sandbox does have edge cases).

### Decision: Drop CLI `scripts/onboarding.py` instead of building it
- **What**: Web onboarding (Task #75) supersedes the CLI flow that CLAUDE.md referenced. CLI flow was never actually implemented (file doesn't exist).
- **Why**: Two onboarding paths is wasted scope. Web is what the migration spec called for; CLI was vestigial documentation.

### Decision: Gap #8 retracted (matching is correctly pull-based)
- **What**: Initial Explore agent flagged "no admin trigger UI, no worker cron for matching." Re-verified: `routers/campaigns.py:26` imports `get_matched_campaigns` from `services/matching.py:490`. When user's daemon polls, the server runs matching for that user inline and inserts `CampaignAssignment` rows with `status='pending_invitation'` (matching.py:589).
- **Why**: Migration #66 AC22 mentions "wait for next worker cron OR pull". Pull path is operative. Not a gap.
- **Lesson**: Single Explore-agent pass is not sufficient for negative findings. Always re-verify "MISSING" claims against direct code paths before filing.

---

## Currently in flight (handoff to next session)

**Task #75 implementation** is running RIGHT NOW in a background `amplifier-coder` agent (started 13:33 IST). When it completes:
1. Pause + notify user that build is ready.
2. Run `/uat-task 75` with **user monitoring first run** (per `feedback_first_run_user_present.md`).
3. Corrections during first UAT run land in `docs/uat/skills/uat-task/LEARNINGS.md` and apply automatically on every future run.
4. Mark #75 done if all 12 ACs pass.

**After #75**:
- Implement #76 → `/uat-task 76` (user monitors)
- Implement #80 → `/uat-task 80` (user monitors)
- Implement #77 + #79 (block #68 closure)
- Implement #19 user-side Stripe Connect UI
- Re-run `/uat-task 74.1` → `74.2` → `74.3` (full launch-UAT sweep)
- Tag v1.0.0 → GHA produces installers → ship

**Estimated total launch-blocker work**: 6–8 days sequential, or 3–4 days parallelized.

---

## Files modified or created (14 total in commit `966a5a4`)

**Created (5 new spec files + 1 audit doc)**:
- `docs/migrations/2026-05-01-migration-gap-audit.md`
- `docs/specs/onboarding.md`
- `docs/specs/agent-control.md`
- `docs/specs/installer-assets.md`
- `docs/specs/admin-actions.md`

**Modified (9 files)**:
- `.claude/skills/update-docs/references/doc-inventory.md`
- `.taskmaster/tasks/tasks.json`
- `CLAUDE.md`
- `docs/STATUS.md`
- `docs/deployment-guide.md`
- `docs/specs/batch-4-business-launch.md`
- `docs/specs/user-app-tech-stack.md`
- `docs/uat/AC-FORMAT.md`
- `server/.env.example`

---

## KG facts to update when MemPalace is back online

(Manually applied by next session via `mempalace_kg_invalidate` + `mempalace_kg_add`.)

| Subject | Predicate | Old object (invalidate) | New object (add) | valid_from |
|---|---|---|---|---|
| `auto_posting_system` | `current_focus` | "Phase D done 2026-05-01..." | "Phase D Gap Audit complete 2026-05-02. 6 launch-blocker tasks filed (#75–#80, #19 update). #75 build in flight via amplifier-coder. Next: /uat-task 75 with user monitoring." | 2026-05-02 |
| `auto_posting_system` | `next_task` | "Phase E: #74 UAT, then #22 landing..." | "#75 web onboarding (build in flight). After: /uat-task 75, then #76, #80, #77+#79, #19 UI, then full /uat-task 74.1/74.2/74.3 sweep, then v1.0.0 tag → installers → launch." | 2026-05-02 |
| `auto_posting_system` | `tasks_done` | "48 done / 1 partial (#68) / 3 pending / 22 deferred / 74 total..." | "48 done / 1 partial (#68) / 8 pending (#19, #22, #57, #59, #60, #73, #74, #75, #76, #77, #79, #80) / 22 deferred / 79 total (2026-05-02; 5 new launch-blocker tasks filed)" | 2026-05-02 |
| `auto_posting_system` | `last_session_date` | "2026-05-01" | "2026-05-02" | 2026-05-02 |
| `auto_posting_system` | `active_branch` | "flask-user-app (commit ded2d7a)" | "flask-user-app (commit 966a5a4)" | 2026-05-02 |
| `auto_posting_system` | `phase_d_status` | (new) | "All 4 migrations shipped (#66 ✅ #67 ✅ #70 ✅ #68 partial). Gap audit 2026-05-02 found 6 launch-blockers between spec and code; tracked as #75/#76/#77/#79/#80/#19. Audit doc: docs/migrations/2026-05-01-migration-gap-audit.md" | 2026-05-02 |
| `auto_posting_system` | `pre_launch_checklist_doc` | (new) | "docs/migrations/2026-05-01-migration-gap-audit.md (pre-launch checklist section). Cross-reference STATUS.md and Task #19 description for Stripe demo→live swap requirement." | 2026-05-02 |
| `task_75` | `created_on` | (new) | "2026-05-02 — web onboarding flow, gap-audit-driven, 12 ACs in docs/specs/onboarding.md" | 2026-05-02 |
| `task_76` | `created_on` | (new) | "2026-05-02 — pause/resume + dashboard agent visibility + drafts-ready count, 8 ACs in docs/specs/agent-control.md" | 2026-05-02 |
| `task_77` | `created_on` | (new) | "2026-05-02 — Windows installer icon.ico (multi-size), blocks #68 closure" | 2026-05-02 |
| `task_79` | `created_on` | (new) | "2026-05-02 — real EULA text (RTF) for installer, blocks #68 closure" | 2026-05-02 |
| `task_80` | `created_on` | (new) | "2026-05-02 — admin financial UI missing 2 buttons (run-earning-promotion + run-payout-processing routes already exist)" | 2026-05-02 |
