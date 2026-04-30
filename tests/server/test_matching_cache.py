"""Tests for server/app/services/matching.py — score cache CRUD and invalidation."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.services.matching import (
    _score_cache,
    get_cached_score,
    cache_score,
    invalidate_cache,
    SCORE_CACHE_TTL,
)


@pytest.fixture(autouse=True)
def clear_cache():
    _score_cache.clear()
    yield
    _score_cache.clear()


def test_cached_score_returned_within_ttl():
    cache_score(1, 1, 85.0)
    result = get_cached_score(1, 1)
    assert result == 85.0


def test_cache_miss_after_ttl_expires():
    stale_time = datetime.now(timezone.utc) - SCORE_CACHE_TTL - timedelta(seconds=1)
    _score_cache[(1, 2)] = (72.0, stale_time)
    result = get_cached_score(1, 2)
    assert result is None
    assert (1, 2) not in _score_cache


def test_cache_invalidated_on_campaign_edit():
    cache_score(10, 1, 60.0)
    cache_score(10, 2, 75.0)
    cache_score(99, 1, 50.0)

    invalidate_cache(campaign_id=10)

    assert get_cached_score(10, 1) is None
    assert get_cached_score(10, 2) is None
    assert get_cached_score(99, 1) == 50.0


def test_cache_invalidated_on_user_profile_refresh():
    cache_score(1, 42, 80.0)
    cache_score(2, 42, 65.0)
    cache_score(1, 99, 70.0)

    invalidate_cache(user_id=42)

    assert get_cached_score(1, 42) is None
    assert get_cached_score(2, 42) is None
    assert get_cached_score(1, 99) == 70.0
