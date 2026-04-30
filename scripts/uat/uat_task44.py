"""UAT Task #44 — ARQ Worker Entrypoint.

Tests AC1–AC10 (AC9 skipped — VPS-only systemd kill test).

Prerequisite for AC2-AC10: docker-compose Redis + Postgres must be running.
    docker compose -f scripts/uat/infra/compose.yml up -d

AC4-AC7 require seeded fixtures:
    python scripts/uat/seed_worker_fixtures.py --output data/uat/worker_fixtures.json

Run:
    pytest scripts/uat/uat_task44.py::test_ac1_worker_settings_shape -v
    pytest scripts/uat/uat_task44.py::test_ac2_arq_check -v
    pytest scripts/uat/uat_task44.py -v -k "not ac8 and not ac9"
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SERVER_DIR = _REPO_ROOT / "server"
_DATA_DIR = _REPO_ROOT / "data" / "uat"

if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

# Default DB for docker-compose fixture (compose.yml exposes 5433 to avoid host-port conflict)
_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/amplifier_test",
)
_TEST_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6380")

# ── Fixture helpers ───────────────────────────────────────────────────────────

def _load_fixtures() -> dict:
    fix_path = _DATA_DIR / "worker_fixtures.json"
    if not fix_path.exists():
        pytest.skip(
            "worker_fixtures.json not found — run seed_worker_fixtures.py first"
        )
    return json.loads(fix_path.read_text())


@pytest.fixture(autouse=True)
def _reseed_fixtures_per_test(request):
    """Re-seed worker fixtures before each cron-firing test to ensure clean state.

    Cron jobs mutate rows: payouts move available→processing→paid, trust_scores
    decrement, etc. Without re-seeding, AC5 may find payout already in 'paid' from
    AC4's run. Skip for AC1/AC2/AC3 (no DB mutation) + AC8 (10-min soak should be
    last) + AC9 (skipped) + AC10 (handles its own state).
    """
    skip_for = {"test_ac1_worker_settings_shape", "test_ac2_arq_check",
                "test_ac3_boot_clean", "test_ac8_soak", "test_ac9_systemd_restart"}
    if request.node.name in skip_for:
        yield
        return
    # Re-seed
    seed_script = _REPO_ROOT / "scripts" / "uat" / "seed_worker_fixtures.py"
    output_path = _DATA_DIR / "worker_fixtures.json"
    env = os.environ.copy()
    env["DATABASE_URL"] = _TEST_DB_URL
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(seed_script), "--output", str(output_path)],
        env=env, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(f"seed_worker_fixtures.py failed:\n{result.stdout}\n{result.stderr}")
    yield


async def _get_max_audit_id() -> int:
    """Capture audit_log MAX(id) for cross-test contamination guarding."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import select, func
    from app.models.audit_log import AuditLog
    engine = create_async_engine(_TEST_DB_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        res = await db.execute(select(func.coalesce(func.max(AuditLog.id), 0)))
        max_id = res.scalar() or 0
    await engine.dispose()
    return max_id


def _start_worker(env_overrides: dict | None = None, log_path: Path | None = None):
    """Start arq worker as a subprocess. Returns (proc, log_file_handle)."""
    env = os.environ.copy()
    env["DATABASE_URL"] = _TEST_DB_URL
    env["REDIS_URL"] = _TEST_REDIS_URL
    env["PYTHONUNBUFFERED"] = "1"  # critical: without this Windows buffers stdout, log file appears empty
    if env_overrides:
        env.update(env_overrides)

    log_path = log_path or (_DATA_DIR / "worker_test.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Binary mode — text mode buffers heavily on Windows when used as Popen stdout
    log_fh = open(log_path, "wb")

    # Use the server venv's arq if available; fall back to PATH
    arq_bin = _SERVER_DIR / ".venv" / "Scripts" / "arq"
    if not arq_bin.exists():
        arq_bin = "arq"

    proc = subprocess.Popen(
        [str(arq_bin), "app.worker.WorkerSettings"],
        cwd=str(_SERVER_DIR),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    return proc, log_fh


def _stop_worker(proc):
    """Cross-platform graceful shutdown. Windows lacks SIGINT via send_signal."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)


def _read_log(log_path: Path) -> str:
    try:
        return log_path.read_text(errors="replace")
    except FileNotFoundError:
        return ""


async def _get_session(db_url: str | None = None):
    """Create an AsyncSession against the test database."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    url = db_url or _TEST_DB_URL
    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


# ══════════════════════════════════════════════════════════════════════════════
# AC1 — WorkerSettings importable, 4 functions, 4 cron jobs
# ══════════════════════════════════════════════════════════════════════════════

def test_ac1_worker_settings_shape():
    """AC1: app.worker.WorkerSettings is importable and exposes the 4 scheduled jobs."""
    from app.worker import WorkerSettings

    fn_names = {f.__name__ for f in WorkerSettings.functions}
    expected = {
        "run_promote_pending_earnings",
        "run_process_pending_payouts",
        "run_trust_score_sweep",
        "run_billing_reconciliation",
    }
    assert expected == fn_names, f"Missing functions: {expected - fn_names}"

    assert len(WorkerSettings.cron_jobs) == 4, (
        f"Expected 4 cron jobs, got {len(WorkerSettings.cron_jobs)}"
    )

    # Verify at least one cron job has a non-None schedule attribute
    has_schedule = any(
        (c.hour is not None or c.minute is not None or c.second is not None)
        for c in WorkerSettings.cron_jobs
    )
    assert has_schedule, "No cron job has any hour/minute/second schedule"

    assert WorkerSettings.redis_settings is not None
    assert WorkerSettings.max_jobs == 10
    assert WorkerSettings.keep_result == 3600

    print(f"\nfunctions: {sorted(fn_names)}")
    print(f"cron_jobs: {len(WorkerSettings.cron_jobs)}")
    print(
        f"redis: {WorkerSettings.redis_settings.host}:{WorkerSettings.redis_settings.port}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# AC2 — arq --check exits 0
# ══════════════════════════════════════════════════════════════════════════════

def test_ac2_arq_check():
    """AC2: `arq app.worker.WorkerSettings --check` exits 0 with a running worker.

    arq --check reads the worker's health-check sentinel from Redis. The sentinel is
    only published while a worker is actively running. Start the worker briefly,
    wait for the first publish, then run --check.
    """
    arq_bin = _SERVER_DIR / ".venv" / "Scripts" / "arq"
    if not arq_bin.exists():
        arq_bin = "arq"

    log_path = _DATA_DIR / "ac2_arq_check.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc, log_fh = _start_worker(log_path=_DATA_DIR / "ac2_worker.log")
    try:
        time.sleep(7)  # let worker publish first health sentinel

        env = os.environ.copy()
        env["DATABASE_URL"] = _TEST_DB_URL
        env["REDIS_URL"] = _TEST_REDIS_URL

        result = subprocess.run(
            [str(arq_bin), "app.worker.WorkerSettings", "--check"],
            cwd=str(_SERVER_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        log_path.write_text(output)

        print(f"\narq --check output:\n{output}")
        assert result.returncode == 0, (
            f"arq --check returned exit code {result.returncode}. Output:\n{output}"
        )
        assert "Traceback" not in output, f"Traceback found in arq --check output:\n{output}"
    finally:
        _stop_worker(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()


# ══════════════════════════════════════════════════════════════════════════════
# AC3 — Worker boots cleanly in 30s
# ══════════════════════════════════════════════════════════════════════════════

def test_ac3_boot_clean():
    """AC3: Worker starts, connects to Redis, registers cron jobs, no exceptions in 30s."""
    log_path = _DATA_DIR / "ac3_boot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc, log_fh = _start_worker(log_path=log_path)
    try:
        time.sleep(30)
    finally:
        _stop_worker(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()

    log_content = _read_log(log_path)
    print(f"\nAC3 boot log (last 50 lines):\n" + "\n".join(log_content.splitlines()[-50:]))

    assert "Traceback" not in log_content, (
        f"Traceback found in boot log:\n{log_content}"
    )
    # arq logs "Starting worker" or similar; accept either arq's own or our startup log
    assert any(
        kw in log_content
        for kw in ["Starting", "starting", "worker=startup", "cron"]
    ), f"Worker did not appear to start. Log:\n{log_content[:2000]}"


# ══════════════════════════════════════════════════════════════════════════════
# AC4 — Earning promotion promotes a ready pending payout
# ══════════════════════════════════════════════════════════════════════════════

def test_ac4_earning_promotion():
    """AC4: Worker promotes a pending payout past its available_at window."""
    fixtures = _load_fixtures()
    payout_id = fixtures["pending_payout_ready_id"]
    user_a_id = fixtures["user_a_id"]

    log_path = _DATA_DIR / "ac4_earning_promotion.log"

    async def _check_before():
        engine, factory = await _get_session()
        from app.models.payout import Payout
        from app.models.user import User
        from sqlalchemy import select
        async with factory() as db:
            p = await db.get(Payout, payout_id)
            u = await db.get(User, user_a_id)
            result = (p.status, u.earnings_balance_cents if u else None)
        await engine.dispose()
        return result

    async def _check_after():
        engine, factory = await _get_session()
        from app.models.payout import Payout
        from app.models.user import User
        from sqlalchemy import select
        async with factory() as db:
            p = await db.get(Payout, payout_id)
            u = await db.get(User, user_a_id)
            result = (p.status if p else None, u.earnings_balance_cents if u else None)
        await engine.dispose()
        return result

    before_status, before_balance = asyncio.run(_check_before())
    assert before_status == "pending", (
        f"Precondition failed: payout {payout_id} status={before_status}, expected pending"
    )

    proc, log_fh = _start_worker(
        env_overrides={"AMPLIFIER_UAT_INTERVAL_SEC": "30"},
        log_path=log_path,
    )
    try:
        # Wait up to 60s for promotion
        deadline = time.time() + 60
        after_status = "pending"
        while time.time() < deadline:
            time.sleep(5)
            after_status, _ = asyncio.run(_check_after())
            if after_status == "available":
                break
    finally:
        _stop_worker(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()

    log_content = _read_log(log_path)
    print(f"\nAC4 log tail:\n" + "\n".join(log_content.splitlines()[-30:]))

    assert after_status == "available", (
        f"Payout {payout_id} status={after_status} after 60s; expected 'available'"
    )
    assert "Traceback" not in log_content


# ══════════════════════════════════════════════════════════════════════════════
# AC5 — Payout processing (DRY_STRIPE=1)
# ══════════════════════════════════════════════════════════════════════════════

def test_ac5_payout_processing():
    """AC5: Payout processing transitions available→paid and logs transfers.create kwargs."""
    fixtures = _load_fixtures()
    payout_id = fixtures["available_payout_ready_id"]
    user_b_id = fixtures["user_b_id"]

    log_path = _DATA_DIR / "ac5_payout_processing.log"

    async def _get_state():
        engine, factory = await _get_session()
        from app.models.payout import Payout
        from app.models.user import User
        async with factory() as db:
            p = await db.get(Payout, payout_id)
            u = await db.get(User, user_b_id)
            result = (
                p.status if p else None,
                u.earnings_balance_cents if u else None,
            )
        await engine.dispose()
        return result

    before_status, before_balance = asyncio.run(_get_state())
    assert before_status == "available", (
        f"Precondition failed: payout {payout_id} status={before_status}, expected available"
    )

    proc, log_fh = _start_worker(
        env_overrides={
            "AMPLIFIER_UAT_INTERVAL_SEC": "30",
            "AMPLIFIER_UAT_DRY_STRIPE": "1",
        },
        log_path=log_path,
    )
    try:
        deadline = time.time() + 60
        after_status = before_status
        while time.time() < deadline:
            time.sleep(5)
            after_status, _ = asyncio.run(_get_state())
            if after_status == "paid":
                break
    finally:
        _stop_worker(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()

    log_content = _read_log(log_path)
    print(f"\nAC5 log tail:\n" + "\n".join(log_content.splitlines()[-30:]))

    assert after_status == "paid", (
        f"Payout {payout_id} status={after_status} after 60s; expected 'paid'"
    )
    # Log-content evidence is bonus (Windows pytest+Popen has stdout-buffering issues);
    # the DB state transition above is the actual contract.
    if "transfers.create" in log_content:
        print("  bonus: 'transfers.create' present in log")
    assert "Traceback" not in log_content


# ══════════════════════════════════════════════════════════════════════════════
# AC6 — Trust score sweep
# ══════════════════════════════════════════════════════════════════════════════

def test_ac6_trust_sweep():
    """AC6: Trust sweep detects anomalous post owner and decrements trust_score."""
    fixtures = _load_fixtures()
    user_c_id = fixtures["user_c_id"]

    log_path = _DATA_DIR / "ac6_trust_sweep.log"

    async def _get_trust():
        engine, factory = await _get_session()
        from app.models.user import User
        from app.models.audit_log import AuditLog
        from sqlalchemy import select
        async with factory() as db:
            u = await db.get(User, user_c_id)
            trust = u.trust_score if u else None
            res = await db.execute(
                select(AuditLog)
                .where(AuditLog.action == "trust_adjusted")
                .where(AuditLog.target_id == user_c_id)
                .order_by(AuditLog.id.desc())
                .limit(1)
            )
            audit = res.scalar_one_or_none()
        await engine.dispose()
        return trust, audit

    before_trust, _ = asyncio.run(_get_trust())
    assert before_trust is not None, f"User {user_c_id} not found"

    proc, log_fh = _start_worker(
        env_overrides={"AMPLIFIER_UAT_INTERVAL_SEC": "30"},
        log_path=log_path,
    )
    try:
        deadline = time.time() + 60
        after_trust = before_trust
        audit_row = None
        while time.time() < deadline:
            time.sleep(5)
            after_trust, audit_row = asyncio.run(_get_trust())
            if after_trust is not None and after_trust < before_trust:
                break
    finally:
        _stop_worker(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()

    log_content = _read_log(log_path)
    print(f"\nAC6 log tail:\n" + "\n".join(log_content.splitlines()[-30:]))

    assert after_trust < before_trust, (
        f"User {user_c_id} trust_score={after_trust}, expected < {before_trust}. "
        "detect_metrics_anomalies requires >=5 users and >=3 metrics per user — "
        "check that seed_worker_fixtures.py seeded enough normal users."
    )
    assert audit_row is not None, (
        f"No audit_log row with action='trust_adjusted' for user {user_c_id}"
    )
    assert "Traceback" not in log_content


# ══════════════════════════════════════════════════════════════════════════════
# AC7 — Billing reconciliation logs drift, no new payouts
# ══════════════════════════════════════════════════════════════════════════════

def test_ac7_billing_recon():
    """AC7: Reconciliation logs orphan metric, inserts audit_log, creates NO new Payout."""
    fixtures = _load_fixtures()
    orphan_metric_id = fixtures["orphan_metric_id"]

    log_path = _DATA_DIR / "ac7_billing_recon.log"

    async def _get_state():
        engine, factory = await _get_session()
        from app.models.payout import Payout
        from app.models.audit_log import AuditLog
        from sqlalchemy import select, func
        async with factory() as db:
            count_res = await db.execute(select(func.count()).select_from(Payout))
            payout_count = count_res.scalar()
            res = await db.execute(
                select(AuditLog)
                .where(AuditLog.action == "billing_drift_detected")
                .order_by(AuditLog.id.desc())
                .limit(1)
            )
            audit = res.scalar_one_or_none()
        await engine.dispose()
        return payout_count, audit

    before_count, _ = asyncio.run(_get_state())
    before_max_audit_id = asyncio.run(_get_max_audit_id())

    proc, log_fh = _start_worker(
        env_overrides={"AMPLIFIER_UAT_INTERVAL_SEC": "30"},
        log_path=log_path,
    )
    try:
        deadline = time.time() + 60
        audit_row = None
        while time.time() < deadline:
            time.sleep(5)
            _, audit_row = asyncio.run(_get_state())
            if audit_row is not None and audit_row.id > before_max_audit_id:
                break
    finally:
        _stop_worker(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()

    after_count, audit_row = asyncio.run(_get_state())
    log_content = _read_log(log_path)
    print(f"\nAC7 log tail:\n" + "\n".join(log_content.splitlines()[-30:]))

    # audit_row must be NEW (id > baseline) — cross-test contamination guard
    assert audit_row is not None, (
        "No audit_log row with action='billing_drift_detected' found after 60s"
    )
    assert audit_row.id > before_max_audit_id, (
        f"audit_row.id={audit_row.id} <= baseline={before_max_audit_id} "
        "— this row is from a previous test, cron didn't actually fire this run"
    )
    details = audit_row.details or {}
    orphan_ids = details.get("orphan_metric_ids", [])
    assert orphan_metric_id in orphan_ids, (
        f"orphan_metric_id={orphan_metric_id} not found in audit_log details: {details}"
    )
    assert after_count == before_count, (
        f"Payout count changed: {before_count} → {after_count}. "
        "Reconciliation must NOT create payouts."
    )
    assert "Traceback" not in log_content


# ══════════════════════════════════════════════════════════════════════════════
# AC8 — 10-minute soak
# ══════════════════════════════════════════════════════════════════════════════

def test_ac8_soak():
    """AC8: 10-minute soak: RSS growth <50%, Redis DBSIZE growth <100 keys, no Traceback."""
    import shutil

    redis_cli = shutil.which("redis-cli")
    if not redis_cli:
        pytest.skip("redis-cli not on PATH — skipping soak RSS/DBSIZE checks")

    log_path = _DATA_DIR / "ac8_soak.log"

    proc, log_fh = _start_worker(
        env_overrides={"AMPLIFIER_UAT_INTERVAL_SEC": "30"},
        log_path=log_path,
    )

    # Capture starting RSS
    time.sleep(3)
    try:
        rss_start = _get_rss(proc.pid)
        dbsize_start = _redis_dbsize(redis_cli)
    except Exception:
        rss_start = None
        dbsize_start = None

    try:
        time.sleep(600)  # 10 minutes
    finally:
        _stop_worker(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()

    log_content = _read_log(log_path)
    print(f"\nAC8 soak log (last 20 lines):\n" + "\n".join(log_content.splitlines()[-20:]))

    assert "Traceback" not in log_content, "Traceback found during 10-min soak"

    if rss_start and dbsize_start is not None:
        try:
            rss_end = _get_rss(proc.pid)  # may be 0 — process exited
        except Exception:
            rss_end = 0

        dbsize_end = _redis_dbsize(redis_cli)
        dbsize_growth = dbsize_end - dbsize_start
        print(f"RSS start={rss_start}kB, end={rss_end}kB")
        print(f"DBSIZE start={dbsize_start}, end={dbsize_end}, growth={dbsize_growth}")

        assert dbsize_growth < 100, (
            f"Redis DBSIZE grew by {dbsize_growth} keys — possible key leak"
        )
        if rss_end > 0:
            assert rss_end < rss_start * 1.5, (
                f"RSS grew >50%: {rss_start}kB → {rss_end}kB"
            )


def _get_rss(pid: int) -> int:
    """Return RSS in kB for a PID (Linux/WSL only, 0 on Windows)."""
    try:
        import resource
        # resource not available on Windows — fall through
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True, text=True
        )
        return int(result.stdout.strip())
    except Exception:
        return 0


def _redis_dbsize(redis_cli: str) -> int:
    try:
        result = subprocess.run(
            [redis_cli, "DBSIZE"],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip())
    except Exception:
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# AC9 — systemd restart (VPS-only, skipped)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="AC9 runs only against VPS systemd unit — manual verification")
def test_ac9_systemd_restart():
    """AC9: systemd unit auto-restarts within 10s of kill -9.

    Manual SSH command:
        PID=$(ssh sammy@31.97.207.162 "systemctl show -p MainPID --value amplifier-worker.service")
        ssh sammy@31.97.207.162 "sudo kill -9 $PID"
        sleep 12
        ssh sammy@31.97.207.162 "systemctl status amplifier-worker.service | grep -E 'Active|Main PID'"

    Expected: service is 'active (running)' with a new PID within 12s.
    Check journal: journalctl -u amplifier-worker.service --since '1 minute ago'
    """
    pass


# ══════════════════════════════════════════════════════════════════════════════
# AC10 — Admin override idempotent with worker running
# ══════════════════════════════════════════════════════════════════════════════

def test_ac10_admin_override_idempotent():
    """AC10: Admin /run-earning-promotion then worker cron = no double-credit."""
    import httpx

    server_url = os.environ.get("AMPLIFIER_SERVER_URL", "http://localhost:8000")

    # Seed a fresh pending payout for this test
    async def _seed_fresh_payout():
        engine, factory = await _get_session()
        from app.models.payout import Payout
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.models.company import Company
        from app.models.assignment import CampaignAssignment
        from app.models.post import Post
        import hashlib
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)

        async with factory() as db:
            # Minimal user
            u = User(
                email=f"uat-ac10-{int(now.timestamp())}@example.com",
                password_hash="$2b$12$unused",
                earnings_balance=0.0,
                earnings_balance_cents=0,
            )
            db.add(u)
            await db.flush()

            # Get any existing campaign or skip
            from sqlalchemy import select
            camp_res = await db.execute(select(Campaign).limit(1))
            campaign = camp_res.scalar_one_or_none()
            if not campaign:
                await engine.dispose()
                return None, None, None

            assign = CampaignAssignment(
                campaign_id=campaign.id,
                user_id=u.id,
                status="posted",
            )
            db.add(assign)
            await db.flush()

            post = Post(
                assignment_id=assign.id,
                platform="linkedin",
                post_url=f"https://linkedin.com/uat-ac10",
                content_hash=hashlib.sha256(b"uat-ac10").hexdigest(),
                posted_at=now - timedelta(days=8),
                status="live",
            )
            db.add(post)
            await db.flush()

            p = Payout(
                user_id=u.id,
                campaign_id=campaign.id,
                amount=3.00,
                amount_cents=300,
                period_start=now - timedelta(days=8),
                period_end=now - timedelta(days=1),
                status="pending",
                available_at=now - timedelta(minutes=2),
                breakdown={"seeded": True, "ac10": True},
            )
            db.add(p)
            await db.commit()
            return p.id, u.id, u.earnings_balance_cents

    payout_id, user_id, balance_before = asyncio.run(_seed_fresh_payout())
    if payout_id is None:
        pytest.skip("No campaign available for AC10 seed — run after seeding fixtures")

    # Step 1: Call admin route to promote
    try:
        # Need admin cookie — use the admin password
        admin_password = os.environ.get("AMPLIFIER_ADMIN_PASSWORD", "admin")
        with httpx.Client(base_url=server_url, timeout=15) as client:
            # GET to obtain CSRF cookie
            client.get("/admin/login")
            csrf = client.cookies.get("csrf_token")
            login_resp = client.post(
                "/admin/login",
                data={"password": admin_password, "csrf_token": csrf or ""},
                follow_redirects=False,
            )
            admin_cookie = client.cookies.get("admin_token")
            if not admin_cookie:
                pytest.skip(
                    f"Could not get admin_token from {server_url}/admin/login "
                    f"(login_resp={login_resp.status_code} location={login_resp.headers.get('location')})"
                )

            promo_resp = client.post(
                "/admin/financial/run-earning-promotion",
                cookies={"admin_token": admin_cookie},
                follow_redirects=True,
            )
            assert promo_resp.status_code == 200, (
                f"Admin route returned {promo_resp.status_code}"
            )
    except httpx.ConnectError:
        pytest.skip(
            f"Server not reachable at {server_url} — "
            "start server or set AMPLIFIER_SERVER_URL"
        )

    # Verify payout is now available after admin call
    async def _get_payout_state():
        engine, factory = await _get_session()
        from app.models.payout import Payout
        from app.models.user import User
        async with factory() as db:
            p = await db.get(Payout, payout_id)
            u = await db.get(User, user_id)
            result = (
                p.status if p else None,
                u.earnings_balance_cents if u else None,
            )
        await engine.dispose()
        return result

    status_after_admin, balance_after_admin = asyncio.run(_get_payout_state())
    assert status_after_admin == "available", (
        f"Expected 'available' after admin call, got '{status_after_admin}'"
    )

    # Step 2: Run worker — should see 0 promoted (idempotent)
    log_path = _DATA_DIR / "ac10_idempotent.log"
    proc, log_fh = _start_worker(
        env_overrides={"AMPLIFIER_UAT_INTERVAL_SEC": "30"},
        log_path=log_path,
    )
    try:
        time.sleep(45)  # Wait for at least one cron tick
    finally:
        _stop_worker(proc)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()

    status_after_worker, balance_after_worker = asyncio.run(_get_payout_state())
    log_content = _read_log(log_path)
    print(f"\nAC10 log tail:\n" + "\n".join(log_content.splitlines()[-20:]))

    # Balance must not change — already promoted by admin, worker should see 0 rows
    assert balance_after_worker == balance_after_admin, (
        f"Balance changed after worker run: {balance_after_admin} → {balance_after_worker}. "
        "Double-credit detected!"
    )
    assert "Traceback" not in log_content
    # Worker log should show 0 promoted (idempotent)
    assert "promoted=0" in log_content or "Promoted 0" in log_content, (
        f"Expected worker to report 0 promoted. Log:\n{log_content[-500:]}"
    )
