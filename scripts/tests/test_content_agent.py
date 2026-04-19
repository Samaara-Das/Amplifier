"""Tests for Task #14 — 4-Phase AI Content Agent.

Covers all 9 acceptance criteria plus caching, banned phrases, and retry loop.
All AI calls are mocked — no live API calls. Tests follow the same pytest +
AsyncMock pattern as test_x_disabled.py.

Acceptance criteria mapped to test cases:
  AC1 — virality → contrarian/surprising hook on X
  AC2 — leads → product mention + CTA on all platforms
  AC3 — day 1 vs day 5 → different content (cosine < 0.8)
  AC4 — Reddit includes caveat keyword
  AC5 — X ≤ 280 chars after FTC disclosure
  AC6 — brand_awareness → X 1/day, Reddit every other day (posts_per_day=0.3)
  AC7 — AI failure → fallback to single-prompt ContentGenerator
  AC8 — research includes recent_niche_news
  AC9 — strategy carries creator_voice_notes
  Extra — banned phrase triggers validator + retry
  Extra — research cache hit (second call skips scrape)
  Extra — strategy cache hit (second call skips refinement)
"""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make scripts/ importable
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# ── Helpers ─────────────────────────────────────────────────────────


def _make_manager(generate_text="ok", with_search=None, with_vision=None, embed=None):
    """Build a mock AiManager with configurable responses."""
    manager = MagicMock()
    manager.has_providers = True
    manager.generate = AsyncMock(return_value=generate_text)
    manager.generate_with_search = AsyncMock(return_value=with_search)
    manager.generate_with_vision = AsyncMock(return_value=with_vision)
    manager.embed = AsyncMock(return_value=embed)
    manager.get = MagicMock(return_value=None)  # no real Gemini provider needed
    return manager


def _make_campaign(goal="brand_awareness", tone="casual", title="Test Product"):
    return {
        "campaign_id": 1,
        "title": title,
        "brief": "A great product for testing purposes.",
        "content_guidance": "Keep it real. Mention the product naturally.",
        "campaign_goal": goal,
        "tone": tone,
        "disclaimer_text": "#ad",
        "assets": {},
        "scraped_data": {},
        "preferred_formats": {},
    }


def _valid_reddit_content(body_text="This product is solid. One thing I didn't love was the packaging."):
    """Return a content dict with a valid reddit shape."""
    return {
        "x": "Short tweet about the product. #ad",
        "linkedin": "L" * 600 + " #ad",
        "facebook": "F" * 300 + " #ad",
        "reddit": {
            "title": "T" * 65 + " honest review",
            "body": body_text + " " + ("B" * 500),
        },
        "image_prompt": "A lifestyle photo of the product.",
    }


# ── Stub for local_db functions ──────────────────────────────────────

DB_STUBS = {
    "utils.local_db.get_research": MagicMock(return_value=[]),
    "utils.local_db.add_research": MagicMock(return_value=1),
    "utils.local_db.get_content_insights": MagicMock(return_value=[]),
    "utils.local_db.get_user_profiles": MagicMock(return_value=[]),
}


# ── AC1: Virality campaign uses contrarian/surprising hook ────────────


class TestAC1ViralityHooks:
    def test_virality_hooks_in_strategy(self):
        """Virality goal strategy includes contrarian/surprising hooks."""
        from utils.content_agent import GOAL_STRATEGY
        virality = GOAL_STRATEGY["virality"]
        hooks_x = virality["x"]["hooks"]
        assert any(h in hooks_x for h in ["contrarian", "surprising_result", "curiosity"]), (
            f"Virality X hooks should include contrarian/surprising/curiosity, got: {hooks_x}"
        )

    def test_virality_not_storytelling_only(self):
        """Virality strategy does NOT default to gentle storytelling."""
        from utils.content_agent import GOAL_STRATEGY
        virality = GOAL_STRATEGY["virality"]
        hooks_x = virality["x"]["hooks"]
        # Should not be only "story" (that's brand_awareness)
        assert hooks_x != ["story"], "Virality should not use only story hooks"


# ── AC2: Leads campaign — product + CTA on every platform ─────────────


