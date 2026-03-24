"""Shared fixtures for agent pipeline tests."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(autouse=True)
def _env_setup(tmp_path, monkeypatch):
    """Set up test environment: temp DB, mock API keys."""
    # Use temp DB so tests don't touch real data
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("utils.local_db.DB_PATH", db_path)

    # Set dummy API keys (tests that hit real APIs should be marked separately)
    monkeypatch.setenv("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", "test-key"))

    # Init DB
    from utils.local_db import init_db
    init_db()


@pytest.fixture
def sample_campaign():
    """A realistic test campaign dict."""
    return {
        "campaign_id": 999,
        "title": "AI Trading Indicator Launch",
        "brief": "Promote our new AI-powered trading indicator that helps retail traders "
                 "spot reversals before they happen. Focus on how it saves people from "
                 "losing money on fake breakouts.",
        "content_guidance": "Target beginner traders. Emphasize ease of use.",
        "assets": "{}",
    }


@pytest.fixture
def sample_state(sample_campaign):
    """A pipeline state with campaign + enabled platforms."""
    return {
        "campaign": sample_campaign,
        "enabled_platforms": ["x", "linkedin", "facebook", "reddit"],
    }
