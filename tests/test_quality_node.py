"""Tests for the quality validation node."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from agents.quality_node import (
    _check_banned_phrases,
    _check_length,
    _check_emotion_hook,
    _check_value,
    _score_draft,
    quality_node,
)


class TestBannedPhrases:
    def test_clean_text(self):
        assert _check_banned_phrases("This indicator helps traders spot reversals") == []

    def test_ai_sounding(self):
        issues = _check_banned_phrases("In today's fast-paced world of trading")
        assert len(issues) == 1
        assert "fast-paced world" in issues[0]

    def test_trading_experience_claim(self):
        issues = _check_banned_phrases("I traded this strategy for 3 years")
        assert len(issues) == 1
        assert "i traded" in issues[0]

    def test_location_reveal_india(self):
        issues = _check_banned_phrases("Markets in India are volatile")
        assert any("india" in i for i in issues)

    def test_ist_standalone_flagged(self):
        """IST as standalone word (timezone) should be flagged."""
        issues = _check_banned_phrases("The market opens at 9:30 IST ")
        assert any("ist" in i.lower() for i in issues)

    def test_ist_inside_word_not_flagged(self):
        """'ist' inside words like 'institutional' should NOT be flagged."""
        issues = _check_banned_phrases("See what institutional traders are doing")
        assert not any("ist" in i.lower() for i in issues)

    def test_multiple_violations(self):
        text = "I traded in India using a game-changer indicator"
        issues = _check_banned_phrases(text)
        assert len(issues) >= 3  # "i traded", "india", "game-changer"


class TestLength:
    def test_x_valid(self):
        assert _check_length("A" * 200, "x") == []

    def test_x_too_long(self):
        issues = _check_length("A" * 300, "x")
        assert any("Too long" in i for i in issues)

    def test_x_too_short(self):
        issues = _check_length("Hi", "x")
        assert any("Too short" in i for i in issues)

    def test_linkedin_valid(self):
        assert _check_length("A" * 800, "linkedin") == []

    def test_linkedin_too_short(self):
        issues = _check_length("A" * 50, "linkedin")
        assert any("Too short" in i for i in issues)

    def test_reddit_title(self):
        assert _check_length("A" * 80, "reddit_title") == []
        issues = _check_length("A" * 150, "reddit_title")
        assert any("Too long" in i for i in issues)

    def test_unknown_platform(self):
        assert _check_length("anything", "unknown_platform") == []


class TestEmotionHook:
    def test_has_emotion(self):
        assert _check_emotion_hook("Most traders lose money because they don't understand this") == []

    def test_has_question(self):
        assert _check_emotion_hook("What if your strategy ran while you slept?") == []

    def test_missing_emotion(self):
        issues = _check_emotion_hook("Here is a technical analysis of moving averages and their applications")
        assert len(issues) == 1
        assert "emotional hook" in issues[0].lower()

    def test_short_text_skipped(self):
        """Very short text shouldn't be flagged for missing emotion."""
        assert _check_emotion_hook("Buy now") == []


class TestValue:
    def test_has_actionable_value(self):
        assert _check_value("Here's how to spot fake breakouts: look for volume divergence at key levels") == []

    def test_has_data(self):
        assert _check_value("We backtested this on 500 trades and found a 64% win rate") == []

    def test_missing_value(self):
        text = "Trading is really important and everyone should learn about the financial markets and how they work in our modern economy"
        issues = _check_value(text)
        assert len(issues) == 1
        assert "actionable value" in issues[0].lower()

    def test_short_text_skipped(self):
        assert _check_value("Quick tip") == []


class TestScoring:
    def test_perfect_score(self):
        score = _score_draft("Great post with backtest data and a question?", "x", [])
        assert score >= 95

    def test_banned_phrase_penalty(self):
        score = _score_draft("text", "x", ["Banned phrase: 'game-changer'"])
        assert score <= 80

    def test_length_penalty(self):
        score = _score_draft("text", "x", ["Too long (300 chars, max 280)"])
        assert score <= 90

    def test_multiple_issues(self):
        issues = ["Banned phrase: 'i traded'", "Too long (500 chars, max 280)", "lacks emotional hook"]
        score = _score_draft("text", "x", issues)
        assert score <= 55

    def test_score_clamped(self):
        issues = ["Banned phrase: 'a'"] * 10
        score = _score_draft("text", "x", issues)
        assert score >= 0


class TestQualityNode:
    def test_scores_all_platforms(self):
        state = {
            "drafts": {
                "x": "Most traders lose money. Here's what the data shows about reversals. #trading",
                "linkedin": "Tired of losing money?\n\nYou're not alone. " + "A" * 400 + "\n\nWhat do you think? #trading #finance",
                "facebook": "Ever wonder why most traders fail? Here's the one thing that changed everything for me.",
                "reddit": {"title": "Why most traders lose money on fake breakouts", "body": "I backtested 500 trades and found that 80% of breakouts fail. Here's what the data shows..." + "A" * 300},
            }
        }
        result = quality_node(state)
        assert "quality_scores" in result
        assert "quality_issues" in result
        assert set(result["quality_scores"].keys()) == {"x", "linkedin", "facebook", "reddit"}
        assert all(0 <= s <= 100 for s in result["quality_scores"].values())

    def test_empty_draft_scores_zero(self):
        state = {"drafts": {"x": ""}}
        result = quality_node(state)
        assert result["quality_scores"]["x"] == 0

    def test_no_drafts(self):
        result = quality_node({"drafts": {}})
        assert result["quality_scores"] == {}
