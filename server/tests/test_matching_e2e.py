"""E2E test for AI matching (Task #12).

Creates test users with mock profiles, a trading campaign,
and verifies AI scoring produces the right results.

Run: cd server && python tests/test_matching_e2e.py
"""
import httpx
import json
import sys
import time
from datetime import datetime, timedelta

BASE = "http://127.0.0.1:8000"

# ── Test users ──

FINANCE_USER = {
    "email": "finance_test_match@test.com",
    "password": "Test1234!",
    "niche_tags": ["trading", "technical analysis", "finance"],
    "audience_region": "us",
    "platforms": {"x": True, "reddit": True},
    "follower_counts": {"x": 450, "reddit": 30},
    "scraped_profiles": {
        "x": {
            "display_name": "TraderMike",
            "bio": "Day trader | SPY options | Technical analysis nerd",
            "follower_count": 450,
            "following_count": 200,
            "posting_frequency": 1.5,
            "recent_posts": [
                {"text": "SPY broke through resistance at 520. RSI divergence on the 15min confirmed.", "likes": 12, "comments": 3, "views": 890, "posted_at": "2h ago"},
                {"text": "My RSI divergence indicator caught the AAPL reversal. 68% win rate backtested.", "likes": 25, "comments": 8, "views": 2100, "posted_at": "1d ago"},
                {"text": "Stop using moving averages as entry signals. They lag. Use structure breaks.", "likes": 45, "comments": 15, "views": 5200, "posted_at": "3d ago"},
            ],
            "ai_detected_niches": ["day trading", "technical analysis", "options trading"],
            "profile_data": {"content_quality": "high"},
        },
    },
    "ai_detected_niches": ["day trading", "technical analysis"],
}

COOKING_USER = {
    "email": "cooking_test_match@test.com",
    "password": "Test1234!",
    "niche_tags": ["cooking", "food photography", "recipes"],
    "audience_region": "us",
    "platforms": {"x": True, "facebook": True},
    "follower_counts": {"x": 1200, "facebook": 350},
    "scraped_profiles": {
        "x": {
            "display_name": "ChefLinda",
            "bio": "Home cook | Recipe creator | Food photography",
            "follower_count": 1200,
            "following_count": 800,
            "posting_frequency": 2.0,
            "recent_posts": [
                {"text": "Made the most amazing sourdough bread today! 72-hour cold ferment.", "likes": 85, "comments": 20, "views": 3500, "posted_at": "4h ago"},
                {"text": "Quick weeknight pasta: garlic, cherry tomatoes, basil, parmesan. 15 minutes.", "likes": 120, "comments": 35, "views": 8900, "posted_at": "1d ago"},
                {"text": "My kitchen gadget tier list: S-tier is the cast iron skillet.", "likes": 200, "comments": 60, "views": 15000, "posted_at": "3d ago"},
            ],
            "ai_detected_niches": ["cooking", "food photography", "recipes"],
            "profile_data": {"content_quality": "high"},
        },
    },
    "ai_detected_niches": ["cooking", "food photography"],
}


