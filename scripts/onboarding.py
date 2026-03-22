"""User onboarding — first-run setup for the campaign auto-poster.

Steps:
1. Register or login to server
2. Connect social media platforms (run login_setup.py)
3. Set follower counts and niche tags
4. Choose operating mode
5. Verify server connectivity
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")
os.environ.setdefault("AUTO_POSTER_ROOT", str(ROOT))

from utils.local_db import init_db, set_setting, get_setting
from utils.server_client import register, login, is_logged_in, update_profile, get_profile


def _input(prompt: str, default: str = None) -> str:
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()


def step_auth():
    """Step 1: Register or login."""
    print("\n=== Step 1: Account Setup ===")
    if is_logged_in():
        try:
            profile = get_profile()
            print(f"Already logged in as {profile['email']}")
            relogin = _input("Re-login? (y/n)", "n")
            if relogin.lower() != "y":
                return
        except Exception:
            print("Previous session expired. Please login again.")

    choice = _input("Register new account or login? (register/login)", "register")

    email = _input("Email")
    password = _input("Password")

    try:
        if choice == "register":
            register(email, password)
            print(f"Registered and logged in as {email}")
        else:
            login(email, password)
            print(f"Logged in as {email}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def step_platforms():
    """Step 2: Connect social media platforms."""
    print("\n=== Step 2: Connect Platforms ===")
    print("You need to log in to each social media platform in the browser.")
    print("This creates persistent profiles so the auto-poster can post on your behalf.\n")

    platforms = ["x", "linkedin", "facebook", "instagram", "reddit", "tiktok"]
    connected = {}

    for platform in platforms:
        profile_dir = ROOT / "profiles" / f"{platform}-profile"
        already_connected = profile_dir.exists() and any(profile_dir.iterdir()) if profile_dir.exists() else False

        if already_connected:
            print(f"  {platform}: already connected")
            username = _input(f"    Your {platform} username/handle", "")
            connected[platform] = {"connected": True, "username": username}
        else:
            connect = _input(f"  Connect {platform}? (y/n)", "y")
            if connect.lower() == "y":
                print(f"    Opening browser for {platform} login...")
                try:
                    subprocess.run(
                        [sys.executable, str(ROOT / "scripts" / "login_setup.py"), platform],
                        check=True,
                    )
                    username = _input(f"    Your {platform} username/handle", "")
                    connected[platform] = {"connected": True, "username": username}
                except subprocess.CalledProcessError:
                    print(f"    Failed to connect {platform}. You can try again later.")
                    connected[platform] = {"connected": False}
            else:
                connected[platform] = {"connected": False}
                print(f"    Skipped {platform}")

    return connected


def step_profile(platforms: dict):
    """Step 3: Set follower counts, audience region, and categories."""
    print("\n=== Step 3: Profile Setup ===")

    # Follower counts
    follower_counts = {}
    for platform, info in platforms.items():
        if info.get("connected"):
            count = _input(f"  Followers on {platform}", "0")
            try:
                follower_counts[platform] = int(count)
            except ValueError:
                follower_counts[platform] = 0

    # Audience region
    print("\n  Where is most of your audience based?")
    print("  Options: us, uk, india, eu, latam, sea, global")
    audience_region = _input("  Audience region", "global").strip().lower()
    if audience_region not in ("us", "uk", "india", "eu", "latam", "sea", "global"):
        audience_region = "global"

    # Categories (niche tags)
    print("\n  Available categories: beauty, fashion, tech, finance, fitness, gaming,")
    print("  food, travel, education, lifestyle, business, health, entertainment, crypto")
    niche_input = _input("  Your categories (comma-separated)", "finance,tech")
    niche_tags = [n.strip().lower() for n in niche_input.split(",") if n.strip()]

    return follower_counts, niche_tags, audience_region


def step_mode():
    """Step 4: Choose operating mode."""
    print("\n=== Step 4: Operating Mode ===")
    print("  full_auto  — Campaigns are processed and posted automatically (1.5x payout)")
    print("  semi_auto  — Content is generated, you review before posting (2.0x payout)")
    print("  manual     — You write your own content from the brief (2.0x payout)")
    mode = _input("  Choose mode", "semi_auto")
    if mode not in ("full_auto", "semi_auto", "manual"):
        mode = "semi_auto"
    return mode


def step_api_key():
    """Step 5: Get a free Gemini API key for content generation."""
    print("\n=== Step 5: API Key Setup ===")
    print("  Content generation requires a free Gemini API key.")
    print("  Get yours at: https://ai.google.dev")
    print("  1. Sign in with Google")
    print("  2. Click 'Get API key' → 'Create API key'")
    print("  3. Copy the key and paste it below\n")

    env_path = ROOT / "config" / ".env"
    existing_key = os.getenv("GEMINI_API_KEY", "").strip()

    if existing_key:
        print(f"  Gemini API key already set (ends with ...{existing_key[-4:]})")
        change = _input("  Replace it? (y/n)", "n")
        if change.lower() != "y":
            return

    key = _input("  Gemini API key (or press Enter to skip)")
    if key:
        # Update the .env file
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            import re
            if "GEMINI_API_KEY=" in content:
                content = re.sub(r"GEMINI_API_KEY=.*", f"GEMINI_API_KEY={key}", content)
            else:
                content += f"\nGEMINI_API_KEY={key}\n"
            env_path.write_text(content, encoding="utf-8")
        else:
            env_path.write_text(f"GEMINI_API_KEY={key}\n", encoding="utf-8")
        os.environ["GEMINI_API_KEY"] = key
        print("  API key saved.")
    else:
        print("  Skipped. You can add it later to config/.env")


def step_verify():
    """Step 6: Verify everything works."""
    print("\n=== Step 6: Verification ===")
    try:
        profile = get_profile()
        print(f"  Server connection: OK")
        print(f"  Email: {profile['email']}")
        print(f"  Trust score: {profile['trust_score']}")
        print(f"  Mode: {profile['mode']}")
        print(f"  Platforms: {list(k for k, v in profile['platforms'].items() if v.get('connected'))}")
        print(f"  Niche tags: {profile['niche_tags']}")
        return True
    except Exception as e:
        print(f"  Server connection: FAILED — {e}")
        return False


def run_onboarding():
    """Run full onboarding flow."""
    print("=" * 50)
    print("  Amplifier Setup")
    print("=" * 50)

    init_db()

    # Step 1: Auth
    step_auth()

    # Step 2: Connect platforms
    platforms = step_platforms()

    # Step 3: Profile
    follower_counts, niche_tags, audience_region = step_profile(platforms)

    # Step 4: Mode
    mode = step_mode()

    # Save to local settings
    set_setting("mode", mode)

    # Update server profile
    try:
        update_profile(
            platforms=platforms,
            follower_counts=follower_counts,
            niche_tags=niche_tags,
            audience_region=audience_region,
            mode=mode,
        )
        print("\n  Profile updated on server.")
    except Exception as e:
        print(f"\n  Warning: Could not update server profile: {e}")

    # Step 5: API Key
    step_api_key()

    # Step 6: Verify
    step_verify()

    print("\n" + "=" * 50)
    print("  Setup complete!")
    print(f"  Dashboard: python scripts/campaign_dashboard.py")
    print(f"  Start runner: python scripts/campaign_runner.py")
    print("=" * 50)


if __name__ == "__main__":
    run_onboarding()
