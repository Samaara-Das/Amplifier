"""Tests for the content generator — prompt structure, JSON parsing, provider chain."""

import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestContentPrompt:
    """Verify the content prompt is campaign-generic, not personal-branded."""

    def test_prompt_has_no_personal_finance_references(self):
        from utils.content_generator import CONTENT_PROMPT
        lower = CONTENT_PROMPT.lower()
        assert "financial markets" not in lower
        assert " rsi " not in lower  # Check as standalone word, not substring of "genuinely"
        assert "backtested" not in lower
        assert "trading" not in lower
        assert "india" not in lower
        assert "us audience only" not in lower

    def test_prompt_is_ugc_focused(self):
        from utils.content_generator import CONTENT_PROMPT
        assert "UGC" in CONTENT_PROMPT
        assert "real person" in CONTENT_PROMPT.lower() or "real user" in CONTENT_PROMPT.lower()

    def test_prompt_has_platform_format_rules(self):
        from utils.content_generator import CONTENT_PROMPT
        assert "280 chars" in CONTENT_PROMPT  # X limit
        assert "linkedin" in CONTENT_PROMPT.lower()
        assert "reddit" in CONTENT_PROMPT.lower()
        assert "facebook" in CONTENT_PROMPT.lower()

    def test_prompt_has_template_placeholders(self):
        from utils.content_generator import CONTENT_PROMPT
        assert "{title}" in CONTENT_PROMPT
        assert "{brief}" in CONTENT_PROMPT
        assert "{content_guidance}" in CONTENT_PROMPT
        assert "{assets}" in CONTENT_PROMPT
        assert "{platforms}" in CONTENT_PROMPT


class TestJSONParsing:
    """Verify the JSON parser handles various AI response formats."""

    def test_clean_json(self):
        from utils.content_generator import _parse_json_response
        result = _parse_json_response('{"x": "hello", "linkedin": "world"}')
        assert result["x"] == "hello"
        assert result["linkedin"] == "world"

    def test_json_with_markdown_fences(self):
        from utils.content_generator import _parse_json_response
        result = _parse_json_response('```json\n{"x": "hello"}\n```')
        assert result["x"] == "hello"

    def test_json_with_surrounding_text(self):
        from utils.content_generator import _parse_json_response
        result = _parse_json_response('Here is the content:\n{"x": "hello"}\nDone!')
        assert result["x"] == "hello"

    def test_invalid_json_raises(self):
        from utils.content_generator import _parse_json_response
        with pytest.raises(ValueError):
            _parse_json_response("not json at all")


class TestProviderChain:
    """Verify provider initialization logic."""

    def test_no_keys_gives_empty_providers(self):
        import os
        # Clear all keys
        old_keys = {}
        for k in ("GEMINI_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY"):
            old_keys[k] = os.environ.pop(k, None)

        from utils.content_generator import ContentGenerator
        gen = ContentGenerator()
        assert len(gen.text_providers) == 0

        # Restore
        for k, v in old_keys.items():
            if v is not None:
                os.environ[k] = v

    def test_gemini_key_creates_provider(self):
        import os
        os.environ["GEMINI_API_KEY"] = "test-fake-key"
        from utils.content_generator import ContentGenerator
        gen = ContentGenerator()
        assert len(gen.text_providers) >= 1
        assert gen.text_providers[0].name == "gemini"
        del os.environ["GEMINI_API_KEY"]


class TestPostImports:
    """Verify post.py imports without crashing after deleted module stubs."""

    def test_post_imports(self):
        import post  # Should not raise ImportError
        assert hasattr(post, "human_delay")
        assert hasattr(post, "human_type")
        assert hasattr(post, "browse_feed")
