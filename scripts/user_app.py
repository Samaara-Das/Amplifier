"""Amplifier User App — Flask web application replacing the Tauri desktop app."""

import json
import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.local_db import get_setting, init_db, set_setting
from utils.server_client import _load_auth, get_profile, is_logged_in, login, register

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Flask app setup ───────────────────────────────────────────────

app = Flask(
    __name__,
    template_folder=str(ROOT / "scripts" / "templates"),
    static_folder=str(ROOT / "scripts" / "static"),
)
app.secret_key = os.urandom(24)

# CSRF protection for all POST forms
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)
app.config["WTF_CSRF_CHECK_DEFAULT"] = True

PORT = 5222


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    logger.error("Unhandled exception: %s\n%s", e, traceback.format_exc())
    return f"<h1>Error</h1><pre>{traceback.format_exc()}</pre>", 500


# ── Auth guard ────────────────────────────────────────────────────

@app.before_request
def check_auth():
    try:
        # Ensure DB tables exist — recreate if DB was deleted while app was running
        init_db()

        allowed = ["/login", "/logout", "/static", "/favicon.ico", "/api/"]
        if any(request.path.startswith(p) for p in allowed):
            return
        if not is_logged_in():
            return redirect(url_for("login_page"))
        if get_setting("onboarding_done") != "true" and not request.path.startswith("/onboarding"):
            return redirect(url_for("onboarding_page"))
    except Exception as e:
        logger.error("before_request error: %s", e, exc_info=True)
        return redirect(url_for("login_page"))


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


# ── Helpers ───────────────────────────────────────────────────────

def _base_context(active_page="dashboard"):
    auth = _load_auth()
    return {
        "active_page": active_page,
        "email": auth.get("email", "User"),
    }


# ── Routes ────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        if is_logged_in():
            return redirect(url_for("dashboard"))
        return render_template("user/login.html")

    action = request.form.get("action", "login")
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    try:
        if action == "register":
            confirm = request.form.get("confirm_password", "").strip()
            if password != confirm:
                return render_template(
                    "user/login.html", error="Passwords do not match.", email=email, action=action
                )
            register(email, password)
            flash("Account created!", "success")
        else:
            login(email, password)
            flash("Logged in!", "success")
        return redirect(url_for("dashboard"))
    except Exception as e:
        return render_template("user/login.html", error=str(e), email=email, action=action)


@app.route("/logout", methods=["POST"])
def logout():
    auth_file = ROOT / "config" / "server_auth.json"
    if auth_file.exists():
        auth_file.unlink()
    try:
        set_setting("onboarding_done", "false")
    except Exception:
        pass
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login_page"))


@app.route("/")
def dashboard():
    ctx = _base_context("dashboard")
    try:
        from utils.local_db import get_all_posts, get_approved_unposted_drafts, get_campaigns, get_earnings_summary, get_notifications, get_pending_drafts, get_scheduled_posts

        campaigns = get_campaigns()
        active_count = len(
            [c for c in campaigns if c.get("status") in ("assigned", "content_generated", "approved")]
        )
        all_posts = get_all_posts()
        # Filter to current month for "Posts This Month" stat
        from datetime import datetime
        current_month = datetime.now().strftime("%Y-%m")
        posts_this_month = [p for p in all_posts if (p.get("posted_at") or "").startswith(current_month)]
        # Try server API for earnings (source of truth), fall back to local
        try:
            from utils.server_client import get_earnings as _get_server_earnings
            earnings = _get_server_earnings()
        except Exception:
            earnings = get_earnings_summary()

        # Get invitations count
        try:
            from utils.server_client import get_invitations

            invitations = get_invitations()
            inv_count = len(invitations)
        except Exception:
            inv_count = 0

        # Platform health
        platforms = {}
        for p in ["x", "linkedin", "facebook", "reddit"]:
            profile_dir = ROOT / "profiles" / f"{p}-profile"
            connected = profile_dir.exists() and any(profile_dir.iterdir()) if profile_dir.exists() else False
            platforms[p] = {
                "connected": connected,
                "health": "green" if connected else "red",
            }

        # Activity feed — recent notifications from background agent
        activity_feed = get_notifications(limit=15)

        # Smart alerts
        alerts = []
        # Check for failed posts
        try:
            failed_posts = get_scheduled_posts("failed")
            if failed_posts:
                alerts.append({"type": "danger", "msg": f"{len(failed_posts)} post(s) failed to publish. Check Posts tab for details."})
        except Exception:
            pass
        # Check for disconnected platforms
        disconnected = [p for p, info in platforms.items() if not info["connected"]]
        if disconnected:
            alerts.append({"type": "warning", "msg": f"Platform(s) not connected: {', '.join(disconnected)}. Go to Settings to connect."})
        # Check for pending invitations
        if inv_count > 0:
            alerts.append({"type": "info", "msg": f"You have {inv_count} campaign invitation(s) waiting for your response."})

        # Draft counts
        drafts_pending_review = get_pending_drafts()
        drafts_ready_to_post = get_approved_unposted_drafts()
        review_count = len(drafts_pending_review)
        ready_count = len(drafts_ready_to_post)

        if review_count > 0:
            alerts.append({"type": "info", "msg": f"{review_count} draft(s) waiting for your review."})
        if ready_count > 0:
            alerts.append({"type": "info", "msg": f"{ready_count} approved draft(s) ready to post."})

        ctx.update(
            {
                "active_campaigns": active_count,
                "invitation_count": inv_count,
                "draft_review_count": review_count,
                "draft_ready_count": ready_count,
                "post_count": len(posts_this_month),
                "total_earned": earnings.get("total_earned", 0),
                "platforms": platforms,
                "activity_feed": activity_feed,
                "alerts": alerts,
            }
        )
    except Exception as e:
        logger.error("Dashboard error: %s", e)
        ctx.update(
            {
                "active_campaigns": 0,
                "invitation_count": 0,
                "draft_review_count": 0,
                "draft_ready_count": 0,
                "post_count": 0,
                "total_earned": 0,
                "platforms": {},
            }
        )

    return render_template("user/dashboard.html", **ctx)


# ── Onboarding routes ────────────────────────────────────────────


