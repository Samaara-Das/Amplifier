"""Review dashboard — Flask app for reviewing, editing, approving, and rejecting drafts."""

import json
import os
import sys
from pathlib import Path

import subprocess
import threading

from flask import Flask, jsonify, redirect, render_template_string, request, url_for
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / "config" / ".env")
os.environ.setdefault("AUTO_POSTER_ROOT", str(ROOT))

from utils.draft_manager import approve_draft, edit_draft, get_failed_drafts, get_review_drafts, reject_draft, retry_failed_draft

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

PILLAR_COLORS = {
    "stop_losing_money": {"bg": "#7f1d1d", "color": "#fca5a5", "label": "Stop Losing Money"},
    "make_money_while_you_sleep": {"bg": "#14532d", "color": "#86efac", "label": "Make Money While You Sleep"},
    "market_cheat_code": {"bg": "#1e3a5f", "color": "#93c5fd", "label": "Market Cheat Code"},
    "proof_not_promises": {"bg": "#4a1d6a", "color": "#d8b4fe", "label": "Proof, Not Promises"},
    "future_proof_your_income": {"bg": "#713f12", "color": "#fde68a", "label": "Future-Proof Your Income"},
    "wildcard": {"bg": "#334155", "color": "#cbd5e1", "label": "Wildcard"},
}

