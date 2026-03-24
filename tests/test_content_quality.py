"""Tests for content quality scoring with brief adherence (Task 11).

Covers:
- Must-include phrase detection (present / missing)
- Content guidance adherence
- Combined score averages rules + adherence correctly
- Warning flag at threshold 60
- Empty brief = 100 adherence (no requirements)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.content_quality import check_brief_adherence, combined_quality_score


# ===================================================================
# Brief adherence checks
# ===================================================================


class TestMustInclude:
    """Must-include phrase detection."""

    def test_phrase_present(self):
        """Content that includes the required phrase gets no issues."""
        result = check_brief_adherence(
            content="Check out our new tool at https://example.com today!",
            campaign_brief="Promote our product",
            must_include=["https://example.com"],
        )
        missing = [i for i in result["issues"] if "must-include" in i.lower()]
        assert missing == []

    def test_phrase_missing(self):
        """Missing must-include phrase is flagged and deducts points."""
        result = check_brief_adherence(
            content="This product is amazing for traders.",
            campaign_brief="Promote our product",
            must_include=["Visit example.com"],
        )
        assert any("Visit example.com" in i for i in result["issues"])
        assert result["score"] <= 80  # -20 for missing phrase

    def test_multiple_phrases_some_missing(self):
        """Multiple must-include: present ones pass, missing ones flagged."""
        result = check_brief_adherence(
            content="Use #BrandTag to share your thoughts about trading tools.",
            campaign_brief="Promote trading tools",
            must_include=["#BrandTag", "Visit our site at brand.com"],
        )
        # #BrandTag is present, "Visit our site at brand.com" is missing
        missing = [i for i in result["issues"] if "must-include" in i.lower()]
        assert len(missing) == 1
        assert "brand.com" in missing[0]

    def test_case_insensitive_match(self):
        """Must-include matching is case-insensitive."""
        result = check_brief_adherence(
            content="VISIT EXAMPLE.COM for more info!",
            campaign_brief="Promote",
            must_include=["visit example.com"],
        )
        missing = [i for i in result["issues"] if "must-include" in i.lower()]
        assert missing == []

    def test_empty_must_include_list(self):
        """Empty must_include list results in no phrase-related issues."""
        result = check_brief_adherence(
            content="Great product for everyone.",
            campaign_brief="Promote our product",
            must_include=[],
        )
        missing = [i for i in result["issues"] if "must-include" in i.lower()]
        assert missing == []

    def test_none_must_include(self):
        """None must_include is handled gracefully."""
        result = check_brief_adherence(
            content="Great product for everyone.",
            campaign_brief="Promote our product",
            must_include=None,
        )
        missing = [i for i in result["issues"] if "must-include" in i.lower()]
        assert missing == []

    def test_whitespace_only_phrase_skipped(self):
        """Whitespace-only must-include phrases are skipped."""
        result = check_brief_adherence(
            content="Great product.",
            campaign_brief="Promote",
            must_include=["", "   "],
        )
        missing = [i for i in result["issues"] if "must-include" in i.lower()]
        assert missing == []


class TestContentGuidance:
    """Content guidance adherence checks."""

    def test_good_guidance_adherence(self):
        """Content that reflects guidance keywords passes."""
        result = check_brief_adherence(
            content="This beginner-friendly trading tool emphasizes simplicity and ease of use for everyone",
            campaign_brief="Promote trading tool",
            content_guidance="Target beginner traders. Emphasize ease of use and simplicity.",
        )
        guidance_issues = [i for i in result["issues"] if "guidance" in i.lower()]
        assert guidance_issues == []

    def test_poor_guidance_adherence(self):
        """Content that ignores guidance gets flagged."""
        result = check_brief_adherence(
            content="The weather is nice today. Let me tell you about my cat.",
            campaign_brief="Promote trading tool",
            content_guidance="Target beginner traders. Emphasize ease of use and simplicity.",
        )
        guidance_issues = [i for i in result["issues"] if "guidance" in i.lower()]
        assert len(guidance_issues) >= 1

    def test_empty_guidance(self):
        """Empty guidance string causes no guidance issues."""
        result = check_brief_adherence(
            content="Random content about anything",
            campaign_brief="Some brief",
            content_guidance="",
        )
        guidance_issues = [i for i in result["issues"] if "guidance" in i.lower()]
        assert guidance_issues == []


class TestBriefRelevance:
    """Brief keyword overlap checks."""

    def test_relevant_content(self):
        """Content that covers brief topics gets good score."""
        result = check_brief_adherence(
            content="This AI-powered trading indicator helps retail traders spot reversals before they happen. Stop losing money on fake breakouts.",
            campaign_brief="Promote our new AI-powered trading indicator that helps retail traders spot reversals before they happen. Focus on how it saves people from losing money on fake breakouts.",
        )
        assert result["score"] >= 85

    def test_irrelevant_content(self):
        """Content completely off-topic from brief gets flagged."""
        result = check_brief_adherence(
            content="The best recipe for chocolate cake is easy to follow",
            campaign_brief="Promote our AI-powered trading indicator for retail traders to spot market reversals and avoid fake breakouts",
        )
        brief_issues = [i for i in result["issues"] if "brief relevance" in i.lower()]
        assert len(brief_issues) >= 1


class TestEmptyBrief:
    """Empty brief = 100 adherence (no requirements)."""

    def test_empty_brief_perfect_score(self):
        """No brief, no guidance, no must-include = 100."""
        result = check_brief_adherence(
            content="Literally anything here",
            campaign_brief="",
            content_guidance="",
            must_include=None,
        )
        assert result["score"] == 100
        assert result["issues"] == []

    def test_all_none(self):
        """All parameters empty/None = 100."""
        result = check_brief_adherence(
            content="Anything",
            campaign_brief="",
            content_guidance="",
            must_include=[],
        )
        assert result["score"] == 100


# ===================================================================
# Combined quality score
# ===================================================================


class TestCombinedScore:
    """Combined score averaging and warning flag."""

    def test_combined_averages_correctly(self):
        """Combined score is average of rules_score and adherence_score."""
        result = combined_quality_score(
            content="Most traders lose money! Here's how our AI indicator spotted 80% of reversals in backtested data. Visit example.com #trading",
            platform="x",
            campaign_brief="Promote AI trading indicator that spots reversals",
            content_guidance="Target beginner traders",
            must_include=["example.com"],
        )
        expected = (result["rules_score"] + result["adherence_score"]) / 2
        assert result["score"] == int(expected)
        assert "rules_score" in result
        assert "adherence_score" in result

    def test_combined_both_fields_present(self):
        """Result contains rules_score, adherence_score, and issues list."""
        result = combined_quality_score(
            content="Great product for traders!",
            platform="x",
            campaign_brief="Promote product",
        )
        assert "rules_score" in result
        assert "adherence_score" in result
        assert "issues" in result
        assert isinstance(result["issues"], list)

    def test_warning_below_60(self):
        """Warning flag is True when combined score < 60."""
        # Use content with many issues: banned phrase + missing must-include + off-topic
        result = combined_quality_score(
            content="In today's fast-paced world, let's dive in to discuss game-changer strategies!",
            platform="x",
            campaign_brief="Promote our AI trading indicator for spotting market reversals in real-time data",
            must_include=["Visit tradingbot.com", "Use code SAVE20"],
        )
        # Multiple banned phrases + missing must-includes should push score well below 60
        assert result["warning"] is True
        assert result["score"] < 60

    def test_no_warning_above_60(self):
        """Warning flag is False when combined score >= 60."""
        result = combined_quality_score(
            content="Most traders lose money! Here's how to spot fake breakouts with backtested data. #trading",
            platform="x",
            campaign_brief="Promote trading education content about breakouts",
        )
        if result["score"] >= 60:
            assert result["warning"] is False

    def test_perfect_content_high_score(self):
        """Content that passes all checks gets high combined score."""
        result = combined_quality_score(
            content="Most traders lose money on fake breakouts! Our AI indicator backtested 500 trades and found 80% accuracy. Visit example.com #trading",
            platform="x",
            campaign_brief="Promote AI trading indicator that detects fake breakouts with high accuracy",
            must_include=["example.com"],
        )
        assert result["score"] >= 70
        assert result["warning"] is False

    def test_empty_brief_full_adherence(self):
        """Empty brief gives 100 adherence, combined depends only on rules."""
        result = combined_quality_score(
            content="Most traders fail. Here's how to use data to find your edge. #trading",
            platform="x",
            campaign_brief="",
        )
        assert result["adherence_score"] == 100
        # Combined = (rules_score + 100) / 2
        expected = (result["rules_score"] + 100) / 2
        assert result["score"] == int(expected)

    def test_score_clamped_0_100(self):
        """Combined score stays within 0-100 range."""
        result = combined_quality_score(
            content="x",
            platform="x",
            campaign_brief="Very specific requirements that content does not match at all",
            must_include=["phrase1", "phrase2", "phrase3", "phrase4", "phrase5"],
        )
        assert 0 <= result["score"] <= 100

    def test_issues_merged(self):
        """Issues from both rules and adherence are merged in the result."""
        result = combined_quality_score(
            content="In today's fast-paced world of trading",
            platform="x",
            campaign_brief="Promote AI indicator",
            must_include=["Visit site.com"],
        )
        # Should have banned phrase issue + must-include issue
        has_banned = any("banned" in i.lower() for i in result["issues"])
        has_missing = any("must-include" in i.lower() for i in result["issues"])
        assert has_banned
        assert has_missing