@app.route("/onboarding")
def onboarding_page():
    # Check which platforms are connected
    platforms = {}
    for p in ["x", "linkedin", "facebook", "reddit"]:
        profile_dir = ROOT / "profiles" / f"{p}-profile"
        platforms[p] = (
            profile_dir.exists() and any(profile_dir.iterdir())
            if profile_dir.exists()
            else False
        )

    # Get scraped profiles
    scraped_profiles = {}
    try:
        from utils.local_db import get_all_scraped_profiles

        for sp in get_all_scraped_profiles():
            scraped_profiles[sp["platform"]] = sp
    except Exception:
        pass

    # Get current settings
    auth = _load_auth()

    # Extract AI-detected niches from scraped profiles
    detected_niches = set()
    for sp_data in scraped_profiles.values():
        ai_niches_raw = sp_data.get("ai_niches", "[]")
        try:
            niches_list = json.loads(ai_niches_raw) if isinstance(ai_niches_raw, str) else ai_niches_raw
            for n in (niches_list or []):
                detected_niches.add(n.lower())
        except (json.JSONDecodeError, TypeError):
            pass

    # Auto-detect region from IP geolocation
    detected_region = get_setting("audience_region") or ""
    if not detected_region:
        try:
            import httpx
            geo = httpx.get("https://ipapi.co/json/", timeout=5).json()
            country = (geo.get("country_code") or "").upper()
            region_map = {
                "US": "us", "GB": "uk", "IN": "india",
                "DE": "eu", "FR": "eu", "IT": "eu", "ES": "eu", "NL": "eu", "BE": "eu", "AT": "eu", "PT": "eu", "IE": "eu", "SE": "eu", "FI": "eu", "DK": "eu", "PL": "eu", "CZ": "eu", "RO": "eu", "GR": "eu",
                "BR": "latam", "MX": "latam", "AR": "latam", "CO": "latam", "CL": "latam", "PE": "latam",
                "SG": "sea", "TH": "sea", "VN": "sea", "PH": "sea", "MY": "sea", "ID": "sea",
            }
            detected_region = region_map.get(country, "global")
            logger.info("Auto-detected region: %s (country=%s)", detected_region, country)
        except Exception as e:
            logger.debug("Region auto-detection failed: %s", e)
            detected_region = "global"
    region_labels = {
        "global": "Global",
        "us": "United States",
        "uk": "United Kingdom",
        "india": "India",
        "eu": "European Union",
        "latam": "Latin America",
        "sea": "Southeast Asia",
    }
    detected_region_label = region_labels.get(detected_region, detected_region.title())

    return render_template(
        "user/onboarding.html",
        email=auth.get("email", ""),
        platforms=platforms,
        scraped_profiles=scraped_profiles,
        detected_niches=list(detected_niches),
        current_mode=get_setting("mode", "semi_auto") or "semi_auto",
        detected_region=detected_region,
        detected_region_label=detected_region_label,
    )


_scraping_platforms = set()  # Track which platforms are currently being scraped


@app.route("/api/scraping-status")
def api_scraping_status():
    """JSON endpoint: which platforms are currently being scraped."""
    return jsonify({"scraping": list(_scraping_platforms)})


@app.route("/api/test-api-key", methods=["POST"])
@csrf.exempt
def api_test_api_key():
    """Test an AI provider API key by making a minimal API call."""
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "").lower()
    key = data.get("key", "").strip()

    if not provider or not key:
        return jsonify({"valid": False, "error": "Missing provider or key"})

    try:
        if provider == "gemini":
            from google import genai

            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents="Say 'ok' in one word.",
            )
            _ = response.text
            return jsonify({"valid": True})

        elif provider == "mistral":
            from mistralai.client import Mistral

            client = Mistral(api_key=key)
            response = client.chat.complete(
                model="mistral-small-latest",
                messages=[{"role": "user", "content": "Say 'ok' in one word."}],
            )
            _ = response.choices[0].message.content
            return jsonify({"valid": True})

        elif provider == "groq":
            from groq import Groq

            client = Groq(api_key=key)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "Say 'ok' in one word."}],
            )
            _ = response.choices[0].message.content
            return jsonify({"valid": True})

        else:
            return jsonify({"valid": False, "error": f"Unknown provider: {provider}"})

    except Exception as e:
        error_msg = str(e)
        # Rate limit / quota errors = key is valid, just temporarily exhausted
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower() or "rate" in error_msg.lower():
            return jsonify({"valid": True, "warning": "Key valid (quota temporarily exceeded — will work when quota resets)"})
        # Auth errors = invalid key
        if "401" in error_msg or "Unauthorized" in error_msg or "invalid" in error_msg.lower():
            error_msg = "Invalid API key"
        elif "403" in error_msg or "Forbidden" in error_msg:
            error_msg = "Access denied — check your key"
        elif len(error_msg) > 100:
            error_msg = error_msg[:100] + "..."
        return jsonify({"valid": False, "error": error_msg})


