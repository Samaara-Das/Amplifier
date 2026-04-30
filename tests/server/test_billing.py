"""Tests for server/app/services/billing.py — earnings calculation, dedup, tiers, hold period."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from types import SimpleNamespace

# Ensure server/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.models.campaign import Campaign
from app.models.metric import Metric
from app.models.payout import Payout, EARNING_HOLD_DAYS
from app.models.user import User
from app.services.billing import (
    calculate_post_earnings_cents,
    get_cpm_multiplier,
    get_tier_config,
    _check_tier_promotion,
    run_billing_cycle,
    promote_pending_earnings,
    void_earnings_for_post,
    TIER_CONFIG,
)


# ---------------------------------------------------------------------------
# calculate_post_earnings_cents — pure function tests
# ---------------------------------------------------------------------------


class TestCalculatePostEarningsCents:
    """Test the core earnings calculation with known inputs."""

    def _make_metric(self, impressions=0, likes=0, reposts=0, clicks=0):
        from types import SimpleNamespace
        return SimpleNamespace(impressions=impressions, likes=likes, reposts=reposts, clicks=clicks)

    def _make_campaign(self, payout_rules=None):
        from types import SimpleNamespace
        return SimpleNamespace(payout_rules=payout_rules or {
            "rate_per_1k_impressions": 0.50,
            "rate_per_like": 0.01,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.10,
        })

    @patch("app.services.billing.settings")
    def test_basic_earnings(self, mock_settings):
        """1000 impressions at $0.50/1K, 50 likes at $0.01, 10 reposts at $0.05, 5 clicks at $0.10."""
        mock_settings.platform_cut_percent = 20.0

        metric = self._make_metric(impressions=1000, likes=50, reposts=10, clicks=5)
        campaign = self._make_campaign()

        cents = calculate_post_earnings_cents(metric, campaign)

        # Raw: (1000 * 50 // 1000) + (50 * 1) + (10 * 5) + (5 * 10)
        #    = 50 + 50 + 50 + 50 = 200 cents raw
        # After 20% cut: 200 * 80 // 100 = 160 cents
        assert cents == 160

    @patch("app.services.billing.settings")
    def test_zero_metrics(self, mock_settings):
        """Zero engagement should return zero earnings."""
        mock_settings.platform_cut_percent = 20.0

        metric = self._make_metric()
        campaign = self._make_campaign()

        cents = calculate_post_earnings_cents(metric, campaign)
        assert cents == 0

    @patch("app.services.billing.settings")
    def test_impressions_only(self, mock_settings):
        """Only impressions, no engagement."""
        mock_settings.platform_cut_percent = 20.0

        metric = self._make_metric(impressions=5000)
        campaign = self._make_campaign()

        cents = calculate_post_earnings_cents(metric, campaign)
        # Raw: 5000 * 50 // 1000 = 250
        # After cut: 250 * 80 // 100 = 200
        assert cents == 200

    @patch("app.services.billing.settings")
    def test_different_platform_cut(self, mock_settings):
        """Test with a different platform cut percentage."""
        mock_settings.platform_cut_percent = 10.0

        metric = self._make_metric(impressions=1000)
        campaign = self._make_campaign()

        cents = calculate_post_earnings_cents(metric, campaign)
        # Raw: 1000 * 50 // 1000 = 50
        # After 10% cut: 50 * 90 // 100 = 45
        assert cents == 45

    @patch("app.services.billing.settings")
    def test_large_engagement(self, mock_settings):
        """Large numbers — verify no overflow or rounding issues."""
        mock_settings.platform_cut_percent = 20.0

        metric = self._make_metric(
            impressions=1_000_000, likes=50_000, reposts=10_000, clicks=5_000
        )
        campaign = self._make_campaign()

        cents = calculate_post_earnings_cents(metric, campaign)
        # Raw: (1M * 50 // 1000) + (50K * 1) + (10K * 5) + (5K * 10)
        #    = 50000 + 50000 + 50000 + 50000 = 200_000 cents
        # After 20% cut: 200000 * 80 // 100 = 160_000
        assert cents == 160_000

    @patch("app.services.billing.settings")
    def test_custom_payout_rules(self, mock_settings):
        """Custom payout rules with different rates."""
        mock_settings.platform_cut_percent = 20.0

        metric = self._make_metric(impressions=2000, likes=100)
        campaign = self._make_campaign(payout_rules={
            "rate_per_1k_impressions": 2.00,  # $2 per 1K
            "rate_per_like": 0.05,             # $0.05 per like
            "rate_per_repost": 0,
            "rate_per_click": 0,
        })

        cents = calculate_post_earnings_cents(metric, campaign)
        # Raw: (2000 * 200 // 1000) + (100 * 5) = 400 + 500 = 900
        # After cut: 900 * 80 // 100 = 720
        assert cents == 720

    @patch("app.services.billing.settings")
    def test_integer_precision(self, mock_settings):
        """All math is in integer cents — no float rounding errors."""
        mock_settings.platform_cut_percent = 20.0

        metric = self._make_metric(impressions=1, likes=1)
        campaign = self._make_campaign()

        cents = calculate_post_earnings_cents(metric, campaign)
        # Raw: (1 * 50 // 1000) + (1 * 1) = 0 + 1 = 1
        # After cut: 1 * 80 // 100 = 0  (integer division)
        assert cents == 0  # Below minimum unit after platform cut


# ---------------------------------------------------------------------------
# Tier config + CPM multiplier
# ---------------------------------------------------------------------------


class TestTierConfig:
    def test_seedling_defaults(self):
        config = get_tier_config("seedling")
        assert config["max_campaigns"] == 3
        assert config["cpm_multiplier"] == 1.0

    def test_grower_config(self):
        config = get_tier_config("grower")
        assert config["max_campaigns"] == 10
        assert config["cpm_multiplier"] == 1.0

    def test_amplifier_config(self):
        config = get_tier_config("amplifier")
        assert config["max_campaigns"] == 999
        assert config["cpm_multiplier"] == 2.0

    def test_unknown_tier_defaults_to_seedling(self):
        config = get_tier_config("nonexistent")
        assert config == TIER_CONFIG["seedling"]

    def test_cpm_multiplier_seedling(self):
        user = SimpleNamespace(tier="seedling")
        assert get_cpm_multiplier(user) == 1.0

    def test_cpm_multiplier_amplifier_2x(self):
        user = SimpleNamespace(tier="amplifier")
        assert get_cpm_multiplier(user) == 2.0


# ---------------------------------------------------------------------------
# Tier promotion
# ---------------------------------------------------------------------------


class TestTierPromotion:
    def test_seedling_to_grower_at_20_posts(self):
        user = SimpleNamespace(id=1, tier="seedling", successful_post_count=20, trust_score=50)

        _check_tier_promotion(user)
        assert user.tier == "grower"

    def test_seedling_stays_below_20_posts(self):
        user = SimpleNamespace(id=1, tier="seedling", successful_post_count=19, trust_score=50)

        _check_tier_promotion(user)
        assert user.tier == "seedling"

    def test_grower_to_amplifier_at_100_posts_high_trust(self):
        user = SimpleNamespace(id=1, tier="grower", successful_post_count=100, trust_score=80)

        _check_tier_promotion(user)
        assert user.tier == "amplifier"

    def test_grower_stays_with_low_trust(self):
        user = SimpleNamespace(id=1, tier="grower", successful_post_count=100, trust_score=79)  # Needs >= 80

        _check_tier_promotion(user)
        assert user.tier == "grower"

    def test_grower_stays_below_100_posts(self):
        user = SimpleNamespace(id=1, tier="grower", successful_post_count=99, trust_score=90)

        _check_tier_promotion(user)
        assert user.tier == "grower"

    def test_amplifier_stays_amplifier(self):
        """Amplifier is the top tier — no further promotion."""
        user = SimpleNamespace(id=1, tier="amplifier", successful_post_count=500, trust_score=100)

        _check_tier_promotion(user)
        assert user.tier == "amplifier"

    def test_none_tier_treated_as_seedling(self):
        user = SimpleNamespace(id=1, tier=None, successful_post_count=25, trust_score=50)

        _check_tier_promotion(user)
        assert user.tier == "grower"


# ---------------------------------------------------------------------------
# run_billing_cycle — integration test using the async test DB
# ---------------------------------------------------------------------------


class TestBillingCycle:
    async def test_billing_creates_payout_record(self, db_session, factory):
        """Full billing flow: metric -> payout record with correct amounts."""
        company = await factory.create_company(db_session)
        campaign = await factory.create_campaign(db_session, company.id, budget_total=500.0)
        user = await factory.create_user(db_session)
        assignment = await factory.create_assignment(db_session, campaign.id, user.id)
        post = await factory.create_post(db_session, assignment.id)
        metric = await factory.create_metric(
            db_session, post.id,
            impressions=1000, likes=50, reposts=10, clicks=5,
        )
        await db_session.flush()

        result = await run_billing_cycle(db_session)

        assert result["posts_processed"] == 1
        assert result["total_earned"] > 0

        # Check payout record was created
        payouts = (await db_session.execute(select(Payout))).scalars().all()
        assert len(payouts) == 1
        payout = payouts[0]
        assert payout.user_id == user.id
        assert payout.campaign_id == campaign.id
        assert payout.status == "pending"
        assert payout.amount_cents > 0
        assert payout.available_at is not None

    async def test_billing_dedup_same_metric(self, db_session, factory):
        """Billing the same metric twice should not create duplicate payouts."""
        company = await factory.create_company(db_session)
        campaign = await factory.create_campaign(db_session, company.id)
        user = await factory.create_user(db_session)
        assignment = await factory.create_assignment(db_session, campaign.id, user.id)
        post = await factory.create_post(db_session, assignment.id)
        await factory.create_metric(db_session, post.id, impressions=1000)
        await db_session.flush()

        # First billing
        result1 = await run_billing_cycle(db_session)
        assert result1["posts_processed"] == 1

        # Second billing — same metric, should be skipped
        result2 = await run_billing_cycle(db_session)
        assert result2["posts_processed"] == 0

    async def test_billing_caps_at_budget(self, db_session, factory):
        """Earnings should not exceed remaining campaign budget."""
        company = await factory.create_company(db_session)
        # Tiny budget — should cap
        campaign = await factory.create_campaign(
            db_session, company.id, budget_total=0.01, budget_remaining=0.01,
        )
        user = await factory.create_user(db_session)
        assignment = await factory.create_assignment(db_session, campaign.id, user.id)
        post = await factory.create_post(db_session, assignment.id)
        await factory.create_metric(db_session, post.id, impressions=100_000)
        await db_session.flush()

        result = await run_billing_cycle(db_session)
        # Budget was only $0.01, so total earned is capped
        assert result["total_earned"] <= 0.01

    async def test_billing_amplifier_tier_2x(self, db_session, factory):
        """Amplifier tier user gets 2x CPM multiplier on earnings."""
        company = await factory.create_company(db_session)
        campaign = await factory.create_campaign(db_session, company.id, budget_total=5000.0)

        # Create two users — one seedling, one amplifier
        user_seedling = await factory.create_user(
            db_session, email="seed@test.com", tier="seedling"
        )
        user_amplifier = await factory.create_user(
            db_session, email="amp@test.com", tier="amplifier"
        )

        # Same campaign, same metrics for both
        assignment_s = await factory.create_assignment(db_session, campaign.id, user_seedling.id)
        assignment_a = await factory.create_assignment(db_session, campaign.id, user_amplifier.id)

        post_s = await factory.create_post(db_session, assignment_s.id)
        post_a = await factory.create_post(db_session, assignment_a.id, post_url="https://x.com/user/status/456")

        await factory.create_metric(db_session, post_s.id, impressions=1000, likes=50)
        await factory.create_metric(db_session, post_a.id, impressions=1000, likes=50)
        await db_session.flush()

        await run_billing_cycle(db_session)

        payouts = (await db_session.execute(select(Payout))).scalars().all()
        assert len(payouts) == 2

        payout_map = {p.user_id: p for p in payouts}
        seedling_cents = payout_map[user_seedling.id].amount_cents
        amplifier_cents = payout_map[user_amplifier.id].amount_cents

        # Amplifier should earn 2x what seedling earns
        assert amplifier_cents == seedling_cents * 2


# ---------------------------------------------------------------------------
# promote_pending_earnings — hold period
# ---------------------------------------------------------------------------


class TestPromotePendingEarnings:
    async def test_promote_after_hold_period(self, db_session, factory):
        """Payouts older than EARNING_HOLD_DAYS should be promoted to available."""
        company = await factory.create_company(db_session)
        campaign = await factory.create_campaign(db_session, company.id)
        user = await factory.create_user(db_session)

        now = datetime.now(timezone.utc)
        old_payout = Payout(
            user_id=user.id,
            campaign_id=campaign.id,
            amount=1.60,
            amount_cents=160,
            period_start=now - timedelta(days=10),
            period_end=now - timedelta(days=10),
            status="pending",
            available_at=now - timedelta(days=1),  # Already past hold
            breakdown={"metric_id": 999},
        )
        db_session.add(old_payout)
        await db_session.flush()

        promoted = await promote_pending_earnings(db_session)
        assert promoted == 1

        await db_session.refresh(old_payout)
        assert old_payout.status == "available"

    async def test_no_promote_before_hold_period(self, db_session, factory):
        """Payouts within the hold period should stay pending."""
        company = await factory.create_company(db_session)
        campaign = await factory.create_campaign(db_session, company.id)
        user = await factory.create_user(db_session)

        now = datetime.now(timezone.utc)
        recent_payout = Payout(
            user_id=user.id,
            campaign_id=campaign.id,
            amount=1.60,
            amount_cents=160,
            period_start=now,
            period_end=now,
            status="pending",
            available_at=now + timedelta(days=EARNING_HOLD_DAYS),
            breakdown={"metric_id": 888},
        )
        db_session.add(recent_payout)
        await db_session.flush()

        promoted = await promote_pending_earnings(db_session)
        assert promoted == 0

        await db_session.refresh(recent_payout)
        assert recent_payout.status == "pending"


# ---------------------------------------------------------------------------
# void_earnings_for_post
# ---------------------------------------------------------------------------


class TestVoidEarnings:
    async def test_void_pending_payout(self, db_session, factory):
        """Voiding a pending payout should mark it voided and return funds to campaign."""
        company = await factory.create_company(db_session)
        campaign = await factory.create_campaign(
            db_session, company.id, budget_total=1000.0, budget_remaining=900.0,
        )
        user = await factory.create_user(db_session)

        now = datetime.now(timezone.utc)
        payout = Payout(
            user_id=user.id,
            campaign_id=campaign.id,
            amount=1.60,
            amount_cents=160,
            period_start=now,
            period_end=now,
            status="pending",
            available_at=now + timedelta(days=7),
            breakdown={"post_id": 42, "metric_id": 99, "budget_cost_cents": 200},
        )
        db_session.add(payout)

        # Give user a balance to deduct from
        user.earnings_balance = 1.60
        user.total_earned = 1.60
        await db_session.flush()

        voided = await void_earnings_for_post(db_session, post_id=42)
        assert voided == 1

        await db_session.refresh(payout)
        assert payout.status == "voided"

        # Budget should be restored by budget_cost_cents (200 cents = $2.00)
        await db_session.refresh(campaign)
        assert float(campaign.budget_remaining) == pytest.approx(902.0, abs=0.01)

        # User balance should be deducted
        await db_session.refresh(user)
        assert float(user.earnings_balance) == pytest.approx(0.0, abs=0.01)

    async def test_void_does_not_affect_available_payouts(self, db_session, factory):
        """Already-available payouts should NOT be voided (hold period passed)."""
        company = await factory.create_company(db_session)
        campaign = await factory.create_campaign(db_session, company.id)
        user = await factory.create_user(db_session)

        now = datetime.now(timezone.utc)
        payout = Payout(
            user_id=user.id,
            campaign_id=campaign.id,
            amount=1.60,
            amount_cents=160,
            period_start=now,
            period_end=now,
            status="available",  # Already promoted past hold
            available_at=now - timedelta(days=1),
            breakdown={"post_id": 42, "metric_id": 99},
        )
        db_session.add(payout)
        await db_session.flush()

        voided = await void_earnings_for_post(db_session, post_id=42)
        assert voided == 0  # Nothing voided — was already available
