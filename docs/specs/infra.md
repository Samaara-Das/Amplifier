# Infra Tasks — Specs & Verification

These tasks live outside the 4 product batches (Money Loop, AI Brain, Product Features, Business Launch). They are server-side infrastructure that supports the product but ships no user-facing feature. Both are launch-blocking before paying users come online.

**Tasks:** #44 (ARQ worker entrypoint), #45 (Alembic baseline migration)

---

## Task #44 — ARQ Worker Entrypoint

### What It Does

Defines `app.worker.WorkerSettings` so background jobs auto-run on a schedule:

- **Earning promotion** (every hour): `services.billing.promote_pending_earnings()` moves payouts past their 7-day hold from `pending` → `available` and credits user balances.
- **Payout processing** (every hour): `services.payments.process_pending_payouts()` sends Stripe Connect transfers for `available` payouts ≥ $10. Status moves `available` → `processing` → `paid` (or `failed`).
- **Trust score sweep** (daily): scans recent posts for anomalies (engagement spikes, deletion rate, cross-user dedup hits) and adjusts trust scores. Implementation can wrap existing `services.trust.*` helpers.
- **Billing reconciliation** (daily): cross-checks `Metric` rows against `Payout` rows to surface drift (metrics submitted but no payout created, or duplicate payouts for one metric).

The repo already imports `arq>=0.26.1` but `app.worker` does not exist. Admin financial dashboard currently triggers `promote_pending_earnings` and `process_pending_payouts` manually via routes in `routers/admin/financial.py:180-210`. Task #44 makes those routes redundant for healthy auto-flow (they remain as admin overrides).

### Why It's Blocking

Without this worker, paying users' pending earnings never auto-promote. The 7-day hold becomes "until an admin clicks the button". Withdrawals never auto-process. This is a prerequisite for Task #19 (Stripe live integration + paying users), Phase D Stripe work.

### Architecture

- **Entry point:** `app.worker.WorkerSettings` class with attributes `redis_settings`, `functions`, `cron_jobs`, `on_startup`, `on_shutdown`, `max_jobs`, `keep_result`.
- **Hosting:** systemd unit `amplifier-worker.service` on the same VPS as the web service (`amplifier-web.service`). Restart on failure, start on boot.
- **Redis:** local Redis already provisioned on VPS per `docs/HOSTING-DECISION-RECORD.md`. Connection details in env vars (`REDIS_URL`).
- **Concurrency:** single worker, `max_jobs=10`. Postgres connection pool sized accordingly.
- **Logging:** structured logs to `/var/log/amplifier/worker.log`, rotated by logrotate. Each job logs start, end, rows touched, errors.

### Acceptance Criteria

1. `app.worker.WorkerSettings` is importable and exposes the four scheduled jobs.
2. `arq app.worker.WorkerSettings --check` exits 0.
3. Worker starts cleanly: connects to Redis, registers cron jobs, no exceptions in 30s.
4. Earning promotion job processes a synthetic pending payout past its `available_at` and updates user balance.
5. Payout processing job processes a synthetic available payout and submits a Stripe Connect Transfer (test mode).
6. Trust score sweep job adjusts a synthetic anomalous post's owner trust score.
7. Billing reconciliation job logs drift (metric without payout) without creating duplicate payouts.
8. Worker survives a 10-minute soak with no memory growth and no orphaned Redis keys.
9. systemd unit `amplifier-worker.service` auto-restarts on crash (verify by `kill -9` and observing restart within 10s).
10. Admin override routes (`/admin/financial/run-earning-promotion`, `/admin/financial/run-payout-processing`) still work — calling them while the worker is running does not duplicate work (idempotent on overlapping runs).

---

## Verification Procedure — Task #44

> Format: `docs/uat/AC-FORMAT.md`. Some ACs run on the **VPS** (real Redis, real systemd, real Stripe test mode), some run locally against a docker-compose'd Postgres+Redis fixture. SSH access to VPS via `ssh -i ~/.ssh/amplifier_vps sammy@31.97.207.162`.

### Preconditions

- Server live at `https://api.pointcapitalis.com`. `/health` returns 200.
- VPS reachable via SSH key `~/.ssh/amplifier_vps`.
- VPS has Redis running on `localhost:6379` (`systemctl status redis-server` → active).
- Stripe **test mode** keys configured in `/etc/amplifier/worker.env` on the VPS — `STRIPE_SECRET_KEY` starts with `sk_test_`. **Do not run this UAT against live Stripe.**
- Local docker-compose available for running Redis+Postgres ACs without needing the VPS.
- Repo on branch `flask-user-app`, working tree clean.
- `app/worker.py` exists with `WorkerSettings` class. (If not, this UAT fails immediately at AC1 and the implementer must build first.)

