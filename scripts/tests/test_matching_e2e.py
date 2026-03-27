"""E2E matching test — creates fake users + campaigns on production, tests matching results.

Creates:
- 3 fake campaigns (tech, beauty, fitness)
- 3 fake users (tech person, beauty blogger, generic user)
- Tests that each user matches the RIGHT campaigns and NOT the wrong ones

Usage:
    python scripts/tests/test_matching_e2e.py setup    # Create test data
    python scripts/tests/test_matching_e2e.py test     # Run matching tests
    python scripts/tests/test_matching_e2e.py cleanup   # Remove test data
"""
import json
import sys
import httpx

SERVER = "https://server-five-omega-23.vercel.app"
SB_URL = "https://ozkntsmomkrsnjziamkr.supabase.co"
SB_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im96a250c21vbWtyc25qemlhbWtyIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDE1NjY4OSwiZXhwIjoyMDg5NzMyNjg5fQ.3R2_1mK1x4wykHTnJr_NhkW4VqX9gEwgFr70w-ioO7E"
SB_HEADERS = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"}

# ── Test Campaigns ──

CAMPAIGNS = [
    {
        "title": "TEST: CodeVault Pro — AI Code Review Tool",
        "brief": "CodeVault Pro is an AI-powered code review tool that catches bugs, security vulnerabilities, and performance issues before they reach production. It integrates with GitHub, GitLab, and Bitbucket. Built for development teams who want to ship faster with fewer bugs. Features: real-time code analysis, AI-suggested fixes, team dashboard with code quality metrics, supports 20+ languages.",
        "content_guidance": "Focus on the developer experience. Show how CodeVault catches real bugs. Use before/after examples. Mention the free tier for open-source projects. Tone: technical but approachable.",
        "targeting": {"niche_tags": ["technology", "ai", "business"], "target_regions": ["us", "india", "global"], "required_platforms": ["x", "linkedin"], "min_followers": {}, "min_engagement": 0},
        "payout_rules": {"rate_per_1k_impressions": 1.0, "rate_per_like": 0.02, "rate_per_repost": 0.10, "rate_per_click": 0},
        "budget_total": 500,
        "expected_match": "tech_user",  # Should match tech users
    },
    {
        "title": "TEST: GlowUp Skincare — Summer Collection Launch",
        "brief": "GlowUp Skincare is launching its Summer 2026 collection — lightweight moisturizers, SPF serums, and vitamin C brightening drops. Target audience: women 18-35 who care about skincare routines. All products are cruelty-free, vegan, and dermatologist-tested. Price range: $15-40.",
        "content_guidance": "Show your skincare routine. Unboxing-style content works great. Mention specific products by name. Use hashtags #GlowUpSummer #SkincareRoutine. Avoid medical claims.",
        "targeting": {"niche_tags": ["beauty", "fashion", "lifestyle", "health"], "target_regions": ["us", "global"], "required_platforms": ["facebook", "reddit"], "min_followers": {}, "min_engagement": 0},
        "payout_rules": {"rate_per_1k_impressions": 0.30, "rate_per_like": 0.015, "rate_per_repost": 0.08, "rate_per_click": 0},
        "budget_total": 300,
        "expected_match": "beauty_user",  # Should match beauty users
    },
    {
        "title": "TEST: FitTrack Home Gym Equipment",
        "brief": "FitTrack makes smart home gym equipment — connected dumbbells, resistance bands with rep counting, and a compact cable machine that fits in any apartment. Built-in AI coach suggests workouts based on your goals. App syncs with Apple Health and Google Fit. Price: $299 for the starter kit.",
        "content_guidance": "Show real workouts using the equipment. Before/after transformation content performs well. Mention the AI coach feature. Keep it motivational but real — no fake transformation photos.",
        "targeting": {"niche_tags": ["fitness", "health", "lifestyle", "sports"], "target_regions": ["us", "india", "global"], "required_platforms": ["x", "facebook", "reddit"], "min_followers": {}, "min_engagement": 0},
        "payout_rules": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0},
        "budget_total": 400,
        "expected_match": "fitness_user",  # Should match fitness users
    },
]

# ── Test Users ──

