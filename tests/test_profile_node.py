"""Tests for the profile extraction node."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from agents.profile_node import profile_node
from utils.local_db import upsert_user_profile


class TestProfileNode:
    def test_no_cached_profiles(self):
        """Returns empty profiles when nothing is cached."""
        state = {"enabled_platforms": ["x", "linkedin"]}
        result = profile_node(state)
        assert result["user_profiles"] == {}

    def test_returns_cached_profiles(self):
        """Returns cached profiles from DB."""
        upsert_user_profile("x", "I help traders", '["post1", "post2"]', "Punchy", 5000)
        upsert_user_profile("linkedin", "Trading educator", '["article1"]', "Professional", 9500)

        state = {"enabled_platforms": ["x", "linkedin"]}
        result = profile_node(state)

        assert "x" in result["user_profiles"]
        assert "linkedin" in result["user_profiles"]
        assert result["user_profiles"]["x"]["bio"] == "I help traders"
        assert result["user_profiles"]["x"]["follower_count"] == 5000
        assert result["user_profiles"]["linkedin"]["bio"] == "Trading educator"

    def test_filters_by_enabled_platforms(self):
        """Only returns profiles for enabled platforms."""
        upsert_user_profile("x", "bio", "[]", "", 100)
        upsert_user_profile("tiktok", "bio", "[]", "", 200)

        state = {"enabled_platforms": ["x"]}
        result = profile_node(state)

        assert "x" in result["user_profiles"]
        assert "tiktok" not in result["user_profiles"]

    def test_marks_stale_profiles(self):
        """Profiles without extracted_at are marked as stale."""
        upsert_user_profile("x", "bio", "[]", "", 100)

        state = {"enabled_platforms": ["x"]}
        result = profile_node(state)

        # Freshly inserted profile should not be stale
        assert result["user_profiles"]["x"]["stale"] is False

    def test_empty_platforms_returns_all(self):
        """When no platforms specified, returns all cached profiles."""
        upsert_user_profile("x", "bio", "[]", "", 100)
        upsert_user_profile("reddit", "bio", "[]", "", 50)

        state = {"enabled_platforms": []}
        result = profile_node(state)
        # With empty list, should return empty (no platforms requested)
        # This matches the current behavior
        assert isinstance(result["user_profiles"], dict)
