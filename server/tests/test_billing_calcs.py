"""Unit tests for billing calculation logic.

Tests pure math — no database, no async. Validates earnings formula,
platform cut, budget cap, CPM/CPE calculations.
"""

import pytest


# ── Earnings Formula ─────────────────────────────────────────────


def calculate_raw_earnings(
    impressions: int, likes: int, reposts: int, clicks: int,
    rate_per_1k_impressions: float, rate_per_like: float,
    rate_per_repost: float, rate_per_click: float,
) -> float:
    """Same formula as billing.py calculate_post_earnings."""
    return (
        (impressions / 1000.0 * rate_per_1k_impressions)
        + (likes * rate_per_like)
        + (reposts * rate_per_repost)
        + (clicks * rate_per_click)
    )


def apply_platform_cut(raw_earning: float, platform_cut_percent: float = 20.0) -> float:
    """Same as billing.py: user gets (1 - cut%)."""
    return round(raw_earning * (1 - platform_cut_percent / 100.0), 2)


def cap_to_budget(earning: float, budget_remaining: float, platform_cut_percent: float = 20.0) -> float:
    """Cap earning to remaining budget."""
    budget_cost = earning / (1 - platform_cut_percent / 100.0)
    if budget_cost > budget_remaining:
        budget_cost = budget_remaining
        earning = budget_cost * (1 - platform_cut_percent / 100.0)
    return round(earning, 2)


# ── CPM/CPE (campaign detail page) ──────────────────────────────


def calculate_cpm(spend: float, impressions: int) -> float:
    """Cost per 1K impressions."""
    return round((spend / impressions * 1000), 2) if impressions > 0 else 0


def calculate_cpe(spend: float, engagement: int) -> float:
    """Cost per engagement."""
    return round((spend / engagement), 2) if engagement > 0 else 0


# ── Tests ────────────────────────────────────────────────────────


class TestEarningsFormula:
    def test_basic_earnings(self):
        raw = calculate_raw_earnings(
            impressions=10000, likes=50, reposts=10, clicks=5,
            rate_per_1k_impressions=0.50, rate_per_like=0.01,
            rate_per_repost=0.05, rate_per_click=0.10,
        )
        # 10000/1000*0.50 + 50*0.01 + 10*0.05 + 5*0.10
        # = 5.00 + 0.50 + 0.50 + 0.50 = 6.50
        assert raw == pytest.approx(6.50)

    def test_zero_metrics(self):
        raw = calculate_raw_earnings(
            impressions=0, likes=0, reposts=0, clicks=0,
            rate_per_1k_impressions=0.50, rate_per_like=0.01,
            rate_per_repost=0.05, rate_per_click=0.10,
        )
        assert raw == 0.0

    def test_impressions_only(self):
        raw = calculate_raw_earnings(
            impressions=1000, likes=0, reposts=0, clicks=0,
            rate_per_1k_impressions=1.00, rate_per_like=0, rate_per_repost=0, rate_per_click=0,
        )
        assert raw == pytest.approx(1.00)

    def test_high_value_niche_rates(self):
        raw = calculate_raw_earnings(
            impressions=5000, likes=100, reposts=20, clicks=10,
            rate_per_1k_impressions=1.00, rate_per_like=0.02,
            rate_per_repost=0.10, rate_per_click=0.15,
        )
        # 5.00 + 2.00 + 2.00 + 1.50 = 10.50
        assert raw == pytest.approx(10.50)


class TestPlatformCut:
    def test_20_percent_cut(self):
        user_earning = apply_platform_cut(10.00, 20.0)
        assert user_earning == 8.00

    def test_zero_cut(self):
        user_earning = apply_platform_cut(10.00, 0.0)
        assert user_earning == 10.00

    def test_zero_earning(self):
        user_earning = apply_platform_cut(0.0, 20.0)
        assert user_earning == 0.0

    def test_rounding(self):
        user_earning = apply_platform_cut(1.11, 20.0)
        assert user_earning == 0.89  # 1.11 * 0.8 = 0.888 → 0.89


class TestBudgetCap:
    def test_within_budget(self):
        earning = cap_to_budget(8.00, budget_remaining=100.00)
        assert earning == 8.00

    def test_exceeds_budget(self):
        earning = cap_to_budget(80.00, budget_remaining=10.00)
        # budget_cost = 80/0.8 = 100 > 10, so budget_cost = 10
        # earning = 10 * 0.8 = 8.00
        assert earning == 8.00

    def test_zero_budget(self):
        earning = cap_to_budget(5.00, budget_remaining=0.0)
        assert earning == 0.0


class TestCPMCPE:
    def test_cpm_normal(self):
        assert calculate_cpm(50.0, 100000) == 0.5

    def test_cpm_zero_impressions(self):
        assert calculate_cpm(50.0, 0) == 0

    def test_cpe_normal(self):
        assert calculate_cpe(10.0, 100) == 0.1

    def test_cpe_zero_engagement(self):
        assert calculate_cpe(10.0, 0) == 0


class TestPayoutRateSuggestions:
    def test_high_value_niches(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["finance", "crypto"])
        assert rates["rate_per_1k_impressions"] == 1.00
        assert rates["rate_per_like"] == 0.02

    def test_engagement_niches(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["beauty", "fashion"])
        assert rates["rate_per_1k_impressions"] == 0.30
        assert rates["rate_per_like"] == 0.015

    def test_general_niches(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["other"])
        assert rates["rate_per_1k_impressions"] == 0.50

    def test_empty_niches(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates([])
        assert rates["rate_per_1k_impressions"] == 0.50