USERS = [
    {
        "email": "test_tech_user@amplifier.dev",
        "password": "test1234",
        "niche_tags": ["technology", "ai", "crypto", "business"],
        "audience_region": "india",
        "mode": "semi_auto",
        "platforms": {"x": True, "linkedin": True, "reddit": True},
        "follower_counts": {"x": 450, "linkedin": 2100, "reddit": 50},
        "scraped_profiles": {
            "x": {
                "display_name": "DevRaj",
                "bio": "Full-stack developer. Building with AI. Open source contributor.",
                "follower_count": 450,
                "following_count": 320,
                "posting_frequency": 0.3,
                "recent_posts": [
                    {"text": "Just shipped a new feature using Claude Code. The AI caught 3 bugs I missed in code review. This is the future of development.", "likes": 12, "retweets": 3, "replies": 5},
                    {"text": "Hot take: most startups don't need microservices. A well-structured monolith with good tests beats a distributed mess every time.", "likes": 45, "retweets": 8, "replies": 15},
                    {"text": "Been testing GPT-4o vs Claude for code generation. Claude handles complex refactors better but GPT-4o is faster for simple stuff.", "likes": 23, "retweets": 6, "replies": 9},
                ],
            },
            "linkedin": {
                "display_name": "Raj Patel",
                "bio": "Senior Software Engineer at TechCorp | AI/ML enthusiast | Open source",
                "follower_count": 2100,
                "following_count": 500,
                "posting_frequency": 0.1,
                "recent_posts": [
                    {"text": "Excited to share that our team just open-sourced our internal code review tool. It uses LLMs to catch common bugs before they hit production.", "likes": 89, "comments": 12, "reposts": 5},
                ],
                "profile_data": {"about": "I build developer tools and write about AI in software engineering. 8 years of experience across startups and large tech companies.", "experience": [{"title": "Senior Software Engineer", "company": "TechCorp", "duration": "3 years"}]},
            },
        },
        "expected_campaigns": ["CodeVault Pro"],  # Should match tech campaign
        "should_not_match": ["GlowUp Skincare"],  # Should NOT match beauty
    },
    {
        "email": "test_beauty_user@amplifier.dev",
        "password": "test1234",
        "niche_tags": ["beauty", "fashion", "lifestyle"],
        "audience_region": "us",
        "mode": "semi_auto",
        "platforms": {"facebook": True, "reddit": True},
        "follower_counts": {"facebook": 800, "reddit": 30},
        "scraped_profiles": {
            "facebook": {
                "display_name": "Sarah Chen",
                "bio": "Skincare addict. Cruelty-free beauty only.",
                "follower_count": 800,
                "following_count": 400,
                "posting_frequency": 0.5,
                "recent_posts": [
                    {"text": "Finally found a vitamin C serum that doesn't break me out! Been using it for 2 weeks and my skin is glowing.", "likes": 34, "comments": 8, "shares": 2},
                    {"text": "My morning skincare routine: cleanser, toner, vitamin C, moisturizer, SPF. Simple but it works.", "likes": 56, "comments": 15, "shares": 5},
                    {"text": "PSA: check your sunscreen expiry dates! Using expired SPF is basically using no SPF.", "likes": 120, "comments": 23, "shares": 18},
                ],
                "profile_data": {"personal_details": {"location": "Los Angeles, CA"}},
            },
        },
        "expected_campaigns": ["GlowUp Skincare"],  # Should match beauty
        "should_not_match": ["CodeVault Pro"],  # Should NOT match tech
    },
    {
        "email": "test_fitness_user@amplifier.dev",
        "password": "test1234",
        "niche_tags": ["fitness", "health", "sports"],
        "audience_region": "us",
        "mode": "full_auto",
        "platforms": {"x": True, "facebook": True, "reddit": True},
        "follower_counts": {"x": 150, "facebook": 200, "reddit": 80},
        "scraped_profiles": {
            "x": {
                "display_name": "Mike_Lifts",
                "bio": "Home gym enthusiast. Calisthenics + weights. No gym membership needed.",
                "follower_count": 150,
                "following_count": 100,
                "posting_frequency": 0.2,
                "recent_posts": [
                    {"text": "Day 90 of home workouts. Added 20lbs to my bench press using just dumbbells and a bench. Proof you don't need a gym.", "likes": 8, "retweets": 1, "replies": 3},
                    {"text": "Best investment I made this year: a set of adjustable dumbbells. $200 and I never have to pay for a gym again.", "likes": 15, "retweets": 2, "replies": 6},
                ],
            },
        },
        "expected_campaigns": ["FitTrack Home Gym"],  # Should match fitness
        "should_not_match": ["GlowUp Skincare"],  # Should NOT match beauty
    },
]