### Test data setup

1. **Local fixture** (for ACs 1–8): `docker compose -f scripts/uat/infra/compose.yml up -d` brings up Postgres 16 + Redis 7. Apply schema: `alembic -c server/alembic.ini upgrade head`.
2. **Seed synthetic data** for ACs 4, 5, 6, 7:
   ```bash
   python scripts/uat/seed_worker_fixtures.py \
     --output data/uat/worker_fixtures.json
   ```
   Output IDs:
   - `pending_payout_ready_id` — payout with `status=pending`, `available_at = NOW() - INTERVAL '1 minute'`
   - `available_payout_ready_id` — payout with `status=available`, `amount_cents=1500`, attached to a user with valid Stripe Connect test account ID
   - `anomalous_post_id` — post with metric jump 100x baseline within 1 hour (trust signal)
   - `orphan_metric_id` — metric row with no corresponding payout (drift signal)
3. **VPS smoke** (for ACs 9, 10): `ssh sammy@31.97.207.162 "systemctl status amplifier-worker.service"` should report active before AC9.

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_UAT_INTERVAL_SEC=30` | Overrides cron `hour=*` schedules to `second=*/30` so jobs fire every 30s during UAT instead of hourly | AC4, AC5, AC6, AC7, AC8 |
| `AMPLIFIER_UAT_DRY_STRIPE=1` | Forces `services.payments` to log the Transfer args without calling Stripe (used in CI / when Stripe test mode is unavailable) | AC5 (fallback path) |

Both flags read at module load. Defaults preserve production behavior.

---

### AC1 — `WorkerSettings` importable and exposes 4 jobs

| Field | Value |
|-------|-------|
| **Setup** | Repo on branch where `app/worker.py` exists. |
| **Action** | `python -c "from app.worker import WorkerSettings; print(sorted(f.__name__ for f in WorkerSettings.functions)); print([(c.name, c.month, c.day, c.hour, c.minute) for c in WorkerSettings.cron_jobs])"` |
| **Expected** | functions list contains all of: `promote_pending_earnings`, `process_pending_payouts`, `trust_score_sweep`, `billing_reconciliation`. cron_jobs has 4 entries with hour/minute schedules (not all `None`). |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac1_worker_settings_shape` |
| **Evidence** | stdout dump |
| **Cleanup** | none |

### AC2 — `arq` health-check passes

| Field | Value |
|-------|-------|
| **Setup** | Local Redis up via docker compose. |
| **Action** | `arq app.worker.WorkerSettings --check 2>&1 \| tee data/uat/ac2_arq_check.log; echo EXIT=$?` |
| **Expected** | EXIT=0. Log contains `WorkerSettings` and lists the 4 functions. No traceback. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac2_arq_check` |
| **Evidence** | log file + exit code |
| **Cleanup** | none |

### AC3 — Worker boots cleanly: Redis connect + cron register, no exceptions in 30s

| Field | Value |
|-------|-------|
| **Setup** | Local Redis up. Postgres up. |
| **Action** | `arq app.worker.WorkerSettings 2>&1 > data/uat/ac3_boot.log &` (capture PID) — wait 30s — `kill -INT $PID`. |
| **Expected** | Log within first 5s contains `Starting worker for 4 functions` and `Redis connection established`. No `Traceback` lines anywhere in the 30s window. Cron jobs appear scheduled (log line per registered cron). |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac3_boot_clean` |
| **Evidence** | `data/uat/ac3_boot.log` |
| **Cleanup** | none |

### AC4 — Earning promotion job promotes a ready pending payout

| Field | Value |
|-------|-------|
| **Setup** | Worker running with `AMPLIFIER_UAT_INTERVAL_SEC=30`. `pending_payout_ready_id` exists with `available_at` 1 min in past. Capture user's `earnings_balance_cents` before. |
| **Action** | Wait up to 60s. |
| **Expected** | Within 60s: payout `status=available`. User's `earnings_balance_cents` increased by the payout `amount_cents`. Worker log contains `promote_pending_earnings: 1 promoted`. No errors. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac4_earning_promotion` |
| **Evidence** | before/after balance from SQL; payout status; log line |
| **Cleanup** | reset balance + payout status for downstream ACs |

