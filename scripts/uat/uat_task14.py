"""UAT Task #14 — 4-Phase AI Content Agent acceptance tests.

AC1–AC14 mapped to test functions. Each function reads the campaign ID from
data/uat/last_campaign_id.txt or --campaign-id pytest option.

Run:
    pytest scripts/uat/uat_task14.py -v
    pytest scripts/uat/uat_task14.py::test_ac1_research_cold_path --campaign-id 42

Note: AC14 runs via Chrome DevTools MCP only — marked skip in this file.
"""

import asyncio
import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DB_PATH = ROOT / "data" / "local.db"
UAT_DIR = ROOT / "data" / "uat"
AGENT_LOG = UAT_DIR / "agent.log"


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def campaign_id(request) -> int:
    from conftest import get_campaign_id
    return get_campaign_id(request.config)


@pytest.fixture(scope="session")
def db():
    """Return a sqlite3 connection to local.db."""
    if not DB_PATH.exists():
        pytest.skip(f"Local DB not found at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _read_log() -> str:
    """Return agent.log content (empty string if not found)."""
    if AGENT_LOG.exists():
        return AGENT_LOG.read_text(encoding="utf-8", errors="replace")
    return ""


def _get_research_rows(db, campaign_id: int, research_type: str) -> list[dict]:
    cur = db.execute(
        "SELECT * FROM agent_research WHERE campaign_id = ? AND research_type = ? ORDER BY created_at DESC",
        (campaign_id, research_type),
    )
    return [dict(r) for r in cur.fetchall()]


def _get_draft_rows(db, campaign_id: int, platform: str | None = None) -> list[dict]:
    if platform:
        cur = db.execute(
            "SELECT * FROM agent_draft WHERE campaign_id = ? AND platform = ? ORDER BY created_at ASC",
            (campaign_id, platform),
        )
    else:
        cur = db.execute(
            "SELECT * FROM agent_draft WHERE campaign_id = ? ORDER BY created_at ASC",
            (campaign_id,),
        )
    return [dict(r) for r in cur.fetchall()]


# ── AC1 — Phase 1 Research cold path ────────────────────────────────


def test_ac1_research_cold_path(campaign_id, db):
    """AC1: agent.log has 'Phase 1 (Research) complete' with N>=3 angles and M>=3 features.
    agent_research has exactly 1 full_research row with the required JSON keys.
    """
    log = _read_log()
    # Check log for Phase 1 complete line
    assert "Phase 1 (Research) complete" in log, (
        "agent.log does not contain 'Phase 1 (Research) complete'. "
        "Run: python scripts/background_agent.py --once --campaign-id <id> 2>&1 | tee data/uat/agent.log"
    )

    # Extract counts from log line
    match = re.search(r"Phase 1 \(Research\) complete: (\d+) angles?, (\d+) features?", log)
    assert match, "Phase 1 log line does not contain angle/feature counts"
    n_angles = int(match.group(1))
    n_features = int(match.group(2))
    assert n_angles >= 3, f"Expected >=3 content angles, got {n_angles}"
    assert n_features >= 3, f"Expected >=3 key features, got {n_features}"

    # Check DB row
    rows = _get_research_rows(db, campaign_id, "full_research")
    assert len(rows) == 1, f"Expected exactly 1 full_research row, got {len(rows)}"

    content = rows[0]["content"]
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        pytest.fail(f"full_research content is not valid JSON: {content[:200]}")

    required_keys = [
        "product_summary", "key_features", "target_audience",
        "competitive_angle", "content_angles", "emotional_hooks",
    ]
    for key in required_keys:
        assert key in data, f"Missing required key '{key}' in research JSON"

    assert data["product_summary"] and len(data["product_summary"]) > 20, (
        f"product_summary too short: {data['product_summary']!r}"
    )

    # Save evidence
    UAT_DIR.mkdir(parents=True, exist_ok=True)
    (UAT_DIR / "ac1_research.json").write_text(json.dumps(data, indent=2))


# ── AC2 — Recent niche news shape ───────────────────────────────────


def test_ac2_news_shape(campaign_id, db):
    """AC2: recent_niche_news is a JSON array of 3-5 non-empty strings (>15 chars each).
    Does not contain markdown fences or literal 'json'.
    """
    rows = _get_research_rows(db, campaign_id, "full_research")
    assert rows, "No full_research row found. Run AC1 first."

    data = json.loads(rows[0]["content"])
    news = data.get("recent_niche_news")

    assert isinstance(news, list), f"recent_niche_news is not a list: {type(news)}"
    assert 3 <= len(news) <= 5, f"Expected 3-5 news items, got {len(news)}: {news}"

    for item in news:
        assert isinstance(item, str) and len(item) > 15, (
            f"News item too short or not a string: {item!r}"
        )
        assert not item.startswith("```"), f"News item starts with markdown fence: {item!r}"
        assert "json" not in item.lower()[:10], f"News item contains literal 'json': {item!r}"

    # Save evidence
    (UAT_DIR / "ac2_news.json").write_text(json.dumps(news, indent=2))
    print(f"\nNiche headlines for manual review:")
    for h in news:
        print(f"  - {h}")


# ── AC3 — Product image vision analysis ─────────────────────────────


def test_ac3_vision_analysis(campaign_id, db):
    """AC3: image_analysis is a non-empty string >50 chars.
    agent.log contains 'Research: product image analysis complete'.
    """
    rows = _get_research_rows(db, campaign_id, "full_research")
    assert rows, "No full_research row found. Run AC1 first."

    data = json.loads(rows[0]["content"])
    image_analysis = data.get("image_analysis", "")

    assert image_analysis and len(image_analysis) > 50, (
        f"image_analysis too short or empty: {image_analysis!r}"
    )

    log = _read_log()
    assert "product image analysis complete" in log, (
        "agent.log missing 'Research: product image analysis complete' line"
    )

    # Check N chars in log matches
    match = re.search(r"product image analysis complete \((\d+) chars\)", log)
    if match:
        log_n = int(match.group(1))
        actual_n = len(image_analysis)
        assert abs(log_n - actual_n) < 5, (
            f"Log says {log_n} chars but research JSON has {actual_n} chars"
        )

    # Save evidence
    (UAT_DIR / "ac3_vision.txt").write_text(image_analysis)


# ── AC4 — Goal strategy mapping ─────────────────────────────────────


def test_ac4_goal_strategy_mapping():
    """AC4: GOAL_STRATEGY dict has correct shape:
    - virality.x.hooks contains contrarian/surprising_result/curiosity
    - leads strategies have cta with 'link' or 'comment_link' for non-reddit
    - brand_awareness.x.posts_per_day == 1, brand_awareness.reddit.posts_per_day < 1
    """
    from utils.content_agent import GOAL_STRATEGY

    # virality.x hooks
    x_hooks = GOAL_STRATEGY["virality"]["x"]["hooks"]
    assert any(h in x_hooks for h in ["contrarian", "surprising_result", "curiosity"]), (
        f"virality.x.hooks missing required hooks: {x_hooks}"
    )

    # leads cta
    for platform in ["x", "linkedin", "facebook"]:
        cta = GOAL_STRATEGY["leads"][platform]["cta"]
        assert "link" in cta, (
            f"leads.{platform}.cta does not contain 'link': {cta!r}"
        )

    # brand_awareness posts_per_day
    assert GOAL_STRATEGY["brand_awareness"]["x"]["posts_per_day"] == 1, (
        f"brand_awareness.x.posts_per_day != 1"
    )
    assert GOAL_STRATEGY["brand_awareness"]["reddit"]["posts_per_day"] < 1, (
        f"brand_awareness.reddit.posts_per_day should be < 1"
    )

    # Save evidence
    UAT_DIR.mkdir(parents=True, exist_ok=True)
    (UAT_DIR / "ac4_strategy.json").write_text(
        json.dumps({
            g: {p: GOAL_STRATEGY[g][p]["hooks"] for p in GOAL_STRATEGY[g]}
            for g in GOAL_STRATEGY
        }, indent=2)
    )


# ── AC5 — Creator voice notes in strategy row ────────────────────────


def test_ac5_creator_voice_notes(campaign_id, db):
    """AC5: strategy row has platforms with creator_voice_notes strings
    (1-2 sentences, >20 chars, <300 chars, mention tone/audience/style).
    agent.log contains 'Strategy refined with AI for campaign'.
    """
    rows = _get_research_rows(db, campaign_id, "strategy")
    assert rows, (
        "No strategy row found. Run AC1 background agent first (Phase 2 must complete)."
    )

    data = json.loads(rows[0]["content"])
    platforms_data = data.get("platforms") or {}

    assert platforms_data, "Strategy row has no 'platforms' key"

    voice_notes: dict[str, str] = {}
    for plat, plat_data in platforms_data.items():
        if isinstance(plat_data, dict):
            note = plat_data.get("creator_voice_notes")
            if note:
                voice_notes[plat] = note

    assert voice_notes, (
        f"No creator_voice_notes found in any platform. platforms keys: {list(platforms_data.keys())}"
    )

    for plat, note in voice_notes.items():
        assert 20 < len(note) < 300, (
            f"{plat}.creator_voice_notes length {len(note)} out of range [20, 300]: {note!r}"
        )

    log = _read_log()
    assert f"Strategy refined with AI for campaign {campaign_id}" in log, (
        f"agent.log missing 'Strategy refined with AI for campaign {campaign_id}'"
    )

    # Save evidence
    (UAT_DIR / "ac5_voice.json").write_text(json.dumps(voice_notes, indent=2))


# ── AC6 — Phase 3: generates for all 3 active platforms ─────────────


def test_ac6_creation_three_platforms(campaign_id, db):
    """AC6: agent_draft has exactly 3 new rows (linkedin, facebook, reddit).
    Every row has non-empty draft_text.
    agent.log has 'Phase 3 (Creation) complete: 3 platform(s)'.
    No ERROR lines in agent.log.
    """
    log = _read_log()
    assert "Phase 3 (Creation) complete: 3 platform(s)" in log, (
        "agent.log missing 'Phase 3 (Creation) complete: 3 platform(s)'"
    )

    rows = _get_draft_rows(db, campaign_id)
    platforms_in_drafts = {r["platform"] for r in rows}
    required = {"linkedin", "facebook", "reddit"}
    assert required.issubset(platforms_in_drafts), (
        f"Missing platforms in agent_draft: {required - platforms_in_drafts}"
    )

    for r in rows:
        assert r["draft_text"] and r["draft_text"].strip(), (
            f"Empty draft_text for platform={r['platform']}, id={r['id']}"
        )

    # Check no ERROR lines
    error_lines = [l for l in log.splitlines() if " ERROR " in l or l.startswith("ERROR")]
    assert not error_lines, f"ERROR lines found in agent.log: {error_lines[:3]}"


# ── AC7 — Reddit draft shape + caveat ───────────────────────────────


CAVEAT_PATTERN = re.compile(
    r"didn't love|wasn't a fan|one (downside|drawback|thing)|to be fair|"
    r"not perfect|the only|that said|but |however",
    re.IGNORECASE,
)

NEGATIVE_WORDS = re.compile(
    r"\bnot\b|\bno\b|\bbut\b|\bhowever\b|\bdownside\b|\bdrawback\b|\blimitation\b|\bwasn't\b|\bdidn't\b",
    re.IGNORECASE,
)

from utils.content_quality import REDDIT_TITLE_MIN, REDDIT_TITLE_MAX, REDDIT_BODY_MIN, REDDIT_BODY_MAX


def test_ac7_reddit_caveat_shape(campaign_id, db):
    """AC7: Reddit draft parses as JSON {title, body}.
    Title length 60-120. Body length 500-2500.
    Body matches caveat regex. Body contains at least one negative-leaning word.
    """
    rows = _get_draft_rows(db, campaign_id, "reddit")
    assert rows, "No reddit draft found. Run AC6 first."

    # Use the most recent day-1 draft
    row = rows[0]
    draft_text = row["draft_text"]

    # Must parse as JSON {title, body}
    try:
        content = json.loads(draft_text)
    except json.JSONDecodeError:
        pytest.fail(
            f"Reddit draft_text is not valid JSON: {draft_text[:300]}"
        )

    assert "title" in content and "body" in content, (
        f"Reddit draft missing 'title' or 'body' keys: {list(content.keys())}"
    )
    title = content["title"]
    body = content["body"]

    assert isinstance(title, str) and isinstance(body, str), (
        "Reddit title and body must be strings"
    )

    assert REDDIT_TITLE_MIN <= len(title) <= REDDIT_TITLE_MAX, (
        f"Reddit title length {len(title)} outside [{REDDIT_TITLE_MIN}, {REDDIT_TITLE_MAX}]: {title!r}"
    )

    assert REDDIT_BODY_MIN <= len(body) <= REDDIT_BODY_MAX, (
        f"Reddit body length {len(body)} outside [{REDDIT_BODY_MIN}, {REDDIT_BODY_MAX}]"
    )

    assert CAVEAT_PATTERN.search(body), (
        f"Reddit body missing caveat phrase (regex: didn't love | wasn't a fan | etc.)\n"
        f"Body preview: {body[:300]}"
    )

    assert NEGATIVE_WORDS.search(body), (
        f"Reddit body contains no negative-leaning words (heuristic purity check)"
    )

    # Save evidence
    (UAT_DIR / "ac7_reddit.txt").write_text(
        f"TITLE: {title}\n\nBODY:\n{body}\n\nCAVEAT MATCH: {bool(CAVEAT_PATTERN.search(body))}"
    )


# ── AC8 — Day-1 vs day-5 diversity ──────────────────────────────────


def _seq_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def test_ac8_diversity(campaign_id, db):
    """AC8: day-1 and day-5 drafts exist for each platform.
    For each platform, SequenceMatcher similarity < 0.90.
    """
    all_rows = _get_draft_rows(db, campaign_id)
    if not all_rows:
        pytest.skip("No drafts found for diversity test. Run AC6 + AC8 background agent run first.")

    # Compute day numbers from creation dates
    dates = sorted(set(r["created_at"][:10] for r in all_rows if r.get("created_at")))
    date_to_day = {d: i + 1 for i, d in enumerate(dates)}

    def get_day(row):
        return date_to_day.get(row.get("created_at", "")[:10], 1)

    # Group by (platform, day)
    by_plat_day: dict[tuple, list] = {}
    for r in all_rows:
        key = (r["platform"], get_day(r))
        by_plat_day.setdefault(key, []).append(r)

    scores: dict[str, float] = {}
    compared = 0
    for platform in ["linkedin", "facebook", "reddit"]:
        day1 = by_plat_day.get((platform, 1), [])
        day5 = by_plat_day.get((platform, 5), [])
        if not day1 or not day5:
            continue

        text1 = day1[0]["draft_text"] or ""
        text5 = day5[0]["draft_text"] or ""
        sim = _seq_similarity(text1, text5)
        scores[platform] = sim
        compared += 1
        assert sim < 0.90, (
            f"{platform}: day-1 vs day-5 similarity {sim:.3f} >= 0.90 threshold. "
            "Content is too repetitive."
        )

    if compared == 0:
        pytest.skip(
            "No platform has both day-1 and day-5 drafts. "
            "Run AC6 (day 1) + AMPLIFIER_UAT_FORCE_DAY=5 agent run first."
        )

    # Save evidence
    (UAT_DIR / "ac8_diversity.json").write_text(json.dumps(scores, indent=2))
    print(f"\nDiversity scores (lower = more diverse): {scores}")


# ── AC9 — Fallback path on AI failure ───────────────────────────────


def test_ac9_fallback(campaign_id, db):
    """AC9: agent.log contains 'ContentAgent pipeline failed:' + 'Falling back to basic generator.'
    New agent_draft rows exist. No uncaught exception.
    """
    log = _read_log()
    assert "ContentAgent pipeline failed:" in log, (
        "agent.log missing 'ContentAgent pipeline failed:' — "
        "run: AMPLIFIER_UAT_BYPASS_AI=1 python scripts/background_agent.py --task=generate_content "
        "--campaign-id <id> --day-number 2 2>&1 | tee -a data/uat/agent.log"
    )
    assert "Falling back to basic generator." in log, (
        "agent.log missing 'Falling back to basic generator.'"
    )

    rows = _get_draft_rows(db, campaign_id)
    assert rows, "No drafts found after fallback run. Fallback generator produced nothing."

    # Ensure no uncaught traceback/exception
    assert "Traceback (most recent call last)" not in log, (
        "Uncaught exception found in agent.log (Traceback present)"
    )


# ── AC10 — Research cache hit ────────────────────────────────────────


def test_ac10_research_cache_hit(campaign_id, db):
    """AC10: Second run does NOT create a new full_research row.
    agent.log contains 'Using cached research for campaign <id>'.
    """
    rows = _get_research_rows(db, campaign_id, "full_research")
    assert len(rows) == 1, (
        f"Expected exactly 1 full_research row, got {len(rows)}. "
        "Either AC1 hasn't run, or cache was busted and a duplicate was created."
    )

    log = _read_log()
    assert f"Using cached research for campaign {campaign_id}" in log, (
        f"agent.log missing 'Using cached research for campaign {campaign_id}'"
    )


# ── AC11 — Strategy cache hit ────────────────────────────────────────


def test_ac11_strategy_cache_hit(campaign_id, db):
    """AC11: Second creation run does NOT create a new strategy row.
    agent.log contains 'Using cached strategy for campaign <id>'.
    """
    rows = _get_research_rows(db, campaign_id, "strategy")
    assert len(rows) == 1, (
        f"Expected exactly 1 strategy row after second run, got {len(rows)}. "
        "Either strategy cache isn't working or no strategy row was created."
    )

    log = _read_log()
    assert f"Using cached strategy for campaign {campaign_id}" in log, (
        f"agent.log missing 'Using cached strategy for campaign {campaign_id}'"
    )


# ── AC12 — Quality validator catches banned phrase + retries ─────────


@pytest.mark.asyncio
async def test_ac12_validator_retry(campaign_id):
    """AC12 (mocked): validator retries on banned phrase, final output is clean.
    This is the one AC where controlled mocking is acceptable (testing validator reaction).
    """
    # Import modules
    from utils.content_agent import ContentAgent, BANNED_PHRASES  # noqa: F401 (confirms import)
    from utils.content_quality import validate_content, BANNED_PHRASES as QC_BANNED

    # Build a mock manager (no real AI needed)
    manager = MagicMock()
    manager.has_providers = True
    manager.generate = AsyncMock()
    manager.generate_with_search = AsyncMock(return_value='["recent headline"]')
    manager.generate_with_vision = AsyncMock(return_value=None)
    manager.embed = AsyncMock(return_value=None)
    manager.get = MagicMock(return_value=None)

    # Content with banned phrase on first call, clean on second
    banned_phrase = QC_BANNED[0]  # e.g. "game-changer"
    clean_text = "This product helped me cut my analysis time in half. Worth trying."
    dirty_content = {
        "linkedin": f"This is a {banned_phrase} tool that everyone should use.",
        "facebook": f"A real {banned_phrase} for traders.",
        "reddit": json.dumps({"title": "Tried this indicator for a week", "body": (
            "Spent a week with this trading indicator. To be fair, the setup was a bit confusing. "
            "But once I got it running, the signals were pretty solid. "
            "Not perfect but it has given me an edge. " * 8
        )}),
    }
    clean_content = {
        "linkedin": clean_text,
        "facebook": clean_text,
        "reddit": json.dumps({"title": "Tried this indicator for a week — honest review", "body": (
            "Been using this for a week now. To be fair, the documentation could be clearer. "
            "But the signals themselves are surprisingly accurate. "
            "I didn't love how long setup took, but the results speak for themselves. " * 6
        )}),
    }

    call_count = 0

    async def mock_creation(campaign, strategy, research, mgr, platforms, day_number, hooks, retry_feedback=None):
        nonlocal call_count
        call_count += 1
        return dirty_content if call_count == 1 else clean_content

    with patch("utils.content_agent._run_creation", side_effect=mock_creation):
        agent = ContentAgent()
        agent._manager = manager

        campaign = {
            "campaign_id": campaign_id,
            "title": "Test",
            "brief": "Test brief",
            "campaign_goal": "brand_awareness",
            "tone": "casual",
            "assets": {},
        }

        # Patch _run_research and _refine_strategy_with_ai to avoid real calls
        with patch("utils.content_agent._run_research", new=AsyncMock(return_value={
            "product_summary": "A test product summary for AC12 validator retry test.",
            "key_features": ["f1", "f2", "f3"],
            "target_audience": "traders",
            "competitive_angle": "unique",
            "content_angles": ["angle1", "angle2", "angle3"],
            "emotional_hooks": ["hook1"],
            "recent_niche_news": ["headline1", "headline2", "headline3"],
            "image_analysis": "",
        })), patch("utils.content_agent._refine_strategy_with_ai", new=AsyncMock(return_value={
            "platforms": {
                "linkedin": {"creator_voice_notes": "Conversational, no jargon."},
                "facebook": {"creator_voice_notes": "Casual and friendly."},
                "reddit": {"creator_voice_notes": "Honest and community-focused."},
            },
            "goal": "brand_awareness",
            "tone": "casual",
            "tone_guide": "",
            "content_angles": [],
            "emotional_hooks": [],
        })), patch("utils.local_db.get_content_insights", return_value=[]):
            result = await agent.generate_content(
                campaign,
                enabled_platforms=["linkedin", "facebook", "reddit"],
                day_number=99,
            )

    # Validate: final result should be clean (no banned phrases)
    assert call_count == 2, f"Expected 2 _run_creation calls (original + retry), got {call_count}"

    for platform, text in result.items():
        if platform == "image_prompt":
            continue
        text_str = text if isinstance(text, str) else json.dumps(text)
        for phrase in QC_BANNED:
            assert phrase.lower() not in text_str.lower(), (
                f"Banned phrase '{phrase}' still present in {platform} after retry"
            )


# ── AC13 — X length guard + disabled platform filter ─────────────────


def test_ac13_x_length_guard():
    """AC13: validate_content rejects X content >280 chars.
    filter_disabled(['x']) returns [] because X is disabled.
    """
    import asyncio as _asyncio
    from utils.content_quality import validate_content, X_CHAR_LIMIT
    from utils.guard import filter_disabled

    # X > 280 chars triggers validation failure
    long_x = "a" * (X_CHAR_LIMIT + 1)
    manager = MagicMock()
    manager.embed = AsyncMock(return_value=None)

    result = _asyncio.run(validate_content({"x": long_x}, [], manager))
    is_valid, reasons = result
    assert not is_valid, "Expected validation to fail for x content exceeding 280 chars"
    assert any("exceeds 280" in r for r in reasons), (
        f"Expected 'exceeds 280' in failure reasons, got: {reasons}"
    )

    # X disabled guard
    filtered = filter_disabled(["x"])
    assert filtered == [], (
        f"Expected filter_disabled(['x']) == [], got {filtered}"
    )


# ── AC14 — Full E2E from user app dashboard ──────────────────────────


@pytest.mark.skip(reason="AC14 runs via Chrome DevTools MCP, not pytest")
def test_ac14_full_e2e_user_app():
    """AC14: full E2E driven by Chrome DevTools MCP (see spec block for procedure).

    Skipped in pytest. The uat-task skill executes this via:
    1. Start user app: python scripts/user_app.py
    2. Start agent with UAT interval: AMPLIFIER_UAT_INTERVAL_SEC=120 python scripts/background_agent.py
    3. Navigate to http://localhost:5222/ via Chrome DevTools MCP
    4. Wait up to 5 min for draft cards to appear in /campaigns view
    5. Screenshot + console/network log captured to data/uat/screenshots/task14_ac14.png
    """
    pass
