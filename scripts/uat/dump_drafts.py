"""UAT helper: pull agent_draft rows by platform/day for a campaign.

Usage:
    python scripts/uat/dump_drafts.py --campaign-id 42 --platform linkedin
    python scripts/uat/dump_drafts.py --campaign-id 42 --platform all
    python scripts/uat/dump_drafts.py --campaign-id 42 --platform reddit --day 1

Output is a JSON array to stdout. Each element:
    {
        "id": int,
        "platform": str,
        "draft_text": str,
        "image_path": str | null,
        "created_at": str,
        "day_number_inferred": int   # date offset from first draft for this campaign
    }

Errors go to stderr.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "local.db"

PLATFORMS = ["linkedin", "facebook", "reddit", "x", "tiktok", "instagram"]


def _infer_day_numbers(rows: list[dict]) -> dict[str, int]:
    """Return {created_at_date: day_number} mapping based on first draft date."""
    dates = sorted(set(r["created_at"][:10] for r in rows if r.get("created_at")))
    return {date: idx + 1 for idx, date in enumerate(dates)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump agent_draft rows for a campaign to JSON."
    )
    parser.add_argument("--campaign-id", type=int, required=True, help="Campaign ID.")
    parser.add_argument(
        "--platform",
        required=True,
        choices=PLATFORMS + ["all"],
        help="Platform to filter by, or 'all' for every platform.",
    )
    parser.add_argument(
        "--day",
        type=int,
        default=None,
        help="Filter to drafts from day N (inferred from creation order).",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Error: database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        if args.platform == "all":
            cur = conn.execute(
                "SELECT id, campaign_id, platform, draft_text, image_path, created_at "
                "FROM agent_draft WHERE campaign_id = ? ORDER BY created_at ASC",
                (args.campaign_id,),
            )
        else:
            cur = conn.execute(
                "SELECT id, campaign_id, platform, draft_text, image_path, created_at "
                "FROM agent_draft WHERE campaign_id = ? AND platform = ? ORDER BY created_at ASC",
                (args.campaign_id, args.platform),
            )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    if not rows:
        print(json.dumps([]))
        return

    # Compute day_number_inferred across all drafts for this campaign (all platforms)
    # Need all-platform rows to compute date offsets correctly
    conn2 = sqlite3.connect(str(DB_PATH))
    conn2.row_factory = sqlite3.Row
    try:
        all_cur = conn2.execute(
            "SELECT created_at FROM agent_draft WHERE campaign_id = ? ORDER BY created_at ASC",
            (args.campaign_id,),
        )
        all_rows = [dict(r) for r in all_cur.fetchall()]
    finally:
        conn2.close()

    day_map = _infer_day_numbers(all_rows)

    result = []
    for r in rows:
        date = r.get("created_at", "")[:10]
        day_num = day_map.get(date, 1)
        result.append({
            "id": r["id"],
            "platform": r["platform"],
            "draft_text": r["draft_text"],
            "image_path": r.get("image_path"),
            "created_at": r["created_at"],
            "day_number_inferred": day_num,
        })

    # Filter by --day if provided
    if args.day is not None:
        result = [r for r in result if r["day_number_inferred"] == args.day]

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
