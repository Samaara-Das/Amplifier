"""Research node — web search + company links + past performance.

Uses the webcrawler CLI for DuckDuckGo searches and page fetching.
"""

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
CRAWLER = Path("C:/Users/dassa/Work/webcrawler/crawl.py")


def _run_crawler(args: list[str], timeout: int = 30) -> str:
    """Run the webcrawler CLI and return stdout."""
    cmd = ["python", str(CRAWLER)] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout.strip()
        logger.warning("Crawler failed: %s", result.stderr[:200])
        return ""
    except subprocess.TimeoutExpired:
        logger.warning("Crawler timed out after %ds", timeout)
        return ""
    except FileNotFoundError:
        logger.warning("Webcrawler not found at %s", CRAWLER)
        return ""


def _search_topics(campaign: dict) -> list[dict]:
    """Search for campaign-relevant topics via DuckDuckGo."""
    title = campaign.get("title", "")
    brief = campaign.get("brief", "")

    # Build search query from campaign context
    query = f"{title} {brief[:100]}".strip()
    if not query:
        return []

    raw = _run_crawler(["--json", "search", query])
    if not raw:
        return []

    try:
        data = json.loads(raw)
        results = data.get("results", data) if isinstance(data, dict) else data
        findings = []
        for item in results[:5]:  # Top 5 results
            findings.append({
                "type": "web_search",
                "title": item.get("title", ""),
                "url": item.get("url", item.get("href", "")),
                "snippet": item.get("description", item.get("body", "")),
            })
        return findings
    except (json.JSONDecodeError, TypeError):
        # Fallback: treat as plain text
        return [{"type": "web_search", "title": "search results", "snippet": raw[:500]}]


def _fetch_company_links(campaign: dict) -> list[dict]:
    """Fetch any URLs provided in the campaign assets."""
    assets = campaign.get("assets", {})
    if isinstance(assets, str):
        try:
            assets = json.loads(assets)
        except (json.JSONDecodeError, TypeError):
            assets = {}

    urls = []
    # Look for URLs in assets
    for key, val in assets.items():
        if isinstance(val, str) and val.startswith("http"):
            urls.append(val)

    # Also check content_guidance for URLs
    guidance = campaign.get("content_guidance", "") or ""
    import re
    urls.extend(re.findall(r'https?://\S+', guidance))

    findings = []
    for url in urls[:3]:  # Max 3 URLs
        content = _run_crawler(["fetch", url], timeout=20)
        if content:
            findings.append({
                "type": "company_link",
                "url": url,
                "content": content[:1000],  # Truncate for prompt size
            })

    return findings


def _get_past_performance(campaign_id: int) -> list[dict]:
    """Query local DB for past post performance insights."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from utils.local_db import get_content_insights

    insights = get_content_insights()
    return insights[:10]  # Top 10 insights


def research_node(state: dict) -> dict:
    """Run research: web search + company links + past performance."""
    campaign = state.get("campaign", {})
    campaign_id = campaign.get("campaign_id", 0)

    all_research = []

    # 1. Web search for campaign-relevant topics
    logger.info("Searching for campaign-relevant topics...")
    search_results = _search_topics(campaign)
    all_research.extend(search_results)
    logger.info("Found %d search results", len(search_results))

    # 2. Fetch company links from campaign assets
    company_links = _fetch_company_links(campaign)
    all_research.extend(company_links)
    if company_links:
        logger.info("Fetched %d company link(s)", len(company_links))

    # 3. Past performance insights
    past = _get_past_performance(campaign_id)
    for p in past:
        all_research.append({
            "type": "past_performance",
            "platform": p.get("platform", ""),
            "insight": f"{p.get('pillar_type', '')} + {p.get('hook_type', '')} "
                       f"→ avg engagement {p.get('avg_engagement_rate', 0):.1%}",
        })

    # Store research in DB
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from utils.local_db import add_research
    for r in all_research:
        add_research(
            campaign_id=campaign_id,
            research_type=r.get("type", "unknown"),
            content=json.dumps(r),
            source_url=r.get("url"),
        )

    logger.info("Research complete: %d findings total", len(all_research))
    return {"research": all_research}
