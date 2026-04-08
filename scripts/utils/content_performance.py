"""Content Performance Tracker — feedback loop from metrics to strategy.

Analyzes post performance after T+72h final metrics arrive, classifies
hooks and formats, and updates agent_content_insights table. The Strategy
Phase in ContentAgent reads these insights to optimize future content.

Flow: metric_scraper → content_performance → agent_content_insights → content_agent
"""

import json
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Hook classification ─────────────────────────────────────────

# Ordered dict — more specific patterns FIRST to avoid premature matches
# (e.g. "I was tired" should match problem_solution, not story's "I was")
HOOK_PATTERNS = {
    "problem_solution": re.compile(
        r"^(i struggled|i was tired|sick of|fed up|the problem with|i couldn'?t figure|i could not)",
        re.IGNORECASE,
    ),
    "surprising_result": re.compile(
        r"^(i didn'?t expect|i did not expect|i was shocked|turns out|i never thought|the result|this changed)",
        re.IGNORECASE,
    ),
    "question": re.compile(
        r"^(did you|have you|what if|why do|how do|ever wonder|what would|what's|when was|who else|anyone else)",
        re.IGNORECASE,
    ),
    "contrarian": re.compile(
        r"^(unpopular opinion|hot take|everyone says|most people think|stop |nobody talks|here's why|the truth about)",
        re.IGNORECASE,
    ),
    "social_proof": re.compile(
        r"^(everyone'?s|everyone is|my feed is|thousands of|the reason|i keep seeing|people are)",
        re.IGNORECASE,
    ),
    "stat": re.compile(
        r"^(\d+%|\d+ percent|\d+ out of|\$\d+|according to|\d+ people|\d+x )",
        re.IGNORECASE,
    ),
    "story": re.compile(
        r"^(i used to|last week|yesterday|a friend|so i was|i just|i recently|i've been|when i|i was)",
        re.IGNORECASE,
    ),
}


def classify_hook(text: str) -> str:
    """Classify the hook type of a post's opening line.

    Uses regex patterns for fast classification. Returns 'unknown' if
    no pattern matches (AI classification could be added later as enhancement).
    """
    if not text:
        return "unknown"

    # Get first sentence/line
    first_line = text.split("\n")[0].strip()
    if not first_line:
        return "unknown"

    for hook_type, pattern in HOOK_PATTERNS.items():
        if pattern.search(first_line):
            return hook_type

    # Check for question marks (catch-all for question hooks)
    if first_line.endswith("?") and len(first_line) < 150:
        return "question"

    return "unknown"


def _calculate_engagement_rate(metrics: dict) -> float:
    """Calculate engagement rate from metric values.

    engagement_rate = (likes + comments + reposts) / max(impressions, 1)
    """
    impressions = metrics.get("impressions", 0) or 0
    likes = metrics.get("likes", 0) or 0
    comments = metrics.get("comments", 0) or 0
    reposts = metrics.get("reposts", 0) or 0

    if impressions <= 0:
        return 0.0

    return (likes + comments + reposts) / impressions


# ── Performance analysis ────────────────────────────────────────


def analyze_post_performance(post_id: int) -> dict | None:
    """Analyze a single post's performance after final metrics arrive.

    Joins agent_draft (content) with local_metric (engagement) to classify
    the hook type and compute engagement rate.

    Returns analysis dict or None if data insufficient.
    """
    from utils.local_db import _get_db

    conn = _get_db()

    # Get the post's draft text and platform
    row = conn.execute("""
        SELECT lp.platform, lp.post_url, lp.campaign_server_id,
               ad.draft_text, ad.pillar_type, ad.format_type
        FROM local_post lp
        LEFT JOIN agent_draft ad ON ad.campaign_id = lp.campaign_server_id
            AND ad.platform = lp.platform AND ad.posted = 1
        WHERE lp.id = ?
        LIMIT 1
    """, (post_id,)).fetchone()

    if not row:
        conn.close()
        return None

    platform = row[0]
    draft_text = row[3] or ""
    pillar_type = row[4] or "unknown"
    format_type = row[5] or "text"

    # Get latest metrics for this post (most recent scrape is billing source of truth)
    metric = conn.execute("""
        SELECT impressions, likes, reposts, comments
        FROM local_metric
        WHERE post_id = ?
        ORDER BY id DESC LIMIT 1
    """, (post_id,)).fetchone()

    conn.close()

    if not metric:
        return None

    metrics = {
        "impressions": metric[0] or 0,
        "likes": metric[1] or 0,
        "reposts": metric[2] or 0,
        "comments": metric[3] or 0,
    }

    engagement_rate = _calculate_engagement_rate(metrics)
    hook_type = classify_hook(draft_text)

    return {
        "post_id": post_id,
        "platform": platform,
        "hook_type": hook_type,
        "pillar_type": pillar_type,
        "format_type": format_type,
        "engagement_rate": engagement_rate,
        "metrics": metrics,
        "draft_text": draft_text[:200],  # First 200 chars for reference
    }


def update_insights_from_metrics() -> int:
    """Batch job: find posts with metrics not yet analyzed,
    run performance analysis, and upsert into agent_content_insights.

    Called by background_agent.py after metric scraping completes.
    Uses the latest metric per post (most recent scrape is billing source of truth).

    Returns: number of insights updated.
    """
    from utils.local_db import _get_db, upsert_content_insight

    conn = _get_db()

    # Find posts with metrics that haven't been analyzed yet.
    # Use posts with at least one metric, ordered by most recent scrape.
    rows = conn.execute("""
        SELECT DISTINCT lm.post_id
        FROM local_metric lm
        JOIN local_post lp ON lp.id = lm.post_id
        ORDER BY lm.scraped_at DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    if not rows:
        return 0

    # Analyze each post
    analyses = []
    for row in rows:
        post_id = row[0]
        analysis = analyze_post_performance(post_id)
        if analysis and analysis["engagement_rate"] > 0:
            analyses.append(analysis)

    if not analyses:
        return 0

    # Group by (platform, pillar_type, hook_type) and compute averages
    groups: dict[tuple, list] = {}
    for a in analyses:
        key = (a["platform"], a["pillar_type"], a["hook_type"])
        if key not in groups:
            groups[key] = []
        groups[key].append(a)

    updated = 0
    for (platform, pillar, hook), items in groups.items():
        if hook == "unknown":
            continue  # Don't pollute insights with unclassified hooks

        avg_rate = sum(i["engagement_rate"] for i in items) / len(items)
        best = max(items, key=lambda x: x["engagement_rate"])
        best_text = best.get("draft_text", "")

        upsert_content_insight(
            platform=platform,
            pillar_type=pillar,
            hook_type=hook,
            avg_engagement_rate=avg_rate,
            sample_count=len(items),
            best_performing_text=best_text,
        )
        updated += 1
        logger.info(
            "Insight: %s/%s/%s — %.1f%% avg engagement (%d posts)",
            platform, pillar, hook, avg_rate * 100, len(items),
        )

    return updated
