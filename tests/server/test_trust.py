"""Tests for server/app/services/trust.py — adjust_trust() event adjustments and bounds."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.services.trust import adjust_trust, TRUST_EVENTS


@pytest.mark.asyncio
async def test_adjust_trust_clamps_to_0_100_bounds(db_session, factory):
    user = await factory.create_user(db_session, email="bounds@test.com", trust_score=99)

    new_score = await adjust_trust(db_session, user.id, "campaign_completed")
    assert new_score == 100
    assert user.trust_score == 100

    user.trust_score = 5
    await db_session.flush()
    new_score = await adjust_trust(db_session, user.id, "confirmed_fake_metrics")
    assert new_score == 0
    assert user.trust_score == 0


@pytest.mark.asyncio
async def test_event_post_verified_live_24h_increments_trust(db_session, factory):
    user = await factory.create_user(db_session, email="verified@test.com", trust_score=50)

    delta = TRUST_EVENTS["post_verified_live_24h"]
    new_score = await adjust_trust(db_session, user.id, "post_verified_live_24h")
    assert new_score == 50 + delta
    assert user.trust_score == 50 + delta


@pytest.mark.asyncio
async def test_event_confirmed_fake_metrics_decrements_trust_severely(db_session, factory):
    user = await factory.create_user(db_session, email="fake@test.com", trust_score=70)

    delta = TRUST_EVENTS["confirmed_fake_metrics"]
    new_score = await adjust_trust(db_session, user.id, "confirmed_fake_metrics")
    assert new_score == max(0, 70 + delta)
    assert user.trust_score == max(0, 70 + delta)


@pytest.mark.asyncio
async def test_unknown_event_no_change_no_crash(db_session, factory):
    user = await factory.create_user(db_session, email="unknown@test.com", trust_score=50)

    result = await adjust_trust(db_session, user.id, "nonexistent_event_xyz")
    assert result == 0
    assert user.trust_score == 50
