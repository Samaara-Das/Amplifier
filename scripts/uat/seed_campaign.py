"""UAT helper: create a campaign on the live server and force-accept the invitation.

Usage:
    python scripts/uat/seed_campaign.py \\
        --title "UAT Trading Indicator 1234" \\
        --goal brand_awareness \\
        --tone casual \\
        --brief "Campaign brief text here." \\
        --guidance "Content guidance here." \\
        --company-urls "https://example.com" \\
        --product-images "data/uat/fixtures/product1.jpg" \\
        --output-id-to data/uat/last_campaign_id.txt

Reads auth credentials from config/.env:
    UAT_TEST_USER_EMAIL, UAT_TEST_USER_PASSWORD
    UAT_TEST_COMPANY_EMAIL, UAT_TEST_COMPANY_PASSWORD

Exits non-zero on any failure. Campaign title MUST start with "UAT ".
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SERVER_URL = "https://api.pointcapitalis.com"


def _load_env() -> dict:
    """Load key=value pairs from config/.env (subset — no dotenv dependency)."""
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


def _get_creds(env: dict) -> tuple[str, str, str, str]:
    """Return (user_email, user_pw, company_email, company_pw) or abort."""
    ue = env.get("UAT_TEST_USER_EMAIL") or os.environ.get("UAT_TEST_USER_EMAIL", "")
    up = env.get("UAT_TEST_USER_PASSWORD") or os.environ.get("UAT_TEST_USER_PASSWORD", "")
    ce = env.get("UAT_TEST_COMPANY_EMAIL") or os.environ.get("UAT_TEST_COMPANY_EMAIL", "")
    cp = env.get("UAT_TEST_COMPANY_PASSWORD") or os.environ.get("UAT_TEST_COMPANY_PASSWORD", "")
    missing = [k for k, v in [
        ("UAT_TEST_USER_EMAIL", ue), ("UAT_TEST_USER_PASSWORD", up),
        ("UAT_TEST_COMPANY_EMAIL", ce), ("UAT_TEST_COMPANY_PASSWORD", cp),
    ] if not v]
    if missing:
        print(
            f"UAT test creds not in config/.env — add them, then re-run.\n"
            f"Missing: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return ue, up, ce, cp


def _login(client: httpx.Client, email: str, password: str, kind: str, server: str = SERVER_URL) -> str:
    """Login as user or company; return JWT token."""
    path = "/api/auth/company/login" if kind == "company" else "/api/auth/login"
    resp = client.post(
        f"{server}{path}",
        json={"email": email, "password": password},
    )
    if resp.status_code != 200:
        print(f"Login failed for {kind} ({email}): {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(2)
    return resp.json()["access_token"]


def _build_campaign_payload(args: argparse.Namespace, image_urls: list[str]) -> dict:
    """Build the CampaignCreate payload."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    start = now.isoformat()
    end = (now + timedelta(days=30)).isoformat()

    assets: dict = {}
    if args.company_urls:
        assets["company_urls"] = [u.strip() for u in args.company_urls.split(",") if u.strip()]
    if image_urls:
        assets["image_urls"] = image_urls

    return {
        "title": args.title,
        "brief": args.brief,
        "content_guidance": args.guidance,
        "assets": assets,
        "budget_total": 150.0,  # Above $100 floor for full quality-gate score
        "payout_rules": {
            "rate_per_1k_impressions": 2.0,  # $2/1K to clear the "below average" rubric flag
            "rate_per_like": 0.02,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.0,
        },
        "targeting": {
            "min_followers": {},
            "min_engagement": 0.0,
            # niche_tags + required_platforms set so the quality gate counts the
            # campaign as "targeted." target_regions stays empty so the test
            # user's auto-detected region (any country) still matches.
            "niche_tags": ["trading", "finance", "investing"],
            "required_platforms": ["linkedin", "facebook", "reddit"],
            "target_regions": [],
        },
        "campaign_goal": args.goal,
        "tone": args.tone,
        "campaign_type": "ai_generated",
        "preferred_formats": {},
        "start_date": start,
        "end_date": end,
    }