SLOT_TIMES = {
    1: "8:00 AM EST",
    2: "10:00 AM EST",
    3: "1:00 PM EST",
    4: "3:00 PM EST",
    5: "6:00 PM EST",
    6: "8:00 PM EST",
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
        .draft-pillar { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; margin-left: 8px; }
        .draft-meta-badges { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
        .meta-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; background: #2a2a3a; color: #aaa; }
        .meta-badge.slot { background: #1e293b; color: #94a3b8; }
        .meta-badge.format { background: #1a1a2e; color: #818cf8; }
        .meta-badge.platform-target { background: #1c2333; color: #67e8f9; }
        .image-preview { background: #12121e; border: 1px solid #333; border-radius: 6px; padding: 10px; margin-top: 8px; font-size: 12px; color: #888; }
        .image-preview-label { font-size: 11px; color: #666; margin-bottom: 4px; }
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
        .ai-rewrite-bar { display: flex; gap: 8px; margin-top: 14px; margin-bottom: 4px; }
        .ai-prompt-input { flex: 1; background: #0f0f1a; color: #e0e0e0; border: 1px solid #333; border-radius: 6px; padding: 8px 12px; font-size: 14px; font-family: inherit; }
        .ai-prompt-input:focus { outline: none; border-color: #a855f7; }
        .ai-prompt-input::placeholder { color: #555; }
        .btn-ai { background: #a855f7; color: #fff; white-space: nowrap; }
        .btn-ai:disabled { background: #555; cursor: wait; }
        .btn-ai.loading { background: #7c3aed; }
        .toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; border-radius: 8px; color: #fff; font-size: 14px; display: none; z-index: 100; }
        .toast.success { background: #22c55e; }
        .toast.error { background: #ef4444; }
        .toast.info { background: #a855f7; }
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
                {% if draft.pillar and draft.pillar in pillar_colors %}
                <span class="draft-pillar" style="background:{{ pillar_colors[draft.pillar].bg }};color:{{ pillar_colors[draft.pillar].color }}">{{ pillar_colors[draft.pillar].label }}</span>
                {% elif draft.pillar %}
                <span class="draft-pillar" style="background:#2a2a4a;color:#8888cc">{{ draft.pillar }}</span>
                {% endif %}
            </div>
            <span class="draft-meta">{{ draft.created_at[:16] if draft.created_at else '' }} &middot; {{ draft._filename }}</span>
        </div>

        <div class="draft-meta-badges">
            {% if draft.slot %}
            <span class="meta-badge slot">Slot {{ draft.slot }}{% if draft.slot in slot_times %} &middot; {{ slot_times[draft.slot] }}{% endif %}</span>
            {% endif %}
            {% if draft.format %}
            <span class="meta-badge format">{{ draft.format }}</span>
            {% endif %}
            {% if draft.platforms %}
            <span class="meta-badge platform-target">{{ draft.platforms | join(', ') }}</span>
            {% endif %}
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
                {% if content is mapping and content.image_text %}
                <div class="image-preview">
                    <div class="image-preview-label">Image text preview</div>
                    {{ content.image_text }}
                </div>
                {% endif %}
            </div>
        </div>
        {% endif %}
        {% endfor %}

        <div class="ai-rewrite-bar">
            <input type="text" class="ai-prompt-input" id="ai-prompt-{{ draft._filename }}"
                   placeholder="Tell AI how to rewrite this post..."
                   onkeydown="if(event.key==='Enter')aiRewrite('{{ draft._filename }}')">
            <button class="btn btn-ai" onclick="aiRewrite('{{ draft._filename }}')" id="ai-btn-{{ draft._filename }}">
                Rewrite with AI
            </button>
        </div>

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

    {% if failed_drafts %}
    <div style="margin-top: 40px; padding-top: 24px; border-top: 1px solid #2a2a3a;">
        <div class="header">
            <h1 style="color: #ef4444;">Failed Drafts</h1>
            <span class="count" style="color: #ef4444;">{{ failed_drafts|length }} failed</span>
        </div>
        {% for draft in failed_drafts %}
        <div class="draft-card" style="border-color: #7f1d1d;">
            <div class="draft-header">
                <span class="draft-title">{{ draft.topic or draft.id or draft._filename }}</span>
                <span class="draft-meta">Failed: {{ draft.failed_at[:16] if draft.failed_at else 'unknown' }}</span>
            </div>
            <div class="draft-meta-badges">
                <span class="meta-badge" style="background:#7f1d1d;color:#fca5a5;">{{ draft.error or 'Unknown error' }}</span>
                {% if draft.retry_count %}
                <span class="meta-badge" style="background:#713f12;color:#fde68a;">Retried {{ draft.retry_count }}x</span>
                {% endif %}
                {% if draft.slot %}
                <span class="meta-badge slot">Slot {{ draft.slot }}</span>
                {% endif %}
            </div>
            <div class="draft-actions">
                <form method="POST" action="{{ url_for('retry', filename=draft._filename) }}" style="display:inline">
                    <button class="btn" style="background:#f59e0b;color:#000;">Retry (move to pending)</button>
                </form>
            </div>
        </div>
        {% endfor %}
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

    function aiRewrite(filename) {
        const input = document.getElementById(`ai-prompt-${filename}`);
        const btn = document.getElementById(`ai-btn-${filename}`);
        const prompt = input.value.trim();
        if (!prompt) { input.focus(); return; }

        btn.disabled = true;
        btn.classList.add('loading');
        btn.textContent = 'Rewriting...';
        showToast('AI is rewriting — this takes ~60s...', 'info');

        fetch(`/ai-rewrite/${filename}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({prompt})
        })
        .then(r => r.json())
        .then(data => {
            btn.disabled = false;
            btn.classList.remove('loading');
            btn.textContent = 'Rewrite with AI';
            if (data.status === 'ok' && data.draft) {
                // Update all textareas with new content
                const content = data.draft.content;
                for (const [platform, val] of Object.entries(content)) {
                    if (typeof val === 'object') {
                        for (const [key, text] of Object.entries(val)) {
                            const ta = document.querySelector(`textarea[data-draft="${filename}"][data-platform="${platform}"][data-key="${key}"]`);
                            if (ta) { ta.value = text; updateCharCount(ta); }
                        }
                    } else {
                        const ta = document.querySelector(`textarea[data-draft="${filename}"][data-platform="${platform}"]:not([data-key])`);
                        if (ta) { ta.value = val; updateCharCount(ta); }
                    }
                }
                // Update topic if changed
                const titleEl = document.querySelector(`#draft-${filename} .draft-title`);
                if (titleEl && data.draft.topic) titleEl.textContent = data.draft.topic;

                input.value = '';
                showToast('Draft rewritten!', 'success');
            } else {
                showToast(data.message || 'Rewrite failed', 'error');
            }
        })
        .catch(() => {
            btn.disabled = false;
            btn.classList.remove('loading');
            btn.textContent = 'Rewrite with AI';
            showToast('Rewrite failed — check console', 'error');
        });
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
    failed = get_failed_drafts()
    return render_template_string(
        DASHBOARD_HTML,
        drafts=drafts,
        failed_drafts=failed,
        char_limits=CHAR_LIMITS,
        platform_labels=PLATFORM_LABELS,
        pillar_colors=PILLAR_COLORS,
        slot_times=SLOT_TIMES,
    )


@app.route("/approve/<filename>", methods=["POST"])
def approve(filename):
    approve_draft(filename)
    return redirect(url_for("index"))


@app.route("/reject/<filename>", methods=["POST"])
def reject(filename):
    reject_draft(filename)
    return redirect(url_for("index"))


@app.route("/retry/<filename>", methods=["POST"])
def retry(filename):
    retry_failed_draft(filename)
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


@app.route("/ai-rewrite/<filename>", methods=["POST"])
def ai_rewrite(filename):
    """Rewrite a draft using Claude CLI based on a user prompt."""
    user_prompt = request.json.get("prompt", "").strip()
    if not user_prompt:
        return jsonify({"status": "error", "message": "No prompt provided"}), 400

    draft_path = ROOT / "drafts" / "review" / filename
    if not draft_path.exists():
        return jsonify({"status": "error", "message": "Draft not found"}), 404

    # Read current draft
    draft = json.loads(draft_path.read_text(encoding="utf-8"))

    # Read content templates for context
    templates_path = ROOT / "config" / "content-templates.md"
    templates = templates_path.read_text(encoding="utf-8") if templates_path.exists() else ""

    # Build Claude prompt
    claude_prompt = (
        "You are a social media content editor. Your job is to update a draft based on the user's instruction.\n\n"
        f"CONTENT GUIDELINES:\n{templates}\n\n"
        f"CURRENT DRAFT:\n{json.dumps(draft, indent=2)}\n\n"
        f"USER INSTRUCTION: {user_prompt}\n\n"
        "Update the draft content based on the instruction above. Keep the exact same JSON structure "
        "(same keys, same platforms, same field names). Only change the content text as needed.\n\n"
        f"Write the updated JSON file to: {draft_path}\n\n"
        "CRITICAL: Write the complete valid JSON file. Keep id, created_at, status, topic, pillar, and all "
        "6 platform keys in content. Respect all platform format rules and character limits."
    )

    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions", "-p", claude_prompt],
            capture_output=True, text=True, env=env, timeout=120,
            cwd=str(ROOT),
        )

        # Re-read the updated file
        if draft_path.exists():
            updated = json.loads(draft_path.read_text(encoding="utf-8"))
            if "content" in updated:
                return jsonify({"status": "ok", "draft": updated})

        return jsonify({
            "status": "error",
            "message": "Claude did not update the file correctly",
            "output": result.stdout[:500] if result.stdout else result.stderr[:500],
        }), 500

    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "Claude CLI timed out (120s)"}), 504
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("REVIEW_DASHBOARD_PORT", "5111"))
    print(f"Review dashboard running at http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
