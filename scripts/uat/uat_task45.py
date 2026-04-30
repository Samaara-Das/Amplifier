"""UAT Task #45 — Baseline Alembic Migration.

Tests AC1–AC7 (AC3 skipped unless AMPLIFIER_UAT_PROD_DB=1).

Prerequisite: docker-compose Postgres running at port 5433.
    docker compose -f scripts/uat/infra/compose.yml up -d

Run:
    pytest scripts/uat/uat_task45.py -v -k "not ac3"
    pytest scripts/uat/uat_task45.py -v  # includes AC3 only if AMPLIFIER_UAT_PROD_DB=1
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SERVER_DIR = _REPO_ROOT / "server"
_DATA_DIR = _REPO_ROOT / "data" / "uat"
_VERSIONS_DIR = _SERVER_DIR / "alembic" / "versions"
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"

if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

_TEST_DB_URL_ASYNC = "postgresql+asyncpg://postgres:postgres@localhost:5433/amplifier_test"
_TEST_DB_URL_SYNC = "postgresql+psycopg2://postgres:postgres@localhost:5433/amplifier_test"


def _alembic(args: list[str], db_url: str = _TEST_DB_URL_ASYNC) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini"] + args,
        cwd=str(_SERVER_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


_COMPOSE_FILE = str(_REPO_ROOT / "scripts" / "uat" / "infra" / "compose.yml")


def _docker_exec(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", _COMPOSE_FILE, "exec", "-T", "postgres"] + cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _psql(sql: str) -> subprocess.CompletedProcess:
    return _docker_exec(["psql", "-U", "postgres", "amplifier_test", "-c", sql])


def _pg_dump_schema() -> str:
    result = _docker_exec([
        "pg_dump",
        "--schema-only",
        "--no-owner",
        "--no-acl",
        "--no-comments",
        "-U", "postgres",
        "amplifier_test",
    ])
    assert result.returncode == 0, f"pg_dump failed: {result.stderr}"
    return result.stdout


def _fresh_test_db():
    subprocess.run(
        ["docker", "compose", "-f", str(_REPO_ROOT / "scripts/uat/infra/compose.yml"),
         "exec", "postgres", "dropdb", "-U", "postgres", "amplifier_test", "--if-exists"],
        check=True, capture_output=True, timeout=30,
    )
    subprocess.run(
        ["docker", "compose", "-f", str(_REPO_ROOT / "scripts/uat/infra/compose.yml"),
         "exec", "postgres", "createdb", "-U", "postgres", "amplifier_test"],
        check=True, capture_output=True, timeout=30,
    )


def _extract_create_tables(dump: str) -> set[str]:
    return set(re.findall(r"CREATE TABLE (?:public\.)?(\w+)", dump))


# ══════════════════════════════════════════════════════════════════════════════
# AC1 — Baseline migration file exists at head
# ══════════════════════════════════════════════════════════════════════════════

def test_ac1_baseline_present():
    """AC1: versions/ has at least one .py revision; alembic heads shows exactly one head."""
    py_files = [f for f in _VERSIONS_DIR.iterdir()
                if f.suffix == ".py" and f.name != "__init__.py"]
    assert len(py_files) >= 1, f"No revision files in {_VERSIONS_DIR}"

    baseline_files = [f for f in py_files if "baseline" in f.name.lower()]
    assert len(baseline_files) >= 1, (
        f"No file with 'baseline' in name found. Files: {[f.name for f in py_files]}"
    )

    result = _alembic(["heads"])
    assert result.returncode == 0, f"alembic heads failed:\n{result.stderr}"
    output = result.stdout + result.stderr
    heads = re.findall(r"[0-9a-f]{12}", output)
    assert len(heads) == 1, (
        f"Expected exactly 1 head, found {len(heads)}: {heads}\nOutput:\n{output}"
    )
    print(f"\nBaseline file: {baseline_files[0].name}")
    print(f"alembic heads: {output.strip()}")


# ══════════════════════════════════════════════════════════════════════════════
# AC2 — alembic upgrade head on empty DB produces schema matching models
# ══════════════════════════════════════════════════════════════════════════════

def test_ac2_baseline_matches_models():
    """AC2: alembic upgrade head + pg_dump matches Base.metadata.create_all + pg_dump."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    # DB-A: upgraded via alembic
    _fresh_test_db()
    result = _alembic(["upgrade", "head"])
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"
    dump_alembic = _pg_dump_schema()
    (_DATA_DIR / "ac2_baseline_alembic.sql").write_text(dump_alembic)

    alembic_tables = _extract_create_tables(dump_alembic)
    alembic_tables.discard("alembic_version")

    # DB-B: schema via create_all
    _fresh_test_db()
    import asyncio
    async def _create_all():
        os.environ["DATABASE_URL"] = _TEST_DB_URL_ASYNC
        # Re-import database module with updated env
        import importlib
        import app.core.database as db_mod
        importlib.reload(db_mod)
        from app.core.database import Base, engine
        import app.models  # noqa
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create_all())
    dump_models = _pg_dump_schema()
    (_DATA_DIR / "ac2_baseline_models.sql").write_text(dump_models)

    models_tables = _extract_create_tables(dump_models)
    models_tables.discard("alembic_version")

    missing = models_tables - alembic_tables
    extra = alembic_tables - models_tables
    assert not missing, f"Tables in models but not in alembic dump: {missing}"
    assert not extra, f"Tables in alembic dump but not in models: {extra}"

    # Note: column/index/constraint-level equivalence is validated by AC4 (alembic check),
    # which compares the DB schema against the models at the SQLAlchemy level and exits 0
    # only when there are zero diffs. Both SQL files are saved to data/uat/ for inspection.
    print(f"\nTables verified ({len(alembic_tables)}): {sorted(alembic_tables)}")