@app.route("/onboarding/connect/<platform>", methods=["POST"])
def onboarding_connect(platform):
    """Launch browser login, then auto-scrape when user closes it."""
    # If this platform is currently being scraped, wait for it to finish
    if platform in _scraping_platforms:
        flash(f"{platform} is still being scraped from the previous login. Please wait a moment and try again.", "warning")
        return redirect(url_for("onboarding_page"))

    def _connect_scrape_classify():
        import subprocess as sp
        import asyncio as aio
        import time

        # Wait for any ongoing scrape of this platform to finish (safety)
        for _ in range(30):
            if platform not in _scraping_platforms:
                break
            time.sleep(1)

        # Kill any browser process using this platform's profile directory.
        # The background agent's session health check or a stale scraper may
        # have locked the profile dir via Playwright persistent context.
        # Without this, login_setup.py crashes (TargetClosedError).
        profile_dir = ROOT / "profiles" / f"{platform}-profile"
        lock_file = profile_dir / "SingletonLock"
        logger.info("Connect %s: checking for profile lock at %s", platform, lock_file)

        # Method 1: Remove the Chrome singleton lock file
        if lock_file.exists():
            try:
                lock_file.unlink()
                logger.info("Connect %s: removed SingletonLock file", platform)
            except Exception as e:
                logger.warning("Connect %s: could not remove SingletonLock: %s", platform, e)

        # Method 2: Kill ALL chrome.exe processes that have this profile in their command line
        try:
            # Use PowerShell for more reliable process finding than wmic
            ps_cmd = f'Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like "*{platform}-profile*" -and $_.Name -eq "chrome.exe" }} | Select-Object -ExpandProperty ProcessId'
            result = sp.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                pid = line.strip()
                if pid.isdigit():
                    sp.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, timeout=5)
                    logger.info("Connect %s: killed chrome PID %s (tree kill)", platform, pid)
        except Exception as e:
            logger.debug("Connect %s: powershell process kill failed: %s", platform, e)

        # Wait a moment for profile dir to be fully released
        time.sleep(1)

        # Block until user closes the browser
        proc = sp.run(
            [sys.executable, str(ROOT / "scripts" / "login_setup.py"), platform],
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            logger.error("login_setup.py failed for %s (exit code %d). Resetting profile and retrying...", platform, proc.returncode)
            # Profile may be corrupted — reset it and retry once
            import shutil
            backup = profile_dir.parent / f"{platform}-profile-backup"
            try:
                if backup.exists():
                    shutil.rmtree(backup)
                profile_dir.rename(backup)
                profile_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Connect %s: reset corrupted profile (backed up to %s)", platform, backup)
                # Retry with fresh profile
                proc = sp.run(
                    [sys.executable, str(ROOT / "scripts" / "login_setup.py"), platform],
                    cwd=str(ROOT),
                )
                if proc.returncode != 0:
                    logger.error("login_setup.py still failed for %s after profile reset (exit code %d)", platform, proc.returncode)
            except Exception as e:
                logger.error("Connect %s: profile reset failed: %s", platform, e)

        # Browser closed — verify login was successful by checking for session cookies
        profile_dir_check = ROOT / "profiles" / f"{platform}-profile"
        has_session = False
        if profile_dir_check.exists():
            # Check for Chromium session files that indicate a successful login
            cookie_files = list(profile_dir_check.glob("**/Cookies")) + list(profile_dir_check.glob("**/Default/Cookies"))
            state_files = list(profile_dir_check.glob("**/Local State"))
            has_session = bool(cookie_files or state_files) and any(profile_dir_check.iterdir())

        if not has_session:
            logger.warning("Connect %s: no session data found after login — user may not have logged in", platform)
            from utils.local_db import add_notification
            add_notification("warning", f"{platform.title()} Login Incomplete", f"No login session detected for {platform}. Please try connecting again and make sure to log in before closing the browser.")
        else:
            # Scrape this platform
            _scraping_platforms.add(platform)
            try:
                from utils.profile_scraper import scrape_all_profiles
                aio.run(scrape_all_profiles([platform]))
                logger.info("Auto-scraped %s after connect", platform)
                from utils.local_db import add_notification
                add_notification("success", f"{platform.title()} Connected", f"Successfully connected to {platform} and scraped your profile.")
            except Exception as e:
                logger.error("Auto-scrape failed for %s: %s", platform, e)
                from utils.local_db import add_notification
                add_notification("warning", f"{platform.title()} Scrape Failed", f"Connected to {platform} but profile scraping failed: {str(e)[:80]}")
            finally:
                _scraping_platforms.discard(platform)

    threading.Thread(target=_connect_scrape_classify, daemon=True).start()
    flash(f"Browser opened for {platform}. Log in and close the browser — profile will be scraped automatically.", "info")
    return redirect(url_for("onboarding_page"))


@app.route("/onboarding/scrape", methods=["POST"])
def onboarding_scrape():
    import asyncio

    from utils.profile_scraper import scrape_all_profiles

    connected = [
        p
        for p in ["x", "linkedin", "facebook", "reddit"]
        if (ROOT / "profiles" / f"{p}-profile").exists()
        and any((ROOT / "profiles" / f"{p}-profile").iterdir())
    ]
    try:
        asyncio.run(scrape_all_profiles(connected))
        flash("Profiles scraped successfully!", "success")
    except Exception as e:
        flash(f"Scraping error: {e}", "error")
    return redirect(url_for("onboarding_page"))


@app.route("/onboarding/save", methods=["POST"])
def onboarding_save():
    niches = request.form.getlist("niches")
    region = request.form.get("region", "global")
    mode = request.form.get("mode", "semi_auto")
    if mode not in ("semi_auto", "full_auto"):
        mode = "semi_auto"

    # Save API keys to local_db
    for key_name in ("gemini_api_key", "mistral_api_key", "groq_api_key"):
        key_val = request.form.get(key_name, "").strip()
        if key_val:
            set_setting(key_name, key_val)

    # Save locally
    set_setting("mode", mode)
    set_setting("audience_region", region)
    set_setting("onboarding_done", "true")

    # Sync to server — include full scraped profile data for AI matching
    try:
        from utils.server_client import update_profile
        from utils.local_db import get_all_scraped_profiles

        platforms_dict = {}
        follower_counts = {}
        for p in ["x", "linkedin", "facebook", "reddit"]:
            profile_dir = ROOT / "profiles" / f"{p}-profile"
            if profile_dir.exists() and any(profile_dir.iterdir()):
                platforms_dict[p] = True
                fc = request.form.get(f"followers_{p}", "0")
                follower_counts[p] = int(fc) if fc.isdigit() else 0

        # Build scraped_profiles dict with all data for server-side AI matching
        scraped_profiles_dict = {}
        for sp in get_all_scraped_profiles():
            platform = sp["platform"]
            profile_entry = {
                "display_name": sp.get("display_name"),
                "bio": sp.get("bio"),
                "follower_count": sp.get("follower_count", 0),
                "following_count": sp.get("following_count", 0),
                "engagement_rate": sp.get("engagement_rate", 0.0),
                "posting_frequency": sp.get("posting_frequency", 0.0),
                "profile_pic_url": sp.get("profile_pic_url"),
            }
            # Parse recent_posts from JSON string
            posts_raw = sp.get("recent_posts", "[]")
            if isinstance(posts_raw, str):
                try:
                    profile_entry["recent_posts"] = json.loads(posts_raw)
                except (json.JSONDecodeError, TypeError):
                    profile_entry["recent_posts"] = []
            else:
                profile_entry["recent_posts"] = posts_raw or []

            # Parse profile_data (extended fields) from JSON string
            pd_raw = sp.get("profile_data")
            if pd_raw and isinstance(pd_raw, str):
                try:
                    profile_entry["profile_data"] = json.loads(pd_raw)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(pd_raw, dict):
                profile_entry["profile_data"] = pd_raw

            scraped_profiles_dict[platform] = profile_entry

        update_profile(
            platforms=platforms_dict,
            follower_counts=follower_counts,
            niche_tags=niches,
            audience_region=region,
            mode=mode,
            scraped_profiles=scraped_profiles_dict,
        )
        logger.info("Synced scraped profiles to server: %s", list(scraped_profiles_dict.keys()))
    except Exception as e:
        logger.error("Failed to sync profile: %s", e)

    # Start background agent now that onboarding is complete
    try:
        start_agent()
    except Exception as e:
        logger.error("Failed to start background agent: %s", e)

    flash("Setup complete! Welcome to Amplifier.", "success")
    return redirect(url_for("dashboard"))


# ── Campaign routes ──────────────────────────────────────────────


@app.route("/campaigns")
def campaigns():
    try:
        return _campaigns_impl()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("Campaigns route error:\n%s", tb)
        return f"<h1>Campaigns Error</h1><pre>{tb}</pre>", 500


def _campaigns_impl():
    ctx = _base_context("campaigns")

    # Get invitations from server
    invitations = []
    try:
        from utils.server_client import get_invitations

        invitations = get_invitations()
    except Exception as e:
        logger.error("Failed to get invitations: %s", e)

    # Get local campaigns by status
    from utils.local_db import get_campaigns, get_todays_drafts

    all_campaigns = get_campaigns()

    # Search filter
    search_query = request.args.get("q", "").strip().lower()
    if search_query:
        all_campaigns = [c for c in all_campaigns if search_query in (c.get("title") or "").lower()]

    active = [
        c
        for c in all_campaigns
        if c.get("status") in ("assigned", "content_generated", "approved", "active")
    ]
    completed = [
        c for c in all_campaigns if c.get("status") in ("posted", "skipped")
    ]

    # Add today's draft summary to each active campaign
    platforms = ["x", "linkedin", "facebook", "reddit"]
    for c in active:
        today_drafts = get_todays_drafts(c.get("server_id"))
        pending_count = sum(1 for d in today_drafts if d.get("approved") == 0)
        approved_count = sum(1 for d in today_drafts if d.get("approved") == 1)
        posted_count = sum(1 for d in today_drafts if d.get("posted") == 1)
        total_platforms = len(platforms)

        if not today_drafts:
            c["today_summary"] = "Generating content..."
        elif posted_count > 0:
            c["today_summary"] = f"Today: {posted_count}/{total_platforms} posted"
        elif approved_count == len(today_drafts) and approved_count > 0:
            c["today_summary"] = "Today: all approved"
        elif pending_count > 0:
            c["today_summary"] = f"Today: {pending_count}/{total_platforms} pending review"
        else:
            c["today_summary"] = f"Today: {approved_count} approved"

    # Generate a hash of the current state so frontend can detect changes
    import hashlib
    hash_input = f"{len(invitations)}:{len(active)}:{len(completed)}"
    for c in active:
        hash_input += f":{c.get('server_id')}:{c.get('status')}"
        today_drafts = get_todays_drafts(c.get("server_id"))
        hash_input += f":{len(today_drafts)}"
    campaign_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]

    ctx.update(
        {
            "invitations": invitations,
            "active_campaigns": active,
            "completed_campaigns": completed,
            "campaign_hash": campaign_hash,
        }
    )
    return render_template("user/campaigns.html", **ctx)