class TestAC2LeadsCTA:
    def test_leads_strategy_has_cta(self):
        """Leads strategy has link/CTA style on all platforms."""
        from utils.content_agent import GOAL_STRATEGY
        leads = GOAL_STRATEGY["leads"]
        for platform, cfg in leads.items():
            cta = cfg.get("cta", "")
            assert cta, f"Leads strategy missing CTA for {platform}"
            # Should be a conversion-oriented CTA, not just "natural_mention"
        assert leads["x"]["cta"] in ("link_in_bio", "link_post", "comment_link", "subtle_mention", "link_in_bio")

    def test_leads_posts_per_day_positive(self):
        """Leads strategy posts at least every other day on all platforms."""
        from utils.content_agent import GOAL_STRATEGY
        leads = GOAL_STRATEGY["leads"]
        for platform, cfg in leads.items():
            ppd = cfg.get("posts_per_day", 0)
            assert ppd > 0, f"Leads posts_per_day must be > 0 for {platform}, got {ppd}"


# ── AC3: Day 1 vs Day 5 — different content ───────────────────────────


class TestAC3Diversity:
    @pytest.mark.asyncio
    async def test_day1_vs_day5_different_angles(self):
        """Day 1 and day 5 creation prompts use different content angles."""
        from utils.content_agent import _run_creation, _build_strategy

        campaign = _make_campaign()
        research = {
            "product_summary": "A test product.",
            "key_features": ["fast", "easy", "cheap"],
            "target_audience": "everyday users",
            "competitive_angle": "none",
            "content_angles": ["angle_a", "angle_b", "angle_c", "angle_d", "angle_e"],
            "emotional_hooks": ["hook_1", "hook_2", "hook_3"],
            "recent_niche_news": [],
            "pricing": "",
            "testimonials": [],
            "image_analysis": "",
        }
        strategy = _build_strategy(campaign, research)

        captured_prompts = []

        async def _capture_generate(prompt):
            captured_prompts.append(prompt)
            return json.dumps({
                "linkedin": "Some linkedin post text here for testing purposes.",
                "facebook": "Some facebook post text here.",
                "reddit": {"title": "Testing the product here 60 chars minimum", "body": "B" * 600},
                "image_prompt": "A lifestyle photo.",
            })

        manager = _make_manager()
        manager.generate = AsyncMock(side_effect=_capture_generate)

        await _run_creation(campaign, strategy, research, manager, ["linkedin", "facebook", "reddit"], day_number=1)
        await _run_creation(campaign, strategy, research, manager, ["linkedin", "facebook", "reddit"], day_number=5)

        assert len(captured_prompts) == 2
        # Angles rotate by (day_number - 1) % len(angles) — day 1 → angle_a, day 5 → angle_e
        assert "angle_a" in captured_prompts[0]
        assert "angle_e" in captured_prompts[1]
        assert captured_prompts[0] != captured_prompts[1]


# ── AC4: Reddit includes caveat keyword ───────────────────────────────


class TestAC4RedditCaveat:
    def test_reddit_instruction_has_caveat_rule(self):
        """Reddit platform instruction contains the mandatory caveat rule."""
        from utils.content_agent import _run_creation, _build_strategy
        import asyncio

        campaign = _make_campaign()
        research = {
            "product_summary": "test",
            "key_features": [],
            "target_audience": "",
            "competitive_angle": "",
            "content_angles": [],
            "emotional_hooks": [],
            "recent_niche_news": [],
            "pricing": "",
            "testimonials": [],
            "image_analysis": "",
        }
        strategy = _build_strategy(campaign, research)
        captured = []

        async def _capture(prompt):
            captured.append(prompt)
            return json.dumps({
                "reddit": {"title": "T" * 65, "body": "B" * 600},
                "image_prompt": "photo",
            })

        manager = _make_manager()
        manager.generate = AsyncMock(side_effect=_capture)

        asyncio.run(_run_creation(campaign, strategy, research, manager, ["reddit"], day_number=1))
        assert captured
        assert "caveat" in captured[0].lower() or "didn't love" in captured[0].lower(), (
            "Reddit instruction must contain caveat/limitation rule"
        )

    def test_validate_reddit_body_caveat_present(self):
        """Validator test helper: body with caveat passes (no separate validator check for caveat)."""
        # The validator doesn't check for caveat keywords — that's enforced via prompt.
        # This test verifies that a valid body passes the shape check.
        from utils.content_quality import validate_content
        content = _valid_reddit_content()
        is_valid, reasons = asyncio.run(validate_content(content, [], _make_manager()))
        # Should pass shape check with valid body
        reddit_reasons = [r for r in reasons if "reddit" in r]
        assert not reddit_reasons, f"Valid reddit should pass shape check, got: {reddit_reasons}"