# ══════════════════════════════════════════════════════════════════════════════
# AC3 — Production stamped at baseline (opt-in)
# ══════════════════════════════════════════════════════════════════════════════

def test_ac3_prod_stamped():
    """AC3: alembic current on prod shows <revision> (head)."""
    if not os.environ.get("AMPLIFIER_UAT_PROD_DB"):
        pytest.skip("AC3 opt-in — set AMPLIFIER_UAT_PROD_DB=1 to run against prod")

    prod_url = os.environ.get("DATABASE_URL_PROD") or os.environ.get("DATABASE_URL")
    assert prod_url, "DATABASE_URL_PROD or DATABASE_URL must be set for AC3"

    result = _alembic(["current"], db_url=prod_url)
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"alembic current failed:\n{output}"
    assert "(head)" in output, (
        f"Expected '(head)' in alembic current output, got:\n{output}"
    )
    print(f"\nalembic current on prod:\n{output.strip()}")


# ══════════════════════════════════════════════════════════════════════════════
# AC4 — alembic check reports zero diffs after upgrade head
# ══════════════════════════════════════════════════════════════════════════════

def test_ac4_alembic_check_clean():
    """AC4: alembic check exits 0 with 'No new upgrade operations detected'."""
    _fresh_test_db()
    upgrade = _alembic(["upgrade", "head"])
    assert upgrade.returncode == 0, f"upgrade head failed:\n{upgrade.stderr}"

    check = _alembic(["check"])
    output = check.stdout + check.stderr
    (_DATA_DIR / "ac4_check.log").parent.mkdir(parents=True, exist_ok=True)
    (_DATA_DIR / "ac4_check.log").write_text(output)

    assert check.returncode == 0, (
        f"alembic check exited {check.returncode}. Output:\n{output}"
    )
    assert "No new upgrade operations detected" in output, (
        f"Expected 'No new upgrade operations detected', got:\n{output}"
    )
    print(f"\nalembic check: {output.strip()}")


# ══════════════════════════════════════════════════════════════════════════════
# AC5 — Round-trip: downgrade base then upgrade head
# ══════════════════════════════════════════════════════════════════════════════