def register_or_login(client: httpx.Client, email: str, password: str) -> str:
    """Register a user (or login if already exists). Returns JWT token."""
    r = client.post(f"{BASE}/api/auth/register", json={"email": email, "password": password})
    if r.status_code == 200:
        return r.json()["access_token"]
    r = client.post(f"{BASE}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def update_user_profile(client: httpx.Client, token: str, user_data: dict):
    """Update user profile with all data including scraped profiles via API."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "niche_tags": user_data["niche_tags"],
        "audience_region": user_data["audience_region"],
        "platforms": user_data["platforms"],
        "follower_counts": user_data["follower_counts"],
        "scraped_profiles": user_data["scraped_profiles"],
        "ai_detected_niches": user_data["ai_detected_niches"],
    }
    r = client.patch(f"{BASE}/api/users/me", json=payload, headers=headers)
    if r.status_code != 200:
        print(f"  WARN: Profile update returned {r.status_code}: {r.text[:200]}")
    return r


def company_login_or_register(client: httpx.Client) -> str:
    """Register or login a company. Returns JWT token."""
    r = client.post(f"{BASE}/api/auth/company/register", json={
        "name": "TradingTools Inc",
        "email": "tradingtools_match@test.com",
        "password": "Test1234!",
    })
    if r.status_code == 200:
        return r.json()["access_token"]
    r = client.post(f"{BASE}/api/auth/company/login", json={
        "email": "tradingtools_match@test.com",
        "password": "Test1234!",
    })
    r.raise_for_status()
    return r.json()["access_token"]


def create_campaign(client: httpx.Client) -> int:
    """Create a trading indicator campaign. Returns campaign ID."""
    token = company_login_or_register(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Top up balance directly in DB (admin-only endpoint uses form + cookie)
    import sqlite3, os
    db_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "amplifier.db"))
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE companies SET balance = 1000.0 WHERE email = 'tradingtools_match@test.com'")
    conn.commit()
    conn.close()
    print("    Company balance set to $1000")

    now = datetime.utcnow()
    campaign_data = {
        "title": "Smart Money Indicator for TradingView",
        "brief": (
            "Promote our Smart Money Indicator for TradingView. "
            "It detects institutional order flow in real-time on SPY, QQQ, AAPL, and TSLA. "
            "Backtested with a 72% win rate over 2 years. "
            "Target audience: retail traders who use TradingView for technical analysis. "
            "The indicator shows when big players are buying or selling."
        ),
        "content_guidance": (
            "Share your honest experience. Show a chart screenshot if possible. "
            "Mention the indicator name and that it's on TradingView. Keep it authentic."
        ),
        "budget_total": 500.0,
        "assets": {
            "company_urls": ["https://tradingview.com"],
            "hashtags": ["#trading", "#SPY", "#TechnicalAnalysis"],
        },
        "targeting": {
            "niche_tags": ["trading", "finance", "technical analysis"],
            "required_platforms": ["x"],
            "target_regions": [],
            "min_followers": {},
            "min_engagement": 0,
        },
        "payout_rules": {
            "rate_per_1k_impressions": 3.00,
            "rate_per_like": 0.02,
            "rate_per_repost": 0.10,
        },
        "campaign_goal": "leads",
        "tone": "conversational",
        "start_date": now.isoformat(),
        "end_date": (now + timedelta(days=30)).isoformat(),
    }
    r = client.post(f"{BASE}/api/company/campaigns", json=campaign_data, headers=headers)
    if r.status_code != 200:
        print(f"  WARN: Campaign creation returned {r.status_code}: {r.text[:300]}")
        return -1

    campaign_id = r.json().get("id", -1)
    print(f"    Created campaign ID: {campaign_id}")

    # Activate the campaign
    r2 = client.patch(
        f"{BASE}/api/company/campaigns/{campaign_id}",
        json={"status": "active"},
        headers=headers,
    )
    if r2.status_code == 200:
        print(f"    Campaign activated")
    else:
        print(f"    WARN: Activation returned {r2.status_code}: {r2.text[:200]}")

    return campaign_id


def test_matching(client: httpx.Client, token: str, user_label: str) -> list:
    """Poll for matched campaigns and return the response."""
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get(f"{BASE}/api/campaigns/mine", headers=headers)
    if r.status_code != 200:
        print(f"  [{user_label}] Matching failed: {r.status_code} {r.text[:200]}")
        return []
    return r.json()


def main():
    print("=" * 60)
    print("Task #12: AI Matching E2E Test")
    print("=" * 60)

    client = httpx.Client(timeout=60)
    try:
        r = client.get(f"{BASE}/health")
        if r.status_code != 200:
            print("ERROR: Server not responding.")
            sys.exit(1)
    except httpx.ConnectError:
        print("ERROR: Cannot connect to server at", BASE)
        sys.exit(1)

    # Step 1: Create campaign
    print("\n[1] Creating trading campaign...")
    campaign_id = create_campaign(client)

    # Step 2: Register users and update profiles
    print("\n[2] Registering and profiling test users...")
    finance_token = register_or_login(client, FINANCE_USER["email"], FINANCE_USER["password"])
    time.sleep(2)  # Avoid rate limit
    cooking_token = register_or_login(client, COOKING_USER["email"], COOKING_USER["password"])
    update_user_profile(client, finance_token, FINANCE_USER)
    update_user_profile(client, cooking_token, COOKING_USER)
    print(f"    Finance: {FINANCE_USER['email']}")
    print(f"    Cooking: {COOKING_USER['email']}")

    # Clean up ALL old assignments for these test users (from previous test runs)
    import sqlite3, os
    db_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "amplifier.db"))
    conn = sqlite3.connect(db_path)
    conn.execute("""
        DELETE FROM campaign_assignments
        WHERE user_id IN (
            SELECT id FROM users WHERE email IN (?, ?)
        )
    """, (FINANCE_USER["email"], COOKING_USER["email"]))
    # Also delete invitation logs
    conn.execute("""
        DELETE FROM campaign_invitation_log
        WHERE user_id IN (
            SELECT id FROM users WHERE email IN (?, ?)
        )
    """, (FINANCE_USER["email"], COOKING_USER["email"]))
    # Deactivate all old test campaigns (keep only the new one active)
    conn.execute("""
        UPDATE campaigns SET status = 'completed'
        WHERE company_id IN (
            SELECT id FROM companies WHERE email = 'tradingtools_match@test.com'
        ) AND id != ? AND status = 'active'
    """, (campaign_id,))
    conn.commit()
    conn.close()
    print("    Cleared ALL old test assignments + deactivated old campaigns")

    # Step 3: Run matching
    print("\n[3] Running AI matching for finance user (expect match)...")
    finance_result = test_matching(client, finance_token, "FINANCE")
    print(f"    Got {len(finance_result)} campaign(s)")
    for c in finance_result:
        print(f"    - {c.get('title', '?')} (id={c.get('campaign_id')})")

    print("\n[4] Running AI matching for cooking user (expect NO match)...")
    cooking_result = test_matching(client, cooking_token, "COOKING")
    print(f"    Got {len(cooking_result)} campaign(s)")
    for c in cooking_result:
        print(f"    - {c.get('title', '?')} (id={c.get('campaign_id')})")

    # Evaluate
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    finance_matched = any("Smart Money" in c.get("title", "") for c in finance_result)
    cooking_matched = any("Smart Money" in c.get("title", "") for c in cooking_result)

    tests = []
    if finance_matched:
        print("  [PASS] Finance user matched to trading campaign")
        tests.append(True)
    else:
        print("  [FAIL] Finance user was NOT matched (expected match)")
        tests.append(False)

    if not cooking_matched:
        print("  [PASS] Cooking user NOT matched (score < 40, correct)")
        tests.append(True)
    else:
        print("  [FAIL] Cooking user WAS matched (should have been filtered by score < 40)")
        tests.append(False)

    passed = all(tests)
    print(f"\n  Overall: {'PASS' if passed else 'FAIL'} ({sum(tests)}/{len(tests)})")
    print(f"\n  Verify in admin dashboard: {BASE}/admin/login (password: admin)")

    client.close()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