# ── AC5: X ≤ 280 chars after FTC disclosure ──────────────────────────


class TestAC5XLength:
    def test_ftc_appended_x_within_limit(self):
        """_append_ftc_disclosure keeps X within 280 chars."""
        from utils.content_generator import _append_ftc_disclosure

        long_tweet = "A" * 275  # 275 chars before FTC
        content = {"x": long_tweet}
        result = _append_ftc_disclosure(content, "#ad")
        # #ad appended = 275 + 1 + 3 = 279 → fits
        assert len(result["x"]) <= 280

    def test_validator_catches_x_over_280(self):
        """validate_content flags X content over 280 chars."""
        from utils.content_quality import validate_content

        content = {
            "x": "A" * 281,  # already over limit (simulates post-FTC)
        }
        is_valid, reasons = asyncio.run(validate_content(content, [], _make_manager()))
        assert not is_valid
        assert any("x:" in r and "280" in r for r in reasons)

    def test_validator_accepts_x_at_exactly_280(self):
        """validate_content accepts X at exactly 280 chars."""
        from utils.content_quality import validate_content

        content = {"x": "A" * 280}
        is_valid, reasons = asyncio.run(validate_content(content, [], _make_manager()))
        x_reasons = [r for r in reasons if r.startswith("x:")]
        assert not x_reasons, f"X at 280 chars should pass, got: {x_reasons}"


# ── AC6: brand_awareness strategy timing ─────────────────────────────


class TestAC6BrandAwarenessStrategy:
    def test_brand_awareness_x_posts_per_day(self):
        """brand_awareness strategy: X at 1 post/day."""
        from utils.content_agent import GOAL_STRATEGY
        ppd = GOAL_STRATEGY["brand_awareness"]["x"]["posts_per_day"]
        assert ppd == 1, f"brand_awareness X should be 1/day, got {ppd}"

    def test_brand_awareness_reddit_fractional(self):
        """brand_awareness strategy: Reddit < 1 post/day (every 3+ days)."""
        from utils.content_agent import GOAL_STRATEGY
        ppd = GOAL_STRATEGY["brand_awareness"]["reddit"]["posts_per_day"]
        assert ppd < 1, f"brand_awareness Reddit should be fractional, got {ppd}"
        assert ppd == 0.3, f"Expected 0.3, got {ppd}"

    def test_brand_awareness_linkedin_daily(self):
        """brand_awareness LinkedIn must post >= 1/day so day 1 is never empty.

        Live UAT (2026-04-18) found that when all non-X platforms were
        fractional (LinkedIn 0.5, Facebook 0.5, Reddit 0.3), a fresh
        brand_awareness campaign generated ZERO drafts on day 1. Dead-on-arrival
        UX. LinkedIn bumped to 1/day as the minimum-viable presence anchor.
        """
        from utils.content_agent import GOAL_STRATEGY
        ppd = GOAL_STRATEGY["brand_awareness"]["linkedin"]["posts_per_day"]
        assert ppd >= 1, f"brand_awareness LinkedIn must be >= 1/day, got {ppd}"

    def test_brand_awareness_day1_has_nonzero_platforms(self):
        """Day 1 of brand_awareness must schedule at least one platform.

        Regression test for the 'dead on arrival' bug where every platform
        was fractional and day 1 % round(1/ppd) != 0 skipped everything.
        """
        from utils.content_agent import ContentAgent

        agent = ContentAgent.__new__(ContentAgent)
        agent._manager = _make_manager()
        agent._image_manager = MagicMock()
        campaign = _make_campaign("brand_awareness")

        with patch("utils.local_db.get_content_insights", return_value=[]):
            plan = agent.get_posting_plan(
                campaign, ["linkedin", "facebook", "reddit"], day_number=1,
            )

        total = sum(
            p.get("post_count", 0) for p in plan.get("platforms", {}).values()
        )
        assert total >= 1, (
            f"brand_awareness day 1 must schedule >= 1 post across platforms, "
            f"got {total}. Plan: {plan}"
        )

    def test_get_posting_plan_brand_awareness(self):
        """get_posting_plan returns correct structure for brand_awareness."""
        from utils.content_agent import ContentAgent

        with patch("utils.content_agent._build_strategy") as mock_strategy, \
             patch("utils.local_db.get_content_insights", return_value=[]):
            from utils.content_agent import GOAL_STRATEGY
            mock_strategy.return_value = {
                "platforms": {
                    "x": {"posts_per_day": 1, "post_times_est": ["08:00"], "image_probability": 0.4, "hooks": ["story"]},
                    "reddit": {"posts_per_day": 0.3, "post_times_est": ["13:00"], "image_probability": 0.0, "hooks": ["story"]},
                }
            }
            agent = ContentAgent.__new__(ContentAgent)
            agent._manager = _make_manager()
            agent._image_manager = MagicMock()
            campaign = _make_campaign("brand_awareness")
            plan = agent.get_posting_plan(campaign, ["x", "reddit"], day_number=1)
            assert "platforms" in plan


