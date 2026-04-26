"""UAT helper: truncate agent_research, agent_draft, and post_schedule rows
for a single campaign in data/local.db.

Usage:
    python scripts/uat/reset_local_cache.py --campaign-id 42

Refuses to run without --campaign-id (no "delete all" option).
Prints row counts deleted from each table.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "local.db"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Truncate agent_research, agent_draft, post_schedule for a UAT campaign."
    )
    parser.add_argument(
        "--campaign-id",
        type=int,
        required=True,
        help="Campaign ID to clear (required — no bulk-delete option).",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Error: database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        tables = {
            "agent_research": "campaign_id",
            "agent_draft": "campaign_id",
            "post_schedule": "campaign_id",
        }
        totals: dict[str, int] = {}
        for table, col in tables.items():
            # Check table exists
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            if not cur.fetchone():
                totals[table] = 0
                print(f"  {table}: table not found, skipping")
                continue
            cur = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (args.campaign_id,))
            count = cur.fetchone()[0]
            conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (args.campaign_id,))
            totals[table] = count

        conn.commit()
    finally:
        conn.close()

    print(f"Reset local cache for campaign_id={args.campaign_id}:")
    for table, count in totals.items():
        print(f"  {table}: {count} row(s) deleted")


if __name__ == "__main__":
    main()
