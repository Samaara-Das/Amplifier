"""UAT helper: pull a specific field from cached research JSON for a campaign.

Usage:
    python scripts/uat/dump_research.py --campaign-id 42 --field recent_niche_news
    python scripts/uat/dump_research.py --campaign-id 42 --field image_analysis
    python scripts/uat/dump_research.py --campaign-id 42 --field strategy_voice_notes
    python scripts/uat/dump_research.py --campaign-id 42 --field full_research

Special fields:
  full_research        — return the entire JSON object from the full_research row
  strategy_voice_notes — extract creator_voice_notes from the strategy row
                         (returns {platform: voice_note_string, ...})
  <any key>            — top-level key from the full_research JSON

Outputs valid JSON to stdout. Errors go to stderr.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "local.db"

KNOWN_FIELDS = [
    "recent_niche_news",
    "image_analysis",
    "strategy_voice_notes",
    "full_research",
    "product_summary",
    "key_features",
    "target_audience",
    "competitive_angle",
    "content_angles",
    "emotional_hooks",
    "scraped_content",
]


def _load_db_row(campaign_id: int, research_type: str) -> dict | None:
    """Return parsed JSON content of the newest row with given research_type."""
    if not DB_PATH.exists():
        print(f"Error: database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT content FROM agent_research "
            "WHERE campaign_id = ? AND research_type = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (campaign_id, research_type),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return json.loads(row["content"])
    except (json.JSONDecodeError, TypeError):
        return {"raw": row["content"]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump a research field from local agent_research cache."
    )
    parser.add_argument("--campaign-id", type=int, required=True, help="Campaign ID.")
    parser.add_argument(
        "--field",
        required=True,
        help=(
            "Field name to dump. Special values: full_research (whole JSON), "
            "strategy_voice_notes (per-platform voice notes from strategy row). "
            "Any top-level key from the full_research JSON also works."
        ),
    )
    args = parser.parse_args()

    field = args.field

    # ── strategy_voice_notes: pull from strategy row ─────────────────
    if field == "strategy_voice_notes":
        data = _load_db_row(args.campaign_id, "strategy")
        if data is None:
            print(
                f"Error: no strategy row found for campaign_id={args.campaign_id}. "
                "Run the background agent first (Phase 2 must complete).",
                file=sys.stderr,
            )
            sys.exit(1)
        platforms_data = data.get("platforms") or {}
        voice_notes: dict = {}
        for plat, plat_data in platforms_data.items():
            if isinstance(plat_data, dict):
                notes = plat_data.get("creator_voice_notes")
                if notes:
                    voice_notes[plat] = notes
        print(json.dumps(voice_notes, indent=2))
        return

    # ── full_research: return entire JSON ────────────────────────────
    if field == "full_research":
        data = _load_db_row(args.campaign_id, "full_research")
        if data is None:
            print(
                f"Error: no full_research row found for campaign_id={args.campaign_id}.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(json.dumps(data, indent=2))
        return

    # ── any top-level key from full_research ─────────────────────────
    data = _load_db_row(args.campaign_id, "full_research")
    if data is None:
        print(
            f"Error: no full_research row found for campaign_id={args.campaign_id}.",
            file=sys.stderr,
        )
        sys.exit(1)
    if field not in data:
        print(
            f"Error: field '{field}' not found in research JSON. "
            f"Available keys: {list(data.keys())}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(json.dumps(data[field], indent=2))


if __name__ == "__main__":
    main()