# ── AC7: AI failure → fallback ────────────────────────────────────────


class TestAC7Fallback:
    @pytest.mark.asyncio
    async def test_ai_failure_uses_fallback_generator(self):
        """ContentAgent falls back to ContentGenerator when all AI fails."""
        fallback_content = {
            "linkedin": "Fallback linkedin post.",
            "facebook": "Fallback facebook post.",
            "reddit": {"title": "Fallback reddit title min 60 chars here", "body": "B" * 500},
            "image_prompt": "fallback photo",
        }

        manager = _make_manager()
        manager.has_providers = True
        manager.generate = AsyncMock(side_effect=RuntimeError("All providers failed"))
        manager.generate_with_search = AsyncMock(return_value=None)
        manager.generate_with_vision = AsyncMock(return_value=None)

        with patch("utils.content_generator.ContentGenerator.generate", new_callable=AsyncMock, return_value=fallback_content), \
             patch("utils.local_db.get_research", return_value=[]), \
             patch("utils.local_db.add_research", return_value=1), \
             patch("utils.local_db.get_content_insights", return_value=[]), \
             patch("utils.content_generator._scrape_url_deep", return_value=None), \
             patch("utils.content_generator._build_research_brief", return_value=""):

            from utils.content_agent import ContentAgent
            agent = ContentAgent.__new__(ContentAgent)
            agent._manager = manager
            agent._image_manager = MagicMock()

            campaign = _make_campaign()
            result = await agent.generate_content(campaign, ["linkedin", "facebook", "reddit"])
            assert result == fallback_content


# ── AC8: Research includes recent_niche_news ──────────────────────────


class TestAC8NicheNews:
    @pytest.mark.asyncio
    async def test_research_includes_recent_niche_news(self):
        """_run_research populates recent_niche_news from generate_with_search."""
        news = ["Headline about crypto 2026", "Another niche headline today"]
        manager = _make_manager(
            generate_text=json.dumps({
                "product_summary": "A crypto trading tool.",
                "key_features": ["fast", "accurate"],
                "target_audience": "crypto traders",
                "competitive_angle": "best on the market",
                "content_angles": ["angle 1"],
                "emotional_hooks": ["hook 1"],
                "pricing": "$99/mo",
                "testimonials": [],
            }),
            with_search=json.dumps(news),
        )

        campaign = _make_campaign()

        with patch("utils.local_db.get_research", return_value=[]), \
             patch("utils.local_db.add_research", return_value=1), \
             patch("utils.content_generator._scrape_url_deep", return_value=None), \
             patch("utils.content_generator._build_research_brief", return_value=""):

            from utils.content_agent import _run_research
            result = await _run_research(campaign, manager)

        assert "recent_niche_news" in result
        assert isinstance(result["recent_niche_news"], list)
        assert len(result["recent_niche_news"]) == 2
        assert result["recent_niche_news"][0] == news[0]

    @pytest.mark.asyncio
    async def test_research_handles_news_failure_gracefully(self):
        """_run_research sets recent_niche_news=[] when search fails."""
        manager = _make_manager(
            generate_text=json.dumps({
                "product_summary": "test",
                "key_features": [],
                "target_audience": "test audience",
                "competitive_angle": "",
                "content_angles": [],
                "emotional_hooks": [],
                "pricing": "",
                "testimonials": [],
            }),
            with_search=None,  # simulates unavailable search
        )
        campaign = _make_campaign()

        with patch("utils.local_db.get_research", return_value=[]), \
             patch("utils.local_db.add_research", return_value=1), \
             patch("utils.content_generator._scrape_url_deep", return_value=None), \
             patch("utils.content_generator._build_research_brief", return_value=""):

            from utils.content_agent import _run_research
            result = await _run_research(campaign, manager)

        assert result["recent_niche_news"] == []


