# Task #85 — `cleanup_test_user.py` Cascade-Delete + Run-On-Prod Ergonomics

**Status:** pending
**Branch:** flask-user-app
**Discovered:** during /uat-task 75 re-run, 2026-05-02 — leftover invitation_log + draft rows after cleanup

## What this fixes

`scripts/uat/cleanup_test_user.py` is the safety-guarded teardown helper invoked by the Aggregated PASS rule of every `uat-task<n>-user@pointcapitalis.com`-style UAT (Tasks #75, #76, #86, #19). It cascade-deletes the test user and all dependent rows so subsequent runs start from a clean state. The script already covers most child tables but was filed because two issues surfaced:

1. **Missing table**: `campaign_invitation_log` rows referencing the test user were not deleted, leaking historical invitation evidence into prod metrics.
2. **Run-on-prod friction**: dev machine runs the script against local SQLite by default; pointing it at prod requires `export DATABASE_URL=<supabase-pooler-url>` first. We need a single, ergonomic CLI flag.

## Files changed

| File | Change |
|---|---|
| `scripts/uat/cleanup_test_user.py` | Add `CampaignInvitationLog` to the cascade; add `--target {local,prod}` flag; enforce safety pattern (uat-task<n>*@pointcapitalis.com only). |

## Features to verify end-to-end (Task #85)

1. Default `--target local` deletes a UAT user from local SQLite cleanly — AC1
2. `--target prod` requires `PROD_DATABASE_URL` env var; helpful error if missing — AC2
3. Cascade includes `campaign_invitation_log` rows — AC3
4. Cascade includes `agent_draft`, `agent_command`, `agent_status`, `payouts`, `penalties`, `metrics`, `posts`, `campaign_assignments` — AC4
5. Safety guard: refuses non-UAT-pattern emails (e.g., `real@user.com`) — AC5
6. Idempotent: running twice on a deleted email doesn't error — AC6

## Verification Procedure — Task #85

### Preconditions

- Local checkout on `flask-user-app` branch with the patched `cleanup_test_user.py`.
- Local SQLite DB present at default path (or `DATABASE_URL` set to a writable target).

### Test data setup

1. Seed a synthetic UAT user + child rows directly via Python (no API calls so we can run offline):
   ```bash
   python scripts/uat/seed_cleanup_fixture.py --email uat-task85-user@pointcapitalis.com
   ```
   This script creates: 1 user row, 2 campaign_assignment rows, 1 invitation_log row, 1 post + 2 metric rows, 1 payout, 1 draft, 1 agent_status, 1 agent_command. Returns the `user_id` for assertion purposes.

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `--target local` (default) | Uses default `DATABASE_URL` (local SQLite) | AC1 |
| `--target prod` | Requires `PROD_DATABASE_URL` env var pointing at the Supabase pooler | AC2 |

---

### AC1 — `--target local` deletes UAT user + every child row — PASS criterion

| Field | Value |
|-------|-------|
| **Setup** | Seeded fixture (test data setup above) — `user_id` captured. Pre-state SQL count of every table containing `user_id=<test_user_id>`. |
| **Action** | `python scripts/uat/cleanup_test_user.py --email uat-task85-user@pointcapitalis.com` |
| **Expected** | Exit 0. Stdout reports counts for every cleaned table. Post-state SQL: zero rows in users + every child table for that user. |
| **Automated** | yes |
| **Automation** | bash + sqlite3 query |
| **Evidence** | pre/post counts; cleanup stdout |
| **Cleanup** | none (the cleanup IS the test) |

### AC2 — `--target prod` requires `PROD_DATABASE_URL`

| Field | Value |
|-------|-------|
| **Setup** | unset env var |
| **Action** | `python scripts/uat/cleanup_test_user.py --email uat-task85-user@pointcapitalis.com --target prod` |
| **Expected** | Exit 2 (or any non-zero); stderr contains a helpful error message naming `PROD_DATABASE_URL`. No DB writes. |
| **Automated** | yes |
| **Automation** | bash + exit code check + stderr grep |
| **Evidence** | stderr text |
| **Cleanup** | none |

### AC3 — Cascade covers `campaign_invitation_log`

| Field | Value |
|-------|-------|
| **Setup** | Seeded fixture has 1 `campaign_invitation_log` row for the test user. |
| **Action** | run cleanup as in AC1 |
| **Expected** | post-state: zero invitation_log rows for that user; cleanup stdout reports "campaign_invitation_log: 1" |
| **Automated** | yes |
| **Automation** | bash + sqlite3 |
| **Evidence** | pre/post counts |
| **Cleanup** | none |

### AC4 — Cascade covers all 7 other child tables

| Field | Value |
|-------|-------|
| **Setup** | Same fixture as AC1 |
| **Action** | run cleanup |
| **Expected** | post-state: zero rows in `agent_draft`, `agent_command`, `agent_status`, `payouts`, `penalties`, `metrics`, `posts`, `campaign_assignments` for that user. |
| **Automated** | yes |
| **Automation** | bash + sqlite3 |
| **Evidence** | per-table pre/post count |
| **Cleanup** | none |

### AC5 — Safety guard refuses non-UAT pattern emails

| Field | Value |
|-------|-------|
| **Setup** | Any email NOT matching `^uat-task\d+.*@pointcapitalis\.com$` |
| **Action** | `python scripts/uat/cleanup_test_user.py --email real-user@gmail.com` |
| **Expected** | Exit non-zero; error message references the safety pattern; no DB writes. |
| **Automated** | yes |
| **Automation** | bash + exit code |
| **Evidence** | stderr |
| **Cleanup** | none |

### AC6 — Idempotent

| Field | Value |
|-------|-------|
| **Setup** | After AC1 (user already deleted) |
| **Action** | run cleanup again with the same email |
| **Expected** | Exit 0. Stdout reports "No user found with email '<email>' — nothing to delete." No errors. |
| **Automated** | yes |
| **Automation** | bash |
| **Evidence** | stdout |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #85

Task #85 is marked done in task-master ONLY when:

1. AC1–AC6 all PASS
2. UAT report `docs/uat/reports/task-85-<yyyy-mm-dd>-<hhmm>.md` written
3. `scripts/uat/seed_cleanup_fixture.py` exists and is reusable (so future regressions can re-run AC1–AC4 in <10s)