def test_ac5_round_trip():
    """AC5: downgrade base leaves only alembic_version; upgrade head restores all tables."""
    _fresh_test_db()
    upgrade = _alembic(["upgrade", "head"])
    assert upgrade.returncode == 0, f"upgrade head failed:\n{upgrade.stderr}"

    dump_before = _pg_dump_schema()
    tables_before = _extract_create_tables(dump_before)
    tables_before.discard("alembic_version")
    assert len(tables_before) >= 14, (
        f"Expected at least 14 app tables before downgrade, got {len(tables_before)}"
    )

    downgrade = _alembic(["downgrade", "base"])
    assert downgrade.returncode == 0, f"downgrade base failed:\n{downgrade.stderr}"

    dump_post_down = _pg_dump_schema()
    tables_post_down = _extract_create_tables(dump_post_down)
    tables_post_down.discard("alembic_version")
    assert len(tables_post_down) == 0, (
        f"Expected 0 app tables after downgrade base, got: {tables_post_down}"
    )
    (_DATA_DIR / "ac5_post_downgrade.sql").parent.mkdir(parents=True, exist_ok=True)
    (_DATA_DIR / "ac5_post_downgrade.sql").write_text(dump_post_down)

    reupgrade = _alembic(["upgrade", "head"])
    assert reupgrade.returncode == 0, f"re-upgrade head failed:\n{reupgrade.stderr}"

    dump_post_up = _pg_dump_schema()
    tables_post_up = _extract_create_tables(dump_post_up)
    tables_post_up.discard("alembic_version")
    (_DATA_DIR / "ac5_post_reupgrade.sql").write_text(dump_post_up)

    assert tables_post_up == tables_before, (
        f"Tables after round-trip differ from before.\n"
        f"Missing: {tables_before - tables_post_up}\n"
        f"Extra: {tables_post_up - tables_before}"
    )
    print(f"\nRound-trip verified: {len(tables_post_up)} tables restored cleanly")


# ══════════════════════════════════════════════════════════════════════════════
# AC6 — New migration generated for a synthetic model change
# ══════════════════════════════════════════════════════════════════════════════

