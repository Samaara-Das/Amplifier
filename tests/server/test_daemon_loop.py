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


# ── Test 3 (Task #84): concurrent loops are spawned at run() start ──────────


@pytest.mark.asyncio
async def test_concurrent_loops_spawned():
    """After start_background_agent(), _cmd_task and _status_task are running.

    Task #84 refactor: command_poll + status_push run as independent
    asyncio.Tasks so heavy main-loop work cannot starve them.
    """
    import asyncio
    with patch.multiple("background_agent", **{
        k.split("background_agent.")[-1]: v
        for k, v in _all_task_patches().items()
        if k.startswith("background_agent.")
    }):
        from background_agent import start_background_agent

        agent = await start_background_agent()
        # Yield once so the spawned tasks get to run their first scheduling step
        await asyncio.sleep(0)

        assert agent._cmd_task is not None, "_cmd_task must be spawned at run() start"
        assert agent._status_task is not None, "_status_task must be spawned at run() start"
        assert not agent._cmd_task.done(), "_cmd_task must still be running"
        assert not agent._status_task.done(), "_status_task must still be running"


# ── Test 4 (Task #84): status_push fires while main loop is blocked ─────────


@pytest.mark.asyncio
async def test_status_push_fires_during_long_main_loop():
    """status_push_loop must fire even when generate_daily_content is slow.

    This is the regression test for the loop-starvation bug discovered during
    /uat-task 82: with content_gen taking ~25s+, the old sequential loop
    couldn't reach push_agent_status. The concurrent-task design (#84) fixes
    this — status push fires on its own schedule.
    """
    import asyncio

    push_calls = {"count": 0}

    async def slow_content_gen(*args, **kwargs):
        # Simulate heavy content gen blocking the main loop
        await asyncio.sleep(2.0)
        return {"generated": 1}

    async def counting_push(_agent):
        push_calls["count"] += 1
        return True

    patches = _all_task_patches()
    patches["background_agent.generate_daily_content"] = slow_content_gen
    patches["background_agent.push_agent_status"] = counting_push

    with patch.multiple("background_agent", **{
        k.split("background_agent.")[-1]: v
        for k, v in patches.items()
        if k.startswith("background_agent.")
    }):
        # Force STATUS_PUSH_INTERVAL to a tiny value so the test runs fast.
        # The constant is module-level — patch it directly.
        with patch("background_agent.STATUS_PUSH_INTERVAL", 0.1):
            from background_agent import start_background_agent

            await start_background_agent()
            # Wait long enough for status push to fire several times,
            # while main-loop content_gen would still be in its first sleep.
            await asyncio.sleep(0.5)

            assert push_calls["count"] >= 2, (
                f"push_agent_status must fire on its own schedule even when "
                f"main loop is blocked. Got {push_calls['count']} calls."
            )
