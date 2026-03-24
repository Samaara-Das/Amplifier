"""Amplifier runner — polls server for campaigns, generates content, posts, reports metrics.

This is the main entry point for campaign mode. It runs as a background loop
that periodically checks for new campaigns and processes them.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")
os.environ.setdefault("AUTO_POSTER_ROOT", str(ROOT))

from utils.server_client import (
    is_logged_in, poll_campaigns, update_assignment, report_posts, get_earnings,
)
from utils.local_db import (
    init_db, upsert_campaign, get_campaigns, get_campaign, update_campaign_status,
    add_post, get_unsynced_posts, mark_posts_synced, get_setting, set_setting,
)
from utils.content_generator import ContentGenerator

# Logging
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "campaign_runner.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("CAMPAIGN_POLL_INTERVAL_SEC", "600"))  # 10 min default


_content_gen = None


def _get_content_generator() -> ContentGenerator:
    global _content_gen
    if _content_gen is None:
        _content_gen = ContentGenerator()
    return _content_gen


async def _generate_content(campaign: dict) -> dict | None:
    """Generate platform content for a campaign using free AI APIs."""
    try:
        gen = _get_content_generator()

        # Determine which platforms are enabled
        with open(ROOT / "config" / "platforms.json", "r", encoding="utf-8") as f:
            platforms_config = json.load(f)
        enabled = [p for p, cfg in platforms_config.items() if cfg.get("enabled")]

        # Generate text content
        content = await gen.generate(campaign, enabled_platforms=enabled)

        # Generate image if we got an image prompt
        image_prompt = content.pop("image_prompt", None)
        if image_prompt:
            image_path = await gen.generate_image(image_prompt)
            if image_path:
                content["_image_path"] = image_path

        return {"content": content}

    except Exception as e:
        logger.error("Content generation failed for campaign %s: %s",
                     campaign.get("campaign_id"), e)
        return None


async def _post_campaign_content(campaign_id: int, assignment_id: int, content: dict):
    """Post campaign content to all platforms using existing poster functions."""
    import importlib.util
    import random

    # Load platform config
    with open(ROOT / "config" / "platforms.json", "r", encoding="utf-8") as f:
        platforms_config = json.load(f)

    # Import post.py module to access posting functions
    spec = importlib.util.spec_from_file_location("post_module", ROOT / "scripts" / "post.py")
    post_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(post_module)

    from playwright.async_api import async_playwright

    posted_platforms = []
    post_records = []

    # Filter to enabled platforms that have generated content
    platforms_to_post = [p for p in content.keys()
                         if p != "_image_path" and platforms_config.get(p, {}).get("enabled")]
    random.shuffle(platforms_to_post)

    # Build a draft structure matching what post_to_* functions expect
    # They call _extract_content(draft["content"], platform) which reads draft["content"][platform]
    draft = {"content": {}, "id": f"campaign-{campaign_id}"}
    for platform in platforms_to_post:
        draft["content"][platform] = content[platform]

    # If campaign generated an image, attach it so post functions can use it
    image_path = content.get("_image_path")

    async with async_playwright() as pw:
        for platform in platforms_to_post:
            logger.info("Posting campaign %d to %s...", campaign_id, platform)

            try:
                # Each post_to_* function manages its own browser context
                post_func = getattr(post_module, f"post_to_{platform}", None)
                if not post_func:
                    logger.warning("No posting function for platform: %s", platform)
                    continue

                result_url = await post_func(draft, pw)
                if result_url:
                    content_str = json.dumps(content[platform]) if isinstance(content[platform], dict) else str(content[platform])
                    content_hash = hashlib.sha256(content_str.encode()).hexdigest()

                    local_post_id = add_post(
                        campaign_server_id=campaign_id,
                        assignment_id=assignment_id,
                        platform=platform,
                        post_url=result_url,
                        content=content_str,
                        content_hash=content_hash,
                    )
                    post_records.append({
                        "local_id": local_post_id,
                        "assignment_id": assignment_id,
                        "platform": platform,
                        "post_url": result_url,
                        "content_hash": content_hash,
                        "posted_at": datetime.now(timezone.utc).isoformat(),
                    })
                    posted_platforms.append(platform)
                    logger.info("Posted to %s", platform)
                else:
                    logger.warning("Failed to post to %s (returned False)", platform)

                # Random delay between platforms (30-90s)
                if platform != platforms_to_post[-1]:
                    delay = random.randint(30, 90)
                    logger.info("Waiting %ds before next platform...", delay)
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error("Failed to post to %s: %s", platform, e)

    return posted_platforms, post_records


def _sync_posts_to_server():
    """Report unsynced posts to the server."""
    unsynced = get_unsynced_posts()
    if not unsynced:
        return

    server_posts = []
    for p in unsynced:
        server_posts.append({
            "assignment_id": p["assignment_id"],
            "platform": p["platform"],
            "post_url": p["post_url"],
            "content_hash": p["content_hash"],
            "posted_at": p["posted_at"],
        })

    try:
        result = report_posts(server_posts)
        # Map server post IDs back to local posts
        created = result.get("created", [])
        server_id_map = {}
        for i, local_post in enumerate(unsynced):
            if i < len(created):
                server_id_map[local_post["id"]] = created[i].get("id")

        mark_posts_synced([p["id"] for p in unsynced], server_id_map)
        logger.info("Synced %d posts to server", len(unsynced))
    except Exception as e:
        logger.error("Failed to sync posts: %s", e)


async def process_campaign(campaign: dict, mode: str = "full_auto"):
    """Process a single campaign: generate content, optionally review, then post."""
    campaign_id = campaign["campaign_id"]
    assignment_id = campaign["assignment_id"]

    logger.info("Processing campaign %d: %s", campaign_id, campaign["title"])

    # Store campaign locally
    upsert_campaign(campaign)

    # Check if already processed
    local = get_campaign(campaign_id)
    if local and local["status"] in ("posted", "skipped"):
        logger.info("Campaign %d already %s, skipping", campaign_id, local["status"])
        return

    # Generate content
    generated = await _generate_content(campaign)
    if not generated:
        logger.error("Failed to generate content for campaign %d", campaign_id)
        return

    content = generated.get("content", {})
    update_campaign_status(campaign_id, "content_generated", json.dumps(content))

    # Report content_generated status to server
    try:
        update_assignment(assignment_id, "content_generated")
    except Exception as e:
        logger.warning("Failed to update assignment status: %s", e)

    if mode == "full_auto":
        # Post immediately
        posted_platforms, post_records = await _post_campaign_content(
            campaign_id, assignment_id, content
        )

        if posted_platforms:
            update_campaign_status(campaign_id, "posted")
            try:
                update_assignment(assignment_id, "posted")
            except Exception as e:
                logger.warning("Failed to update assignment status: %s", e)
            logger.info("Campaign %d posted to: %s", campaign_id, posted_platforms)
        else:
            logger.error("Campaign %d: no platforms posted successfully", campaign_id)

        # Sync posts to server
        _sync_posts_to_server()

    else:
        # semi_auto or manual — leave for dashboard review
        logger.info("Campaign %d content generated. Awaiting review in dashboard.", campaign_id)


async def run_poll_loop():
    """Main polling loop — fetches campaigns and processes them."""
    mode = get_setting("mode", "semi_auto")
    logger.info("Amplifier runner started (mode: %s, poll interval: %ds)", mode, POLL_INTERVAL)

    while True:
        try:
            if not is_logged_in():
                logger.warning("Not logged in. Waiting for onboarding...")
                await asyncio.sleep(60)
                continue

            # Poll for campaigns
            campaigns = poll_campaigns()

            if campaigns:
                logger.info("Received %d campaign(s)", len(campaigns))
                for campaign in campaigns:
                    await process_campaign(campaign, mode=mode)
            else:
                logger.info("No new campaigns. Sleeping %ds...", POLL_INTERVAL)

            # Sync any unsynced posts
            _sync_posts_to_server()

        except Exception as e:
            logger.error("Poll loop error: %s", e)

        await asyncio.sleep(POLL_INTERVAL)


async def run_once():
    """Single poll + process run (for testing or manual trigger)."""
    init_db()
    if not is_logged_in():
        logger.error("Not logged in. Run onboarding first.")
        return

    mode = get_setting("mode", "semi_auto")
    campaigns = poll_campaigns()
    logger.info("Received %d campaign(s)", len(campaigns))

    for campaign in campaigns:
        await process_campaign(campaign, mode=mode)

    _sync_posts_to_server()


def main():
    parser = argparse.ArgumentParser(description="Amplifier runner — poll, generate, post")
    parser.add_argument("--once", action="store_true", help="Run once then exit (no loop)")
    parser.add_argument("--mode", choices=["full_auto", "semi_auto", "manual"],
                        help="Override operating mode")
    args = parser.parse_args()

    init_db()

    if args.mode:
        set_setting("mode", args.mode)

    if args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(run_poll_loop())


if __name__ == "__main__":
    main()