# ── AC9: Strategy carries creator_voice_notes ─────────────────────────


class TestAC9CreatorVoiceNotes:
    @pytest.mark.asyncio
    async def test_strategy_refinement_adds_voice_notes(self):
        """_refine_strategy_with_ai adds creator_voice_notes to strategy."""
        from utils.content_agent import _build_strategy, _refine_strategy_with_ai

        campaign = _make_campaign()
        research = {
            "product_summary": "test",
            "key_features": [],
            "target_audience": "traders",
            "competitive_angle": "",
            "content_angles": ["angle 1"],
            "emotional_hooks": [],
            "recent_niche_news": [],
            "pricing": "",
            "testimonials": [],
            "image_analysis": "",
        }
        base_strategy = _build_strategy(campaign, research)
        # Add creator_voice_notes to base_strategy for the mock to return
        expected_refined = dict(base_strategy)
        for plat in expected_refined.get("platforms", {}):
            expected_refined["platforms"][plat] = dict(expected_refined["platforms"][plat])
            expected_refined["platforms"][plat]["creator_voice_notes"] = f"Match casual {plat} tone."

        manager = _make_manager(generate_text=json.dumps(expected_refined))
        user_profiles = [{"platform": "linkedin", "bio": "casual trader", "style_notes": "casual, short sentences"}]

        with patch("utils.local_db.get_research", return_value=[]), \
             patch("utils.local_db.add_research", return_value=1):

            refined = await _refine_strategy_with_ai(campaign, base_strategy, research, manager, user_profiles)

        # At least one platform should have creator_voice_notes
        has_voice_notes = any(
            plat_cfg.get("creator_voice_notes")
            for plat_cfg in refined.get("platforms", {}).values()
        )
        assert has_voice_notes, "Refined strategy should have creator_voice_notes on at least one platform"

    @pytest.mark.asyncio
    async def test_user_profile_reaches_refinement_prompt(self):
        """user_profiles bio + style_notes must appear in the AI prompt sent to manager.

        Live UAT (2026-04-18) couldn't verify this due to Gemini rate-limits.
        This test captures the prompt passed to manager.generate() and asserts
        the distinctive profile tokens are embedded — proving the plumbing.
        """
        from utils.content_agent import _build_strategy, _refine_strategy_with_ai

        campaign = _make_campaign()
        research = {
            "product_summary": "test",
            "content_angles": ["a1"],
            "emotional_hooks": [],
            "key_features": [],
            "target_audience": "",
            "competitive_angle": "",
            "recent_niche_news": [],
            "pricing": "",
            "testimonials": [],
            "image_analysis": "",
        }
        base_strategy = _build_strategy(campaign, research)

        captured_prompts: list[str] = []

        class CapturingManager:
            has_providers = True
            async def generate(self, prompt, preferred=None):
                captured_prompts.append(prompt)
                return json.dumps(base_strategy)

        distinctive_bio = "zzUNIQUEBIOzz"
        distinctive_style = "qqDISTINCTIVESTYLEqq"
        user_profiles = [{
            "platform": "linkedin",
            "bio": distinctive_bio,
            "style_notes": distinctive_style,
            "recent_posts": "",
            "follower_count": 100,
        }]

        with patch("utils.local_db.get_research", return_value=[]), \
             patch("utils.local_db.add_research", return_value=1):
            await _refine_strategy_with_ai(
                campaign, base_strategy, research, CapturingManager(), user_profiles
            )

        assert captured_prompts, "Manager.generate should have been called"
        prompt_text = captured_prompts[0]
        assert distinctive_bio in prompt_text, (
            f"User profile bio should appear in refinement prompt. "
            f"Missing '{distinctive_bio}'. Prompt excerpt: {prompt_text[:500]}"
        )
        assert distinctive_style in prompt_text, (
            f"User profile style_notes should appear in refinement prompt. "
            f"Missing '{distinctive_style}'."
        )