@app.route("/api/campaigns-hash")
def campaigns_hash():
    """Return a hash of current campaign state for auto-reload detection."""
    from utils.local_db import get_campaigns, get_todays_drafts
    import hashlib
    all_campaigns = get_campaigns()
    active = [c for c in all_campaigns if c.get("status") in ("assigned", "content_generated", "approved", "active")]
    hash_input = f"{len(all_campaigns)}:{len(active)}"
    for c in active:
        hash_input += f":{c.get('server_id')}:{c.get('status')}"
        today_drafts = get_todays_drafts(c.get("server_id"))
        hash_input += f":{len(today_drafts)}"
    campaign_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]
    return jsonify({"hash": campaign_hash})


@app.route("/campaigns/poll", methods=["POST"])
def campaigns_poll():
    try:
        from utils.local_db import upsert_campaign
        from utils.server_client import poll_campaigns

        campaigns_list = poll_campaigns()
        for c in campaigns_list:
            upsert_campaign(c)
        flash(f"Found {len(campaigns_list)} campaign(s).", "success")
    except Exception as e:
        flash(f"Poll failed: {e}", "error")
    return redirect(url_for("campaigns"))


@app.route("/invitations/<int:assignment_id>/accept", methods=["POST"])
def accept_invitation(assignment_id):
    try:
        from utils.server_client import accept_invitation as server_accept
        from utils.local_db import _get_db as get_db_connection

        server_accept(assignment_id)
        # Update local campaign status so content generation kicks in
        conn = get_db_connection()
        conn.execute(
            "UPDATE local_campaign SET status = 'assigned' WHERE assignment_id = ?",
            (assignment_id,),
        )
        conn.commit()
        conn.close()
        flash("Campaign accepted! Content will be generated shortly.", "success")
    except Exception as e:
        flash(f"Accept failed: {e}", "error")
    return redirect(url_for("campaigns"))


@app.route("/invitations/<int:assignment_id>/reject", methods=["POST"])
def reject_invitation(assignment_id):
    try:
        from utils.server_client import reject_invitation as server_reject
        from utils.local_db import _get_db as get_db_connection

        reason = request.form.get("decline_reason", "").strip() or None
        server_reject(assignment_id, reason=reason)
        # Remove from local DB
        conn = get_db_connection()
        conn.execute("DELETE FROM local_campaign WHERE assignment_id = ?", (assignment_id,))
        conn.commit()
        conn.close()
        flash("Campaign rejected.", "info")
    except Exception as e:
        flash(f"Reject failed: {e}", "error")
    return redirect(url_for("campaigns"))