def setup():
    """Create test campaigns and users on production."""
    print("=== SETUP: Creating test data on production ===\n")

    # Get Cluely company ID
    resp = httpx.get(f"{SB_URL}/rest/v1/companies?email=eq.cluely%40gmail.com&select=id", headers=SB_HEADERS)
    companies = resp.json()
    if not companies:
        print("ERROR: Cluely company not found on production. Register it first.")
        return
    company_id = companies[0]["id"]
    print(f"Using company ID: {company_id}")

    # Create campaigns
    for c in CAMPAIGNS:
        payload = {
            "company_id": company_id,
            "title": c["title"],
            "brief": c["brief"],
            "content_guidance": c["content_guidance"],
            "targeting": c["targeting"],
            "payout_rules": c["payout_rules"],
            "budget_total": c["budget_total"],
            "budget_remaining": c["budget_total"],
            "assets": {},
            "penalty_rules": {},
            "status": "active",
            "start_date": "2026-03-01T00:00:00+00:00",
            "end_date": "2026-06-01T00:00:00+00:00",
            "company_urls": [],
            "ai_generated_brief": False,
            "budget_exhaustion_action": "auto_pause",
            "budget_alert_sent": False,
            "screening_status": "approved",
            "campaign_version": 1,
            "invitation_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "expired_count": 0,
            "max_users": 100,
        }
        resp = httpx.post(f"{SB_URL}/rest/v1/campaigns", headers={**SB_HEADERS, "Prefer": "return=representation"}, json=payload, timeout=10)
        if resp.status_code == 201:
            cid = resp.json()[0]["id"]
            print(f"  Created campaign: {c['title']} (ID: {cid})")
        else:
            print(f"  FAILED: {c['title']} — {resp.text[:200]}")

    # Create users
    for u in USERS:
        resp = httpx.post(f"{SERVER}/api/auth/register", json={"email": u["email"], "password": u["password"]}, timeout=10)
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            # Update profile with scraped data
            httpx.patch(f"{SERVER}/api/users/me", headers={"Authorization": f"Bearer {token}"}, json={
                "platforms": u["platforms"],
                "follower_counts": u["follower_counts"],
                "niche_tags": u["niche_tags"],
                "audience_region": u["audience_region"],
                "mode": u["mode"],
                "scraped_profiles": u["scraped_profiles"],
            }, timeout=10)
            print(f"  Created user: {u['email']} (niches: {u['niche_tags']})")
        else:
            print(f"  FAILED: {u['email']} — {resp.text[:200]}")

    print("\nSetup complete. Run 'test' to verify matching.")


def test():
    """Test matching for each user."""
    print("=== TEST: Verifying matching results ===\n")

    results = {"pass": 0, "fail": 0}

    for u in USERS:
        # Login
        resp = httpx.post(f"{SERVER}/api/auth/login", json={"email": u["email"], "password": u["password"]}, timeout=10)
        if resp.status_code != 200:
            print(f"SKIP {u['email']}: login failed — {resp.text[:100]}")
            continue
        token = resp.json()["access_token"]

        # Poll for matches
        resp = httpx.get(f"{SERVER}/api/campaigns/mine", headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if resp.status_code != 200:
            print(f"FAIL {u['email']}: matching returned {resp.status_code}")
            results["fail"] += 1
            continue

        matched = resp.json()
        matched_titles = [c["title"] for c in matched]
        print(f"\n{u['email']} (niches: {u['niche_tags']})")
        print(f"  Matched {len(matched)} campaigns:")
        for c in matched:
            print(f"    - {c['title']}")

        # Check expected matches
        for expected in u.get("expected_campaigns", []):
            found = any(expected in t for t in matched_titles)
            if found:
                print(f"  PASS: Matched '{expected}' as expected")
                results["pass"] += 1
            else:
                print(f"  FAIL: Should have matched '{expected}' but didn't")
                results["fail"] += 1

        # Check should-NOT-match
        for unwanted in u.get("should_not_match", []):
            found = any(unwanted in t for t in matched_titles)
            if found:
                print(f"  FAIL: Matched '{unwanted}' but shouldn't have")
                results["fail"] += 1
            else:
                print(f"  PASS: Correctly did NOT match '{unwanted}'")
                results["pass"] += 1

    print(f"\n=== RESULTS: {results['pass']} passed, {results['fail']} failed ===")


def cleanup():
    """Remove test data from production."""
    print("=== CLEANUP: Removing test data ===\n")

    # Delete test campaigns
    resp = httpx.delete(f"{SB_URL}/rest/v1/campaigns?title=like.TEST%3A*", headers={**SB_HEADERS, "Prefer": "return=representation"}, timeout=10)
    deleted = resp.json() if resp.status_code == 200 else []
    print(f"Deleted {len(deleted)} test campaigns")

    # Delete test users (and their assignments)
    for u in USERS:
        # Find user ID
        resp = httpx.get(f"{SB_URL}/rest/v1/users?email=eq.{u['email']}&select=id", headers=SB_HEADERS, timeout=10)
        users = resp.json()
        if users:
            uid = users[0]["id"]
            httpx.delete(f"{SB_URL}/rest/v1/campaign_assignments?user_id=eq.{uid}", headers=SB_HEADERS, timeout=10)
            httpx.delete(f"{SB_URL}/rest/v1/campaign_invitation_log?user_id=eq.{uid}", headers=SB_HEADERS, timeout=10)
            httpx.delete(f"{SB_URL}/rest/v1/users?id=eq.{uid}", headers=SB_HEADERS, timeout=10)
            print(f"Deleted user: {u['email']}")

    print("\nCleanup complete.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "setup":
        setup()
    elif cmd == "test":
        test()
    elif cmd == "cleanup":
        cleanup()
    else:
        print(f"Usage: {sys.argv[0]} [setup|test|cleanup]")
