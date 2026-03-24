"""Tests for agent pipeline DB tables and CRUD functions."""

import json
from utils.local_db import (
    upsert_user_profile, get_user_profiles, get_user_profile,
    add_research, get_research,
    add_draft, get_drafts, approve_draft, mark_draft_posted,
    upsert_content_insight, get_content_insights,
    get_setting, set_setting,
)


class TestUserProfiles:
    def test_upsert_and_get(self):
        upsert_user_profile("x", "Trading educator", '["post1", "post2"]', "Punchy, direct", 5000)
        profile = get_user_profile("x")
        assert profile is not None
        assert profile["bio"] == "Trading educator"
        assert profile["follower_count"] == 5000
        assert json.loads(profile["recent_posts"]) == ["post1", "post2"]

    def test_upsert_updates_existing(self):
        upsert_user_profile("x", "Old bio", "[]", "Old style", 100)
        upsert_user_profile("x", "New bio", "[]", "New style", 500)
        profile = get_user_profile("x")
        assert profile["bio"] == "New bio"
        assert profile["follower_count"] == 500

    def test_get_multiple_platforms(self):
        upsert_user_profile("x", "X bio", "[]", "", 100)
        upsert_user_profile("linkedin", "LI bio", "[]", "", 200)
        upsert_user_profile("facebook", "FB bio", "[]", "", 300)

        profiles = get_user_profiles(["x", "linkedin"])
        assert len(profiles) == 2
        platforms = {p["platform"] for p in profiles}
        assert platforms == {"x", "linkedin"}

    def test_get_nonexistent(self):
        profile = get_user_profile("tiktok")
        assert profile is None

    def test_get_all(self):
        upsert_user_profile("x", "bio", "[]", "", 0)
        upsert_user_profile("reddit", "bio", "[]", "", 0)
        all_profiles = get_user_profiles()
        assert len(all_profiles) >= 2


class TestResearch:
    def test_add_and_get(self):
        rid = add_research(1, "web_search", '{"title": "test"}', "https://example.com")
        assert rid > 0

        results = get_research(1)
        assert len(results) == 1
        assert results[0]["research_type"] == "web_search"
        assert results[0]["source_url"] == "https://example.com"

    def test_multiple_findings(self):
        add_research(1, "web_search", '{"a": 1}')
        add_research(1, "company_link", '{"b": 2}', "https://company.com")
        add_research(1, "past_performance", '{"c": 3}')

        results = get_research(1)
        assert len(results) == 3

    def test_separate_campaigns(self):
        add_research(1, "web_search", '{"x": 1}')
        add_research(2, "web_search", '{"y": 2}')

        assert len(get_research(1)) == 1
        assert len(get_research(2)) == 1


class TestDrafts:
    def test_add_and_get(self):
        did = add_draft(1, "x", "Check out this indicator! #trading", "pillar_1", 85.0)
        assert did > 0

        drafts = get_drafts(1, "x")
        assert len(drafts) == 1
        assert drafts[0]["platform"] == "x"
        assert drafts[0]["quality_score"] == 85.0

    def test_approve_and_post(self):
        did = add_draft(1, "linkedin", "Long form post...", "pillar_3", 92.0)
        approve_draft(did)
        mark_draft_posted(did)

        drafts = get_drafts(1, "linkedin")
        assert drafts[0]["approved"] == 1
        assert drafts[0]["posted"] == 1

    def test_sorted_by_quality(self):
        add_draft(1, "x", "Low quality", None, 40.0)
        add_draft(1, "x", "High quality", None, 95.0)
        add_draft(1, "x", "Medium quality", None, 70.0)

        drafts = get_drafts(1, "x")
        scores = [d["quality_score"] for d in drafts]
        assert scores == sorted(scores, reverse=True)

    def test_get_all_platforms(self):
        add_draft(1, "x", "tweet", None, 80.0)
        add_draft(1, "linkedin", "post", None, 90.0)

        all_drafts = get_drafts(1)
        assert len(all_drafts) == 2


class TestContentInsights:
    def test_upsert_and_get(self):
        upsert_content_insight("x", "pillar_1", "fear", 0.05, 10, "Best tweet ever")
        insights = get_content_insights("x")
        assert len(insights) == 1
        assert insights[0]["hook_type"] == "fear"
        assert insights[0]["avg_engagement_rate"] == 0.05

    def test_get_all_platforms(self):
        upsert_content_insight("x", "pillar_1", "fear", 0.05, 10)
        upsert_content_insight("linkedin", "pillar_3", "competence", 0.08, 5)
        all_insights = get_content_insights()
        assert len(all_insights) >= 2

    def test_sorted_by_engagement(self):
        upsert_content_insight("x", "p1", "fear", 0.02, 5)
        upsert_content_insight("x", "p2", "freedom", 0.10, 5)
        upsert_content_insight("x", "p3", "greed", 0.05, 5)

        insights = get_content_insights("x")
        rates = [i["avg_engagement_rate"] for i in insights]
        assert rates == sorted(rates, reverse=True)


class TestFeatureFlag:
    def test_set_and_get(self):
        set_setting("enable_agent_pipeline", "true")
        assert get_setting("enable_agent_pipeline") == "true"

    def test_default_value(self):
        assert get_setting("nonexistent_key", "default") == "default"

    def test_override(self):
        set_setting("key1", "value1")
        set_setting("key1", "value2")
        assert get_setting("key1") == "value2"
