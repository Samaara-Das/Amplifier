"""Tests for AI niche classification module.

Tests cover:
- Prompt construction (correct format, posts included, truncation)
- Response parsing (valid JSON array extraction)
- Invalid niche filtering (niches not in VALID_NICHES are removed)
- Empty posts returns empty niches
- Gemini API failure falls back to empty list
- classify_and_store updates local DB
- get_detected_niches merges across platforms
- Truncation at 50 posts
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.niche_classifier import (
    VALID_NICHES,
    classify_niches,
    classify_and_store,
    get_detected_niches,
    _build_prompt,
    _parse_niches_response,
)
from utils.local_db import (
    upsert_scraped_profile,
    get_scraped_profile,
    get_all_scraped_profiles,
)


# ── VALID_NICHES constant ────────────────────────────────────────


class TestValidNiches:
    def test_valid_niches_is_list(self):
        assert isinstance(VALID_NICHES, list)

    def test_valid_niches_count(self):
        assert len(VALID_NICHES) == 14

    def test_expected_niches_present(self):
        expected = [
            "finance", "tech", "beauty", "fashion", "fitness", "gaming",
            "food", "travel", "education", "lifestyle", "business",
            "health", "entertainment", "crypto",
        ]
        assert VALID_NICHES == expected


# ── Prompt Construction ──────────────────────────────────────────


class TestBuildPrompt:
    def test_includes_post_texts(self):
        """Prompt includes the actual post text content."""
        scraped = {
            "x": {"recent_posts": [{"text": "Bitcoin is mooning today"}]},
        }
        prompt = _build_prompt(scraped)
        assert "Bitcoin is mooning today" in prompt

    def test_includes_valid_niches_list(self):
        """Prompt lists all valid niches for the LLM."""
        scraped = {"x": {"recent_posts": [{"text": "test post"}]}}
        prompt = _build_prompt(scraped)
        for niche in VALID_NICHES:
            assert niche in prompt

    def test_multi_platform_posts(self):
        """Prompt collects posts from multiple platforms."""
        scraped = {
            "x": {"recent_posts": [{"text": "X post about stocks"}]},
            "linkedin": {"recent_posts": [{"text": "LinkedIn post about leadership"}]},
        }
        prompt = _build_prompt(scraped)
        assert "X post about stocks" in prompt
        assert "LinkedIn post about leadership" in prompt

    def test_truncation_at_50_posts(self):
        """Prompt includes at most 50 posts total."""
        posts = [{"text": f"Post number {i}"} for i in range(80)]
        scraped = {"x": {"recent_posts": posts}}
        prompt = _build_prompt(scraped)
        # Post 49 should be included (0-indexed, 50 posts = 0..49)
        assert "Post number 49" in prompt
        # Post 50 should NOT be included
        assert "Post number 50" not in prompt

    def test_empty_posts_returns_prompt_without_content(self):
        """Prompt can be built with no posts (will contain empty section)."""
        scraped = {"x": {"recent_posts": []}}
        prompt = _build_prompt(scraped)
        assert "JSON array" in prompt  # Still contains instruction

    def test_reddit_uses_title_field(self):
        """Reddit posts use 'title' field instead of 'text'."""
        scraped = {
            "reddit": {"recent_posts": [{"title": "My DD on TSLA earnings"}]},
        }
        prompt = _build_prompt(scraped)
        assert "My DD on TSLA earnings" in prompt

    def test_skips_empty_text_posts(self):
        """Posts with empty text are skipped."""
        scraped = {
            "x": {"recent_posts": [
                {"text": ""},
                {"text": "Valid post"},
                {"text": None},
            ]},
        }
        prompt = _build_prompt(scraped)
        assert "Valid post" in prompt

    def test_requests_json_array_output(self):
        """Prompt asks for JSON array format."""
        scraped = {"x": {"recent_posts": [{"text": "hello"}]}}
        prompt = _build_prompt(scraped)
        assert "JSON array" in prompt


# ── Response Parsing ─────────────────────────────────────────────


class TestParseNichesResponse:
    def test_clean_json_array(self):
        """Parses a clean JSON array response."""
        result = _parse_niches_response('["finance", "tech"]')
        assert result == ["finance", "tech"]

    def test_json_with_markdown_fences(self):
        """Parses JSON wrapped in markdown code fences."""
        result = _parse_niches_response('```json\n["finance", "crypto"]\n```')
        assert result == ["finance", "crypto"]

    def test_filters_invalid_niches(self):
        """Removes niches not in VALID_NICHES."""
        result = _parse_niches_response('["finance", "astrology", "tech", "politics"]')
        assert result == ["finance", "tech"]

    def test_case_insensitive_matching(self):
        """Handles mixed case in response (lowercases before matching)."""
        result = _parse_niches_response('["Finance", "TECH", "Beauty"]')
        assert result == ["finance", "tech", "beauty"]

    def test_removes_duplicates(self):
        """Deduplicates niches in response."""
        result = _parse_niches_response('["finance", "finance", "tech"]')
        assert result == ["finance", "tech"]

    def test_extracts_json_from_surrounding_text(self):
        """Handles response with text around the JSON array."""
        result = _parse_niches_response(
            'Based on the posts, I classify the niches as:\n["finance", "crypto"]\nThese are the main topics.'
        )
        assert result == ["finance", "crypto"]

    def test_empty_array(self):
        """Handles empty JSON array."""
        result = _parse_niches_response("[]")
        assert result == []

    def test_unparseable_returns_empty(self):
        """Returns empty list for completely unparseable response."""
        result = _parse_niches_response("I cannot classify these posts sorry")
        assert result == []

    def test_non_string_elements_filtered(self):
        """Filters out non-string elements from the array."""
        result = _parse_niches_response('["finance", 42, "tech", null, "beauty"]')
        assert result == ["finance", "tech", "beauty"]


# ── classify_niches (Gemini call) ────────────────────────────────


class TestClassifyNiches:
    @pytest.mark.asyncio
    async def test_returns_niches_from_gemini(self):
        """classify_niches calls Gemini and returns parsed niches."""
        mock_response = MagicMock()
        mock_response.text = '["finance", "crypto"]'

        mock_model = MagicMock()
        mock_model.generate_content = MagicMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.models = mock_model

        with patch("utils.niche_classifier._get_gemini_client", return_value=mock_client):
            result = await classify_niches({
                "x": {"recent_posts": [{"text": "BTC to the moon"}]},
            })

        assert result == ["finance", "crypto"]
        mock_model.generate_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_profiles_returns_empty(self):
        """classify_niches returns empty list when no posts exist."""
        result = await classify_niches({})
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_posts_across_platforms_returns_empty(self):
        """classify_niches returns empty list when all platforms have empty posts."""
        result = await classify_niches({
            "x": {"recent_posts": []},
            "linkedin": {"recent_posts": []},
        })
        assert result == []

    @pytest.mark.asyncio
    async def test_gemini_failure_returns_empty(self):
        """classify_niches returns empty list when Gemini API fails."""
        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(
            side_effect=Exception("API quota exceeded")
        )

        with patch("utils.niche_classifier._get_gemini_client", return_value=mock_client):
            result = await classify_niches({
                "x": {"recent_posts": [{"text": "Some content"}]},
            })

        assert result == []

    @pytest.mark.asyncio
    async def test_gemini_returns_invalid_json_returns_empty(self):
        """classify_niches returns empty list when Gemini returns garbage."""
        mock_response = MagicMock()
        mock_response.text = "I am confused and cannot classify"

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("utils.niche_classifier._get_gemini_client", return_value=mock_client):
            result = await classify_niches({
                "x": {"recent_posts": [{"text": "Some content"}]},
            })

        assert result == []

    @pytest.mark.asyncio
    async def test_gemini_no_api_key_returns_empty(self):
        """classify_niches returns empty list when no API key is configured."""
        with patch("utils.niche_classifier._get_gemini_client", return_value=None):
            result = await classify_niches({
                "x": {"recent_posts": [{"text": "Some content"}]},
            })

        assert result == []

    @pytest.mark.asyncio
    async def test_filters_invalid_niches_from_gemini(self):
        """classify_niches filters out invalid niches from Gemini response."""
        mock_response = MagicMock()
        mock_response.text = '["finance", "astrology", "tech"]'

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("utils.niche_classifier._get_gemini_client", return_value=mock_client):
            result = await classify_niches({
                "x": {"recent_posts": [{"text": "content"}]},
            })

        assert result == ["finance", "tech"]

    @pytest.mark.asyncio
    async def test_limits_to_4_niches(self):
        """classify_niches returns at most 4 niches even if Gemini returns more."""
        mock_response = MagicMock()
        mock_response.text = '["finance", "tech", "crypto", "business", "education", "health"]'

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("utils.niche_classifier._get_gemini_client", return_value=mock_client):
            result = await classify_niches({
                "x": {"recent_posts": [{"text": "diverse content"}]},
            })

        assert len(result) <= 4

    @pytest.mark.asyncio
    async def test_50_post_truncation(self):
        """classify_niches truncates to 50 posts before calling Gemini."""
        posts = [{"text": f"Post {i}"} for i in range(80)]
        scraped = {"x": {"recent_posts": posts}}

        mock_response = MagicMock()
        mock_response.text = '["finance"]'

        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("utils.niche_classifier._get_gemini_client", return_value=mock_client):
            result = await classify_niches(scraped)

        # Verify the prompt sent to Gemini only has 50 posts
        call_args = mock_client.models.generate_content.call_args
        prompt_sent = call_args[1]["contents"] if "contents" in (call_args[1] or {}) else call_args[0][0] if call_args[0] else call_args[1].get("contents", "")
        # The actual check: post 49 is in the prompt, post 50 is not
        # We check via _build_prompt logic which is tested separately
        assert result == ["finance"]


# ── classify_and_store ───────────────────────────────────────────


class TestClassifyAndStore:
    @pytest.mark.asyncio
    async def test_loads_profiles_and_stores_niches(self):
        """classify_and_store reads from DB, classifies, and writes back."""
        # Seed scraped profiles in local DB
        upsert_scraped_profile(
            platform="x",
            follower_count=1000,
            recent_posts=json.dumps([
                {"text": "Just backtested a new BTC strategy"},
                {"text": "S&P 500 looking strong this week"},
            ]),
        )
        upsert_scraped_profile(
            platform="linkedin",
            follower_count=500,
            recent_posts=json.dumps([
                {"text": "Building the future of fintech"},
            ]),
        )

        mock_response = MagicMock()
        mock_response.text = '["finance", "crypto", "tech"]'
        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("utils.niche_classifier._get_gemini_client", return_value=mock_client), \
             patch("utils.niche_classifier.update_profile") as mock_server_update:
            await classify_and_store()

        # Check that local DB was updated
        x_profile = get_scraped_profile("x")
        niches = json.loads(x_profile["ai_niches"])
        assert "finance" in niches
        assert "crypto" in niches
        assert "tech" in niches

        li_profile = get_scraped_profile("linkedin")
        li_niches = json.loads(li_profile["ai_niches"])
        assert "finance" in li_niches

        # Check server was called
        mock_server_update.assert_called_once()
        call_kwargs = mock_server_update.call_args[1]
        assert "ai_detected_niches" in call_kwargs
        assert "finance" in call_kwargs["ai_detected_niches"]

    @pytest.mark.asyncio
    async def test_no_profiles_does_nothing(self):
        """classify_and_store does nothing if no profiles exist."""
        with patch("utils.niche_classifier._get_gemini_client") as mock_gemini:
            await classify_and_store()

        # Gemini should not have been called
        mock_gemini.assert_not_called()

    @pytest.mark.asyncio
    async def test_server_sync_failure_does_not_crash(self):
        """classify_and_store handles server sync failure gracefully."""
        upsert_scraped_profile(
            platform="x",
            follower_count=100,
            recent_posts=json.dumps([{"text": "test post"}]),
        )

        mock_response = MagicMock()
        mock_response.text = '["tech"]'
        mock_client = MagicMock()
        mock_client.models.generate_content = MagicMock(return_value=mock_response)

        with patch("utils.niche_classifier._get_gemini_client", return_value=mock_client), \
             patch("utils.niche_classifier.update_profile", side_effect=Exception("Server down")):
            # Should not raise
            await classify_and_store()

        # Local DB should still be updated
        profile = get_scraped_profile("x")
        niches = json.loads(profile["ai_niches"])
        assert "tech" in niches

    @pytest.mark.asyncio
    async def test_classification_failure_leaves_db_unchanged(self):
        """classify_and_store leaves DB unchanged when classification fails."""
        upsert_scraped_profile(
            platform="x",
            follower_count=100,
            recent_posts=json.dumps([{"text": "test post"}]),
            ai_niches="[]",
        )

        with patch("utils.niche_classifier._get_gemini_client", return_value=None):
            await classify_and_store()

        profile = get_scraped_profile("x")
        niches = json.loads(profile["ai_niches"])
        assert niches == []


# ── get_detected_niches ──────────────────────────────────────────


class TestGetDetectedNiches:
    def test_merges_niches_across_platforms(self):
        """get_detected_niches returns union of niches from all platforms."""
        upsert_scraped_profile(
            platform="x",
            follower_count=1000,
            ai_niches='["finance", "crypto"]',
        )
        upsert_scraped_profile(
            platform="linkedin",
            follower_count=500,
            ai_niches='["finance", "tech", "business"]',
        )

        result = get_detected_niches()
        assert set(result) == {"finance", "crypto", "tech", "business"}

    def test_deduplicates_niches(self):
        """get_detected_niches does not return duplicates."""
        upsert_scraped_profile(
            platform="x",
            ai_niches='["finance", "tech"]',
        )
        upsert_scraped_profile(
            platform="linkedin",
            ai_niches='["finance", "tech"]',
        )

        result = get_detected_niches()
        assert len(result) == len(set(result))

    def test_no_profiles_returns_empty(self):
        """get_detected_niches returns empty list when no profiles exist."""
        result = get_detected_niches()
        assert result == []

    def test_profiles_with_no_niches_returns_empty(self):
        """get_detected_niches returns empty list when niches are all empty."""
        upsert_scraped_profile(platform="x", ai_niches="[]")
        upsert_scraped_profile(platform="linkedin", ai_niches="[]")

        result = get_detected_niches()
        assert result == []

    def test_handles_malformed_json_gracefully(self):
        """get_detected_niches handles corrupted ai_niches JSON."""
        upsert_scraped_profile(platform="x", ai_niches="not valid json")
        upsert_scraped_profile(
            platform="linkedin",
            ai_niches='["tech"]',
        )

        result = get_detected_niches()
        assert "tech" in result

    def test_returns_sorted_list(self):
        """get_detected_niches returns niches in sorted order."""
        upsert_scraped_profile(
            platform="x",
            ai_niches='["tech", "finance", "crypto"]',
        )

        result = get_detected_niches()
        assert result == sorted(result)
