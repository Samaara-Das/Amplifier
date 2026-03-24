"""Campaign dashboard — Flask app with 5 tabs: Campaigns, Posts, Earnings, Settings, Onboarding."""

import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template_string, request, url_for
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / "config" / ".env", override=True)
os.environ.setdefault("AUTO_POSTER_ROOT", str(ROOT))

from utils.local_db import (
    init_db, get_campaigns, get_campaign, update_campaign_status,
    get_posts_for_campaign, get_all_posts, get_earnings_summary,
    get_campaign_earnings, get_setting, set_setting,
)
from utils.server_client import (
    is_logged_in, get_profile, get_earnings, poll_campaigns,
    register, login, update_profile,
)

app = Flask(__name__)

PLATFORMS_JSON = ROOT / "config" / "platforms.json"
PROFILES_DIR = ROOT / "profiles"


def _load_platforms_config() -> dict:
    if PLATFORMS_JSON.exists():
        with open(PLATFORMS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _get_platform_connection_status() -> list[dict]:
    """Check which platforms have browser profiles on disk."""
    config = _load_platforms_config()
    result = []
    for key, info in config.items():
        profile_dir = PROFILES_DIR / f"{key}-profile"
        result.append({
            "key": key,
            "name": info.get("name", key),
            "enabled": info.get("enabled", False),
            "connected": profile_dir.exists() and any(profile_dir.iterdir()) if profile_dir.exists() else False,
        })
    return result


# ---------------------------------------------------------------------------
# Inline HTML template
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Amplifier</title>
    <link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet">
    <style>
        /* ── Reset & base ─────────────────────────────────── */
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a; color: #e2e8f0; padding: 0; min-height: 100vh;
        }
        a { color: #60a5fa; text-decoration: none; }
        a:hover { text-decoration: underline; }

        /* ── Top bar ──────────────────────────────────────── */
        .topbar {
            background: #0f172a; border-bottom: 1px solid #334155;
            padding: 16px 28px; display: flex; justify-content: space-between; align-items: center;
            box-shadow: 0 1px 20px rgba(37, 99, 235, 0.06);
        }
        .topbar h1 { font-size: 20px; color: #fff; font-weight: 700; letter-spacing: -0.3px; }
        .topbar-right { display: flex; gap: 14px; align-items: center; }
        .mini-stat { text-align: center; }
        .mini-stat-val { font-size: 16px; font-weight: 700; color: #22c55e; }
        .mini-stat-lbl { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }

        /* ── Navigation tabs ──────────────────────────────── */
        .nav-bar {
            background: #0f172a; border-bottom: 1px solid #334155;
            display: flex; gap: 0; padding: 0 28px;
        }
        .nav-tab {
            padding: 12px 22px; cursor: pointer; font-size: 13px; font-weight: 500;
            color: #64748b; border-bottom: 2px solid transparent; transition: all 0.15s;
            user-select: none;
        }
        .nav-tab:hover { color: #aaa; }
        .nav-tab.active { color: #60a5fa; border-bottom-color: #3b82f6; }

        /* ── Content wrapper ──────────────────────────────── */
        .content { padding: 24px 28px; max-width: 1200px; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        /* ── Cards ────────────────────────────────────────── */
        .card {
            background: linear-gradient(145deg, #1e293b 0%, #1a2332 100%); border-radius: 12px; padding: 20px;
            margin-bottom: 16px; border: 1px solid #334155;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .card:hover {
            transform: translateY(-1px); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
        }
        .card-header {
            display: flex; justify-content: space-between; align-items: flex-start;
            margin-bottom: 12px;
        }
        .card-title { font-size: 17px; font-weight: 600; color: #fff; }
        .section-title { font-size: 15px; font-weight: 600; color: #ccc; margin-bottom: 14px; }

        /* ── Summary strip (top of tabs) ──────────────────── */
        .summary-strip {
            display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap;
        }
        .summary-card {
            background: linear-gradient(145deg, #1e293b 0%, #1a2332 100%); border: 1px solid #334155; border-radius: 12px;
            padding: 16px 22px; flex: 1; min-width: 150px; text-align: center;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .summary-card:hover {
            transform: translateY(-1px); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
        }
        .summary-val { font-size: 26px; font-weight: 700; }
        .summary-val.green { color: #22c55e; }
        .summary-val.blue { color: #3b82f6; }
        .summary-val.yellow { color: #eab308; }
        .summary-val.purple { color: #a855f7; }
        .summary-val.white { color: #fff; }
        .summary-lbl { font-size: 11px; color: #64748b; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }

        /* ── Status badges ────────────────────────────────── */
        .badge {
            display: inline-block; padding: 3px 10px; border-radius: 12px;
            font-size: 12px; font-weight: 500; border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .badge-assigned { background: #064e3b; color: #6ee7b7; }
        .badge-content_generated { background: #713f12; color: #fde68a; }
        .badge-approved { background: #1a3a1a; color: #86efac; }
        .badge-posted { background: #14532d; color: #86efac; }
        .badge-skipped { background: #334155; color: #cbd5e1; }
        .badge-pending { background: #713f12; color: #fde68a; }
        .badge-paid { background: #14532d; color: #86efac; }
        .badge-connected { background: #14532d; color: #86efac; }
        .badge-disconnected { background: #3b1a1a; color: #fca5a5; }
        .badge-enabled { background: #064e3b; color: #6ee7b7; }
        .badge-disabled { background: #334155; color: #cbd5e1; }

        /* ── Brief / info rows ────────────────────────────── */
        .brief-text {
            color: #aaa; font-size: 14px; line-height: 1.6; margin-bottom: 12px;
            max-height: 100px; overflow-y: auto;
        }
        .chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
        .chip {
            background: #0f172a; padding: 4px 10px; border-radius: 6px;
            font-size: 12px; color: #94a3b8;
        }
        .multiplier { font-size: 11px; color: #a855f7; margin-left: 8px; }

        .platform-posts { display: flex; gap: 8px; flex-wrap: wrap; }
        .platform-pill {
            background: #0f172a; padding: 5px 12px; border-radius: 6px; font-size: 13px;
        }
        .platform-pill a { color: #60a5fa; }

        /* ── Content preview ──────────────────────────────── */
        .content-preview {
            background: #0f172a; border-radius: 6px; padding: 12px; margin-top: 8px;
        }
        .content-preview h4 { font-size: 13px; color: #64748b; margin-bottom: 6px; }
        .content-preview pre {
            white-space: pre-wrap; word-wrap: break-word;
            font-size: 13px; color: #ccc; font-family: inherit;
        }

        /* ── Buttons ──────────────────────────────────────── */
        .btn {
            padding: 8px 16px; border: none; border-radius: 8px; cursor: pointer;
            font-size: 13px; font-weight: 500; transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
            display: inline-block;
        }
        .btn:hover { transform: translateY(-1px); }
        .btn-primary { background: #2563eb; color: #fff; }
        .btn-primary:hover { background: #1d4ed8; box-shadow: 0 4px 16px rgba(37, 99, 235, 0.35); }
        .btn-success { background: #22c55e; color: #fff; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-secondary { background: #334155; color: #e2e8f0; }
        .btn-sm { padding: 6px 12px; font-size: 12px; }
        .card-actions { display: flex; gap: 8px; margin-top: 14px; }

        /* ── Tables ───────────────────────────────────────── */
        .tbl { width: 100%; border-collapse: collapse; }
        .tbl th, .tbl td {
            padding: 10px 14px; text-align: left; border-bottom: 1px solid #334155;
        }
        .tbl th {
            color: #64748b; font-size: 11px; font-weight: 600; text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .tbl td { color: #ccc; font-size: 13px; }
        .tbl tbody tr:hover { background: rgba(37, 99, 235, 0.04); }
        .tbl tbody tr:hover td:first-child { box-shadow: inset 3px 0 0 #2563eb; }
        .tbl .num { text-align: right; font-variant-numeric: tabular-nums; }
        .tbl .truncate {
            max-width: 260px; white-space: nowrap; overflow: hidden;
            text-overflow: ellipsis;
        }

        /* ── Trust bar ────────────────────────────────────── */
        .trust-bar { height: 6px; background: #334155; border-radius: 3px; margin-top: 4px; width: 80px; }
        .trust-fill { height: 100%; border-radius: 3px; }

        /* ── Forms / inputs ───────────────────────────────── */
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; font-size: 13px; color: #aaa; margin-bottom: 6px; }
        .form-input {
            background: #0f172a; color: #e2e8f0; border: 1px solid #333;
            border-radius: 8px; padding: 10px 14px; font-size: 14px; width: 100%;
        }
        .form-input:focus { outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1); }
        select.form-input { cursor: pointer; }
        .form-row { display: flex; gap: 16px; flex-wrap: wrap; }
        .form-row .form-group { flex: 1; min-width: 200px; }

        /* ── Filter bar ───────────────────────────────────── */
        .filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
        .filter-bar label { font-size: 13px; color: #94a3b8; }
        .filter-bar select { background: #0f172a; color: #e2e8f0; border: 1px solid #333; border-radius: 6px; padding: 6px 10px; font-size: 13px; }

        /* ── Platform grid (settings) ─────────────────────── */
        .platform-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
        .platform-card {
            background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 14px 16px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .platform-card .name { font-size: 14px; color: #e2e8f0; font-weight: 500; }
        .platform-card .badges { display: flex; gap: 6px; }

        /* ── Onboarding ───────────────────────────────────── */
        .onboard-container { max-width: 560px; margin: 0 auto; padding-top: 20px; }
        .step-indicator { display: flex; gap: 0; margin-bottom: 28px; }
        .step-dot {
            flex: 1; height: 4px; background: #334155; border-radius: 2px;
            transition: background 0.2s;
        }
        .step-dot.done { background: #22c55e; }
        .step-dot.current { background: #3b82f6; }
        .step-section { display: none; }
        .step-section.active { display: block; }
        .step-title { font-size: 20px; font-weight: 600; color: #fff; margin-bottom: 6px; }
        .step-desc { font-size: 14px; color: #94a3b8; margin-bottom: 20px; }
        .tag-input-wrap { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
        .tag { background: #2563eb; color: #fff; padding: 4px 10px; border-radius: 12px; font-size: 12px; display: inline-flex; align-items: center; gap: 4px; }
        .tag .remove { cursor: pointer; opacity: 0.7; }
        .tag .remove:hover { opacity: 1; }

        /* ── Empty state ──────────────────────────────────── */
        .empty-state { text-align: center; padding: 60px 20px; color: #555; }
        .empty-state h2 { font-size: 18px; color: #94a3b8; margin-bottom: 8px; }

        /* ── Alert ────────────────────────────────────────── */
        .alert { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
        .alert-info { background: #1e3a5f; color: #93bbfd; border: 1px solid #1e40af; }
        .alert-success { background: #14532d; color: #86efac; border: 1px solid #1a6a3a; }
        .alert-error { background: #3b1a1a; color: #fca5a5; border: 1px solid #5a2a2a; }
    </style>
</head>
<body>

    <!-- ═══════════ Top bar ═══════════ -->
    <div class="topbar">
        <h1>Amplifier</h1>
        <div class="topbar-right">
            <div class="mini-stat">
                <div class="mini-stat-val">${{ "%.2f"|format(earnings.total_earned) }}</div>
                <div class="mini-stat-lbl">Earned</div>
            </div>
            <div class="mini-stat">
                <div class="mini-stat-val">${{ "%.2f"|format(earnings.current_balance) }}</div>
                <div class="mini-stat-lbl">Balance</div>
            </div>
            <div class="mini-stat">
                <div class="mini-stat-val" style="color:#fff">{{ trust_score }}/100</div>
                <div class="mini-stat-lbl">Trust</div>
                <div class="trust-bar">
                    <div class="trust-fill" style="width:{{ trust_score }}%;background:{% if trust_score >= 70 %}#22c55e{% elif trust_score >= 40 %}#eab308{% else %}#ef4444{% endif %}"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- ═══════════ Nav tabs ═══════════ -->
    <div class="nav-bar">
        <div class="nav-tab active" data-tab="campaigns" onclick="switchTab(this)">Campaigns</div>
        <div class="nav-tab" data-tab="posts" onclick="switchTab(this)">Posts</div>
        <div class="nav-tab" data-tab="earnings" onclick="switchTab(this)">Earnings</div>
        <div class="nav-tab" data-tab="settings" onclick="switchTab(this)">Settings</div>
        {% if not onboarding_complete %}
        <div class="nav-tab" data-tab="onboarding" onclick="switchTab(this)" style="margin-left:auto;color:#eab308">Get Started</div>
        {% endif %}
    </div>

    <div class="content">
        {% if flash_msg %}
        <div class="alert alert-{{ flash_type or 'info' }}">{{ flash_msg }}</div>
        {% endif %}

        <!-- ═══════════════════════════════════════════════════
             TAB 1 — CAMPAIGNS
             ═══════════════════════════════════════════════════ -->
        <div class="tab-content active" id="tab-campaigns">
            <!-- Status counts -->
            <div class="summary-strip">
                <div class="summary-card">
                    <div class="summary-val blue">{{ status_counts.assigned }}</div>
                    <div class="summary-lbl">Assigned</div>
                </div>
                <div class="summary-card">
                    <div class="summary-val yellow">{{ status_counts.content_generated }}</div>
                    <div class="summary-lbl">Content Ready</div>
                </div>
                <div class="summary-card">
                    <div class="summary-val green">{{ status_counts.posted }}</div>
                    <div class="summary-lbl">Posted</div>
                </div>
                <div class="summary-card">
                    <div class="summary-val purple">{{ status_counts.approved }}</div>
                    <div class="summary-lbl">Approved</div>
                </div>
                <div class="summary-card">
                    <div class="summary-val white">{{ status_counts.skipped }}</div>
                    <div class="summary-lbl">Skipped</div>
                </div>
            </div>

            <!-- Poll button -->
            {% if logged_in %}
            <div style="margin-bottom:16px">
                <form method="POST" action="{{ url_for('manual_poll') }}" style="display:inline">
                    <button class="btn btn-secondary btn-sm" type="submit">Poll for New Campaigns</button>
                </form>
            </div>
            {% endif %}

            {% if campaigns %}
            {% for c in campaigns %}
            <div class="card">
                <div class="card-header">
                    <div>
                        <span class="card-title">{{ c.title }}</span>
                        <span class="multiplier">{{ c.payout_multiplier }}x payout</span>
                    </div>
                    <span class="badge badge-{{ c.status }}">{{ c.status | replace('_', ' ') | title }}</span>
                </div>

                <div class="brief-text">{{ c.brief }}</div>

                {% if c.payout_rules %}
                {% set rules = c.payout_rules if c.payout_rules is mapping else {} %}
                <div class="chip-row">
                    {% if rules.get('rate_per_1k_impressions') %}<span class="chip">${{ rules.rate_per_1k_impressions }}/1K imp</span>{% endif %}
                    {% if rules.get('rate_per_like') %}<span class="chip">${{ rules.rate_per_like }}/like</span>{% endif %}
                    {% if rules.get('rate_per_repost') %}<span class="chip">${{ rules.rate_per_repost }}/repost</span>{% endif %}
                    {% if rules.get('rate_per_click') %}<span class="chip">${{ rules.rate_per_click }}/click</span>{% endif %}
                </div>
                {% endif %}

                {% if c.posts %}
                <div class="platform-posts">
                    {% for p in c.posts %}
                    <span class="platform-pill">
                        {{ p.platform }}
                        {% if p.post_url %}<a href="{{ p.post_url }}" target="_blank">view</a>{% endif %}
                    </span>
                    {% endfor %}
                </div>
                {% endif %}

                {% if c.content and c.status == 'content_generated' %}
                <div class="content-preview">
                    <h4>Generated Content — edit before approving</h4>
                    <form method="POST" action="{{ url_for('approve_campaign', campaign_id=c.server_id) }}">
                        {% set content_parsed = c.content_json or {} %}
                        {% for platform, text in content_parsed.items() %}
                        {% if platform != '_image_path' %}
                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px;">{{ platform }}</label>
                            {% if text is mapping %}
                            <textarea name="content_{{ platform }}_title" class="form-input" rows="1" style="margin-bottom:4px;" placeholder="Title">{{ text.get('title', '') }}</textarea>
                            <textarea name="content_{{ platform }}_body" class="form-input" rows="4" placeholder="Body">{{ text.get('body', '') }}</textarea>
                            {% else %}
                            <textarea name="content_{{ platform }}" class="form-input" rows="3">{{ text }}</textarea>
                            {% endif %}
                        </div>
                        {% endif %}
                        {% endfor %}
                        <div class="card-actions">
                            <button class="btn btn-success" type="submit">Approve &amp; Post</button>
                            <a href="{{ url_for('skip_campaign', campaign_id=c.server_id) }}" class="btn btn-secondary" onclick="fetch('{{ url_for('skip_campaign', campaign_id=c.server_id) }}',{method:'POST'});location.reload();return false;">Skip</a>
                        </div>
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
                <p>{% if not logged_in %}Complete onboarding to start receiving campaigns.{% else %}Campaigns will appear here when matched to your profile.{% endif %}</p>
            </div>
            {% endif %}
        </div>

        <!-- ═══════════════════════════════════════════════════
             TAB 2 — POSTS
             ═══════════════════════════════════════════════════ -->
        <div class="tab-content" id="tab-posts">
            <div class="summary-strip">
                <div class="summary-card">
                    <div class="summary-val white">{{ all_posts | length }}</div>
                    <div class="summary-lbl">Total Posts</div>
                </div>
                <div class="summary-card">
                    <div class="summary-val blue">{{ post_platform_counts | length }}</div>
                    <div class="summary-lbl">Platforms Used</div>
                </div>
            </div>

            <div class="filter-bar">
                <label>Filter by platform:</label>
                <select id="postPlatformFilter" onchange="filterPosts()">
                    <option value="all">All Platforms</option>
                    {% for plat in post_platform_counts %}
                    <option value="{{ plat }}">{{ plat | capitalize }} ({{ post_platform_counts[plat] }})</option>
                    {% endfor %}
                </select>
            </div>

            {% if all_posts %}
            <div class="card" style="padding:0;overflow:hidden">
                <table class="tbl" id="postsTable">
                    <thead>
                        <tr>
                            <th>Platform</th>
                            <th>Campaign</th>
                            <th>Content</th>
                            <th>Post Link</th>
                            <th>Posted</th>
                            <th class="num">Imp.</th>
                            <th class="num">Likes</th>
                            <th class="num">Reposts</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for p in all_posts %}
                        <tr data-platform="{{ p.platform }}">
                            <td><span class="badge badge-assigned">{{ p.platform | capitalize }}</span></td>
                            <td>{{ p.campaign_title or '-' }}</td>
                            <td class="truncate" title="{{ p.content or '' }}">{{ (p.content or '-')[:80] }}{% if p.content and p.content|length > 80 %}...{% endif %}</td>
                            <td>{% if p.post_url %}<a href="{{ p.post_url }}" target="_blank">View Post</a>{% else %}-{% endif %}</td>
                            <td>{{ p.posted_at[:16] if p.posted_at else '-' }}</td>
                            <td class="num">{{ p.impressions if p.impressions is not none else '-' }}</td>
                            <td class="num">{{ p.likes if p.likes is not none else '-' }}</td>
                            <td class="num">{{ p.reposts if p.reposts is not none else '-' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="empty-state">
                <h2>No posts yet</h2>
                <p>Posts will appear here after you approve and post campaign content.</p>
            </div>
            {% endif %}
        </div>

        <!-- ═══════════════════════════════════════════════════
             TAB 3 — EARNINGS
             ═══════════════════════════════════════════════════ -->
        <div class="tab-content" id="tab-earnings">
            <div class="summary-strip">
                <div class="summary-card">
                    <div class="summary-val green">${{ "%.2f"|format(earnings.total_earned) }}</div>
                    <div class="summary-lbl">Total Earned</div>
                </div>
                <div class="summary-card">
                    <div class="summary-val blue">${{ "%.2f"|format(earnings.current_balance) }}</div>
                    <div class="summary-lbl">Balance</div>
                </div>
                <div class="summary-card">
                    <div class="summary-val yellow">${{ "%.2f"|format(earnings.pending) }}</div>
                    <div class="summary-lbl">Pending</div>
                </div>
                <div class="summary-card">
                    <div class="summary-val purple">${{ "%.2f"|format(earnings.paid) }}</div>
                    <div class="summary-lbl">Paid Out</div>
                </div>
            </div>

            <!-- Per-campaign earnings table -->
            <div class="card">
                <div class="section-title">Campaign Earnings</div>
                {% if campaign_earnings %}
                <table class="tbl">
                    <thead>
                        <tr><th>Campaign</th><th class="num">Amount</th><th>Period</th><th>Status</th></tr>
                    </thead>
                    <tbody>
                        {% for e in campaign_earnings %}
                        <tr>
                            <td>{{ e.campaign_title or ('Campaign #' ~ e.campaign_server_id) }}</td>
                            <td class="num">${{ "%.2f"|format(e.amount) }}</td>
                            <td>{{ e.period or '-' }}</td>
                            <td><span class="badge badge-{{ e.status }}">{{ e.status | title }}</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color:#64748b">No earnings yet. Complete campaigns to start earning.</p>
                {% endif %}
            </div>

            <!-- Per-platform earnings breakdown -->
            <div class="card">
                <div class="section-title">Earnings by Platform</div>
                {% if platform_earnings %}
                <table class="tbl">
                    <thead>
                        <tr><th>Platform</th><th class="num">Posts</th><th class="num">Total Earned</th></tr>
                    </thead>
                    <tbody>
                        {% for plat, info in platform_earnings.items() %}
                        <tr>
                            <td>{{ plat | capitalize }}</td>
                            <td class="num">{{ info.count }}</td>
                            <td class="num">${{ "%.2f"|format(info.earned) }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color:#64748b">Platform earnings will appear after posts earn revenue.</p>
                {% endif %}
            </div>

            <!-- Recent payout history -->
            <div class="card">
                <div class="section-title">Recent Payouts</div>
                {% if paid_earnings %}
                <table class="tbl">
                    <thead>
                        <tr><th>Campaign</th><th class="num">Amount</th><th>Date</th></tr>
                    </thead>
                    <tbody>
                        {% for e in paid_earnings %}
                        <tr>
                            <td>{{ e.campaign_title or ('Campaign #' ~ e.campaign_server_id) }}</td>
                            <td class="num">${{ "%.2f"|format(e.amount) }}</td>
                            <td>{{ e.updated_at[:16] if e.updated_at else '-' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color:#64748b">No payouts yet.</p>
                {% endif %}
            </div>
        </div>

        <!-- ═══════════════════════════════════════════════════
             TAB 4 — SETTINGS
             ═══════════════════════════════════════════════════ -->
        <div class="tab-content" id="tab-settings">
            <div class="card">
                <div class="section-title">General Settings</div>
                <form method="POST" action="{{ url_for('save_settings') }}">
                    <div class="form-row">
                        <div class="form-group">
                            <label>Mode</label>
                            <select name="mode" class="form-input">
                                <option value="full_auto" {{ 'selected' if mode == 'full_auto' }}>Full Auto</option>
                                <option value="semi_auto" {{ 'selected' if mode == 'semi_auto' }}>Semi-Auto (review before posting)</option>
                                <option value="manual" {{ 'selected' if mode == 'manual' }}>Manual</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Poll Interval (seconds)</label>
                            <input type="number" name="poll_interval" class="form-input" value="{{ poll_interval }}" min="60" max="3600">
                        </div>
                    </div>
                    <button class="btn btn-primary" type="submit">Save Settings</button>
                </form>
            </div>

            {% if profile %}
            <div class="card">
                <div class="section-title">Server Profile</div>
                <div class="chip-row">
                    <span class="chip">Email: {{ profile.email }}</span>
                    <span class="chip">Trust: {{ profile.trust_score }}/100</span>
                    <span class="chip">Mode: {{ profile.mode }}</span>
                    <span class="chip">Status: {{ profile.status }}</span>
                </div>
                <div style="margin-top:8px;color:#64748b;font-size:13px">
                    Server platforms: {{ profile.platforms.keys() | list | join(', ') if profile.platforms else 'None connected' }}
                </div>
            </div>
            {% endif %}

            <div class="card">
                <div class="section-title">Platform Connection Status</div>
                <p style="color:#64748b;font-size:13px;margin-bottom:14px">
                    Shows which platforms have a browser profile set up locally.
                    Run <code style="color:#aaa">python scripts/login_setup.py &lt;platform&gt;</code> to connect a new platform.
                </p>
                <div class="platform-grid">
                    {% for p in platform_status %}
                    <div class="platform-card">
                        <span class="name">{{ p.name }}</span>
                        <div class="badges">
                            {% if p.connected %}
                                <span class="badge badge-connected">Connected</span>
                            {% else %}
                                <span class="badge badge-disconnected">Not Connected</span>
                            {% endif %}
                            {% if p.enabled %}
                                <span class="badge badge-enabled">Enabled</span>
                            {% else %}
                                <span class="badge badge-disabled">Disabled</span>
                            {% endif %}
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>

        <!-- ═══════════════════════════════════════════════════
             TAB 5 — ONBOARDING
             ═══════════════════════════════════════════════════ -->
        <div class="tab-content" id="tab-onboarding">
            <div class="onboard-container">

                <!-- Step indicators -->
                <div class="step-indicator">
                    <div class="step-dot current" id="dot-1"></div>
                    <div class="step-dot" id="dot-2"></div>
                    <div class="step-dot" id="dot-3"></div>
                    <div class="step-dot" id="dot-4"></div>
                </div>

                <!-- STEP 1: Register / Login -->
                <div class="step-section active" id="step-1">
                    <div class="step-title">Create Account or Log In</div>
                    <div class="step-desc">Connect to the campaign server to receive and track campaigns.</div>

                    {% if logged_in %}
                    <div class="alert alert-success">You are already logged in. Continue to the next step.</div>
                    <button class="btn btn-primary" onclick="goToStep(2)">Next</button>
                    {% else %}
                    <div id="authToggle" style="margin-bottom:16px">
                        <button class="btn btn-primary btn-sm" id="showRegister" onclick="toggleAuth('register')" style="opacity:1">Register</button>
                        <button class="btn btn-secondary btn-sm" id="showLogin" onclick="toggleAuth('login')">Log In</button>
                    </div>

                    <form id="registerForm" method="POST" action="{{ url_for('onboarding_auth') }}">
                        <input type="hidden" name="action" value="register">
                        <div class="form-group">
                            <label>Email</label>
                            <input type="email" name="email" class="form-input" required placeholder="you@example.com">
                        </div>
                        <div class="form-group">
                            <label>Password</label>
                            <input type="password" name="password" class="form-input" required minlength="8" placeholder="Min 8 characters">
                        </div>
                        <button class="btn btn-success" type="submit">Create Account</button>
                    </form>

                    <form id="loginForm" method="POST" action="{{ url_for('onboarding_auth') }}" style="display:none">
                        <input type="hidden" name="action" value="login">
                        <div class="form-group">
                            <label>Email</label>
                            <input type="email" name="email" class="form-input" required placeholder="you@example.com">
                        </div>
                        <div class="form-group">
                            <label>Password</label>
                            <input type="password" name="password" class="form-input" required placeholder="Your password">
                        </div>
                        <button class="btn btn-primary" type="submit">Log In</button>
                    </form>
                    {% endif %}
                </div>

                <!-- STEP 2: Connect Platforms -->
                <div class="step-section" id="step-2">
                    <div class="step-title">Connect Your Platforms</div>
                    <div class="step-desc">
                        Set up browser profiles so the system can post on your behalf.
                        Run the login command for each platform you want to use.
                    </div>

                    <div class="platform-grid" style="margin-bottom:20px">
                        {% for p in platform_status %}
                        <div class="platform-card">
                            <span class="name">{{ p.name }}</span>
                            {% if p.connected %}
                                <span class="badge badge-connected">Connected</span>
                            {% else %}
                                <span class="badge badge-disconnected">Not Connected</span>
                            {% endif %}
                        </div>
                        {% endfor %}
                    </div>

                    <div class="card" style="background:#0f172a">
                        <p style="font-size:13px;color:#aaa;margin-bottom:8px">Run in a terminal for each platform:</p>
                        <code style="color:#22c55e;font-size:14px">python scripts/login_setup.py &lt;platform&gt;</code>
                        <p style="font-size:12px;color:#64748b;margin-top:6px">Platforms: x, linkedin, facebook, instagram, reddit, tiktok</p>
                    </div>

                    <div style="margin-top:16px;display:flex;gap:8px">
                        <button class="btn btn-secondary" onclick="goToStep(1)">Back</button>
                        <button class="btn btn-primary" onclick="goToStep(3)">Next</button>
                    </div>
                </div>

                <!-- STEP 3: Niche & Followers -->
                <div class="step-section" id="step-3">
                    <div class="step-title">Your Niche &amp; Audience</div>
                    <div class="step-desc">Help us match you with the right campaigns. Add your niche tags and follower counts.</div>

                    <form method="POST" action="{{ url_for('onboarding_profile') }}">
                        <div class="form-group">
                            <label>Niche Tags (comma-separated)</label>
                            <input type="text" name="niche_tags" class="form-input"
                                   placeholder="e.g. trading, finance, stocks, crypto"
                                   value="{{ current_niche_tags or '' }}">
                        </div>

                        <div class="section-title" style="margin-top:16px">Follower Counts</div>
                        <div class="form-row">
                            {% for p in platform_status %}
                            {% if p.connected %}
                            <div class="form-group">
                                <label>{{ p.name }}</label>
                                <input type="number" name="followers_{{ p.key }}" class="form-input" min="0"
                                       placeholder="0" value="{{ current_followers.get(p.key, '') if current_followers else '' }}">
                            </div>
                            {% endif %}
                            {% endfor %}
                        </div>

                        <div style="margin-top:16px;display:flex;gap:8px">
                            <button class="btn btn-secondary" type="button" onclick="goToStep(2)">Back</button>
                            <button class="btn btn-primary" type="submit">Save &amp; Next</button>
                        </div>
                    </form>
                </div>

                <!-- STEP 4: Choose Mode -->
                <div class="step-section" id="step-4">
                    <div class="step-title">Choose Your Mode</div>
                    <div class="step-desc">How do you want to handle campaigns?</div>

                    <form method="POST" action="{{ url_for('onboarding_mode') }}">
                        <div class="form-group">
                            <label style="display:flex;align-items:center;gap:10px;padding:12px;background:#0f172a;border-radius:8px;cursor:pointer;margin-bottom:8px">
                                <input type="radio" name="mode" value="full_auto" {{ 'checked' if mode == 'full_auto' }}>
                                <div>
                                    <div style="color:#fff;font-weight:500">Full Auto</div>
                                    <div style="color:#64748b;font-size:12px">Content is generated and posted automatically. No manual review needed.</div>
                                </div>
                            </label>
                            <label style="display:flex;align-items:center;gap:10px;padding:12px;background:#0f172a;border-radius:8px;cursor:pointer;margin-bottom:8px">
                                <input type="radio" name="mode" value="semi_auto" {{ 'checked' if mode == 'semi_auto' or not mode }}>
                                <div>
                                    <div style="color:#fff;font-weight:500">Semi-Auto (Recommended)</div>
                                    <div style="color:#64748b;font-size:12px">Content is generated automatically, but you review and approve before posting.</div>
                                </div>
                            </label>
                            <label style="display:flex;align-items:center;gap:10px;padding:12px;background:#0f172a;border-radius:8px;cursor:pointer">
                                <input type="radio" name="mode" value="manual" {{ 'checked' if mode == 'manual' }}>
                                <div>
                                    <div style="color:#fff;font-weight:500">Manual</div>
                                    <div style="color:#64748b;font-size:12px">You write all content yourself. Full control, more work.</div>
                                </div>
                            </label>
                        </div>

                        <div style="margin-top:16px;display:flex;gap:8px">
                            <button class="btn btn-secondary" type="button" onclick="goToStep(3)">Back</button>
                            <button class="btn btn-success" type="submit">Complete Setup</button>
                        </div>
                    </form>
                </div>

            </div>
        </div>

    </div><!-- /.content -->

    <!-- ═══════════ JavaScript ═══════════ -->
    <script>
    function switchTab(el) {
        var tab = el.dataset.tab;
        document.querySelectorAll('.tab-content').forEach(function(c){ c.classList.remove('active'); });
        document.querySelectorAll('.nav-tab').forEach(function(t){ t.classList.remove('active'); });
        document.getElementById('tab-' + tab).classList.add('active');
        el.classList.add('active');
        // Clear flash messages on tab switch
        document.querySelectorAll('.alert').forEach(function(a){ a.remove(); });
        // remember last tab
        try { sessionStorage.setItem('activeTab', tab); } catch(e){}
    }

    // Auto-navigate to onboarding step if set by server
    {% if onboarding_step is defined and onboarding_step %}
    (function(){
        var tabEl = document.querySelector('.nav-tab[data-tab="onboarding"]');
        if (tabEl) {
            switchTab(tabEl);
            goToStep({{ onboarding_step }});
        }
    })();
    {% else %}
    // Restore last active tab
    (function(){
        try {
            var saved = sessionStorage.getItem('activeTab');
            if (saved) {
                var tabEl = document.querySelector('.nav-tab[data-tab="' + saved + '"]');
                if (tabEl) switchTab(tabEl);
            }
        } catch(e){}
    })();
    {% endif %}

    // Posts filter
    function filterPosts() {
        var v = document.getElementById('postPlatformFilter').value;
        var rows = document.querySelectorAll('#postsTable tbody tr');
        rows.forEach(function(r){
            r.style.display = (v === 'all' || r.dataset.platform === v) ? '' : 'none';
        });
    }

    // Onboarding steps
    function goToStep(n) {
        document.querySelectorAll('.step-section').forEach(function(s){ s.classList.remove('active'); });
        document.getElementById('step-' + n).classList.add('active');
        for (var i = 1; i <= 4; i++) {
            var dot = document.getElementById('dot-' + i);
            dot.className = 'step-dot';
            if (i < n) dot.classList.add('done');
            else if (i === n) dot.classList.add('current');
        }
    }

    // Auth toggle (register / login)
    function toggleAuth(mode) {
        if (mode === 'login') {
            document.getElementById('registerForm').style.display = 'none';
            document.getElementById('loginForm').style.display = 'block';
            document.getElementById('showRegister').style.opacity = '0.5';
            document.getElementById('showLogin').style.opacity = '1';
            document.getElementById('showLogin').className = 'btn btn-primary btn-sm';
            document.getElementById('showRegister').className = 'btn btn-secondary btn-sm';
        } else {
            document.getElementById('registerForm').style.display = 'block';
            document.getElementById('loginForm').style.display = 'none';
            document.getElementById('showRegister').style.opacity = '1';
            document.getElementById('showLogin').style.opacity = '0.5';
            document.getElementById('showRegister').className = 'btn btn-primary btn-sm';
            document.getElementById('showLogin').className = 'btn btn-secondary btn-sm';
        }
    }
    </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helper: build template context
# ---------------------------------------------------------------------------

def _build_context(flash_msg: str = None, flash_type: str = None) -> dict:
    """Build the full template context used by every page render."""
    # Campaigns
    campaigns = get_campaigns()
    for c in campaigns:
        if isinstance(c.get("payout_rules"), str):
            try:
                c["payout_rules"] = json.loads(c["payout_rules"])
            except (json.JSONDecodeError, TypeError):
                c["payout_rules"] = {}
        c["posts"] = get_posts_for_campaign(c["server_id"])
        # Parse content JSON for editing UI
        try:
            c["content_json"] = json.loads(c["content"]) if isinstance(c.get("content"), str) else (c.get("content") or {})
        except (json.JSONDecodeError, TypeError):
            c["content_json"] = {}

    # Status counts
    status_counts = {"assigned": 0, "content_generated": 0, "posted": 0, "approved": 0, "skipped": 0}
    for c in campaigns:
        s = c.get("status", "")
        if s in status_counts:
            status_counts[s] += 1

    # Earnings (local + server fallback)
    local_earnings = get_earnings_summary()
    try:
        server_earnings = get_earnings() if is_logged_in() else {}
    except Exception:
        server_earnings = {}

    earnings = {
        "total_earned": server_earnings.get("total_earned", local_earnings["total_earned"]),
        "current_balance": server_earnings.get("current_balance", 0),
        "pending": server_earnings.get("pending", local_earnings["pending"]),
        "paid": server_earnings.get("paid", local_earnings["paid"]),
    }

    # Profile & trust
    profile = None
    trust_score = 50
    try:
        if is_logged_in():
            profile = get_profile()
            trust_score = profile.get("trust_score", 50)
    except Exception:
        pass

    # All posts (for Posts tab)
    all_posts = get_all_posts()
    post_platform_counts = {}
    for p in all_posts:
        plat = p.get("platform", "unknown")
        post_platform_counts[plat] = post_platform_counts.get(plat, 0) + 1

    # Campaign earnings
    campaign_earnings_list = get_campaign_earnings()

    # Paid-only earnings (recent payouts)
    paid_earnings = [e for e in campaign_earnings_list if e.get("status") == "paid"]

    # Per-platform earnings breakdown (computed from posts + earnings)
    platform_earnings = {}
    for p in all_posts:
        plat = p.get("platform", "unknown")
        if plat not in platform_earnings:
            platform_earnings[plat] = {"count": 0, "earned": 0.0}
        platform_earnings[plat]["count"] += 1
    # Distribute campaign earnings across platforms proportionally
    for e in campaign_earnings_list:
        cid = e.get("campaign_server_id")
        campaign_posts = [p for p in all_posts if p.get("campaign_server_id") == cid]
        if campaign_posts:
            per_post = e.get("amount", 0) / len(campaign_posts)
            for p in campaign_posts:
                plat = p.get("platform", "unknown")
                if plat in platform_earnings:
                    platform_earnings[plat]["earned"] += per_post

    # Settings
    mode = get_setting("mode", "semi_auto")
    poll_interval = get_setting("poll_interval", "600")
    logged_in = is_logged_in()

    # Platform connection status
    platform_status = _get_platform_connection_status()

    # Current niche tags and follower counts (from server profile if available)
    current_niche_tags = ""
    current_followers = {}
    if profile:
        tags = profile.get("niche_tags")
        if isinstance(tags, list):
            current_niche_tags = ", ".join(tags)
        elif isinstance(tags, str):
            current_niche_tags = tags
        current_followers = profile.get("follower_counts", {}) or {}

    # Onboarding is complete only after all 4 steps (explicit flag set in step 4)
    onboarding_complete = logged_in and get_setting("onboarding_done") == "true"

    return {
        "campaigns": campaigns,
        "status_counts": status_counts,
        "earnings": earnings,
        "trust_score": trust_score,
        "all_posts": all_posts,
        "post_platform_counts": post_platform_counts,
        "campaign_earnings": campaign_earnings_list,
        "paid_earnings": paid_earnings,
        "platform_earnings": platform_earnings,
        "mode": mode,
        "poll_interval": poll_interval,
        "profile": profile,
        "logged_in": logged_in,
        "onboarding_complete": onboarding_complete,
        "platform_status": platform_status,
        "current_niche_tags": current_niche_tags,
        "current_followers": current_followers,
        "flash_msg": flash_msg,
        "flash_type": flash_type,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    # If not logged in, default to onboarding tab via flash
    ctx = _build_context()
    return render_template_string(DASHBOARD_HTML, **ctx)


@app.route("/approve/<int:campaign_id>", methods=["POST"])
def approve_campaign(campaign_id):
    # Save edited content from form
    campaign = get_campaign(campaign_id)
    if campaign and campaign.get("content"):
        try:
            content = json.loads(campaign["content"]) if isinstance(campaign["content"], str) else campaign["content"]
        except (json.JSONDecodeError, TypeError):
            content = {}

        # Update content with edited values from form
        for key in list(content.keys()):
            if key.startswith("_"):
                continue
            form_val = request.form.get(f"content_{key}")
            form_title = request.form.get(f"content_{key}_title")
            form_body = request.form.get(f"content_{key}_body")
            if form_title is not None and form_body is not None:
                content[key] = {"title": form_title, "body": form_body}
            elif form_val is not None:
                content[key] = form_val

        update_campaign_status(campaign_id, "approved", json.dumps(content))
    else:
        update_campaign_status(campaign_id, "approved")
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
    """Trigger content generation for a campaign using AI APIs."""
    import asyncio
    campaign = get_campaign(campaign_id)
    if not campaign:
        return redirect(url_for("index"))

    brief = {
        "campaign_id": campaign["server_id"],
        "assignment_id": campaign["assignment_id"],
        "title": campaign["title"],
        "brief": campaign["brief"],
        "content_guidance": campaign.get("content_guidance", ""),
        "assets": json.loads(campaign["assets"]) if isinstance(campaign["assets"], str) else campaign.get("assets", {}),
    }

    try:
        from utils.content_generator import ContentGenerator
        gen = ContentGenerator()

        # Get enabled platforms
        platforms_config = _load_platforms_config()
        enabled = [p for p, cfg in platforms_config.items() if cfg.get("enabled")]

        content = asyncio.run(gen.generate(brief, enabled_platforms=enabled))
        content.pop("image_prompt", None)  # Remove image prompt from stored content
        update_campaign_status(campaign_id, "content_generated", json.dumps(content))
    except Exception as e:
        ctx = _build_context(
            flash_msg=f"Content generation failed: {e}",
            flash_type="error",
        )
        return render_template_string(DASHBOARD_HTML, **ctx)

    ctx = _build_context(
        flash_msg="Content generated! Review and approve below.",
        flash_type="success",
    )
    return render_template_string(DASHBOARD_HTML, **ctx)


@app.route("/settings", methods=["POST"])
def save_settings():
    mode = request.form.get("mode", "semi_auto")
    poll_interval = request.form.get("poll_interval", "600")
    set_setting("mode", mode)
    set_setting("poll_interval", poll_interval)

    if is_logged_in():
        try:
            update_profile(mode=mode)
        except Exception:
            pass

    ctx = _build_context(flash_msg="Settings saved.", flash_type="success")
    return render_template_string(DASHBOARD_HTML, **ctx)


@app.route("/poll", methods=["POST"])
def manual_poll():
    """Manually trigger a campaign poll."""
    if not is_logged_in():
        ctx = _build_context(flash_msg="Not logged in. Complete onboarding first.", flash_type="error")
        return render_template_string(DASHBOARD_HTML, **ctx), 401
    try:
        from utils.local_db import upsert_campaign
        campaigns = poll_campaigns()
        for c in campaigns:
            upsert_campaign(c)
        ctx = _build_context(
            flash_msg=f"Poll complete. {len(campaigns)} campaign(s) found.",
            flash_type="success",
        )
        return render_template_string(DASHBOARD_HTML, **ctx)
    except Exception as e:
        ctx = _build_context(flash_msg=f"Poll failed: {e}", flash_type="error")
        return render_template_string(DASHBOARD_HTML, **ctx), 500


# ── Onboarding routes ─────────────────────────────────────────────


@app.route("/onboarding/auth", methods=["POST"])
def onboarding_auth():
    """Handle register or login from the onboarding flow."""
    action = request.form.get("action", "register")
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        ctx = _build_context(flash_msg="Email and password are required.", flash_type="error")
        return render_template_string(DASHBOARD_HTML, **ctx)

    try:
        if action == "register":
            register(email, password)
            msg = f"Account created for {email}. Welcome!"
        else:
            login(email, password)
            msg = f"Logged in as {email}."
        ctx = _build_context(flash_msg=msg, flash_type="success")
        ctx["onboarding_step"] = 2  # Auto-advance to step 2
        return render_template_string(DASHBOARD_HTML, **ctx)
    except Exception as e:
        error_msg = str(e)
        # Parse server validation errors into friendly messages
        if "value is not a valid email" in error_msg:
            error_msg = "Please enter a valid email address."
        elif "already registered" in error_msg.lower() or "already exists" in error_msg.lower():
            error_msg = "An account with this email already exists. Try logging in."
        elif "Invalid credentials" in error_msg or "401" in error_msg:
            error_msg = "Invalid email or password."
        ctx = _build_context(flash_msg=f"Registration failed: {error_msg}", flash_type="error")
        ctx["onboarding_step"] = 1  # Stay on auth step
        return render_template_string(DASHBOARD_HTML, **ctx)


@app.route("/onboarding/profile", methods=["POST"])
def onboarding_profile():
    """Save niche tags and follower counts."""
    niche_raw = request.form.get("niche_tags", "")
    niche_tags = [t.strip() for t in niche_raw.split(",") if t.strip()]

    # Gather follower counts from form
    follower_counts = {}
    for key in request.form:
        if key.startswith("followers_"):
            platform = key.replace("followers_", "")
            val = request.form.get(key, "0")
            try:
                follower_counts[platform] = int(val) if val else 0
            except ValueError:
                follower_counts[platform] = 0

    # Determine connected platforms
    platform_status = _get_platform_connection_status()
    platforms = {}
    for p in platform_status:
        if p["connected"]:
            platforms[p["key"]] = {
                "connected": True,
                "username": "",
                "follower_count": follower_counts.get(p["key"], 0),
            }

    if is_logged_in():
        try:
            update_profile(
                niche_tags=niche_tags,
                follower_counts=follower_counts,
                platforms=platforms,
            )
        except Exception:
            pass

    ctx = _build_context(flash_msg="Profile updated. Choose your mode to finish.", flash_type="success")
    ctx["onboarding_step"] = 4  # Advance to mode selection
    return render_template_string(DASHBOARD_HTML, **ctx)


@app.route("/onboarding/mode", methods=["POST"])
def onboarding_mode():
    """Save mode and complete onboarding."""
    mode = request.form.get("mode", "semi_auto")
    set_setting("mode", mode)
    set_setting("onboarding_done", "true")

    if is_logged_in():
        try:
            update_profile(mode=mode)
        except Exception:
            pass

    ctx = _build_context(
        flash_msg="Setup complete! You're ready to receive campaigns.",
        flash_type="success",
    )
    return render_template_string(DASHBOARD_HTML, **ctx)


# ── JSON API (for future desktop app) ─────────────────────────────


@app.route("/api/campaigns")
def api_campaigns():
    return jsonify(get_campaigns())


@app.route("/api/earnings")
def api_earnings_api():
    return jsonify(get_earnings_summary())


@app.route("/api/posts")
def api_posts():
    return jsonify(get_all_posts())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    port = int(os.getenv("CAMPAIGN_DASHBOARD_PORT", "5222"))
    print(f"Amplifier Dashboard running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
