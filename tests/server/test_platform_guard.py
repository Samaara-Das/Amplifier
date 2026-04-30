"""Tests for server/app/utils/platform_guard.py — disabled platform safety guard."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.utils.platform_guard import (
    DISABLED_PLATFORMS,
    is_platform_disabled,
    contains_disabled,
    filter_disabled,
)


class TestDisabledPlatformsFrozenset:
    def test_frozenset_is_exactly_x(self):
        assert DISABLED_PLATFORMS == frozenset({"x"})


class TestIsPlatformDisabled:
    def test_x_lowercase_disabled(self):
        assert is_platform_disabled("x") is True

    def test_x_uppercase_disabled(self):
        assert is_platform_disabled("X") is True

    def test_x_with_spaces_disabled(self):
        assert is_platform_disabled(" x ") is True
        assert is_platform_disabled("  X  ") is True

    def test_linkedin_not_disabled(self):
        assert is_platform_disabled("linkedin") is False

    def test_facebook_not_disabled(self):
        assert is_platform_disabled("facebook") is False

    def test_reddit_not_disabled(self):
        assert is_platform_disabled("reddit") is False

    def test_tiktok_not_disabled(self):
        assert is_platform_disabled("tiktok") is False

    def test_instagram_not_disabled(self):
        assert is_platform_disabled("instagram") is False

    def test_none_not_disabled(self):
        assert is_platform_disabled(None) is False

    def test_empty_string_not_disabled(self):
        assert is_platform_disabled("") is False


class TestContainsDisabled:
    def test_list_with_x_returns_true(self):
        assert contains_disabled(["x", "linkedin"]) is True

    def test_list_without_x_returns_false(self):
        assert contains_disabled(["linkedin", "reddit"]) is False

    def test_empty_list_returns_false(self):
        assert contains_disabled([]) is False

    def test_none_returns_false(self):
        assert contains_disabled(None) is False

    def test_uppercase_x_in_list(self):
        assert contains_disabled(["X", "facebook"]) is True


class TestFilterDisabled:
    def test_strips_x_preserves_order(self):
        result = filter_disabled(["x", "linkedin", "X", "reddit", "facebook"])
        assert result == ["linkedin", "reddit", "facebook"]

    def test_no_disabled_returns_all(self):
        result = filter_disabled(["linkedin", "reddit", "facebook"])
        assert result == ["linkedin", "reddit", "facebook"]

    def test_all_disabled_returns_empty(self):
        result = filter_disabled(["x", "X", " x "])
        assert result == []

    def test_none_returns_empty_list(self):
        assert filter_disabled(None) == []

    def test_empty_returns_empty_list(self):
        assert filter_disabled([]) == []
