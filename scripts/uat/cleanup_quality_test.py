"""UAT helper: cancel all 8 Task #15 quality-gate fixture campaigns.

Sets each to status=cancelled on the server. Refuses to touch any campaign
whose title does not start with "UAT-15 " — safety guard against accidentally
voiding real campaigns.

Usage:
    python scripts/uat/cleanup_quality_test.py \
        --ids data/uat/quality_campaign_ids.json

    Or pass individual IDs:
    python scripts/uat/cleanup_quality_test.py --id 42 43 44

Exit codes:
    0 — all campaigns cancelled (or already cancelled)
    1 — safety violation (title doesn't start with "UAT-15 ")
    2 — server error or auth failure

Reads auth credentials from config/.env:
    UAT_TEST_COMPANY_EMAIL, UAT_TEST_COMPANY_PASSWORD
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SERVER_URL = "https://api.pointcapitalis.com"

UAT_PREFIX = "UAT-15 "


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


def _get_campaign(client: httpx.Client, headers: dict, server: str, campaign_id: int) -> dict | None:
    resp = client.get(f"{server}/api/company/campaigns/{campaign_id}", headers=headers, timeout=15.0)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        print(f"  GET campaign {campaign_id} failed: {resp.status_code} {resp.text}", file=sys.stderr)
        return None
    return resp.json()


def _cancel_campaign(client: httpx.Client, headers: dict, server: str, campaign_id: int) -> bool:
    """Set campaign status to cancelled. Returns True on success."""
    resp = client.patch(
        f"{server}/api/company/campaigns/{campaign_id}",
        headers=headers,
        json={"status": "cancelled"},
        timeout=15.0,
    )
    if resp.status_code in (200, 204):
        return True
    # Try the status endpoint as fallback (web form path)
    resp2 = client.post(
        f"{server}/company/campaigns/{campaign_id}/status",
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
        data={"new_status": "cancelled"},
        timeout=15.0,
    )
    if resp2.status_code in (200, 302, 303):
        return True
    print(
        f"  Cancel failed for campaign {campaign_id}: "
        f"PATCH {resp.status_code}, POST {resp2.status_code}",
        file=sys.stderr,
    )
    return False


def _cleanup_campaign(
    client: httpx.Client,
    headers: dict,
    server: str,
    campaign_id: int,
    allowed_ids: set[int] | None = None,
) -> bool:
    """Fetch, safety-check, and cancel one campaign. Returns True on success.

    Safety guard: a campaign is allowed if its title starts with UAT_PREFIX
    OR its id is in allowed_ids (i.e. listed in the output JSON file).
    Either signal is sufficient proof of UAT origin.
    """
    campaign = _get_campaign(client, headers, server, campaign_id)
    if campaign is None:
        print(f"  Campaign {campaign_id}: not found or already deleted — skipping")
        return True

    title = campaign.get("title", "")
    status = campaign.get("status", "")

    # Safety guard — allow if title starts with prefix OR id is in the known-UAT set
    id_in_output = allowed_ids is not None and campaign_id in allowed_ids
    if not title.startswith(UAT_PREFIX) and not id_in_output:
        print(
            f"SAFETY VIOLATION: Campaign {campaign_id} title '{title}' does not start with "
            f"'{UAT_PREFIX}' and is not in the output IDs file. Refusing to cancel.",
            file=sys.stderr,
        )
        sys.exit(1)

    if status == "cancelled":
        print(f"  Campaign {campaign_id} ('{title}'): already cancelled — skipping")
        return True

    ok = _cancel_campaign(client, headers, server, campaign_id)
    if ok:
        print(f"  Campaign {campaign_id} ('{title}'): cancelled successfully")
    else:
        print(f"  Campaign {campaign_id} ('{title}'): cancel FAILED", file=sys.stderr)
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cancel all Task #15 quality-gate UAT fixture campaigns."
    )
    parser.add_argument(
        "--ids",
        default=None,
        help="JSON file with campaign IDs (default: data/uat/quality_campaign_ids.json)",
    )
    parser.add_argument(
        "--id",
        nargs="+",
        type=int,
        dest="explicit_ids",
        default=None,
        help="Explicit campaign IDs to cancel (overrides --ids)",
    )
    args = parser.parse_args()

    env = _load_env()
    company_email = env.get("UAT_TEST_COMPANY_EMAIL") or os.environ.get("UAT_TEST_COMPANY_EMAIL", "")
    company_pw = env.get("UAT_TEST_COMPANY_PASSWORD") or os.environ.get("UAT_TEST_COMPANY_PASSWORD", "")
    server_url = (
        env.get("CAMPAIGN_SERVER_URL") or os.environ.get("CAMPAIGN_SERVER_URL") or SERVER_URL
    ).rstrip("/")

    if not company_email or not company_pw:
        print(
            "Missing UAT_TEST_COMPANY_EMAIL or UAT_TEST_COMPANY_PASSWORD in config/.env",
            file=sys.stderr,
        )
        sys.exit(2)

    # Resolve campaign IDs
    allowed_ids: set[int] | None = None
    if args.explicit_ids:
        campaign_ids = args.explicit_ids
    else:
        ids_file = Path(args.ids) if args.ids else ROOT / "data" / "uat" / "quality_campaign_ids.json"
        if not ids_file.exists():
            print(f"IDs file not found: {ids_file}", file=sys.stderr)
            sys.exit(2)
        with open(ids_file, encoding="utf-8") as f:
            ids_map = json.load(f)
        campaign_ids = list(ids_map.values())
        allowed_ids = set(campaign_ids)

    print(f"Cancelling {len(campaign_ids)} campaign(s) on {server_url}...")

    with httpx.Client(timeout=30.0) as client:
        token = _login_company(client, company_email, company_pw, server_url)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        success_count = 0
        for cid in campaign_ids:
            ok = _cleanup_campaign(client, headers, server_url, cid, allowed_ids=allowed_ids)
            if ok:
                success_count += 1

    print(f"\nDone: {success_count}/{len(campaign_ids)} campaigns cancelled.")
    if success_count < len(campaign_ids):
        sys.exit(2)


if __name__ == "__main__":
    main()
