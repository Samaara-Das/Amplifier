"""Tests for BackgroundAgent lifecycle: start, singleton guard, and stop.

These tests verify the module-level start_background_agent / stop_background_agent
functions without running real network calls or platform automation. All heavy
tasks (post execution, campaign polling, metric scraping, etc.) are patched to
no-ops so the agent loop can boot cleanly inside the test event loop.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _reset_agent():
    """Ensure the module-level _agent singleton is None before and after each test."""
    import background_agent as ba

    # Reset before
    ba._agent = None

    yield

    # Stop and reset after, regardless of test outcome
    try:
        await ba.stop_background_agent()
    except Exception:
        pass
    ba._agent = None


def _all_task_patches():
    """Return a dict of all run-loop task functions patched to async no-ops.

    Patches are applied at the background_agent module level so the run()
    loop picks them up when it calls e.g. `execute_due_posts()`.
    """
    return {
        "background_agent.execute_due_posts": AsyncMock(return_value={"skipped": 0}),
        "background_agent.poll_campaigns": AsyncMock(return_value={"success": True}),
        "background_agent.generate_daily_content": AsyncMock(return_value={"generated": 0}),
        "background_agent.check_sessions": AsyncMock(return_value={"checked": 0}),
        "background_agent.backup_local_db": AsyncMock(return_value={"ok": True}),
        "background_agent.refresh_profiles": AsyncMock(return_value={"refreshed": 0}),
        "background_agent.run_metric_scraping": AsyncMock(return_value={"scraped": 0}),
        "background_agent.sync_unsynced_drafts": AsyncMock(return_value={"synced": 0}),
        "background_agent.process_server_commands": AsyncMock(return_value={"processed": 0}),
        "background_agent.push_agent_status": AsyncMock(return_value=True),
        # Suppress requeue_failed_posts (non-async util import inside run)
        "utils.local_db.requeue_failed_posts": MagicMock(return_value=0),
        # Suppress auto_update import (optional dependency, may not exist in test env)
        "utils.auto_update.check_and_notify": MagicMock(),
    }


# ── Test 1: start_background_agent returns a running agent ──────────────────


@pytest.mark.asyncio
async def test_start_background_agent_returns_running_agent():
    """start_background_agent() returns a non-None agent with running=True."""
    with patch.multiple("background_agent", **{
        k.split("background_agent.")[-1]: v
        for k, v in _all_task_patches().items()
        if k.startswith("background_agent.")
    }):
        from background_agent import start_background_agent, stop_background_agent

        agent = await start_background_agent()

        assert agent is not None, "start_background_agent() must return an agent"
        assert agent.running is True, "agent.running must be True immediately after start"
        assert agent._task is not None, "agent._task must be set (asyncio.Task)"
        assert not agent._task.done(), "agent._task must still be running"


# ── Test 2: calling start_background_agent twice returns the same agent ──────


@pytest.mark.asyncio
async def test_start_background_agent_singleton_idempotent():
    """Calling start_background_agent() while agent is running returns the same instance."""
    with patch.multiple("background_agent", **{
        k.split("background_agent.")[-1]: v
        for k, v in _all_task_patches().items()
        if k.startswith("background_agent.")
    }):
        from background_agent import start_background_agent

        agent_first = await start_background_agent()
        agent_second = await start_background_agent()

        assert agent_first is agent_second, (
            "Second call must return the same agent instance (singleton guard)"
        )
        assert agent_first.running is True
