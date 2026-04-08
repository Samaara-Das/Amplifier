"""Test profile scraper with live logins (Task #13).

Runs scrape_all_profiles() against real logged-in platforms and
prints the results for manual verification.

Run: python scripts/test_profile_scraper.py [platform]
Examples:
    python scripts/test_profile_scraper.py           # all platforms
    python scripts/test_profile_scraper.py x          # X only
    python scripts/test_profile_scraper.py reddit     # Reddit only
"""
import asyncio
import json
import logging
import sys
import os

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from utils.profile_scraper import scrape_all_profiles


def print_result(platform: str, data: dict):
    """Pretty-print a single platform's scrape result."""
    print(f"\n{'=' * 60}")
    print(f"  {platform.upper()} PROFILE")
    print(f"{'=' * 60}")

    if not data:
        print("  (no data)")
        return

    print(f"  Display name: {data.get('display_name')}")
    print(f"  Username:     {data.get('username')}")
    print(f"  Bio:          {(data.get('bio') or '')[:100]}")
    print(f"  Followers:    {data.get('follower_count', 0)}")
    print(f"  Following:    {data.get('following_count', 0)}")
    print(f"  Post count:   {data.get('post_count', 0)}")
    print(f"  Location:     {data.get('location')}")
    print(f"  Website:      {data.get('website')}")
    print(f"  Join date:    {data.get('join_date')}")
    print(f"  Verified:     {data.get('verified')}")
    print(f"  Engagement:   {data.get('engagement_rate', 0):.4f}")
    print(f"  Post freq:    {data.get('posting_frequency', 0):.2f}/day")
    print(f"  Quality:      {data.get('content_quality')}")
    print(f"  Niches:       {data.get('ai_detected_niches', [])}")

    # Profile data
    pd = data.get("profile_data", {})
    if pd:
        print(f"\n  Extended profile data:")
        if pd.get("about"):
            print(f"    About: {pd['about'][:150]}...")
        if pd.get("experience"):
            print(f"    Experience: {len(pd['experience'])} entries")
            for exp in pd["experience"][:3]:
                if isinstance(exp, dict):
                    print(f"      - {exp.get('title', '?')} @ {exp.get('company', '?')}")
        if pd.get("education"):
            print(f"    Education: {pd['education']}")
        if pd.get("skills"):
            print(f"    Skills: {pd['skills'][:5]}{'...' if len(pd.get('skills', [])) > 5 else ''}")
        if pd.get("karma"):
            print(f"    Karma: {pd['karma']}")
        if pd.get("reddit_age"):
            print(f"    Reddit age: {pd['reddit_age']}")
        if pd.get("active_subreddits"):
            print(f"    Active subs: {pd['active_subreddits'][:5]}")
        if pd.get("personal_details"):
            print(f"    Personal: {json.dumps(pd['personal_details'], indent=6)[:200]}")

    # Audience demographics
    demo = data.get("audience_demographics_estimate")
    if demo:
        print(f"\n  Audience demographics:")
        print(f"    Age range: {demo.get('age_range')}")
        print(f"    Interests: {demo.get('interests', [])[:5]}")

    # Recent posts
    posts = data.get("recent_posts", [])
    print(f"\n  Recent posts: {len(posts)}")
    for i, p in enumerate(posts[:5]):
        text = (p.get("text") or "")[:80]
        metrics = []
        if p.get("likes"): metrics.append(f"{p['likes']} likes")
        if p.get("comments"): metrics.append(f"{p['comments']} comments")
        if p.get("reposts"): metrics.append(f"{p['reposts']} reposts")
        if p.get("views"): metrics.append(f"{p['views']} views")
        sub = f" [{p['subreddit']}]" if p.get("subreddit") else ""
        media = " [has media]" if p.get("has_media") else ""
        print(f"    {i+1}. {text}...")
        print(f"       {', '.join(metrics) or 'no metrics'}{sub}{media} | {p.get('posted_at', '?')}")


async def main():
    # Parse platform argument
    platforms = None
    if len(sys.argv) > 1:
        platforms = [sys.argv[1].lower()]
        print(f"Testing platform: {platforms[0]}")
    else:
        print("Testing ALL platforms")

    print("\nStarting profile scraper...")
    results = await scrape_all_profiles(platforms)

    print(f"\n\nGot results for {len(results)} platform(s)")

    for platform, data in results.items():
        print_result(platform, data)

    # Summary
    print(f"\n\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    for platform, data in results.items():
        name = data.get("display_name", "?")
        followers = data.get("follower_count", 0)
        posts = len(data.get("recent_posts", []))
        niches = data.get("ai_detected_niches", [])
        quality = data.get("content_quality", "?")
        tier = "Tier 1 (text)" if data.get("username") else "CSS fallback"
        print(f"  {platform:10s}: {name} | {followers} followers | {posts} posts | {niches} | {quality} | {tier}")

    # Write full results to file for inspection
    output_path = os.path.join(os.path.dirname(__file__), "..", "scrape_test_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
