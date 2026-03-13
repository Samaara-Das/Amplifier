"""Review dashboard — Flask app for reviewing, editing, approving, and rejecting drafts."""

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

from utils.draft_manager import approve_draft, edit_draft, get_review_drafts, reject_draft

app = Flask(__name__)

CHAR_LIMITS = {
    "x": 280,
    "linkedin": 3000,
    "facebook": 63206,
    "instagram": 2200,
    "reddit": None,
    "tiktok": 2200,
}

PLATFORM_LABELS = {
    "x": "X (Twitter)",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "reddit": "Reddit",
    "tiktok": "TikTok",
}

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="60">
    <title>Draft Review Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #2a2a3a; }
        .header h1 { font-size: 24px; color: #fff; }
        .header .count { background: #1a1a2e; padding: 6px 14px; border-radius: 20px; font-size: 14px; color: #8888aa; }
        .actions-bar { margin-bottom: 20px; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: opacity 0.2s; }
        .btn:hover { opacity: 0.85; }
        .btn-approve { background: #22c55e; color: #fff; }
        .btn-reject { background: #ef4444; color: #fff; }
        .btn-approve-all { background: #16a34a; color: #fff; font-size: 15px; padding: 10px 24px; }
        .btn-save { background: #3b82f6; color: #fff; }
        .draft-card { background: #1a1a2e; border-radius: 10px; padding: 20px; margin-bottom: 20px; border: 1px solid #2a2a3a; }
        .draft-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .draft-title { font-size: 18px; font-weight: 600; color: #fff; }
        .draft-meta { font-size: 12px; color: #666; }
        .draft-pillar { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; background: #2a2a4a; color: #8888cc; margin-left: 8px; }
        .platform-tabs { display: flex; gap: 4px; margin-bottom: 12px; flex-wrap: wrap; }
        .platform-tab { padding: 6px 12px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 13px; background: #12121e; color: #888; border: 1px solid #2a2a3a; border-bottom: none; }
        .platform-tab.active { background: #1a1a2e; color: #fff; border-color: #3b82f6; }
        .platform-content { display: none; }
        .platform-content.active { display: block; }
        .platform-section { background: #12121e; border-radius: 0 6px 6px 6px; padding: 12px; border: 1px solid #2a2a3a; }
        .char-count { font-size: 12px; color: #666; margin-bottom: 6px; }
        .char-count.over { color: #ef4444; }
        textarea { width: 100%; min-height: 100px; background: #0f0f1a; color: #e0e0e0; border: 1px solid #333; border-radius: 4px; padding: 10px; font-family: inherit; font-size: 14px; resize: vertical; line-height: 1.5; }
        textarea:focus { outline: none; border-color: #3b82f6; }
        .draft-actions { display: flex; gap: 8px; margin-top: 16px; align-items: center; }
        .draft-actions .spacer { flex: 1; }
        .empty-state { text-align: center; padding: 80px 20px; color: #555; }
        .empty-state h2 { font-size: 20px; color: #888; margin-bottom: 8px; }
        .structured-fields { display: flex; flex-direction: column; gap: 8px; }
        .structured-fields label { font-size: 12px; color: #888; font-weight: 500; }
        .toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; border-radius: 8px; color: #fff; font-size: 14px; display: none; z-index: 100; }
        .toast.success { background: #22c55e; }
        .toast.error { background: #ef4444; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Draft Review</h1>
        <span class="count">{{ drafts|length }} draft{{ 's' if drafts|length != 1 }} awaiting review</span>
    </div>

    {% if drafts %}
    <div class="actions-bar">
        <form method="POST" action="{{ url_for('approve_all') }}" style="display:inline">
            <button class="btn btn-approve-all" type="submit">Approve All ({{ drafts|length }})</button>
        </form>
    </div>

    {% for draft in drafts %}
    <div class="draft-card" id="draft-{{ draft._filename }}">
        <div class="draft-header">
            <div>
                <span class="draft-title">{{ draft.topic or draft.id or draft._filename }}</span>
                {% if draft.pillar %}<span class="draft-pillar">Pillar {{ draft.pillar }}</span>{% endif %}
            </div>
            <span class="draft-meta">{{ draft.created_at[:16] if draft.created_at else '' }} &middot; {{ draft._filename }}</span>
        </div>

        <div class="platform-tabs" data-draft="{{ draft._filename }}">
            {% for platform in ['x', 'linkedin', 'facebook', 'instagram', 'reddit', 'tiktok'] %}
            {% if platform in draft.content %}
            <div class="platform-tab {% if loop.first %}active{% endif %}"
                 onclick="switchTab('{{ draft._filename }}', '{{ platform }}')">
                {{ platform_labels.get(platform, platform) }}
            </div>
            {% endif %}
            {% endfor %}
        </div>

        {% for platform in ['x', 'linkedin', 'facebook', 'instagram', 'reddit', 'tiktok'] %}
        {% if platform in draft.content %}
        {% set content = draft.content[platform] %}
        <div class="platform-content {% if loop.first %}active{% endif %}"
             id="content-{{ draft._filename }}-{{ platform }}">
            <div class="platform-section">
                {% if content is mapping %}
                    {# Structured content (reddit, tiktok, or text+image) #}
                    <div class="structured-fields">
                        {% for key, val in content.items() %}
                        <div>
                            <label>{{ key }}</label>
                            <div class="char-count" id="cc-{{ draft._filename }}-{{ platform }}-{{ key }}">{{ val|length }} chars</div>
                            <textarea data-draft="{{ draft._filename }}" data-platform="{{ platform }}"
                                      data-key="{{ key }}" rows="3"
                                      oninput="updateCharCount(this)">{{ val }}</textarea>
                        </div>
                        {% endfor %}
                    </div>
                {% else %}
                    {# Plain text content #}
                    {% set limit = char_limits.get(platform) %}
                    <div class="char-count {% if limit and content|length > limit %}over{% endif %}"
                         id="cc-{{ draft._filename }}-{{ platform }}">
                        {{ content|length }}{% if limit %}/{{ limit }}{% endif %} chars
                    </div>
                    <textarea data-draft="{{ draft._filename }}" data-platform="{{ platform }}"
                              rows="{{ [3, (content|length // 60 + 2)]|max }}"
                              oninput="updateCharCount(this)">{{ content }}</textarea>
                {% endif %}
            </div>
        </div>
        {% endif %}
        {% endfor %}

        <div class="draft-actions">
            <button class="btn btn-save" onclick="saveDraft('{{ draft._filename }}')">Save Edits</button>
            <div class="spacer"></div>
            <form method="POST" action="{{ url_for('reject', filename=draft._filename) }}" style="display:inline">
                <button class="btn btn-reject" type="submit">Reject</button>
            </form>
            <form method="POST" action="{{ url_for('approve', filename=draft._filename) }}" style="display:inline">
                <button class="btn btn-approve" type="submit">Approve</button>
            </form>
        </div>
    </div>
    {% endfor %}

    {% else %}
    <div class="empty-state">
        <h2>No drafts to review</h2>
        <p>You're all caught up. New drafts will appear here after generation runs.</p>
    </div>
    {% endif %}

    <div class="toast" id="toast"></div>

    <script>
    function switchTab(draftFilename, platform) {
        // Hide all content for this draft
        document.querySelectorAll(`[id^="content-${draftFilename}-"]`).forEach(el => el.classList.remove('active'));
        // Deactivate all tabs for this draft
        document.querySelector(`[data-draft="${draftFilename}"]`).querySelectorAll('.platform-tab').forEach(t => t.classList.remove('active'));
        // Activate selected
        document.getElementById(`content-${draftFilename}-${platform}`).classList.add('active');
        event.target.classList.add('active');
    }

    function updateCharCount(textarea) {
        const draft = textarea.dataset.draft;
        const platform = textarea.dataset.platform;
        const key = textarea.dataset.key;
        const id = key ? `cc-${draft}-${platform}-${key}` : `cc-${draft}-${platform}`;
        const el = document.getElementById(id);
        if (el) {
            const limits = {{ char_limits | tojson }};
            const limit = limits[platform];
            const len = textarea.value.length;
            el.textContent = limit ? `${len}/${limit} chars` : `${len} chars`;
            el.className = 'char-count' + (limit && len > limit ? ' over' : '');
        }
    }

    function showToast(message, type) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type}`;
        toast.style.display = 'block';
        setTimeout(() => { toast.style.display = 'none'; }, 3000);
    }

    function saveDraft(filename) {
        const textareas = document.querySelectorAll(`textarea[data-draft="${filename}"]`);
        const content = {};
        textareas.forEach(ta => {
            const platform = ta.dataset.platform;
            const key = ta.dataset.key;
            if (key) {
                if (!content[platform]) content[platform] = {};
                content[platform][key] = ta.value;
            } else {
                content[platform] = ta.value;
            }
        });

        fetch(`/edit/${filename}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(content)
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'ok') showToast('Edits saved', 'success');
            else showToast('Save failed', 'error');
        })
        .catch(() => showToast('Save failed', 'error'));
    }
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    drafts = get_review_drafts()
    return render_template_string(
        DASHBOARD_HTML,
        drafts=drafts,
        char_limits=CHAR_LIMITS,
        platform_labels=PLATFORM_LABELS,
    )


@app.route("/approve/<filename>", methods=["POST"])
def approve(filename):
    approve_draft(filename)
    return redirect(url_for("index"))


@app.route("/reject/<filename>", methods=["POST"])
def reject(filename):
    reject_draft(filename)
    return redirect(url_for("index"))


@app.route("/approve-all", methods=["POST"])
def approve_all():
    for draft in get_review_drafts():
        approve_draft(draft["_filename"])
    return redirect(url_for("index"))


@app.route("/edit/<filename>", methods=["POST"])
def edit(filename):
    updated_content = request.json
    result = edit_draft(filename, updated_content)
    return jsonify({"status": "ok", "draft_id": result.get("id")})


if __name__ == "__main__":
    port = int(os.getenv("REVIEW_DASHBOARD_PORT", "5111"))
    print(f"Review dashboard running at http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
