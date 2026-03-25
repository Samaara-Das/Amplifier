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
    flash,
    jsonify,
    redirect,
    render_template,
    request,
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
        from utils.local_db import get_all_posts, get_campaigns, get_earnings_summary

        campaigns = get_campaigns()
        active_count = len(
            [c for c in campaigns if c.get("status") in ("assigned", "content_generated", "approved")]
        )
        posts = get_all_posts()
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

        ctx.update(
            {
                "active_campaigns": active_count,
                "invitation_count": inv_count,
                "post_count": len(posts),
                "total_earned": earnings.get("total_earned", 0),
                "platforms": platforms,
            }
        )
    except Exception as e:
        logger.error("Dashboard error: %s", e)
        ctx.update(
            {
                "active_campaigns": 0,
                "invitation_count": 0,
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

    return render_template(
        "user/onboarding.html",
        email=auth.get("email", ""),
        platforms=platforms,
        scraped_profiles=scraped_profiles,
        detected_niches=list(detected_niches),
        current_mode=get_setting("mode", "semi_auto") or "semi_auto",
        current_region=get_setting("audience_region", "global") or "global",
    )


@app.route("/onboarding/connect/<platform>", methods=["POST"])
def onboarding_connect(platform):
    """Launch browser login, then auto-scrape when user closes it."""
    def _connect_scrape_classify():
        import subprocess as sp
        import asyncio as aio
        # Block until user closes the browser
        sp.run(
            [sys.executable, str(ROOT / "scripts" / "login_setup.py"), platform],
            cwd=str(ROOT),
        )
        # Browser closed — scrape this platform, then run niche classification
        try:
            from utils.profile_scraper import scrape_all_profiles
            aio.run(scrape_all_profiles([platform]))
            logger.info("Auto-scraped %s after connect", platform)
        except Exception as e:
            logger.error("Auto-scrape failed for %s: %s", platform, e)

        # Run AI niche classification on all scraped profiles
        try:
            from utils.niche_classifier import classify_niches
            from utils.local_db import get_all_scraped_profiles, upsert_scraped_profile
            profiles_list = get_all_scraped_profiles()
            scraped = {}
            for p in profiles_list:
                posts = json.loads(p.get("recent_posts", "[]")) if p.get("recent_posts") else []
                scraped[p["platform"]] = {"bio": p.get("bio"), "recent_posts": posts}
            if scraped:
                niches = aio.run(classify_niches(scraped))
                if niches:
                    # Store niches in all scraped profiles
                    for p in profiles_list:
                        upsert_scraped_profile(
                            platform=p["platform"],
                            follower_count=p.get("follower_count", 0),
                            following_count=p.get("following_count", 0),
                            bio=p.get("bio"),
                            display_name=p.get("display_name"),
                            profile_pic_url=p.get("profile_pic_url"),
                            recent_posts=p.get("recent_posts", "[]"),
                            engagement_rate=p.get("engagement_rate", 0.0),
                            posting_frequency=p.get("posting_frequency", 0.0),
                            ai_niches=json.dumps(niches),
                        )
                    logger.info("AI niche classification: %s", niches)
        except Exception as e:
            logger.error("Niche classification failed: %s", e)

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

    # Save locally
    set_setting("mode", mode)
    set_setting("audience_region", region)
    set_setting("onboarding_done", "true")

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
    from utils.local_db import get_campaigns

    all_campaigns = get_campaigns()
    active = [
        c
        for c in all_campaigns
        if c.get("status") in ("assigned", "content_generated", "approved")
    ]
    completed = [
        c for c in all_campaigns if c.get("status") in ("posted", "skipped")
    ]

    ctx.update(
        {
            "invitations": invitations,
            "active_campaigns": active,
            "completed_campaigns": completed,
        }
    )
    return render_template("user/campaigns.html", **ctx)


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

        server_accept(assignment_id)
        flash("Campaign accepted!", "success")
    except Exception as e:
        flash(f"Accept failed: {e}", "error")
    return redirect(url_for("campaigns"))


@app.route("/invitations/<int:assignment_id>/reject", methods=["POST"])
def reject_invitation(assignment_id):
    try:
        from utils.server_client import reject_invitation as server_reject

        server_reject(assignment_id)
        flash("Campaign rejected.", "info")
    except Exception as e:
        flash(f"Reject failed: {e}", "error")
    return redirect(url_for("campaigns"))


@app.route("/campaigns/<int:campaign_id>")
def campaign_detail(campaign_id):
    ctx = _base_context("campaigns")

    from utils.local_db import get_campaign

    campaign = get_campaign(campaign_id)
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("campaigns"))

    # Parse content JSON
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

    ctx.update(
        {
            "campaign": campaign,
            "content": content,
            "payout_rules": payout_rules,
            "platforms": ["x", "linkedin", "facebook", "reddit"],
        }
    )
    return render_template("user/campaign_detail.html", **ctx)


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


# ── Posts routes ──────────────────────────────────────────────────


@app.route("/posts")
def posts():
    ctx = _base_context("posts")
    try:
        from utils.local_db import get_all_posts

        all_posts = get_all_posts()
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
            set_setting("mode", mode)
        if region:
            set_setting("audience_region", region)

        # Save Gemini API key if provided
        gemini_key = request.form.get("gemini_api_key", "").strip()
        if gemini_key:
            set_setting("gemini_api_key", gemini_key)

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
    """JSON endpoint for agent status (polled by frontend)."""
    from background_agent import get_agent
    agent = get_agent()
    status = "running" if agent and agent.running else "stopped"
    return jsonify({"agent_status": status})


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    # Start background agent if user is logged in and onboarded
    if is_logged_in() and get_setting("onboarding_done") == "true":
        try:
            start_agent()
        except Exception as e:
            logger.error("Failed to start background agent: %s", e)

    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)