def test_ac6_autogenerate():
    """AC6: Adding a column to User → alembic revision --autogenerate detects it."""
    user_model_path = _SERVER_DIR / "app" / "models" / "user.py"
    original_content = user_model_path.read_text(encoding="utf-8")

    # Find a good insertion point — before the final closing of the class
    assert "stripe_account_id" in original_content, (
        "Could not find stripe_account_id in user.py — model may have changed"
    )

    synthetic_column = (
        '    uat_test_column: Mapped[str | None] = mapped_column(String(20), nullable=True)\n'
    )
    patched = original_content.replace(
        "    stripe_account_id: Mapped[str | None]",
        f"{synthetic_column}    stripe_account_id: Mapped[str | None]",
    )
    assert patched != original_content, "Patch did not apply — insertion point not found"

    new_migration_path = None
    try:
        # Ensure DB is at head
        _fresh_test_db()
        upgrade = _alembic(["upgrade", "head"])
        assert upgrade.returncode == 0, f"upgrade head failed:\n{upgrade.stderr}"

        # Write patched model
        user_model_path.write_text(patched, encoding="utf-8")

        # Capture existing versions before autogenerate
        existing_versions = {f.name for f in _VERSIONS_DIR.iterdir()
                             if f.suffix == ".py" and f.name != "__init__.py"}

        # Generate migration
        rev = _alembic(["revision", "--autogenerate", "-m", "uat_add_test_column"])
        assert rev.returncode == 0, f"autogenerate failed:\n{rev.stdout}\n{rev.stderr}"

        # Find the new file
        new_versions = {f.name for f in _VERSIONS_DIR.iterdir()
                        if f.suffix == ".py" and f.name != "__init__.py"}
        new_files = new_versions - existing_versions
        assert len(new_files) == 1, (
            f"Expected 1 new migration file, got {len(new_files)}: {new_files}"
        )
        new_migration_name = next(iter(new_files))
        new_migration_path = _VERSIONS_DIR / new_migration_name
        migration_content = new_migration_path.read_text(encoding="utf-8")

        assert "op.add_column" in migration_content and "uat_test_column" in migration_content, (
            f"op.add_column('users', ..., 'uat_test_column') not in migration:\n{migration_content}"
        )
        assert "op.drop_column" in migration_content and "uat_test_column" in migration_content, (
            f"op.drop_column for uat_test_column not in migration:\n{migration_content}"
        )
        print(f"\nNew migration: {new_migration_name}")

        # Apply the migration
        upgrade2 = _alembic(["upgrade", "head"])
        assert upgrade2.returncode == 0, f"upgrade with new column failed:\n{upgrade2.stderr}"

        # Verify column exists
        check = _psql(r"\d users")
        assert "uat_test_column" in check.stdout, (
            f"uat_test_column not found in \\d users output:\n{check.stdout}"
        )
        print(f"Column added: uat_test_column visible in \\d users")

        # Downgrade one step
        downgrade = _alembic(["downgrade", "-1"])
        assert downgrade.returncode == 0, f"downgrade -1 failed:\n{downgrade.stderr}"

        # Verify column removed
        check2 = _psql(r"\d users")
        assert "uat_test_column" not in check2.stdout, (
            f"uat_test_column still present after downgrade:\n{check2.stdout}"
        )
        print("Column removed after downgrade -1")

    finally:
        # Restore original model file
        user_model_path.write_text(original_content, encoding="utf-8")
        # Delete synthetic migration file
        if new_migration_path and new_migration_path.exists():
            new_migration_path.unlink()
        # Restore DB to head (baseline)
        try:
            _fresh_test_db()
            _alembic(["upgrade", "head"])
        except Exception:
            pass

    # Verify git status is clean for user.py
    git_check = subprocess.run(
        ["git", "diff", "--name-only", str(user_model_path)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert git_check.stdout.strip() == "", (
        f"user.py still has uncommitted changes: {git_check.stdout}"
    )
    # Verify no synthetic migration left
    leftover = [f for f in _VERSIONS_DIR.iterdir()
                if f.suffix == ".py" and "uat_add_test_column" in f.name]
    assert len(leftover) == 0, f"Synthetic migration not cleaned up: {leftover}"


# ══════════════════════════════════════════════════════════════════════════════
# AC7 — CLAUDE.md contains schema-migration policy
# ══════════════════════════════════════════════════════════════════════════════

def test_ac7_policy_documented():
    """AC7: CLAUDE.md has schema migration policy with Task #41 incident reference."""
    assert _CLAUDE_MD.exists(), f"CLAUDE.md not found at {_CLAUDE_MD}"
    content = _CLAUDE_MD.read_text(encoding="utf-8")

    # At least one of the required patterns
    patterns = [
        r"Schema migration",
        r"alembic.*PR",
        r"model change.*migration",
        r"server/app/models/.*migration",
    ]
    matches = [p for p in patterns if re.search(p, content, re.IGNORECASE)]
    assert matches, (
        f"None of the expected patterns found in CLAUDE.md: {patterns}"
    )

    # Must mention Task #41 or the consequence (silent prod drift)
    has_incident = (
        "Task #41" in content or
        "silent" in content.lower() and "drift" in content.lower() or
        "decline_reason" in content
    )
    assert has_incident, (
        "CLAUDE.md schema policy section must reference Task #41 incident or "
        "mention silent prod drift consequence"
    )

    # Must state the PR requirement
    has_pr_rule = re.search(
        r"every\s+PR.*model|model.*every\s+PR|PR.*model.*migration|migration.*same\s+PR",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    assert has_pr_rule, (
        "CLAUDE.md must state that every PR changing a model must include a migration"
    )
    print(f"\nPolicy patterns matched: {matches}")
    print("Task #41 incident reference: present")
    print("PR requirement rule: present")