@app.route("/campaigns/<int:campaign_id>")
def campaign_detail(campaign_id):
    ctx = _base_context("campaigns")

    from utils.local_db import (
        get_campaign, get_pending_drafts, get_all_drafts,
        get_todays_drafts, get_posts_for_campaign,
    )

    campaign = get_campaign(campaign_id)
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("campaigns"))

    # Parse content JSON (backward compat for old campaigns)
    content = {}
    if campaign.get("content"):
        try:
            content = json.loads(campaign["content"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse payout_rules from JSON string to dict
    payout_rules = {}
    if campaign.get("payout_rules"):
        try:
            pr = campaign["payout_rules"]
            payout_rules = json.loads(pr) if isinstance(pr, str) else pr
        except (json.JSONDecodeError, TypeError):
            pass

    # Get drafts from agent_draft table
    all_drafts = get_all_drafts(campaign_id)
    today_drafts = get_todays_drafts(campaign_id)
    pending_drafts = get_pending_drafts(campaign_id)

    # Group today's drafts by platform
    today_by_platform = {}
    for d in today_drafts:
        today_by_platform[d.get("platform", "")] = d

    # Group past drafts by date (excluding today)
    from datetime import datetime as _dt
    today_str = _dt.now().strftime('%Y-%m-%d')
    past_by_date = {}
    for d in all_drafts:
        date_str = (d.get("created_at") or "")[:10]
        if date_str == today_str:
            continue
        if date_str not in past_by_date:
            past_by_date[date_str] = []
        past_by_date[date_str].append(d)

    # Sort dates descending
    sorted_past_dates = sorted(past_by_date.keys(), reverse=True)

    # Get posts for this campaign (for post URLs in past drafts)
    campaign_posts = get_posts_for_campaign(campaign_id)
    posts_by_platform_date = {}
    for p in campaign_posts:
        key = f"{p.get('platform', '')}_{(p.get('posted_at') or '')[:10]}"
        posts_by_platform_date[key] = p

    # Determine if this is a new-style (draft-based) or old-style (content-based) campaign
    use_drafts = len(all_drafts) > 0

    # Hash for auto-reload detection
    import hashlib
    detail_hash_input = f"{campaign.get('status')}:{len(today_drafts)}:{len(all_drafts)}"
    for d in today_drafts:
        detail_hash_input += f":{d.get('id')}:{d.get('approved')}"
    detail_hash = hashlib.md5(detail_hash_input.encode()).hexdigest()[:12]

    ctx.update(
        {
            "campaign": campaign,
            "content": content,
            "payout_rules": payout_rules,
            "platforms": ["x", "linkedin", "facebook", "reddit"],
            "use_drafts": use_drafts,
            "today_by_platform": today_by_platform,
            "past_by_date": past_by_date,
            "sorted_past_dates": sorted_past_dates,
            "pending_drafts": pending_drafts,
            "today_str": today_str,
            "posts_by_platform_date": posts_by_platform_date,
            "detail_hash": detail_hash,
        }
    )
    return render_template("user/campaign_detail.html", **ctx)


@app.route("/api/campaign-detail-hash/<int:campaign_id>")
def campaign_detail_hash(campaign_id):
    """Return hash of campaign detail state for auto-reload."""
    from utils.local_db import get_campaign, get_todays_drafts, get_all_drafts
    import hashlib
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({"hash": ""})
    today_drafts = get_todays_drafts(campaign_id)
    all_drafts = get_all_drafts(campaign_id)
    h = f"{campaign.get('status')}:{len(today_drafts)}:{len(all_drafts)}"
    for d in today_drafts:
        h += f":{d.get('id')}:{d.get('approved')}"
    return jsonify({"hash": hashlib.md5(h.encode()).hexdigest()[:12]})


@app.route("/campaigns/<int:campaign_id>/generate", methods=["POST"])
def generate_content(campaign_id):
    import asyncio

    from utils.content_generator import ContentGenerator
    from utils.local_db import get_campaign, update_campaign_status

    campaign = get_campaign(campaign_id)
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("campaigns"))

    try:
        gen = ContentGenerator()
        result = asyncio.run(
            gen.generate(
                {
                    "campaign_id": campaign_id,
                    "title": campaign.get("title", ""),
                    "brief": campaign.get("brief", ""),
                    "content_guidance": campaign.get("content_guidance", ""),
                    "assets": campaign.get("assets", "{}"),
                    "disclaimer_text": campaign.get("disclaimer_text"),
                },
                enabled_platforms=["x", "linkedin", "facebook", "reddit"],
            )
        )

        if result:
            content = result.get("content", result) if isinstance(result, dict) else result
            update_campaign_status(campaign_id, "content_generated", json.dumps(content))
            flash("Content generated! Review and approve below.", "success")
        else:
            flash("Content generation failed -- no result returned.", "error")
    except Exception as e:
        flash(f"Generation error: {e}", "error")

    return redirect(url_for("campaign_detail", campaign_id=campaign_id))


@app.route("/campaigns/<int:campaign_id>/regenerate", methods=["POST"])
def regenerate_drafts(campaign_id):
    """Regenerate today's drafts for a campaign. Clears existing unapproved drafts and creates new ones."""
    import asyncio

    from utils.content_generator import ContentGenerator
    from utils.local_db import (
        get_campaign, get_todays_drafts, add_draft, get_all_drafts,
        approve_draft, add_scheduled_post, get_setting,
    )

    campaign = get_campaign(campaign_id)
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("campaigns"))

    platforms = ["x", "linkedin", "facebook", "reddit"]
    platform = request.form.get("platform", "")  # Optional: regenerate for specific platform

    try:
        # Delete today's unapproved drafts for this campaign
        from utils.local_db import _get_db
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        conn = _get_db()
        if platform:
            # Regenerate single platform
            conn.execute(
                "DELETE FROM agent_draft WHERE campaign_server_id = ? AND platform = ? AND approved = 0 AND created_at LIKE ?",
                (campaign_id, platform, f"{today}%"),
            )
            regen_platforms = [platform]
        else:
            # Regenerate all platforms
            conn.execute(
                "DELETE FROM agent_draft WHERE campaign_server_id = ? AND approved = 0 AND created_at LIKE ?",
                (campaign_id, f"{today}%"),
            )
            regen_platforms = platforms
        conn.commit()
        conn.close()

        # Get previous drafts for anti-repetition
        previous = get_all_drafts(campaign_id)
        previous_hooks = []
        for d in previous[:12]:
            text = d.get("draft_text", "")
            if text:
                first_line = text.split("\n")[0][:80]
                previous_hooks.append(first_line)

        unique_dates = set(d.get("created_at", "")[:10] for d in previous if d.get("created_at"))
        day_number = len(unique_dates) + 1

        gen = ContentGenerator()
        campaign_data = {
            "campaign_id": campaign_id,
            "title": campaign.get("title", ""),
            "brief": campaign.get("brief", ""),
            "content_guidance": campaign.get("content_guidance", ""),
            "assets": campaign.get("assets", {}),
            "disclaimer_text": campaign.get("disclaimer_text"),
        }

        result = asyncio.run(
            gen.research_and_generate(
                campaign_data,
                enabled_platforms=regen_platforms,
                day_number=day_number,
                previous_hooks=previous_hooks,
            )
        )

        if result:
            content = result.get("content", result) if isinstance(result, dict) else result
            new_count = 0
            for p in regen_platforms:
                text = content.get(p, "")
                if text:
                    if isinstance(text, dict):
                        text = json.dumps(text)
                    add_draft(campaign_id, p, str(text), iteration=day_number)
                    new_count += 1

            flash(f"Regenerated {new_count} draft(s). Review them below.", "success")
            from utils.local_db import add_notification
            add_notification("content", "Drafts Regenerated", f"Regenerated {new_count} draft(s) for \"{campaign.get('title', '')}\".")
        else:
            flash("Regeneration failed — no content returned.", "error")

    except Exception as e:
        logger.error("Regeneration failed for campaign %s: %s", campaign_id, e)
        flash(f"Regeneration error: {e}", "error")

    return redirect(url_for("campaign_detail", campaign_id=campaign_id))