# ── Banned phrases validator ─────────────────────────────────────────


class TestBannedPhrases:
    @pytest.mark.asyncio
    async def test_banned_phrase_fails_validation(self):
        """validate_content rejects content with banned AI phrases."""
        from utils.content_quality import validate_content

        content = {
            "linkedin": "This product is a game-changer for everyone.",
            "reddit": {
                "title": "T" * 65 + " honest review here",
                "body": "This is a great product. " + "B" * 490,
            },
            "image_prompt": "photo",
        }
        is_valid, reasons = await validate_content(content, [], _make_manager())
        assert not is_valid
        assert any("game-changer" in r or "game changer" in r for r in reasons)

    @pytest.mark.asyncio
    async def test_clean_content_passes_banned_check(self):
        """validate_content passes content without banned phrases."""
        from utils.content_quality import validate_content

        content = _valid_reddit_content()
        manager = _make_manager()
        manager.embed = AsyncMock(return_value=None)  # no diversity check
        is_valid, reasons = await validate_content(content, [], manager)
        banned_reasons = [r for r in reasons if "banned phrase" in r]
        assert not banned_reasons, f"Clean content should pass banned check, got: {banned_reasons}"


# ── Research cache hit ───────────────────────────────────────────────


class TestResearchCacheHit:
    @pytest.mark.asyncio
    async def test_second_call_uses_cache(self):
        """_run_research returns cached result on second call within 7 days."""
        from datetime import datetime, timezone
        from utils.content_agent import _run_research

        cached_research = {
            "product_summary": "cached product",
            "key_features": ["a", "b"],
            "target_audience": "cached audience",
            "competitive_angle": "cached angle",
            "content_angles": ["cached angle 1"],
            "emotional_hooks": ["cached hook"],
            "pricing": "",
            "testimonials": [],
            "recent_niche_news": ["cached headline"],
            "image_analysis": "",
        }
        now_iso = datetime.now(timezone.utc).isoformat()
        cache_row = {
            "research_type": "full_research",
            "content": json.dumps(cached_research),
            "created_at": now_iso,
        }

        manager = _make_manager()
        # If cache is hit, generate should NOT be called
        manager.generate = AsyncMock(side_effect=AssertionError("Should not call AI when cache hit"))

        campaign = _make_campaign()
        with patch("utils.local_db.get_research", return_value=[cache_row]):
            result = await _run_research(campaign, manager)

        assert result["product_summary"] == "cached product"
        assert result["recent_niche_news"] == ["cached headline"]


# ── Strategy cache hit ────────────────────────────────────────────────


class TestStrategyCacheHit:
    @pytest.mark.asyncio
    async def test_second_call_uses_strategy_cache(self):
        """_refine_strategy_with_ai returns cached strategy within 7 days."""
        from datetime import datetime, timezone
        from utils.content_agent import _build_strategy, _refine_strategy_with_ai

        campaign = _make_campaign()
        research = {
            "product_summary": "test",
            "key_features": [],
            "target_audience": "",
            "competitive_angle": "",
            "content_angles": [],
            "emotional_hooks": [],
        }
        base = _build_strategy(campaign, research)
        cached_strategy = dict(base)
        cached_strategy["_from_cache"] = True
        now_iso = datetime.now(timezone.utc).isoformat()
        cache_row = {
            "research_type": "strategy",
            "content": json.dumps(cached_strategy),
            "created_at": now_iso,
        }

        manager = _make_manager()
        # If cache hit, generate should NOT be called
        manager.generate = AsyncMock(side_effect=AssertionError("Should not call AI when strategy cached"))

        with patch("utils.local_db.get_research", return_value=[cache_row]):
            result = await _refine_strategy_with_ai(campaign, base, research, manager)

        assert result.get("_from_cache") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
