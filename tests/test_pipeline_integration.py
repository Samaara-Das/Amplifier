"""Integration tests for the full agent pipeline.

These tests hit real APIs (Gemini, webcrawler) — skip with -m "not integration" if needed.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from agents.pipeline import build_graph, run_pipeline
from agents.state import PipelineState


class TestPipelineGraph:
    def test_graph_builds(self):
        """Graph compiles without errors."""
        graph = build_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_all_nodes(self):
        """Graph contains all expected nodes."""
        graph = build_graph()
        # StateGraph stores nodes in a dict
        node_names = set(graph.nodes.keys())
        expected = {"profile", "research", "draft", "quality", "output"}
        assert expected.issubset(node_names)


class TestPipelineWithMocks:
    def test_pipeline_with_mock_llm(self, sample_campaign):
        """Pipeline runs end-to-end with mocked LLM calls."""
        mock_response_text = json.dumps({
            "x": "Test tweet about trading #test",
            "linkedin": "Test LinkedIn post about trading strategies.",
            "facebook": "Test Facebook post.",
            "reddit": {"title": "Test Reddit Title", "body": "Test Reddit body content."},
            "image_prompt": "A chart showing upward trend",
        })

        # Mock the LLM and webcrawler to avoid real API calls
        with patch("agents.research_node._run_crawler") as mock_crawler, \
             patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_llm_cls:

            # Mock webcrawler search results
            mock_crawler.return_value = json.dumps({
                "results": [
                    {"title": "Trading strategies 2026", "url": "https://example.com", "description": "Top strategies"}
                ]
            })

            # Mock LLM responses
            mock_llm = mock_llm_cls.return_value
            mock_response = type("MockResponse", (), {"content": "Test draft for platform"})()
            mock_llm.invoke.return_value = mock_response

            result = run_pipeline(sample_campaign, ["x", "linkedin"])

            assert isinstance(result, dict)
            # Should have content for requested platforms
            assert "x" in result or "linkedin" in result


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "test-key",
    reason="GEMINI_API_KEY not set — skipping real API test",
)
class TestPipelineReal:
    """Tests that hit real APIs. Only run when GEMINI_API_KEY is set."""

    def test_full_pipeline_real(self, sample_campaign):
        """Full pipeline with real Gemini + webcrawler."""
        result = run_pipeline(sample_campaign, ["x", "reddit"])

        assert isinstance(result, dict)
        assert len(result) >= 1  # At least one platform generated

        # Check X draft exists and is reasonable
        if "x" in result:
            assert len(result["x"]) > 20
            assert len(result["x"]) <= 500  # Rough sanity check

        # Check Reddit draft structure
        if "reddit" in result:
            if isinstance(result["reddit"], dict):
                assert "title" in result["reddit"]
                assert "body" in result["reddit"]

        # Should have an image prompt
        if "image_prompt" in result:
            assert len(result["image_prompt"]) > 10
