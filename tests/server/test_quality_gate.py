"""Tests for server/app/services/quality_gate.py — score_campaign() rubric."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.services.quality_gate import score_campaign


def make_campaign(**overrides):
    today = datetime.now(timezone.utc)
    defaults = {
        "title": "Default Campaign Title Long Enough",
        "brief": "B" * 350,
        "content_guidance": "G" * 60,
        "payout_rules": {
            "rate_per_like": 0.05,
            "rate_per_repost": 0.10,
            "rate_per_1k_impressions": 0.50,
            "rate_per_click": 0.10,
        },
        "targeting": {
            "niche_tags": ["business"],
            "required_platforms": ["linkedin"],
            "min_followers": {},
            "min_engagement": 0,
            "target_regions": ["US"],
        },
        "assets": {
            "image_urls": ["https://example.com/img.jpg"],
            "links": [],
            "file_urls": [],
            "file_contents": [],
            "hashtags": [],
            "brand_guidelines": "",
        },
        "start_date": today,
        "end_date": today + timedelta(days=14),
        "budget_total": 200,
        "campaign_type": "ai_generated",
        "company_urls": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestBriefCompleteness:
    def test_brief_completeness_full_partial_zero(self):
        result = score_campaign(make_campaign(brief="B" * 350))
        assert result["criteria"]["brief_completeness"]["score"] == 25
        assert "Brief is complete." in result["criteria"]["brief_completeness"]["feedback"]

        result = score_campaign(make_campaign(brief="B" * 150))
        assert result["criteria"]["brief_completeness"]["score"] == 12
        assert "Brief is too short" in result["criteria"]["brief_completeness"]["feedback"]

        result = score_campaign(make_campaign(brief="B" * 50))
        assert result["criteria"]["brief_completeness"]["score"] == 0


class TestContentGuidance:
    def test_content_guidance_full_partial_zero_and_repost_exempt(self):
        result = score_campaign(make_campaign(content_guidance="G" * 60))
        assert result["criteria"]["content_guidance"]["score"] == 15

        result = score_campaign(make_campaign(content_guidance="G" * 25))
        assert result["criteria"]["content_guidance"]["score"] == 7

        result = score_campaign(make_campaign(content_guidance=""))
        assert result["criteria"]["content_guidance"]["score"] == 0

        result = score_campaign(make_campaign(content_guidance="", campaign_type="repost"))
        assert result["criteria"]["content_guidance"]["score"] == 15


class TestPayoutRates:
    def test_payout_rates_full_partial_zero(self):
        result = score_campaign(make_campaign(payout_rules={
            "rate_per_like": 0.05,
            "rate_per_repost": 0.10,
            "rate_per_1k_impressions": 0.0,
            "rate_per_click": 0.0,
        }))
        assert result["criteria"]["payout_rates"]["score"] == 15

        result = score_campaign(make_campaign(payout_rules={
            "rate_per_like": 0.0,
            "rate_per_repost": 0.10,
            "rate_per_1k_impressions": 0.0,
            "rate_per_click": 0.0,
        }))
        assert result["criteria"]["payout_rates"]["score"] == 7

        result = score_campaign(make_campaign(payout_rules={
            "rate_per_like": 0.0,
            "rate_per_repost": 0.0,
            "rate_per_1k_impressions": 0.0,
            "rate_per_click": 0.0,
        }))
        assert result["criteria"]["payout_rates"]["score"] == 0

    def test_payout_rates_competitive_requires_rate_per_like_at_least_001(self):
        result = score_campaign(make_campaign(payout_rules={
            "rate_per_like": 0.005,
            "rate_per_repost": 0.10,
            "rate_per_1k_impressions": 0.50,
            "rate_per_click": 0.0,
        }))
        assert result["criteria"]["payout_rates"]["score"] == 7


class TestTargeting:
    def test_targeting_full_partial_zero_and_disabled_platform(self):
        result = score_campaign(make_campaign(targeting={
            "niche_tags": ["business"],
            "required_platforms": ["linkedin"],
        }))
        assert result["criteria"]["targeting"]["score"] == 10

        result = score_campaign(make_campaign(targeting={
            "niche_tags": ["business"],
            "required_platforms": [],
        }))
        assert result["criteria"]["targeting"]["score"] == 5

        result = score_campaign(make_campaign(targeting={
            "niche_tags": [],
            "required_platforms": ["linkedin"],
        }))
        assert result["criteria"]["targeting"]["score"] == 5

        result = score_campaign(make_campaign(targeting={
            "niche_tags": [],
            "required_platforms": [],
        }))
        assert result["criteria"]["targeting"]["score"] == 0

        result = score_campaign(make_campaign(targeting={
            "niche_tags": ["business"],
            "required_platforms": ["x"],
        }))
        assert result["criteria"]["targeting"]["score"] == 0
        assert "Disabled platform" in result["criteria"]["targeting"]["feedback"]


class TestAssetsProvided:
    def test_assets_provided_images_or_links_or_neither(self):
        result = score_campaign(make_campaign(assets={
            "image_urls": ["https://example.com/img.jpg"],
            "links": [],
            "file_urls": [],
        }, company_urls=[]))
        assert result["criteria"]["assets_provided"]["score"] == 10

        result = score_campaign(make_campaign(assets={
            "image_urls": [],
            "links": ["https://example.com"],
            "file_urls": [],
        }, company_urls=[]))
        assert result["criteria"]["assets_provided"]["score"] == 10

        result = score_campaign(make_campaign(assets={
            "image_urls": [],
            "links": [],
            "file_urls": [],
        }, company_urls=[]))
        assert result["criteria"]["assets_provided"]["score"] == 0


class TestTitleQuality:
    def test_title_quality_too_short_too_long_ideal(self):
        result = score_campaign(make_campaign(title="A" * 30))
        assert result["criteria"]["title_quality"]["score"] == 10

        result = score_campaign(make_campaign(title="AAAAAAAAAAAA"))
        assert result["criteria"]["title_quality"]["score"] == 5

        result = score_campaign(make_campaign(title="ABCD"))
        assert result["criteria"]["title_quality"]["score"] == 0

        result = score_campaign(make_campaign(title="A" * 110))
        assert result["criteria"]["title_quality"]["score"] == 0


class TestDatesValid:
    def test_dates_valid_past_start_and_duration_bounds(self):
        today = datetime.now(timezone.utc)

        result = score_campaign(make_campaign(start_date=today, end_date=today + timedelta(days=14)))
        assert result["criteria"]["dates_valid"]["score"] == 5

        result = score_campaign(make_campaign(start_date=today - timedelta(days=1), end_date=today + timedelta(days=14)))
        assert result["criteria"]["dates_valid"]["score"] == 2

        result = score_campaign(make_campaign(start_date=today, end_date=today + timedelta(days=3)))
        assert result["criteria"]["dates_valid"]["score"] == 2

        result = score_campaign(make_campaign(start_date=today, end_date=today - timedelta(days=1)))
        assert result["criteria"]["dates_valid"]["score"] == 0


class TestBudgetSufficient:
    def test_budget_sufficient_thresholds_50_10_0(self):
        result = score_campaign(make_campaign(budget_total=200))
        assert result["criteria"]["budget_sufficient"]["score"] == 10

        result = score_campaign(make_campaign(budget_total=30))
        assert result["criteria"]["budget_sufficient"]["score"] == 5

        result = score_campaign(make_campaign(budget_total=5))
        assert result["criteria"]["budget_sufficient"]["score"] == 0


class TestHardFailVeto:
    def test_hard_fail_payout_zero_vetoes_passed(self):
        campaign = make_campaign(payout_rules={
            "rate_per_like": 0.0,
            "rate_per_repost": 0.0,
            "rate_per_1k_impressions": 0.0,
            "rate_per_click": 0.0,
        })
        result = score_campaign(campaign)
        assert result["score"] >= 85
        assert result["criteria"]["payout_rates"]["score"] == 0
        assert result["passed"] is False

    def test_hard_fail_assets_empty_vetoes_passed(self):
        campaign = make_campaign(
            assets={"image_urls": [], "links": [], "file_urls": []},
            company_urls=[],
        )
        result = score_campaign(campaign)
        assert result["score"] >= 85
        assert result["criteria"]["assets_provided"]["score"] == 0
        assert result["passed"] is False

    def test_hard_fail_targeting_empty_vetoes_passed(self):
        campaign = make_campaign(targeting={"niche_tags": [], "required_platforms": []})
        result = score_campaign(campaign)
        assert result["score"] >= 85
        assert result["criteria"]["targeting"]["score"] == 0
        assert result["passed"] is False