### AC5 — Payout processing job sends Stripe Connect transfer (test mode)

| Field | Value |
|-------|-------|
| **Setup** | Worker running. `available_payout_ready_id` with $15 amount and a test-mode Stripe Connect account ID on the user. Stripe test secret key in env. |
| **Action** | Wait up to 60s. |
| **Expected** | Payout transitions `available` → `processing` → `paid` within 60s. Stripe API receives a `transfers.create` call (verify via Stripe test dashboard search OR via mock recorder if `AMPLIFIER_UAT_DRY_STRIPE=1`). User's `available_balance_cents` decremented by 1500. Worker log contains `process_pending_payouts: 1 paid, 0 failed`. |
| **Automated** | yes (with `AMPLIFIER_UAT_DRY_STRIPE=1` for CI, real Stripe test for VPS run) |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac5_payout_processing` |
| **Evidence** | payout status timeline from SQL; Stripe transfer ID in worker log |
| **Cleanup** | none |

### AC6 — Trust score sweep job adjusts an anomalous post's owner

| Field | Value |
|-------|-------|
| **Setup** | Worker running. `anomalous_post_id` belongs to a user with `trust_score=80`. Anomaly is a 100x metric jump. |
| **Action** | Wait up to 60s. |
| **Expected** | Worker log contains `trust_score_sweep: N anomalies flagged` with N≥1. The post's owner has `trust_score < 80` afterward (specific delta depends on `services.trust` rules — just verify it moved down). audit_log has new row `event='trust_adjusted'` for this user. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac6_trust_sweep` |
| **Evidence** | trust_score before/after; audit_log row |
| **Cleanup** | none |

### AC7 — Billing reconciliation logs drift without creating duplicate payouts

| Field | Value |
|-------|-------|
| **Setup** | Worker running. `orphan_metric_id` is a Metric row with no corresponding Payout. Capture total Payout count before. |
| **Action** | Wait up to 60s. |
| **Expected** | Worker log contains `billing_reconciliation: 1 drift_metric_no_payout` (or similar key=value line) referencing `orphan_metric_id`. Payout count UNCHANGED — reconciliation only logs drift, does not auto-create payouts (drift is investigated manually). audit_log has `event='billing_drift_detected'` row. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac7_billing_recon` |
| **Evidence** | log line; payout count diff (should be 0); audit_log row |
| **Cleanup** | none |

### AC8 — 10-minute soak: no memory growth, no orphaned Redis keys

| Field | Value |
|-------|-------|
| **Setup** | Fresh worker process. Capture starting RSS via `ps -o rss= -p $PID`. Capture starting Redis key count: `redis-cli DBSIZE`. |
| **Action** | Run worker for 10 minutes wall clock with `AMPLIFIER_UAT_INTERVAL_SEC=30` (so cron fires ~20 times for each of 4 jobs). |
| **Expected** | After 10 min: RSS growth < 50% of starting RSS. Redis DBSIZE growth < 100 keys (arq leaves a small fixed number of bookkeeping keys; large growth = leak). No `Traceback` in worker log. Process still alive at end. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac8_soak` |
| **Evidence** | RSS before/after; DBSIZE before/after; log size diff |
| **Cleanup** | kill worker; `redis-cli FLUSHDB` on the test Redis only |

### AC9 — systemd unit auto-restarts on crash (VPS-only)

| Field | Value |
|-------|-------|
| **Setup** | VPS reachable via SSH. `amplifier-worker.service` is `active`. |
| **Action** | `ssh sammy@31.97.207.162 "sudo systemctl status amplifier-worker.service \| grep -E 'Active\|Main PID'; PID=\$(systemctl show -p MainPID --value amplifier-worker.service); sudo kill -9 \$PID; sleep 12; systemctl status amplifier-worker.service \| grep -E 'Active\|Main PID'"` |
| **Expected** | Old PID killed. Within 12s: service `active (running)` again with a NEW MainPID. `journalctl -u amplifier-worker.service --since '1 minute ago'` shows restart. |
| **Automated** | partial (manual confirmation of journal) |
| **Automation** | bash sequence above; manual eyeball of journal line |
| **Evidence** | Old PID, new PID, journal excerpt |
| **Cleanup** | none — service should be running |

