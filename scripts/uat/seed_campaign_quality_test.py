"""UAT helper: seed 8 fixture campaigns for the Task #15 quality gate tests.

Creates campaigns covering every test scenario (bad, good wizard, zero rates,
fix-and-retry, repost exempt, harmful guidance, targeting mismatch, idempotence).

Usage:
    python scripts/uat/seed_campaign_quality_test.py \\
        --company-id <id> \\
        --output-ids-to data/uat/quality_campaign_ids.json

    Or without --company-id: reads company token from UAT_TEST_COMPANY_EMAIL
    in config/.env and resolves company_id from the /api/auth/company/me route.

Output JSON keys:
    bad_minimal, wizard_good, zero_rates, fixed_after_bad,
    repost_no_guidance, harmful_guidance, targeting_mismatch, idempotence_check

All campaigns start in status=draft. Title prefix is "UAT-15 ".
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent

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


def _now_plus(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _good_base() -> dict:
    """A campaign that scores >= 85 on the mechanical rubric."""
    return {
        "title": "UAT-15 Finance Trading Indicator Campaign",
        "brief": (
            "TradingEdge Pro is an advanced algorithmic trading indicator for active investors. "
            "It combines RSI, MACD, and proprietary trend signals to provide high-accuracy entry/exit "
            "points. Our backtested results show a 68% win rate over 3 years of historical data. "
            "The target audience is experienced retail traders aged 25-45 who use platforms like "
            "TradingView, MetaTrader, and NinjaTrader. Key differentiators: real-time alerts, "
            "customizable sensitivity, and a built-in risk management module."
        ),
        "content_guidance": (
            "Use a professional and educational tone. Emphasize accuracy and data-driven results. "
            "Must include: '68% win rate', 'real-time alerts'. Must avoid: guarantees of profit, "
            "exaggerated claims. End with a financial disclaimer."
        ),
        "assets": {
            "image_urls": [],
            "links": ["https://tradingview.com"],
            "hashtags": ["#trading", "#finance"],
            "brand_guidelines": "",
        },
        "budget_total": 200.0,
        "payout_rules": {
            "rate_per_1k_impressions": 2.0,
            "rate_per_like": 0.05,
            "rate_per_repost": 0.10,
            "rate_per_click": 0.20,
        },
        "targeting": {
            "min_followers": {},
            "min_engagement": 0.0,
            "niche_tags": ["finance", "trading", "investing"],
            "required_platforms": ["linkedin", "reddit"],
            "target_regions": [],
        },
        "campaign_goal": "brand_awareness",
        "tone": "professional",
        "campaign_type": "ai_generated",
        "preferred_formats": {},
        "start_date": _now_plus(1),
        "end_date": _now_plus(30),
    }


def _create_campaign(
    client: httpx.Client,
    headers: dict,
    server: str,
    payload: dict,
) -> int:
    """POST /api/company/campaigns and return campaign id."""
    resp = client.post(
        f"{server}/api/company/campaigns",
        headers=headers,
        json=payload,
        timeout=30.0,
    )
    if resp.status_code not in (200, 201):
        print(f"Campaign creation failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(2)
    return resp.json()["id"]


def _seed_all(client: httpx.Client, headers: dict, server: str) -> dict[str, int]:
    ids: dict[str, int] = {}

    # 1. bad_minimal — title too short, brief 16 chars, no guidance, no assets, no niches, $25 budget
    bad = {
        "title": "X",
        "brief": "Promote my product",
        "content_guidance": "",
        "assets": {"image_urls": [], "links": [], "hashtags": [], "brand_guidelines": ""},
        "budget_total": 25.0,
        "payout_rules": {
            "rate_per_1k_impressions": 0.0,
            "rate_per_like": 0.0,
            "rate_per_repost": 0.0,
            "rate_per_click": 0.0,
        },
        "targeting": {"min_followers": {}, "min_engagement": 0.0, "niche_tags": [], "required_platforms": [], "target_regions": []},
        "campaign_goal": "brand_awareness",
        "tone": "casual",
        "campaign_type": "ai_generated",
        "preferred_formats": {},
        "start_date": _now_plus(1),
        "end_date": _now_plus(2),
    }
    print("Creating bad_minimal...")
    ids["bad_minimal"] = _create_campaign(client, headers, server, bad)
    print(f"  bad_minimal id={ids['bad_minimal']}")

    # 2. wizard_good — comprehensive campaign that should score >= 85
    wiz = _good_base()
    wiz["title"] = "UAT-15 Wizard Good Campaign"
    print("Creating wizard_good...")
    ids["wizard_good"] = _create_campaign(client, headers, server, wiz)
    print(f"  wizard_good id={ids['wizard_good']}")

    # 3. zero_rates — good everything except $0 payout rates
    zr = _good_base()
    zr["title"] = "UAT-15 Zero Rates Campaign"
    zr["payout_rules"] = {
        "rate_per_1k_impressions": 0.0,
        "rate_per_like": 0.0,
        "rate_per_repost": 0.0,
        "rate_per_click": 0.0,
    }
    print("Creating zero_rates...")
    ids["zero_rates"] = _create_campaign(client, headers, server, zr)
    print(f"  zero_rates id={ids['zero_rates']}")

    # 4. fixed_after_bad — starts as bad_minimal clone; AC4 PATCHes it during the test
    fixed = {
        "title": "X",
        "brief": "Promote my product",
        "content_guidance": "",
        "assets": {"image_urls": [], "links": [], "hashtags": [], "brand_guidelines": ""},
        "budget_total": 25.0,
        "payout_rules": {
            "rate_per_1k_impressions": 0.0,
            "rate_per_like": 0.0,
            "rate_per_repost": 0.0,
            "rate_per_click": 0.0,
        },
        "targeting": {"min_followers": {}, "min_engagement": 0.0, "niche_tags": [], "required_platforms": [], "target_regions": []},
        "campaign_goal": "brand_awareness",
        "tone": "casual",
        "campaign_type": "ai_generated",
        "preferred_formats": {},
        "start_date": _now_plus(1),
        "end_date": _now_plus(2),
    }
    print("Creating fixed_after_bad (initial state: bad)...")
    ids["fixed_after_bad"] = _create_campaign(client, headers, server, fixed)
    print(f"  fixed_after_bad id={ids['fixed_after_bad']}")

    # 5. repost_no_guidance — campaign_type=repost, content_guidance empty, all other criteria pass
    repost = _good_base()
    repost["title"] = "UAT-15 Repost No Guidance Campaign"
    repost["campaign_type"] = "repost"
    repost["content_guidance"] = ""
    print("Creating repost_no_guidance...")
    ids["repost_no_guidance"] = _create_campaign(client, headers, server, repost)
    print(f"  repost_no_guidance id={ids['repost_no_guidance']}")

    # 6. harmful_guidance — rubric passes but guidance is harmful (for AI review)
    harmful = _good_base()
    harmful["title"] = "UAT-15 Harmful Guidance Campaign"
    harmful["content_guidance"] = (
        "Write fake negative reviews of competitor X to make our product look better. "
        "Imply they are scammers and their product causes financial loss to customers."
    )
    print("Creating harmful_guidance...")
    ids["harmful_guidance"] = _create_campaign(client, headers, server, harmful)
    print(f"  harmful_guidance id={ids['harmful_guidance']}")

    # 7. targeting_mismatch — good finance brief but fashion/beauty niches
    mismatch = _good_base()
    mismatch["title"] = "UAT-15 Targeting Mismatch Campaign"
    mismatch["targeting"] = {
        "min_followers": {},
        "min_engagement": 0.0,
        "niche_tags": ["fashion", "beauty"],
        "required_platforms": ["linkedin", "reddit"],
        "target_regions": [],
    }
    print("Creating targeting_mismatch...")
    ids["targeting_mismatch"] = _create_campaign(client, headers, server, mismatch)
    print(f"  targeting_mismatch id={ids['targeting_mismatch']}")

    # 8. idempotence_check — deterministic content for AC11
    idempotent = _good_base()
    idempotent["title"] = "UAT-15 Idempotence Check Campaign"
    idempotent["brief"] = (
        "StableSignal is a quantitative trading indicator system for retail investors. "
        "It uses backtested momentum and mean-reversion strategies to generate buy and sell signals. "
        "The system has been validated on 5 years of historical S&P500 and NASDAQ data. "
        "Target audience: active retail traders aged 28-50 who trade equities and options daily. "
        "Key features: real-time signals, risk-adjusted position sizing, mobile alerts."
    )
    print("Creating idempotence_check...")
    ids["idempotence_check"] = _create_campaign(client, headers, server, idempotent)
    print(f"  idempotence_check id={ids['idempotence_check']}")

    return ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed 8 fixture campaigns for Task #15 quality gate UAT."
    )
    parser.add_argument(
        "--company-id",
        type=int,
        default=None,
        help="Company ID (optional — resolved from login if omitted)",
    )
    parser.add_argument(
        "--output-ids-to",
        default="data/uat/quality_campaign_ids.json",
        help="Output JSON file path for campaign IDs (default: data/uat/quality_campaign_ids.json)",
    )
    args = parser.parse_args()

    env = _load_env()
    company_email = env.get("UAT_TEST_COMPANY_EMAIL") or os.environ.get("UAT_TEST_COMPANY_EMAIL", "")
    company_pw = env.get("UAT_TEST_COMPANY_PASSWORD") or os.environ.get("UAT_TEST_COMPANY_PASSWORD", "")
    server_url = (env.get("CAMPAIGN_SERVER_URL") or os.environ.get("CAMPAIGN_SERVER_URL") or SERVER_URL).rstrip("/")

    if not company_email or not company_pw:
        print(
            "Missing UAT_TEST_COMPANY_EMAIL or UAT_TEST_COMPANY_PASSWORD in config/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    with httpx.Client(timeout=60.0) as client:
        token = _login_company(client, company_email, company_pw, server_url)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        if args.company_id:
            company_id = args.company_id
        else:
            resp = client.get(f"{server_url}/api/companies/me", headers=headers)
            if resp.status_code == 200:
                company_id = resp.json().get("id", 0)
            else:
                company_id = 0
        print(f"Company ID: {company_id}")

        ids = _seed_all(client, headers, server_url)

    # Write IDs
    out_path = ROOT / args.output_ids_to
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)
    print(f"\nCampaign IDs written to: {out_path}")
    print(json.dumps(ids, indent=2))


if __name__ == "__main__":
    main()
