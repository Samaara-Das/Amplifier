"""UAT helper: set a UAT campaign to 'completed' on the server and delete local data.

Usage:
    python scripts/uat/cleanup_campaign.py --id 42

Safety: refuses if campaign title does not start with "UAT " (case-sensitive, space-suffixed).
This prevents accidentally voiding a real campaign.

Exit codes:
    0 — success
    1 — safety violation (title doesn't start with "UAT ")
    2 — server error or auth failure

Reads auth credentials from config/.env:
    UAT_TEST_COMPANY_EMAIL, UAT_TEST_COMPANY_PASSWORD
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SERVER_URL = "https://api.pointcapitalis.com"


def _load_env() -> dict:
    env: dict = {}
    env_file = ROOT / "config" / ".env"
    if not env_file.exists():
        return env
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _login_company(client: httpx.Client, email: str, password: str, server: str) -> str:
    resp = client.post(
        f"{server}/api/auth/company/login",
        json={"email": email, "password": password},
    )
    if resp.status_code != 200:
        print(f"Company login failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(2)
    return resp.json()["access_token"]


def _delete_local(campaign_id: int) -> dict[str, int]:
    """Delete local DB rows for this campaign. Returns {table: count} deleted."""
    db_path = ROOT / "data" / "local.db"
    if not db_path.exists():
        return {}
    tables = {
        "agent_draft": "campaign_id",
        "agent_research": "campaign_id",
        "post_schedule": "campaign_id",
    }
    counts: dict[str, int] = {}
    conn = sqlite3.connect(str(db_path))
    try:
        for table, col in tables.items():
            cur = conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            if not cur.fetchone():
                counts[table] = 0
                continue
            cur = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (campaign_id,))
            counts[table] = cur.fetchone()[0]
            conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (campaign_id,))
        conn.commit()
    finally:
        conn.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mark a UAT campaign as completed on server + delete local data."
    )
    parser.add_argument(
        "--id",
        type=int,
        required=True,
        help="Campaign ID to clean up.",
    )
    args = parser.parse_args()

    env = _load_env()
    company_email = env.get("UAT_TEST_COMPANY_EMAIL") or os.environ.get("UAT_TEST_COMPANY_EMAIL", "")
    company_pw = env.get("UAT_TEST_COMPANY_PASSWORD") or os.environ.get("UAT_TEST_COMPANY_PASSWORD", "")
    server_url = env.get("CAMPAIGN_SERVER_URL") or os.environ.get("CAMPAIGN_SERVER_URL", SERVER_URL)
    server_url = server_url.rstrip("/")

    if not company_email or not company_pw:
        print(
            "UAT test creds not in config/.env — add UAT_TEST_COMPANY_EMAIL and "
            "UAT_TEST_COMPANY_PASSWORD, then re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    with httpx.Client(timeout=30.0) as client:
        # Login
        token = _login_company(client, company_email, company_pw, server_url)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Fetch campaign to check title
        resp = client.get(
            f"{server_url}/api/company/campaigns/{args.id}",
            headers=headers,
        )
        if resp.status_code == 404:
            print(f"Error: campaign {args.id} not found on server.", file=sys.stderr)
            sys.exit(2)
        if resp.status_code != 200:
            print(f"Error fetching campaign: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(2)

        campaign = resp.json()
        title = campaign.get("title", "")

        # Safety check
        if not title.startswith("UAT "):
            print(
                f"Safety violation: campaign title {title!r} does not start with 'UAT '. "
                "Refusing to modify a non-UAT campaign.",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Campaign {args.id}: {title!r} (status={campaign.get('status')})")

        # Set status to completed
        resp = client.patch(
            f"{server_url}/api/company/campaigns/{args.id}",
            headers=headers,
            json={"status": "completed"},
        )
        if resp.status_code not in (200, 201):
            # completed may not be in valid_transitions; try cancelled instead
            resp2 = client.patch(
                f"{server_url}/api/company/campaigns/{args.id}",
                headers=headers,
                json={"status": "cancelled"},
            )
            if resp2.status_code not in (200, 201):
                print(
                    f"Error: could not set campaign to completed/cancelled: "
                    f"{resp.status_code} {resp.text}",
                    file=sys.stderr,
                )
                sys.exit(2)
            print(f"Campaign {args.id} set to: cancelled (completed not allowed from current status)")
        else:
            print(f"Campaign {args.id} set to: {resp.json().get('status')}")

    # Delete local data
    counts = _delete_local(args.id)
    if counts:
        print("Local data deleted:")
        for table, cnt in counts.items():
            print(f"  {table}: {cnt} row(s)")
    else:
        print("No local data found to delete.")

    print(f"\nCleanup complete for campaign {args.id}.")


if __name__ == "__main__":
    main()