### AC10 — Admin override routes idempotent with worker running

| Field | Value |
|-------|-------|
| **Setup** | Worker running with normal hourly cron (no UAT interval flag). Seed 1 ready-to-promote payout. |
| **Action** | (1) Hit `POST /admin/financial/run-earning-promotion` immediately after seeding. (2) Wait until next worker cron tick (or trigger via `arq` CLI directly). |
| **Expected** | First call: payout promoted, log shows 1 promoted. Second call (worker cron): log shows 0 promoted (idempotent — already done). User balance not double-credited. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task44.py::test_ac10_admin_override_idempotent` |
| **Evidence** | balance unchanged after second run; log lines |
| **Cleanup** | reset payout |

---

### Aggregated PASS rule for Task #44

Task #44 is marked done in task-master ONLY when:
1. AC1–AC10 all PASS (AC9 manual confirmation = user `y` after reading journal output)
2. Worker log grep `(?i)error|exception|traceback` returns zero lines (warnings OK) across all AC runs
3. No payout double-credit, no balance drift — verified by reconciliation diff before/after the full UAT run
4. systemd unit on VPS still `active (running)` at end of UAT
5. UAT report `docs/uat/reports/task-44-<yyyy-mm-dd>-<hhmm>.md` written with all evidence embedded
6. `docker compose down` cleanup ran successfully — no leftover containers

---

## Task #45 — Baseline Alembic Migration + Going-Forward Policy

### What It Does

Establishes Alembic as the source of truth for schema. Currently `server/alembic/` is configured (env.py, alembic.ini) but `server/alembic/versions/` is **empty** — no migrations have ever been generated. Models drifted silently from production schema, causing 2 prod-blocking bugs during Task #41 deployment (`decline_reason` column missing, 14 columns needed `json` → `jsonb`). Both fixes were applied via raw SQL captured in `docs/migrations/2026-04-25-task41-schema-fixes.md` — the schema is fine in production, but Alembic doesn't know.

### Three Pieces of Work

1. **Generate baseline revision** that captures the current production schema as `0001_baseline.py`. Use `alembic revision --autogenerate` against a database mirroring production, then hand-review the output to remove any spurious diffs.
2. **Stamp production** with the baseline so `alembic current` on prod reads `0001_baseline (head)`. This tells Alembic "the schema is already at this revision — don't try to recreate it."
3. **Document the policy** in `CLAUDE.md`: every PR that changes a model in `server/app/models/` must include a corresponding migration in `server/alembic/versions/`. CI/pre-commit hook to enforce (best-effort — at minimum a documented contributor rule).

### Why It's Blocking

Without baseline migrations, every model addition is silent until deploy. Task #15 (quality gate) likely adds columns. Phase D migration to HTMX/creator-app-split may add tables. Without Alembic, those go to prod via "manual SQL after deploy" — same trap as Task #41 schema drift bugs.

### Acceptance Criteria

1. `server/alembic/versions/` contains `0001_baseline.py` (or equivalent name with timestamp prefix) at the head of the revision tree.
2. `alembic upgrade head` against an empty database produces a schema byte-equivalent to the SQLAlchemy models' DDL.
3. `alembic current` on production Supabase shows `0001_baseline (head)` after stamping.
4. `alembic check` (or `alembic revision --autogenerate` against a freshly-upgraded DB) reports zero diffs against current models.
5. `alembic downgrade base` then `upgrade head` round-trip cleanly on a test DB.
6. Adding a column to a model and running `alembic revision --autogenerate -m "add_column"` produces a migration file containing the new column. Running `upgrade` on that migration applies it; `downgrade` reverts.
7. `CLAUDE.md` contains a "Schema migration policy" section requiring migrations in the same PR as model changes.

---

## Verification Procedure — Task #45

> Format: `docs/uat/AC-FORMAT.md`. Mostly local — uses a docker-compose'd Postgres for upgrade/downgrade testing. Production stamp (AC3) requires SSH access to the VPS or direct Supabase connection.

### Preconditions

- Repo on branch `flask-user-app` with `server/alembic/versions/0001_baseline.py` present.
- Local Postgres available (docker compose up — same fixture as Task #44).
- Production Supabase reachable from the local machine OR via VPS (`ssh sammy@31.97.207.162 "..."`). Use the **transaction pooler** URL (`aws-1-us-east-1.pooler.supabase.com:6543`) with `prepared_statement_cache_size=0`.
- `alembic` installed in the project venv (`pip install -r server/requirements.txt`).
- `pg_dump` and `pg_restore` available locally (for AC2's schema-equivalence check).

### Test data setup

1. **Empty test DB**: `docker compose -f scripts/uat/infra/compose.yml exec postgres dropdb -U postgres amplifier_test && docker compose ... createdb -U postgres amplifier_test`.
2. **Production schema dump** (read-only — no writes to prod): `pg_dump --schema-only --no-owner --no-acl <PROD_URL> > data/uat/prod_schema.sql`. Captured for AC2 comparison.
3. **Models DDL dump**: `python scripts/uat/dump_models_ddl.py > data/uat/models_ddl.sql`. (New helper: imports all models, calls `Base.metadata.create_all(MockEngine)` to a string buffer.)

### Test-mode flags

None required — Alembic operations are deterministic and don't need timing overrides.

---

### AC1 — Baseline migration file exists at head

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `ls server/alembic/versions/*.py && cd server && alembic heads` |
| **Expected** | At least one revision file exists. `alembic heads` outputs exactly one revision (no branching). The revision filename includes "baseline" or is dated 2026-04-2x-baseline. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task45.py::test_ac1_baseline_present` |
| **Evidence** | file listing + `alembic heads` stdout |
| **Cleanup** | none |

### AC2 — `alembic upgrade head` on empty DB produces schema equivalent to models

| Field | Value |
|-------|-------|
| **Setup** | Empty `amplifier_test` DB created. |
| **Action** | `cd server && DATABASE_URL=postgresql://postgres:postgres@localhost:5432/amplifier_test alembic upgrade head; pg_dump --schema-only --no-owner --no-acl postgresql://postgres:postgres@localhost:5432/amplifier_test > data/uat/baseline_applied.sql` |
| **Expected** | `alembic upgrade head` exits 0. Diff between `baseline_applied.sql` and `models_ddl.sql` (after normalizing whitespace, owner/grant clauses) is empty for table definitions, columns, indexes, and constraints. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task45.py::test_ac2_baseline_matches_models` |
| **Evidence** | normalized diff output → empty |
| **Cleanup** | drop test DB |

### AC3 — Production stamped at baseline (read-only verification)

| Field | Value |
|-------|-------|
| **Setup** | Baseline merged + deployed. Production DB stamp performed once via `alembic stamp head` against prod URL. |
| **Action** | `cd server && DATABASE_URL=<PROD_POOLER_URL> alembic current` |
| **Expected** | Output: `<revision_id> (head)`. Matches the revision in `server/alembic/versions/`. No `(empty)` or `Can't locate revision`. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task45.py::test_ac3_prod_stamped` (gated by `AMPLIFIER_UAT_PROD_DB=1` env so it only runs when explicitly opted in) |
| **Evidence** | `alembic current` stdout |
| **Cleanup** | none |

### AC4 — `alembic check` reports zero diffs against current models

| Field | Value |
|-------|-------|
| **Setup** | Empty `amplifier_test` DB. Run `alembic upgrade head` against it. |
| **Action** | `cd server && DATABASE_URL=...amplifier_test alembic check 2>&1 \| tee data/uat/ac4_check.log; echo EXIT=$?` |
| **Expected** | EXIT=0. Log line `No new upgrade operations detected` (alembic 1.13+) OR equivalent for installed version. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task45.py::test_ac4_alembic_check_clean` |
| **Evidence** | log + exit code |
| **Cleanup** | drop test DB |

### AC5 — Round-trip: `downgrade base` then `upgrade head` is clean

| Field | Value |
|-------|-------|
| **Setup** | `amplifier_test` DB at head. |
| **Action** | `cd server && DATABASE_URL=...amplifier_test alembic downgrade base; pg_dump --schema-only ... > data/uat/post_downgrade.sql; alembic upgrade head; pg_dump --schema-only ... > data/uat/post_reupgrade.sql` |
| **Expected** | `post_downgrade.sql` contains zero `CREATE TABLE` statements for app tables (only Alembic's `alembic_version` table remains). `post_reupgrade.sql` byte-equivalent to `baseline_applied.sql` from AC2. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task45.py::test_ac5_round_trip` |
| **Evidence** | both pg_dump files |
| **Cleanup** | drop test DB |

### AC6 — New migration generated for a synthetic model change

| Field | Value |
|-------|-------|
| **Setup** | `amplifier_test` DB at head. Branch off a temp git branch `uat-task45-ac6` so we can revert. Add a synthetic column to `server/app/models/user.py`: `uat_test_column: Mapped[str \| None] = mapped_column(String(20), nullable=True)`. |
| **Action** | `cd server && alembic revision --autogenerate -m "uat_add_test_column"; ls -t alembic/versions/*.py \| head -1` (capture new file path); `alembic upgrade head`; `psql ...amplifier_test -c "\d users"` (verify new column); `alembic downgrade -1`; `psql -c "\d users"` (verify removed). |
| **Expected** | New migration file exists. Contains `op.add_column('users', sa.Column('uat_test_column', ...))` in `upgrade()` and `op.drop_column(...)` in `downgrade()`. Upgrade adds the column; downgrade removes it. |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task45.py::test_ac6_autogenerate` |
| **Evidence** | migration file content; psql output before/after |
| **Cleanup** | `git checkout flask-user-app && git branch -D uat-task45-ac6`; drop test DB |

### AC7 — `CLAUDE.md` contains schema-migration policy

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `grep -n "Schema migration\|alembic.*PR\|model change.*migration" CLAUDE.md` |
| **Expected** | At least 1 hit. The matched section explicitly states: every PR changing a file in `server/app/models/` must include a migration file in `server/alembic/versions/`. Mentions consequence of skipping (silent prod drift, Task #41 incident referenced). |
| **Automated** | yes |
| **Automation** | `pytest scripts/uat/uat_task45.py::test_ac7_policy_documented` |
| **Evidence** | grep output |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #45

Task #45 is marked done in task-master ONLY when:
1. AC1–AC7 all PASS (AC3 only required if `AMPLIFIER_UAT_PROD_DB=1` set; otherwise PASS noted as "skipped — opt-in required")
2. No untracked migration files left in `server/alembic/versions/` after AC6 cleanup
3. `git status` clean at end of run (no model edits left over)
4. UAT report `docs/uat/reports/task-45-<yyyy-mm-dd>-<hhmm>.md` written with the autogenerate diff included verbatim
5. Production `alembic current` re-checked at end (AC3) — still at head, not accidentally bumped

---

## Task #18 — Automated pytest suite (money loop + quality gate + trust + matching)

### What It Does

Pytest unit suite covering three service layers with no external dependencies: the 8-criterion campaign quality gate rubric (`score_campaign()`), trust event adjustments (`adjust_trust()`), and matching score cache CRUD and TTL invalidation. Builds on existing billing and campaign tests already in `tests/server/`. All tests run against in-memory SQLite (via `tests/conftest.py`) — no real AI calls, no network, no Postgres required.

- `tests/server/test_billing.py` — 43 cases: earnings formula, tier promotion, hold periods, dedup (existing)
- `tests/server/test_campaigns.py` — CRUD + matching hard filters (existing)
- `tests/server/test_auth.py` — JWT auth flows (existing)
- `server/tests/test_billing_calcs.py` — pure-math billing (existing)
- `tests/server/test_quality_gate.py` — 12 tests: all 8 rubric criteria + hard-fail veto (new)
- `tests/server/test_trust.py` — 4 tests: event deltas, clamping, unknown event (new)
- `tests/server/test_matching_cache.py` — 4 tests: TTL hit/miss, campaign edit invalidation, user refresh invalidation (new)

---

## Verification Procedure — Task #18

> Format: `docs/uat/AC-FORMAT.md`. All ACs run locally — in-memory SQLite, no VPS, no external services.

### Preconditions

- Repo on branch `flask-user-app`, working tree clean.
- `pip install -r requirements-test.txt` (installs pytest 8.0+, pytest-asyncio 0.24+, httpx, aiosqlite).
- `pyproject.toml` has `testpaths = ["tests"]` and `asyncio_mode = "auto"`.

### Test data setup

None. All tests use in-memory SQLite via `tests/conftest.py`. No seeding required.

### Test-mode flags

None.

---

### AC1 — Existing tests still green (regression guard)

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `cd /c/Users/dassa/Work/Auto-Posting-System && pytest tests/server/test_billing.py tests/server/test_campaigns.py tests/server/test_auth.py -v` |
| **Expected** | All tests PASS. Zero `ERROR` or `FAILED` lines. |
| **Automated** | yes |
| **Automation** | command above |
| **Evidence** | pytest stdout |
| **Cleanup** | none |

### AC2 — Quality gate rubric: 12 tests green

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `pytest tests/server/test_quality_gate.py -v` |
| **Expected** | 12 tests PASS. Covers all 8 criteria (brief, guidance, payout, targeting, assets, title, dates, budget) + hard-fail veto for each hard-fail criterion. Zero `ERROR` or `FAILED` lines. |
| **Automated** | yes |
| **Automation** | command above |
| **Evidence** | pytest stdout |
| **Cleanup** | none |

### AC3 — Trust events: 4 tests green

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `pytest tests/server/test_trust.py -v` |
| **Expected** | 4 tests PASS: clamping at 0 and 100, `post_verified_live_24h` increment, `confirmed_fake_metrics` severe decrement, unknown event no-op. Zero `ERROR` or `FAILED` lines. |
| **Automated** | yes |
| **Automation** | command above |
| **Evidence** | pytest stdout |
| **Cleanup** | none |

### AC4 — Matching cache: 4 tests green

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `pytest tests/server/test_matching_cache.py -v` |
| **Expected** | 4 tests PASS: TTL hit, TTL miss/eviction, campaign edit invalidation, user profile refresh invalidation. Zero `ERROR` or `FAILED` lines. |
| **Automated** | yes |
| **Automation** | command above |
| **Evidence** | pytest stdout |
| **Cleanup** | none |

### AC5 — Full suite: all tests green, wall clock < 60s

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `pytest tests/ -v` |
| **Expected** | All tests PASS. Zero `error`/`exception`/`traceback` lines (case-insensitive). Suite completes in < 60 seconds wall clock. |
| **Automated** | yes |
| **Automation** | command above |
| **Evidence** | pytest stdout including timing summary |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #18

Task #18 is marked done in task-master ONLY when:
1. AC1–AC5 all PASS
2. Zero `FAILED` or `ERROR` lines in `pytest tests/ -v` output
3. No skipped tests outside of explicit `@pytest.mark.skip` decorators
4. Suite wall clock < 60s

---

## Task #73 — Fix Gemini model ID 404 in AI review

### What It Does

Replaces deprecated bare model ID `gemini-1.5-flash` (returns 404 from Google Gemini API) with the stable alias `gemini-1.5-flash-latest` in the AI review fallback chain in `server/app/services/quality_gate.py`.

### Files Changed

- `server/app/services/quality_gate.py` line ~377: `gemini_models` list updated.

---

## Verification Procedure — Task #73

**Preconditions**:
- Server codebase available locally
- `grep` available

**Test data setup**: None.

**Test-mode flags**: none

---

### AC1: No bare `gemini-1.5-flash` references remain in server/app/services/

| Field | Value |
|-------|-------|
| **Setup** | None. |
| **Action** | `grep -r "gemini-1.5-flash" server/app/services/` — expect zero matches for the bare name (only `gemini-1.5-flash-latest` or `gemini-2.0-flash` are allowed). |
| **Expected** | Zero lines matching the bare string `gemini-1.5-flash` (without `-latest` or `-002` suffix). |
| **Automated** | yes |
| **Automation** | `pytest tests/server/test_quality_gate.py -v` (all pass = no import-time errors from the provider chain) |
| **Evidence** | grep output showing zero matches; pytest stdout `185 passed` |
| **Cleanup** | none |

---

### Aggregated PASS rule for Task #73

- AC1 PASS (grep returns empty for bare `gemini-1.5-flash`)
- `pytest tests/server/test_quality_gate.py -v` → all tests PASS

---

## Task #27 — Server-side post URL dedup

### What It Does

Adds app-level deduplication to `POST /api/posts` (`register_posts` in `server/app/routers/metrics.py`). Before inserting a new `Post` row, the endpoint checks whether a row with the same `post_url` already exists. If it does, the post is silently skipped and `skipped_duplicate` is incremented. Also makes the existing invalid-assignment skip observable via `skipped_invalid_assignment`. Response gains two new fields: `skipped_duplicate` and `skipped_invalid_assignment`. No schema change — no Alembic migration required.

### Files Changed

- `server/app/routers/metrics.py` — `register_posts()` updated with URL dedup query and extended response shape.
- `tests/server/test_metrics_routes.py` — 3 new tests added in `TestPostRegisterDedup` class.

---

## Verification Procedure — Task #27

**Preconditions**:
- Repo on branch `flask-user-app`, working tree clean.
- `pip install -r requirements-test.txt` (pytest, pytest-asyncio, httpx, aiosqlite).
- Server live at `https://api.pointcapitalis.com` with a valid user account for AC4.

**Test data setup**: None — unit tests are self-contained (in-memory SQLite).

**Test-mode flags**: None.

---

### AC1: Same URL submitted twice results in 1 DB row and skipped_duplicate=1

| Field | Value |
|-------|-------|
| **Setup** | None (in-memory test DB). |
| **Action** | `pytest tests/server/test_metrics_routes.py::TestPostRegisterDedup::test_register_posts_dedups_same_url -v` |
| **Expected** | PASS. First POST: `count=1`, `skipped_duplicate=0`. Second POST: `count=0`, `skipped_duplicate=1`. Only 1 row in `posts` table for that URL. |
| **Automated** | yes |
| **Automation** | `pytest tests/server/test_metrics_routes.py::TestPostRegisterDedup::test_register_posts_dedups_same_url` |
| **Evidence** | pytest stdout — `1 passed` |
| **Cleanup** | none |

---

### AC2: Two distinct URLs in a single batch both created

| Field | Value |
|-------|-------|
| **Setup** | None (in-memory test DB). |
| **Action** | `pytest tests/server/test_metrics_routes.py::TestPostRegisterDedup::test_register_posts_two_different_urls_both_created -v` |
| **Expected** | PASS. `count=2`, `skipped_duplicate=0`. |
| **Automated** | yes |
| **Automation** | `pytest tests/server/test_metrics_routes.py::TestPostRegisterDedup::test_register_posts_two_different_urls_both_created` |
| **Evidence** | pytest stdout — `1 passed` |
| **Cleanup** | none |

---

### AC3: Response JSON contains all 4 expected keys

| Field | Value |
|-------|-------|
| **Setup** | None (in-memory test DB). |
| **Action** | `pytest tests/server/test_metrics_routes.py::TestPostRegisterDedup::test_register_posts_response_shape -v` |
| **Expected** | PASS. Response has keys: `created`, `count`, `skipped_duplicate`, `skipped_invalid_assignment`. |
| **Automated** | yes |
| **Automation** | `pytest tests/server/test_metrics_routes.py::TestPostRegisterDedup::test_register_posts_response_shape` |
| **Evidence** | pytest stdout — `1 passed` |
| **Cleanup** | none |

---

### AC4: Live prod smoke — dedup works end-to-end against api.pointcapitalis.com

| Field | Value |
|-------|-------|
| **Setup** | Valid user account exists on prod. Obtain a JWT: `curl -s -X POST https://api.pointcapitalis.com/api/auth/user/login -H "Content-Type: application/json" -d '{"email":"<EMAIL>","password":"<PASS>"}' \| jq -r .access_token` — capture as `$TOKEN`. Obtain a valid `assignment_id` for an active campaign (`GET /api/invitations/active`). |
| **Action** | POST the same URL twice: `curl -s -X POST https://api.pointcapitalis.com/api/posts -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"posts":[{"assignment_id":<ID>,"platform":"linkedin","post_url":"https://linkedin.com/posts/uat-task27-smoke","content_hash":"uat27","posted_at":"2026-04-30T12:00:00Z"}]}' \| jq .` — repeat the same curl. |
| **Expected** | First call: `{"created":[{"id":N,"platform":"linkedin"}],"count":1,"skipped_duplicate":0,"skipped_invalid_assignment":0}`. Second call: `{"created":[],"count":0,"skipped_duplicate":1,"skipped_invalid_assignment":0}`. |
| **Automated** | no |
| **Automation** | manual |
| **Evidence** | JSON output of both curl calls captured in terminal. |
| **Cleanup** | Delete the UAT post row from prod DB: `ssh sammy@31.97.207.162 "psql \$DATABASE_URL -c \"DELETE FROM posts WHERE post_url='https://linkedin.com/posts/uat-task27-smoke';\""` |

---

### Aggregated PASS rule for Task #27

Task #27 is marked done in task-master ONLY when:
1. AC1, AC2, AC3 PASS (all 3 pytest tests green)
2. AC4 PASS (manual prod smoke confirms dedup behavior)
3. `pytest tests/server/test_metrics_routes.py -v` → all 9 tests PASS (3 new + 6 existing)
4. `pytest tests/ -v` → no regressions, total count = 188