@app.route("/campaigns/<int:campaign_id>/approve", methods=["POST"])
def approve_content(campaign_id):
    from utils.local_db import get_campaign, update_campaign_status

    campaign = get_campaign(campaign_id)
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("campaigns"))

    # Collect edited content from form
    content = {}
    for platform in ["x", "linkedin", "facebook", "reddit"]:
        text = request.form.get(f"content_{platform}", "").strip()
        if text:
            if platform == "reddit":
                title = request.form.get(f"content_{platform}_title", "").strip()
                content[platform] = json.dumps({"title": title, "body": text})
            else:
                content[platform] = text

    update_campaign_status(campaign_id, "approved", json.dumps(content))

    # Update server assignment status
    try:
        from utils.server_client import update_assignment

        assignment_id = campaign.get("assignment_id")
        if assignment_id:
            update_assignment(assignment_id, "content_approved")
    except Exception as e:
        logger.error("Failed to update assignment: %s", e)

    flash("Content approved and queued for posting!", "success")
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))


@app.route("/campaigns/<int:campaign_id>/skip", methods=["POST"])
def skip_campaign(campaign_id):
    from utils.local_db import get_campaign, update_campaign_status

    campaign = get_campaign(campaign_id)
    if campaign:
        update_campaign_status(campaign_id, "skipped")

        try:
            from utils.server_client import update_assignment

            assignment_id = campaign.get("assignment_id")
            if assignment_id:
                update_assignment(assignment_id, "skipped")
        except Exception:
            pass

    flash("Campaign skipped.", "info")
    return redirect(url_for("campaigns"))


# ── Draft scheduling helper ──────────────────────────────────────


def _schedule_draft(draft: dict):
    """Schedule an approved draft into post_schedule for the background agent to execute."""
    from utils.local_db import add_scheduled_post, get_scheduled_posts
    from datetime import datetime, timedelta
    import random

    campaign_id = draft.get("campaign_id")
    platform = draft.get("platform", "")
    content = draft.get("draft_text", "")
    draft_id = draft.get("id")

    # Check if already scheduled
    existing = get_scheduled_posts("queued")
    for e in existing:
        if e.get("draft_id") == draft_id:
            return  # Already scheduled

    # Calculate scheduled time: next available slot with 30-min spacing
    now = datetime.now()
    # Find the latest scheduled time for any platform
    latest = now
    for e in existing:
        try:
            t = datetime.fromisoformat(e.get("scheduled_at", ""))
            if t > latest:
                latest = t
        except (ValueError, TypeError):
            pass

    # Schedule at least 5 min from now, 30 min after the last scheduled post
    earliest = max(now + timedelta(minutes=5), latest + timedelta(minutes=30))
    # Add random jitter (0-10 min)
    jitter = random.randint(0, 10)
    scheduled_at = earliest + timedelta(minutes=jitter)

    add_scheduled_post(
        campaign_server_id=campaign_id,
        platform=platform,
        scheduled_at=scheduled_at.isoformat(),
        content=content,
        image_path=draft.get("image_path"),
        draft_id=draft_id,
    )
    logger.info("Scheduled draft %d for %s at %s", draft_id, platform, scheduled_at.isoformat())


# ── Draft routes (daily content) ─────────────────────────────────


@app.route("/drafts/<int:draft_id>/image")
def draft_image(draft_id):
    """Serve a draft's generated image from the local filesystem."""
    from pathlib import Path
    from utils.local_db import get_draft
    draft = get_draft(draft_id)
    if draft and draft.get("image_path"):
        img_path = Path(draft["image_path"])
        if img_path.exists():
            return send_file(str(img_path))
    abort(404)


@app.route("/drafts/<int:draft_id>/approve", methods=["POST"])
def approve_single_draft(draft_id):
    from utils.local_db import approve_draft, get_draft, add_scheduled_post

    draft = get_draft(draft_id)
    if not draft:
        flash("Draft not found.", "error")
        return redirect(url_for("campaigns"))

    approve_draft(draft_id)
    _schedule_draft(draft)
    flash("Draft approved and scheduled for posting!", "success")
    return redirect(url_for("campaign_detail", campaign_id=draft["campaign_id"]))


@app.route("/drafts/<int:draft_id>/reject", methods=["POST"])
def reject_single_draft(draft_id):
    from utils.local_db import reject_draft, get_draft

    draft = get_draft(draft_id)
    if not draft:
        flash("Draft not found.", "error")
        return redirect(url_for("campaigns"))

    reject_draft(draft_id)
    flash("Draft rejected.", "info")
    return redirect(url_for("campaign_detail", campaign_id=draft["campaign_id"]))