def _upload_product_images(
    client: httpx.Client,
    company_token: str,
    image_paths: list[str],
    server: str = SERVER_URL,
) -> list[str]:
    """Upload product images to server storage; return list of image URLs.

    If a file doesn't exist locally, warns and skips (continues).
    Returns empty list if no images provided or upload not supported.
    """
    uploaded: list[str] = []
    headers = {"Authorization": f"Bearer {company_token}"}
    for path_str in image_paths:
        p = Path(path_str.strip())
        if not p.exists():
            print(f"Warning: product image not found, skipping: {p}", file=sys.stderr)
            continue
        try:
            with open(p, "rb") as f:
                resp = client.post(
                    f"{server}/api/storage/upload",
                    headers=headers,
                    files={"file": (p.name, f, "image/jpeg")},
                    timeout=30.0,
                )
            if resp.status_code in (200, 201):
                data = resp.json()
                url = data.get("url") or data.get("file_url") or data.get("path")
                if url:
                    uploaded.append(url)
                    print(f"Uploaded: {p.name} -> {url}")
            else:
                print(
                    f"Warning: image upload failed for {p.name}: "
                    f"{resp.status_code} {resp.text[:200]}",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"Warning: image upload error for {p.name}: {e}", file=sys.stderr)
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a UAT campaign on the live server and force-accept the invitation."
    )
    parser.add_argument("--title", required=True, help='Campaign title (must start with "UAT ")')
    parser.add_argument(
        "--goal",
        required=True,
        choices=["leads", "virality", "brand_awareness", "engagement"],
        help="Campaign goal",
    )
    parser.add_argument(
        "--tone",
        required=True,
        choices=["casual", "professional", "edgy", "educational", "humorous", "inspirational"],
        help="Content tone",
    )
    parser.add_argument("--brief", required=True, help="Campaign brief (product description)")
    parser.add_argument("--guidance", required=True, help="Content guidance for creators")
    parser.add_argument(
        "--company-urls",
        default="",
        help="Comma-separated company URLs (1-3) to include as assets",
    )
    parser.add_argument(
        "--product-images",
        default="",
        help="Comma-separated local file paths for product images to upload",
    )
    parser.add_argument(
        "--output-id-to",
        default="",
        help="Write the resulting campaign ID (plain int) to this file",
    )
    args = parser.parse_args()

    if not args.title.startswith("UAT "):
        print('Error: --title must start with "UAT " (uppercase, space-suffixed).', file=sys.stderr)
        sys.exit(1)

    env = _load_env()
    user_email, user_pw, company_email, company_pw = _get_creds(env)

    server_url = (env.get("CAMPAIGN_SERVER_URL") or os.environ.get("CAMPAIGN_SERVER_URL") or SERVER_URL).rstrip("/")

    with httpx.Client(timeout=30.0) as client:
        # 1. Company login
        print(f"Logging in as company: {company_email}")
        company_token = _login(client, company_email, company_pw, "company", server=server_url)
        company_headers = {"Authorization": f"Bearer {company_token}", "Content-Type": "application/json"}

        # 2. Upload product images (if any)
        image_urls: list[str] = []
        if args.product_images:
            paths = [p for p in args.product_images.split(",") if p.strip()]
            if paths:
                image_urls = _upload_product_images(client, company_token, paths, server=server_url)

        # 3. Create campaign
        payload = _build_campaign_payload(args, image_urls)
        print(f"Creating campaign: {args.title!r}")
        resp = client.post(
            f"{server_url}/api/company/campaigns",
            headers=company_headers,
            json=payload,
        )
        if resp.status_code not in (200, 201):
            print(f"Campaign creation failed: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(2)
        campaign = resp.json()
        campaign_id = campaign["id"]
        print(f"Campaign created: id={campaign_id}, status={campaign['status']}")

        # 4. Activate campaign (draft -> active)
        print(f"Activating campaign {campaign_id}...")
        resp = client.patch(
            f"{server_url}/api/company/campaigns/{campaign_id}",
            headers=company_headers,
            json={"status": "active"},
        )
        if resp.status_code not in (200, 201):
            print(f"Campaign activation failed: {resp.status_code} {resp.text}", file=sys.stderr)
            print("Note: insufficient balance or quality gate. Campaign left in draft.", file=sys.stderr)
            # Write ID anyway so subsequent steps have something to work with
            if args.output_id_to:
                Path(args.output_id_to).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output_id_to).write_text(str(campaign_id))
            sys.exit(2)
        print(f"Campaign activated: {resp.json().get('status')}")

        # 5. User login
        print(f"Logging in as user: {user_email}")
        user_token = _login(client, user_email, user_pw, "user", server=server_url)
        user_headers = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}

        # 6. Poll /campaigns/mine to trigger matching + get invitation
        print("Polling /api/campaigns/mine to trigger matching...")
        assignment_id: int | None = None
        for attempt in range(6):  # up to ~30s
            resp = client.get(f"{server_url}/api/campaigns/mine", headers=user_headers)
            if resp.status_code != 200:
                print(f"Warning: /campaigns/mine returned {resp.status_code}", file=sys.stderr)
                time.sleep(5)
                continue
            campaigns_list = resp.json()
            for c in campaigns_list:
                if c.get("campaign_id") == campaign_id or c.get("id") == campaign_id:
                    assignment_id = c.get("assignment_id")
                    break
            if assignment_id:
                break
            print(f"  Attempt {attempt+1}: invitation not yet visible, retrying in 5s...")
            time.sleep(5)

        if not assignment_id:
            print(
                f"Error: invitation for campaign {campaign_id} not found after polling. "
                "Check server matching logs.",
                file=sys.stderr,
            )
            sys.exit(2)
        print(f"Invitation found: assignment_id={assignment_id}")

        # 7. Accept the invitation
        print(f"Accepting invitation {assignment_id}...")
        resp = client.post(
            f"{server_url}/api/invitations/{assignment_id}/accept",
            headers=user_headers,
        )
        if resp.status_code not in (200, 201):
            print(f"Invitation accept failed: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(2)
        print(f"Invitation accepted: {resp.json().get('status')}")

    # 8. Write campaign ID to file
    if args.output_id_to:
        out_path = Path(args.output_id_to)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(str(campaign_id))
        print(f"Campaign ID written to: {out_path}")

    print(f"\nDone. Campaign ID: {campaign_id}")


if __name__ == "__main__":
    main()
