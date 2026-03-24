"""LangGraph content pipeline — profile → research → draft → quality → output.

Usage:
    from agents.pipeline import run_pipeline
    result = run_pipeline(campaign_dict, enabled_platforms)
    # result["output"] has same format as ContentGenerator.generate()
"""

import json
import logging
import os
import sys
from pathlib import Path

from langgraph.graph import StateGraph, START, END

from agents.state import PipelineState
from agents.profile_node import profile_node
from agents.research_node import research_node
from agents.draft_node import draft_node
from agents.quality_node import quality_node

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent


def _output_node(state: dict) -> dict:
    """Format pipeline output to match ContentGenerator's output format.

    This ensures backward compatibility — campaign_runner.py gets the same
    dict format regardless of whether the old or new pipeline was used.
    """
    drafts = state.get("drafts", {})
    image_prompt = state.get("image_prompt", "")
    quality_scores = state.get("quality_scores", {})

    output = {}
    for platform, draft in drafts.items():
        if draft:
            output[platform] = draft

    if image_prompt:
        output["image_prompt"] = image_prompt

    # Log summary
    platforms_done = [p for p in output if p != "image_prompt"]
    avg_score = sum(quality_scores.values()) / max(len(quality_scores), 1)
    logger.info("Pipeline complete: %d platforms, avg quality %.0f/100",
                len(platforms_done), avg_score)

    return {"output": output}


def build_graph() -> StateGraph:
    """Build the LangGraph content pipeline."""
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("profile", profile_node)
    graph.add_node("research", research_node)
    graph.add_node("draft", draft_node)
    graph.add_node("quality", quality_node)
    graph.add_node("output", _output_node)

    # Wire edges: profile → research → draft → quality → output
    graph.add_edge(START, "profile")
    graph.add_edge("profile", "research")
    graph.add_edge("research", "draft")
    graph.add_edge("draft", "quality")
    graph.add_edge("quality", "output")
    graph.add_edge("output", END)

    return graph


# Compiled graph (singleton)
_compiled = None


def get_pipeline():
    """Get or create the compiled pipeline."""
    global _compiled
    if _compiled is None:
        graph = build_graph()
        _compiled = graph.compile()
    return _compiled


def run_pipeline(campaign: dict, enabled_platforms: list[str] = None) -> dict:
    """Run the content pipeline synchronously.

    Args:
        campaign: Campaign dict from server (title, brief, content_guidance, assets)
        enabled_platforms: List of platform names to generate for

    Returns:
        Dict with same format as ContentGenerator.generate():
        {"x": "tweet text", "linkedin": "post text", ..., "image_prompt": "..."}
    """
    if enabled_platforms is None:
        enabled_platforms = ["x", "linkedin", "facebook", "reddit"]

    # Load .env for API keys
    from dotenv import load_dotenv
    load_dotenv(ROOT / "config" / ".env", override=True)

    # Initialize DB (ensures agent tables exist)
    sys.path.insert(0, str(ROOT / "scripts"))
    from utils.local_db import init_db
    init_db()

    pipeline = get_pipeline()

    initial_state = {
        "campaign": campaign,
        "enabled_platforms": enabled_platforms,
    }

    logger.info("Running agent pipeline for campaign: %s", campaign.get("title", "?"))
    result = pipeline.invoke(initial_state)

    return result.get("output", {})


if __name__ == "__main__":
    """Test the pipeline with a mock campaign."""
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load .env
    from dotenv import load_dotenv
    load_dotenv(ROOT / "config" / ".env", override=True)

    test_campaign = {
        "campaign_id": 999,
        "title": "AI Trading Indicator Launch",
        "brief": "Promote our new AI-powered trading indicator that helps retail traders "
                 "spot reversals before they happen. Focus on how it saves people from "
                 "losing money on fake breakouts.",
        "content_guidance": "Target beginner traders. Emphasize ease of use and data-driven approach.",
        "assets": "{}",
    }

    result = run_pipeline(test_campaign, ["x", "linkedin", "reddit"])

    print("\n" + "=" * 60)
    print("PIPELINE OUTPUT")
    print("=" * 60)
    for platform, content in result.items():
        if platform == "image_prompt":
            print(f"\nImage prompt: {content}")
        elif isinstance(content, dict):
            print(f"\n--- {platform.upper()} ---")
            for k, v in content.items():
                print(f"  {k}: {v[:200]}...")
        else:
            print(f"\n--- {platform.upper()} ---")
            print(f"  {content[:300]}")