@app.route("/drafts/<int:draft_id>/restore", methods=["POST"])
def restore_single_draft(draft_id):
    from utils.local_db import get_draft

    draft = get_draft(draft_id)
    if not draft:
        flash("Draft not found.", "error")
        return redirect(url_for("campaigns"))

    # Set approved back to 0 (pending)
    conn = __import__("sqlite3").connect(str(ROOT / "data" / "local.db"))
    conn.execute("UPDATE agent_draft SET approved = 0 WHERE id = ?", (draft_id,))
    conn.commit()
    conn.close()

    flash("Draft restored to pending review.", "success")
    return redirect(url_for("campaign_detail", campaign_id=draft["campaign_id"]))


@app.route("/drafts/<int:draft_id>/unapprove", methods=["POST"])
def unapprove_single_draft(draft_id):
    from utils.local_db import get_draft

    draft = get_draft(draft_id)
    if not draft:
        flash("Draft not found.", "error")
        return redirect(url_for("campaigns"))

    # Only unapprove if approved and not yet posted
    if draft.get("approved") == 1 and draft.get("posted") != 1:
        conn = __import__("sqlite3").connect(str(ROOT / "data" / "local.db"))
        # Set back to pending
        conn.execute("UPDATE agent_draft SET approved = 0 WHERE id = ?", (draft_id,))
        # Remove from post schedule
        conn.execute("DELETE FROM post_schedule WHERE draft_id = ?", (draft_id,))
        conn.commit()
        conn.close()
        flash("Draft unapproved and removed from posting schedule.", "success")
    else:
        flash("Cannot unapprove — draft is already posted or not approved.", "warning")

    return redirect(url_for("campaign_detail", campaign_id=draft["campaign_id"]))


@app.route("/drafts/<int:draft_id>/edit", methods=["POST"])
def edit_single_draft(draft_id):
    from utils.local_db import update_draft_text, get_draft

    draft = get_draft(draft_id)
    if not draft:
        flash("Draft not found.", "error")
        return redirect(url_for("campaigns"))

    new_text = request.form.get("draft_text", "").strip()
    if new_text:
        update_draft_text(draft_id, new_text)
        flash("Draft updated.", "success")

    return redirect(url_for("campaign_detail", campaign_id=draft["campaign_id"]))


@app.route("/campaigns/<int:campaign_id>/approve-all", methods=["POST"])
def approve_all_drafts(campaign_id):
    from utils.local_db import get_todays_drafts, approve_draft, update_draft_text

    today_drafts = get_todays_drafts(campaign_id)
    approved_count = 0

    for draft in today_drafts:
        if draft.get("approved") == 0:
            # Check if user edited the text via form
            edited_text = request.form.get(f"draft_text_{draft['id']}", "").strip()
            if edited_text and edited_text != draft.get("draft_text", ""):
                update_draft_text(draft["id"], edited_text)
                draft["draft_text"] = edited_text
            approve_draft(draft["id"])
            _schedule_draft(draft)
            approved_count += 1

    flash(f"Approved and scheduled {approved_count} draft(s) for posting!", "success")
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))


# ── Posts routes ──────────────────────────────────────────────────


@app.route("/posts")
def posts():
    ctx = _base_context("posts")
    try:
        from utils.local_db import get_all_posts
        from datetime import datetime, timezone, timedelta

        all_posts = get_all_posts()

        # Convert posted_at from UTC to local time, and clean up Reddit JSON display
        local_tz = datetime.now(timezone.utc).astimezone().tzinfo
        for post in all_posts:
            # UTC → local timezone
            if post.get("posted_at"):
                try:
                    ts = post["posted_at"]
                    # Parse UTC timestamp (stored with or without +00:00)
                    ts_clean = ts.replace("+00:00", "").replace("Z", "")
                    dt_utc = datetime.fromisoformat(ts_clean).replace(tzinfo=timezone.utc)
                    dt_local = dt_utc.astimezone(local_tz)
                    post["posted_at"] = dt_local.isoformat()
                except Exception:
                    pass  # keep original if parsing fails

            # Reddit: show title instead of raw JSON
            content = post.get("content", "")
            if content and content.strip().startswith("{"):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and "title" in parsed:
                        post["content"] = parsed["title"]
                except (json.JSONDecodeError, TypeError):
                    pass

        ctx["posts"] = all_posts
    except Exception as e:
        logger.error("Posts route error: %s", e)
        ctx["posts"] = []
    return render_template("user/posts.html", **ctx)


# ── Earnings routes ──────────────────────────────────────────────


@app.route("/earnings")
def earnings():
    ctx = _base_context("earnings")
    try:
        from utils.server_client import get_earnings

        server_earnings = get_earnings()
    except Exception as e:
        logger.error("Failed to get server earnings: %s", e)
        server_earnings = {
            "total_earned": 0,
            "current_balance": 0,
            "pending": 0,
            "per_campaign": [],
            "per_platform": {},
            "payout_history": [],
        }

    ctx.update(
        {
            "total_earned": server_earnings.get("total_earned", 0),
            "current_balance": server_earnings.get("current_balance", 0),
            "pending": server_earnings.get("pending", 0),
            "per_campaign": server_earnings.get("per_campaign", []),
            "per_platform": server_earnings.get("per_platform", {}),
            "payout_history": server_earnings.get("payout_history", []),
        }
    )
    return render_template("user/earnings.html", **ctx)


@app.route("/earnings/withdraw", methods=["POST"])
def withdraw():
    amount = float(request.form.get("amount", 0))
    try:
        from utils.server_client import request_payout

        request_payout(amount)
        flash(f"Withdrawal of ${amount:.2f} requested!", "success")
    except Exception as e:
        flash(f"Withdrawal failed: {e}", "error")
    return redirect(url_for("earnings"))


