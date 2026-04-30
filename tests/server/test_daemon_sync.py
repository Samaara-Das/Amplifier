"""Unit tests for daemon-side server-sync logic: command dispatch and draft upload.

These tests are pure-mock (no DB, no server, no async fixtures from conftest).
They import daemon code from scripts/ and patch at the utils.* call sites.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))


# ── Helpers ────────────────────────────────────────────────────────


def _make_agent(paused: bool = False):
    """Return a minimal BackgroundAgent-like stub."""
    from background_agent import BackgroundAgent
    agent = BackgroundAgent.__new__(BackgroundAgent)
    agent.running = True
    agent.paused = paused
    # Provide a real pause/resume so handlers can call them
    agent.pause = lambda: setattr(agent, "paused", True)
    agent.resume = lambda: setattr(agent, "paused", False)
    return agent


# ── Tests ──────────────────────────────────────────────────────────


class TestProcessServerCommands:
    @pytest.mark.asyncio
    async def test_pause_agent_command_sets_paused(self):
        """pause_agent command should flip agent.paused to True and ack done."""
        agent = _make_agent(paused=False)
        assert agent.paused is False

        cmd = {"id": 1, "type": "pause_agent", "payload": {}}
        with patch("utils.server_client.get_pending_commands", return_value=[cmd]) as _mock_get, \
             patch("utils.server_client.ack_command") as mock_ack:
            from background_agent import process_server_commands
            result = await process_server_commands(agent)

        assert agent.paused is True
        mock_ack.assert_called_once_with(1, result="done")
        assert result["processed"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_resume_agent_command_clears_paused(self):
        """resume_agent command should flip agent.paused to False and ack done."""
        agent = _make_agent(paused=True)
        assert agent.paused is True

        cmd = {"id": 2, "type": "resume_agent", "payload": {}}
        with patch("utils.server_client.get_pending_commands", return_value=[cmd]), \
             patch("utils.server_client.ack_command") as mock_ack:
            from background_agent import process_server_commands
            result = await process_server_commands(agent)

        assert agent.paused is False
        mock_ack.assert_called_once_with(2, result="done")
        assert result["processed"] == 1

    @pytest.mark.asyncio
    async def test_unknown_command_type_acked_as_failed(self):
        """Unknown command types should be acked with result='failed'."""
        agent = _make_agent()
        cmd = {"id": 3, "type": "teleport_drone", "payload": {}}
        with patch("utils.server_client.get_pending_commands", return_value=[cmd]), \
             patch("utils.server_client.ack_command") as mock_ack:
            from background_agent import process_server_commands
            result = await process_server_commands(agent)

        mock_ack.assert_called_once_with(3, result="failed", error="unknown command type")
        assert result["failed"] == 1
        assert result["processed"] == 0

    @pytest.mark.asyncio
    async def test_generate_content_command_calls_handler_with_campaign_id(self):
        """generate_content command should invoke generate_daily_content with campaign_id_filter."""
        agent = _make_agent(paused=False)
        cmd = {"id": 4, "type": "generate_content", "payload": {"campaign_id": 99}}

        with patch("utils.server_client.get_pending_commands", return_value=[cmd]), \
             patch("utils.server_client.ack_command"), \
             patch("background_agent.generate_daily_content", new_callable=AsyncMock) as mock_gen:
            from background_agent import process_server_commands
            result = await process_server_commands(agent)

        mock_gen.assert_called_once_with(campaign_id_filter=99)
        assert result["processed"] == 1

    @pytest.mark.asyncio
    async def test_generate_content_skipped_when_paused(self):
        """generate_content handler should skip (not raise) when agent is paused."""
        agent = _make_agent(paused=True)
        cmd = {"id": 5, "type": "generate_content", "payload": {"campaign_id": 7}}

        with patch("utils.server_client.get_pending_commands", return_value=[cmd]), \
             patch("utils.server_client.ack_command") as mock_ack, \
             patch("background_agent.generate_daily_content", new_callable=AsyncMock) as mock_gen:
            from background_agent import process_server_commands
            result = await process_server_commands(agent)

        # Handler should ack done (handler ran, just no-op because paused)
        mock_ack.assert_called_once_with(5, result="done")
        mock_gen.assert_not_called()
        assert result["processed"] == 1


class TestSyncUnsyncedDrafts:
    @pytest.mark.asyncio
    async def test_uploads_unsynced_drafts_and_marks_synced(self):
        """Both unsynced drafts should be uploaded and marked synced."""
        drafts = [
            {"id": 10, "campaign_id": 1, "platform": "linkedin",
             "draft_text": "Hello world", "image_path": None,
             "quality_score": 80, "iteration": 1},
            {"id": 11, "campaign_id": 1, "platform": "reddit",
             "draft_text": "Another post", "image_path": None,
             "quality_score": 75, "iteration": 1},
        ]

        with patch("utils.local_db.get_unsynced_drafts", return_value=drafts), \
             patch("utils.local_db.mark_draft_synced") as mock_mark, \
             patch("utils.server_client.upload_draft",
                   return_value={"id": 200, "status": "pending"}) as mock_upload:
            from background_agent import sync_unsynced_drafts
            result = await sync_unsynced_drafts()

        assert result["uploaded"] == 2
        assert result["failed"] == 0
        assert mock_upload.call_count == 2
        mock_mark.assert_any_call(10, server_draft_id=200)
        mock_mark.assert_any_call(11, server_draft_id=200)

    @pytest.mark.asyncio
    async def test_first_draft_failure_does_not_skip_second(self):
        """If the first upload fails, the second should still be attempted."""
        drafts = [
            {"id": 20, "campaign_id": 2, "platform": "x",
             "draft_text": "Post A", "image_path": None,
             "quality_score": 70, "iteration": 1},
            {"id": 21, "campaign_id": 2, "platform": "facebook",
             "draft_text": "Post B", "image_path": None,
             "quality_score": 65, "iteration": 1},
        ]

        call_count = {"n": 0}

        def _upload_side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Server unavailable")
            return {"id": 300, "status": "pending"}

        with patch("utils.local_db.get_unsynced_drafts", return_value=drafts), \
             patch("utils.local_db.mark_draft_synced") as mock_mark, \
             patch("utils.server_client.upload_draft",
                   side_effect=_upload_side_effect):
            from background_agent import sync_unsynced_drafts
            result = await sync_unsynced_drafts()

        assert result["uploaded"] == 1
        assert result["failed"] == 1
        # Second draft was marked synced
        mock_mark.assert_called_once_with(21, server_draft_id=300)
