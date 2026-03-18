"""Campaign dashboard — Flask app for viewing campaigns, reviewing content, tracking earnings."""

import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template_string, request, url_for
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / "config" / ".env")
os.environ.setdefault("AUTO_POSTER_ROOT", str(ROOT))

from utils.local_db import (
    init_db, get_campaigns, get_campaign, update_campaign_status,
    get_posts_for_campaign, get_earnings_summary, get_campaign_earnings,
    get_setting, set_setting,
)
from utils.server_client import is_logged_in, get_profile, get_earnings, poll_campaigns

app = Flask(__name__)

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="120">
    <title>Campaign Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #2a2a3a; }
        .header h1 { font-size: 24px; color: #fff; }
        .header-stats { display: flex; gap: 16px; }
        .stat-badge { background: #1a1a2e; padding: 8px 16px; border-radius: 8px; text-align: center; }
        .stat-value { font-size: 20px; font-weight: 700; color: #22c55e; }
        .stat-label { font-size: 11px; color: #666; margin-top: 2px; }
        .nav-tabs { display: flex; gap: 4px; margin-bottom: 20px; }
        .nav-tab { padding: 10px 20px; border-radius: 8px 8px 0 0; cursor: pointer; font-size: 14px; background: #12121e; color: #888; border: 1px solid #2a2a3a; border-bottom: none; }
        .nav-tab.active { background: #1a1a2e; color: #fff; border-color: #3b82f6; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .card { background: #1a1a2e; border-radius: 10px; padding: 20px; margin-bottom: 16px; border: 1px solid #2a2a3a; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .card-title { font-size: 18px; font-weight: 600; color: #fff; }
        .status-badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
        .status-assigned { background: #1e3a5f; color: #93c5fd; }
        .status-content_generated { background: #713f12; color: #fde68a; }
        .status-posted { background: #14532d; color: #86efac; }
        .status-skipped { background: #334155; color: #cbd5e1; }
        .brief-text { color: #aaa; font-size: 14px; line-height: 1.6; margin-bottom: 12px; max-height: 100px; overflow-y: auto; }
        .payout-info { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
        .payout-chip { background: #12121e; padding: 4px 10px; border-radius: 6px; font-size: 12px; color: #8888aa; }
        .platform-posts { display: flex; gap: 8px; flex-wrap: wrap; }
        .platform-post { background: #12121e; padding: 6px 12px; border-radius: 6px; font-size: 13px; }
        .platform-post a { color: #3b82f6; text-decoration: none; }
        .platform-post a:hover { text-decoration: underline; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: opacity 0.2s; }
        .btn:hover { opacity: 0.85; }
        .btn-primary { background: #3b82f6; color: #fff; }
        .btn-success { background: #22c55e; color: #fff; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-secondary { background: #334155; color: #e0e0e0; }
        .card-actions { display: flex; gap: 8px; margin-top: 12px; }
        .content-preview { background: #12121e; border-radius: 6px; padding: 12px; margin-top: 8px; }
        .content-preview h4 { font-size: 13px; color: #666; margin-bottom: 6px; }
        .content-preview pre { white-space: pre-wrap; word-wrap: break-word; font-size: 13px; color: #ccc; font-family: inherit; }
        .settings-form { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
        .settings-form label { font-size: 14px; color: #aaa; }
        .settings-form select, .settings-form input { background: #12121e; color: #e0e0e0; border: 1px solid #333; border-radius: 6px; padding: 8px 12px; font-size: 14px; }
        .empty-state { text-align: center; padding: 60px 20px; color: #555; }
        .empty-state h2 { font-size: 20px; color: #888; margin-bottom: 8px; }
        .earnings-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        .earnings-table th, .earnings-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #2a2a3a; }
        .earnings-table th { color: #666; font-size: 12px; font-weight: 600; text-transform: uppercase; }
        .earnings-table td { color: #ccc; font-size: 14px; }
        .multiplier { font-size: 11px; color: #a855f7; }
        .trust-bar { height: 6px; background: #2a2a3a; border-radius: 3px; margin-top: 4px; }
        .trust-fill { height: 100%; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Campaign Dashboard</h1>
        <div class="header-stats">
            <div class="stat-badge">
                <div class="stat-value">${{ "%.2f"|format(earnings.total_earned) }}</div>
                <div class="stat-label">Total Earned</div>
            </div>
            <div class="stat-badge">
                <div class="stat-value">${{ "%.2f"|format(earnings.current_balance) }}</div>
                <div class="stat-label">Balance</div>
            </div>
            <div class="stat-badge">
                <div class="stat-value">{{ trust_score }}/100</div>
                <div class="stat-label">Trust Score</div>
                <div class="trust-bar">
                    <div class="trust-fill" style="width:{{ trust_score }}%;background:{% if trust_score >= 70 %}#22c55e{% elif trust_score >= 40 %}#eab308{% else %}#ef4444{% endif %}"></div>
                </div>
            </div>
            <div class="stat-badge">
                <div class="stat-value">{{ active_count }}</div>
                <div class="stat-label">Active Campaigns</div>
            </div>
        </div>
    </div>

    <div class="nav-tabs">
        <div class="nav-tab active" onclick="switchView('campaigns')">Campaigns</div>
        <div class="nav-tab" onclick="switchView('earnings')">Earnings</div>
        <div class="nav-tab" onclick="switchView('settings')">Settings</div>
    </div>

    <!-- Campaigns Tab -->
    <div class="tab-content active" id="view-campaigns">
        {% if campaigns %}
        {% for c in campaigns %}
        <div class="card">
            <div class="card-header">
                <div>
                    <span class="card-title">{{ c.title }}</span>
                    <span class="multiplier">{{ c.payout_multiplier }}x payout</span>
                </div>
                <span class="status-badge status-{{ c.status }}">{{ c.status | replace('_', ' ') | title }}</span>
            </div>
            <div class="brief-text">{{ c.brief }}</div>
            {% if c.payout_rules %}
            {% set rules = c.payout_rules if c.payout_rules is mapping else {} %}
            <div class="payout-info">
                {% if rules.get('rate_per_1k_impressions') %}<span class="payout-chip">${{ rules.rate_per_1k_impressions }}/1K imp</span>{% endif %}
                {% if rules.get('rate_per_like') %}<span class="payout-chip">${{ rules.rate_per_like }}/like</span>{% endif %}
                {% if rules.get('rate_per_repost') %}<span class="payout-chip">${{ rules.rate_per_repost }}/repost</span>{% endif %}
                {% if rules.get('rate_per_click') %}<span class="payout-chip">${{ rules.rate_per_click }}/click</span>{% endif %}
            </div>
            {% endif %}
            {% if c.posts %}
            <div class="platform-posts">
                {% for p in c.posts %}
                <span class="platform-post">{{ p.platform }} {% if p.post_url %}<a href="{{ p.post_url }}" target="_blank">view</a>{% endif %}</span>
                {% endfor %}
            </div>
            {% endif %}
            {% if c.content and c.status == 'content_generated' %}
            <div class="content-preview">
                <h4>Generated Content (awaiting approval)</h4>
                <pre>{{ c.content[:500] }}{% if c.content|length > 500 %}...{% endif %}</pre>
            </div>
            <div class="card-actions">
                <form method="POST" action="{{ url_for('approve_campaign', campaign_id=c.server_id) }}">
                    <button class="btn btn-success" type="submit">Approve & Post</button>
                </form>
                <form method="POST" action="{{ url_for('skip_campaign', campaign_id=c.server_id) }}">
                    <button class="btn btn-secondary" type="submit">Skip</button>
                </form>
            </div>
            {% elif c.status == 'assigned' %}
            <div class="card-actions">
                <form method="POST" action="{{ url_for('generate_campaign', campaign_id=c.server_id) }}">
                    <button class="btn btn-primary" type="submit">Generate Content</button>
                </form>
                <form method="POST" action="{{ url_for('skip_campaign', campaign_id=c.server_id) }}">
                    <button class="btn btn-secondary" type="submit">Skip</button>
                </form>
            </div>
            {% endif %}
        </div>
        {% endfor %}
        {% else %}
        <div class="empty-state">
            <h2>No campaigns yet</h2>
            <p>{% if not logged_in %}Log in to start receiving campaigns{% else %}Campaigns will appear here when matched to your profile{% endif %}</p>
        </div>
        {% endif %}
    </div>

    <!-- Earnings Tab -->
    <div class="tab-content" id="view-earnings">
        <div class="card">
            <div class="card-title" style="margin-bottom:12px">Earnings Summary</div>
            <div class="payout-info">
                <span class="payout-chip">Total: ${{ "%.2f"|format(earnings.total_earned) }}</span>
                <span class="payout-chip">Balance: ${{ "%.2f"|format(earnings.current_balance) }}</span>
                <span class="payout-chip">Pending: ${{ "%.2f"|format(earnings.pending) }}</span>
            </div>
            {% if campaign_earnings %}
            <table class="earnings-table">
                <thead>
                    <tr><th>Campaign</th><th>Earned</th><th>Status</th></tr>
                </thead>
                <tbody>
                    {% for e in campaign_earnings %}
                    <tr>
                        <td>{{ e.campaign_title or ('Campaign #' ~ e.campaign_server_id) }}</td>
                        <td>${{ "%.2f"|format(e.amount) }}</td>
                        <td>{{ e.status }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p style="color:#666;margin-top:12px">No earnings yet. Complete campaigns to start earning.</p>
            {% endif %}
        </div>
    </div>

    <!-- Settings Tab -->
    <div class="tab-content" id="view-settings">
        <div class="card">
            <div class="card-title" style="margin-bottom:16px">Settings</div>
            <form method="POST" action="{{ url_for('save_settings') }}" class="settings-form">
                <label>Mode:</label>
                <select name="mode">
                    <option value="full_auto" {{ 'selected' if mode == 'full_auto' }}>Full Auto</option>
                    <option value="semi_auto" {{ 'selected' if mode == 'semi_auto' }}>Semi-Auto</option>
                    <option value="manual" {{ 'selected' if mode == 'manual' }}>Manual</option>
                </select>
                <label>Poll Interval (sec):</label>
                <input type="number" name="poll_interval" value="{{ poll_interval }}" min="60" max="3600">
                <button class="btn btn-primary" type="submit">Save</button>
            </form>
        </div>
        {% if profile %}
        <div class="card" style="margin-top:16px">
            <div class="card-title" style="margin-bottom:12px">Profile</div>
            <div class="payout-info">
                <span class="payout-chip">Email: {{ profile.email }}</span>
                <span class="payout-chip">Trust: {{ profile.trust_score }}/100</span>
                <span class="payout-chip">Mode: {{ profile.mode }}</span>
                <span class="payout-chip">Status: {{ profile.status }}</span>
            </div>
            <div style="margin-top:8px;color:#666;font-size:13px">
                Platforms: {{ profile.platforms.keys() | list | join(', ') if profile.platforms else 'None connected' }}
            </div>
        </div>
        {% endif %}
    </div>

    <script>
    function switchView(view) {
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
        document.getElementById('view-' + view).classList.add('active');
        var tab = event.target.closest('.nav-tab');
        if (tab) tab.classList.add('active');
    }
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    campaigns = get_campaigns()
    # Parse payout_rules JSON strings
    for c in campaigns:
        if isinstance(c.get("payout_rules"), str):
            try:
                c["payout_rules"] = json.loads(c["payout_rules"])
            except (json.JSONDecodeError, TypeError):
                c["payout_rules"] = {}
        # Attach posts
        c["posts"] = get_posts_for_campaign(c["server_id"])

    # Get earnings info
    local_earnings = get_earnings_summary()
    try:
        server_earnings = get_earnings() if is_logged_in() else {}
    except Exception:
        server_earnings = {}

    earnings = {
        "total_earned": server_earnings.get("total_earned", local_earnings["total_earned"]),
        "current_balance": server_earnings.get("current_balance", 0),
        "pending": server_earnings.get("pending", local_earnings["pending"]),
    }

    # Profile info
    profile = None
    trust_score = 50
    try:
        if is_logged_in():
            profile = get_profile()
            trust_score = profile.get("trust_score", 50)
    except Exception:
        pass

    mode = get_setting("mode", "semi_auto")
    poll_interval = get_setting("poll_interval", "600")
    active_count = sum(1 for c in campaigns if c["status"] in ("assigned", "content_generated"))

    return render_template_string(
        DASHBOARD_HTML,
        campaigns=campaigns,
        earnings=earnings,
        trust_score=trust_score,
        active_count=active_count,
        mode=mode,
        poll_interval=poll_interval,
        profile=profile,
        campaign_earnings=get_campaign_earnings(),
        logged_in=is_logged_in(),
    )


@app.route("/approve/<int:campaign_id>", methods=["POST"])
def approve_campaign(campaign_id):
    update_campaign_status(campaign_id, "approved")
    # TODO: trigger posting for this campaign
    return redirect(url_for("index"))


@app.route("/skip/<int:campaign_id>", methods=["POST"])
def skip_campaign(campaign_id):
    update_campaign_status(campaign_id, "skipped")
    from utils.server_client import update_assignment
    campaign = get_campaign(campaign_id)
    if campaign:
        try:
            update_assignment(campaign["assignment_id"], "skipped")
        except Exception:
            pass
    return redirect(url_for("index"))


@app.route("/generate/<int:campaign_id>", methods=["POST"])
def generate_campaign(campaign_id):
    """Trigger content generation for a campaign."""
    import subprocess
    import tempfile

    campaign = get_campaign(campaign_id)
    if not campaign:
        return redirect(url_for("index"))

    # Build campaign brief for the generator
    brief = {
        "campaign_id": campaign["server_id"],
        "assignment_id": campaign["assignment_id"],
        "title": campaign["title"],
        "brief": campaign["brief"],
        "content_guidance": campaign.get("content_guidance"),
        "assets": json.loads(campaign["assets"]) if isinstance(campaign["assets"], str) else campaign.get("assets", {}),
    }

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(brief, tmp, indent=2)
    tmp.close()

    script = ROOT / "scripts" / "generate_campaign.ps1"
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-CampaignFile", tmp.name],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            output_path = result.stdout.strip().split("\n")[-1].strip()
            if output_path and Path(output_path).exists():
                with open(output_path, "r", encoding="utf-8") as f:
                    generated = json.load(f)
                content = json.dumps(generated.get("content", {}))
                update_campaign_status(campaign_id, "content_generated", content)
    except Exception:
        pass
    finally:
        os.unlink(tmp.name)

    return redirect(url_for("index"))


@app.route("/settings", methods=["POST"])
def save_settings():
    mode = request.form.get("mode", "semi_auto")
    poll_interval = request.form.get("poll_interval", "600")
    set_setting("mode", mode)
    set_setting("poll_interval", poll_interval)

    # Update server profile too
    if is_logged_in():
        try:
            from utils.server_client import update_profile
            update_profile(mode=mode)
        except Exception:
            pass

    return redirect(url_for("index"))


@app.route("/api/campaigns")
def api_campaigns():
    """JSON API for campaigns (for future electron/desktop app)."""
    campaigns = get_campaigns()
    return jsonify(campaigns)


@app.route("/api/earnings")
def api_earnings():
    return jsonify(get_earnings_summary())


@app.route("/poll", methods=["POST"])
def manual_poll():
    """Manually trigger a campaign poll."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), 401
    try:
        from utils.local_db import upsert_campaign
        campaigns = poll_campaigns()
        for c in campaigns:
            upsert_campaign(c)
        return redirect(url_for("index"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("CAMPAIGN_DASHBOARD_PORT", "5222"))
    print(f"Campaign Dashboard running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