# ── Settings routes ──────────────────────────────────────────────


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        mode = request.form.get("mode")
        region = request.form.get("region")
        niches = request.form.getlist("niches") or [
            n.strip()
            for n in request.form.get("niche_tags", "").split(",")
            if n.strip()
        ]

        if mode:
            if mode not in ("semi_auto", "full_auto"):
                mode = "semi_auto"
            set_setting("mode", mode)
        if region:
            set_setting("audience_region", region)

        # Save API keys if provided
        for key_name in ("gemini_api_key", "mistral_api_key", "groq_api_key"):
            key_val = request.form.get(key_name, "").strip()
            if key_val:
                set_setting(key_name, key_val)

        # Sync to server
        try:
            from utils.server_client import update_profile

            platforms_dict = {}
            follower_counts = {}
            for p in ["x", "linkedin", "facebook", "reddit"]:
                profile_dir = ROOT / "profiles" / f"{p}-profile"
                if profile_dir.exists() and any(profile_dir.iterdir()):
                    platforms_dict[p] = True
                    fc = request.form.get(f"followers_{p}", "0")
                    follower_counts[p] = int(fc) if fc.isdigit() else 0

            update_profile(
                platforms=platforms_dict,
                follower_counts=follower_counts,
                niche_tags=niches,
                audience_region=region,
                mode=mode,
            )
            flash("Settings saved.", "success")
        except Exception as e:
            logger.error("Failed to sync settings: %s", e)
            flash(f"Settings saved locally. Server sync failed: {e}", "error")

        return redirect(url_for("settings"))

    # GET
    ctx = _base_context("settings")

    # Platform connections
    platforms = {}
    for p in ["x", "linkedin", "facebook", "reddit"]:
        profile_dir = ROOT / "profiles" / f"{p}-profile"
        platforms[p] = (
            profile_dir.exists() and any(profile_dir.iterdir())
            if profile_dir.exists()
            else False
        )

    # Scraped profiles
    scraped_profiles = {}
    try:
        from utils.local_db import get_all_scraped_profiles

        for sp in get_all_scraped_profiles():
            scraped_profiles[sp["platform"]] = sp
    except Exception:
        pass

    # Current settings from server
    try:
        profile = get_profile()
    except Exception:
        profile = {}

    ctx.update(
        {
            "platforms": platforms,
            "scraped_profiles": scraped_profiles,
            "mode": get_setting("mode", "semi_auto") or "semi_auto",
            "region": get_setting("audience_region", "global") or "global",
            "niche_tags": profile.get("niche_tags", []) or [],
            "follower_counts": profile.get("follower_counts", {}) or {},
            "gemini_api_key": get_setting("gemini_api_key", ""),
            "mistral_api_key": get_setting("mistral_api_key", ""),
            "groq_api_key": get_setting("groq_api_key", ""),
        }
    )
    return render_template("user/settings.html", **ctx)


@app.route("/settings/connect/<platform>", methods=["POST"])
def settings_connect(platform):
    """Launch browser login, then auto-scrape when user closes it."""
    def _connect_and_scrape():
        import subprocess as sp
        import asyncio as aio
        sp.run(
            [sys.executable, str(ROOT / "scripts" / "login_setup.py"), platform],
            cwd=str(ROOT),
        )
        try:
            from utils.profile_scraper import scrape_all_profiles
            aio.run(scrape_all_profiles([platform]))
            logger.info("Auto-scraped %s after reconnect", platform)
        except Exception as e:
            logger.error("Auto-scrape failed for %s: %s", platform, e)

    threading.Thread(target=_connect_and_scrape, daemon=True).start()
    flash(
        f"Browser opened for {platform}. Log in and close the browser — profile will be scraped automatically.",
        "info",
    )
    return redirect(url_for("settings"))


@app.route("/settings/scrape", methods=["POST"])
def settings_scrape():
    import asyncio

    from utils.profile_scraper import scrape_all_profiles

    connected = [
        p
        for p in ["x", "linkedin", "facebook", "reddit"]
        if (ROOT / "profiles" / f"{p}-profile").exists()
        and any((ROOT / "profiles" / f"{p}-profile").iterdir())
    ]
    try:
        asyncio.run(scrape_all_profiles(connected))
        flash("Profiles refreshed!", "success")
    except Exception as e:
        flash(f"Scraping error: {e}", "error")
    return redirect(url_for("settings"))


# ── Background Agent ─────────────────────────────────────────────

_agent_loop = None
_agent_thread = None


def _run_agent_loop(loop):
    """Run asyncio event loop in a background thread."""
    import asyncio
    asyncio.set_event_loop(loop)
    loop.run_forever()


def start_agent():
    """Start the background agent in a daemon thread."""
    global _agent_loop, _agent_thread
    import asyncio
    from background_agent import start_background_agent

    if _agent_thread and _agent_thread.is_alive():
        logger.info("Background agent already running")
        return

    _agent_loop = asyncio.new_event_loop()
    _agent_thread = threading.Thread(target=_run_agent_loop, args=(_agent_loop,), daemon=True)
    _agent_thread.start()

    asyncio.run_coroutine_threadsafe(start_background_agent(), _agent_loop)
    logger.info("Background agent started in daemon thread")


def stop_agent():
    """Stop the background agent."""
    global _agent_loop, _agent_thread
    import asyncio
    from background_agent import stop_background_agent

    if _agent_loop and _agent_thread and _agent_thread.is_alive():
        asyncio.run_coroutine_threadsafe(stop_background_agent(), _agent_loop).result(timeout=10)
        _agent_loop.call_soon_threadsafe(_agent_loop.stop)
        _agent_thread.join(timeout=5)
        logger.info("Background agent stopped")
    _agent_loop = None
    _agent_thread = None


@app.route("/api/status")
def api_status():
    """JSON endpoint for agent status + draft counts (polled by frontend)."""
    from background_agent import get_agent
    from utils.local_db import get_approved_unposted_drafts, get_pending_drafts

    agent = get_agent()
    status = "running" if agent and agent.running else "stopped"
    pending_review = get_pending_drafts()
    ready_to_post = get_approved_unposted_drafts()
    return jsonify({
        "agent_status": status,
        "pending_drafts": len(pending_review),
        "ready_drafts": len(ready_to_post),
    })


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    # use_reloader spawns a child process — only start tray/agent in the child
    # (the parent is the reloader watcher, not the actual app)
    # With reloader disabled, this is always the main process
    is_main_process = True

    if is_main_process:
        # Start system tray icon (only in the actual app process)
        try:
            from utils.tray import start_tray, stop_tray, send_notification

            def _on_quit():
                """Called when user clicks Quit in tray menu."""
                try:
                    stop_agent()
                except Exception:
                    pass
                os._exit(0)

            start_tray(port=PORT, on_quit=_on_quit)
        except Exception as e:
            logger.warning("System tray not available: %s", e)

        # Start background agent if user is logged in and onboarded
        if is_logged_in() and get_setting("onboarding_done") == "true":
            try:
                start_agent()
            except Exception as e:
                logger.error("Failed to start background agent: %s", e)

        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    print(f"\n  Amplifier is running at http://localhost:{PORT}")
    print("  The app is in your system tray — keep it running for campaigns to work.\n")

    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
