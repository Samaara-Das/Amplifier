# Batch 3: Product Feature Specifications

**Tasks:** #16 (content formats), #5 (invitation UX), #7 (repost campaign UI), #8 (admin payout actions)

---

## Task #16 — Content Formats (Threads, Polls, Carousels)

### What It Does

Expand posting beyond single text + image to the most-used content formats per platform. The content agent decides which format to use based on the campaign goal and platform strategy.

### IMPORTANT: Research First

Before implementing, research the **most-used content formats on each platform in 2026** by actual engagement data. Build formats people use, not an exhaustive list.

### Formats to Implement (by platform)

| Platform | Format | Priority | How it works |
|----------|--------|----------|-------------|
| **X** | Text post | Already working | Single tweet ≤280 chars |
| **X** | Text + image | Already working | Tweet with attached image |
| **X** | Thread | HIGH | Multiple linked tweets. Click "+" in compose to add tweet to thread. Post all at once. |
| **X** | Poll | MEDIUM | Tweet with poll options. Duration 1-7 days. |
| **LinkedIn** | Text post | Already working | Single post |
| **LinkedIn** | Text + image | Already working | Post with attached image |
| **LinkedIn** | Poll | HIGH | Create a poll in compose modal. Question + 2-4 options. Duration 1-2 weeks. |
| **LinkedIn** | Document/carousel | HIGH | Upload a PDF that displays as swipeable slides. Currently highest organic reach on LinkedIn. |
| **Facebook** | Text post | Already working | Single post |
| **Facebook** | Text + image | Already working | Post with attached image |
| **Facebook** | Poll | MEDIUM | Create poll in compose. Question + options. |
| **Facebook** | Photo album | LOW | Multiple images in one post. |
| **Reddit** | Text post | Already working | Title + body |
| **Reddit** | Image post | Already working | Title + image |
| **Reddit** | Link post | MEDIUM | Title + external URL. Different submit tab. |

### New JSON Posting Scripts Needed

Each new format needs a JSON script in `config/scripts/`:

- `x_thread.json` — compose first tweet → click "+" → type next tweet → repeat → post all
- `x_poll.json` — compose tweet → click poll icon → fill question + options → set duration → post
- `linkedin_poll.json` — click "Start a post" → click "Create a poll" → fill fields → post
- `linkedin_carousel.json` — click "Start a post" → click "Add a document" → upload PDF → add title → post
- `facebook_poll.json` — click "What's on your mind" → click "Poll" → fill fields → post
- `reddit_link.json` — navigate to submit → click "Link" tab → fill title + URL → post

### Content Agent Integration

The content agent's strategy phase determines the format per platform per post. The creation phase must produce format-specific JSON output:

**Thread output:**
```json
{"platform": "x", "format": "thread", "content": {
    "tweets": ["First tweet (hook)", "Second tweet (detail)", "Third tweet (CTA)"]
}}
```

**Poll output:**
```json
{"platform": "linkedin", "format": "poll", "content": {
    "question": "What's your biggest challenge with X?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "duration_days": 3
}}
```

**Carousel output (LinkedIn):**
```json
{"platform": "linkedin", "format": "carousel", "content": {
    "title": "5 Things I Learned About X",
    "slides": [
        {"text": "Slide 1: The problem", "image_prompt": "..."},
        {"text": "Slide 2: The solution", "image_prompt": "..."}
    ]
}}
```

### Posting Orchestrator Update

`scripts/post.py` `post_to_platform()` must select the right JSON script based on `content_format`:

```python
def _get_script_path(platform: str, content_format: str) -> Path:
    script_name = f"{platform}_{content_format}.json"
    path = ROOT / "config" / "scripts" / script_name
    if path.exists():
        return path
    return ROOT / "config" / "scripts" / f"{platform}_post.json"  # fallback to basic
```

### Local DB Changes

Add `format_type` column to `post_schedule` table so the posting engine knows which script to use:
```sql
ALTER TABLE post_schedule ADD COLUMN format_type TEXT DEFAULT 'text';
```

The `agent_draft` table already has `format_type` from Phase C migration.

### Verification

1. Generate content for X with `goal=virality`. Strategy should sometimes produce a thread (3-5 tweets). Post via `x_thread.json`. Verify thread appears on X as linked tweets.
2. Generate content for LinkedIn with `goal=engagement`. Strategy should produce a poll. Post via `linkedin_poll.json`. Verify poll appears with all options.
3. Attempt thread format on Reddit (not supported). Must gracefully fall back to text post.
4. All existing text + image posting still works (no regressions).

---

## Task #5 — Invitation UX (Countdown, Expired Badge, Decline Reason)

### What It Does

Improve the campaign invitation interface so users can see how much time they have to respond, clearly identify expired invitations, and provide feedback when declining.

### Current State

The invitation card (in `campaigns.html`) shows:
- Campaign title, company name, brief, content guidance, product images, payout rates
- "Expires {date}" as static text
- Accept and Reject buttons

### What's Missing

1. **Countdown timer** — show "2h 15m remaining" that updates in real-time
2. **Expired visual state** — red badge, grayed-out card, disabled buttons
3. **Decline reason** — optional text input when rejecting

### Countdown Timer Implementation

Add JavaScript to the invitation card that computes time remaining from `expires_at`:

```javascript
function updateCountdown(element, expiresAt) {
    const diff = new Date(expiresAt) - new Date();
    if (diff <= 0) {
        element.textContent = "EXPIRED";
        element.style.color = "#ef4444";
        // Gray out parent card, disable buttons
        const card = element.closest('.invitation-card');
        card.style.opacity = '0.5';
        card.querySelectorAll('button').forEach(b => b.disabled = true);
        return false; // stop updating
    }
    const hours = Math.floor(diff / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    if (hours > 24) {
        const days = Math.floor(hours / 24);
        element.textContent = `${days}d ${hours % 24}h remaining`;
    } else {
        element.textContent = `${hours}h ${mins}m remaining`;
    }
    if (hours < 6) element.style.color = "#f59e0b"; // yellow warning
    if (hours < 1) element.style.color = "#ef4444"; // red urgent
    return true; // keep updating
}

// Update every minute
setInterval(() => {
    document.querySelectorAll('[data-expires]').forEach(el => {
        updateCountdown(el, el.dataset.expires);
    });
}, 60000);
```

### Expired Badge

When `expires_at < now`:
- Show red "EXPIRED" badge next to campaign title
- Gray out the entire invitation card (opacity 0.5)
- Disable Accept/Reject buttons
- Move expired invitations to the bottom of the list

### Decline Reason

When user clicks "Reject":
1. Show a small text input (optional): "Why are you declining? (optional)"
2. Common quick-select reasons: "Not relevant to my audience", "Payout too low", "Don't have time", "Other"
3. Send the reason with the reject API call: `POST /api/campaigns/invitations/{id}/reject` with body `{"reason": "..."}`
4. Server stores the reason on `CampaignAssignment.decline_reason` (new column)
5. Company can see decline reasons on their campaign detail page — helps them improve targeting

### Server Changes

Add `decline_reason` column to `CampaignAssignment` model:
```python
decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Update reject endpoint in `server/app/routers/invitations.py` to accept and store the reason.

### Verification

1. View invitation expiring in 2 hours. Expect: countdown shows "2h 0m remaining", updates every minute.
2. View invitation expired 1 hour ago. Expect: red "EXPIRED" badge, card grayed out, buttons disabled.
3. Reject with reason "Payout too low". Expect: reason stored on server. Company sees it on campaign detail.
4. Reject without reason (leave empty). Expect: works fine, reason is null.

---

## Task #7 — Repost Campaign Company Creation UI

### What It Does

The company dashboard needs a UI for creating repost campaigns — where the company provides exact pre-written post text per platform instead of using AI generation.

### Current State

- Campaign type toggle exists in `campaign_create.html` (AI Generated vs Repost buttons)
- Repost text editors exist for X (280 char limit), LinkedIn (3000), Facebook, Reddit (title + body)
- Backend `CampaignPost` model and API endpoints exist
- Background agent handles repost campaigns (skips AI gen, schedules pre-written content directly)

**What's actually missing (from the audit):** The repost content textareas in `campaign_create.html` exist but the form submission may not properly save the repost content to the `campaign_posts` table. Need to verify the end-to-end flow.

### What to Verify/Fix

1. **Form submission flow:** When company selects "Repost" type and fills in per-platform text, on form submit:
   - `campaign_type` must be set to `"repost"` in the campaign record
   - Each platform's text must be saved as a `CampaignPost` row linked to the campaign
   - The brief should be auto-generated from the repost content (already in JS: lines 362-367 of campaign_create.html)

2. **Editing repost content:** On the campaign detail/edit page, if `campaign_type == "repost"`, show the per-platform text editors pre-filled with existing `campaign_posts` content. Allow editing.

3. **Character counts:** Each platform editor shows remaining chars (X: 280, LinkedIn: 3000, Reddit title: 300).

4. **Preview:** Show how the repost content will look on each platform (use the platform preview CSS from Task #65).

5. **Validation:** Don't allow activation of a repost campaign with zero platform content. At least one platform must have text.

### API Endpoints (verify these exist and work)

- `POST /company/campaigns/{id}/posts` — add a campaign post
- `GET /company/campaigns/{id}/posts` — list campaign posts
- `DELETE /company/campaigns/{id}/posts/{post_id}` — delete a campaign post

### Verification

1. Company creates repost campaign. Fills X text "Check out our product #ad" and LinkedIn text. Submits. Expect: `campaign_type = "repost"` in DB, 2 rows in `campaign_posts`.
2. User polls. Repost campaign appears with `repost_content` populated. Content matches what company typed.
3. User accepts. Background agent does NOT call ContentAgent. Drafts are pre-filled from repost content.
4. Company edits the repost text after creation. Changes are saved and reflected on next user poll.
5. Company tries to activate repost campaign with zero content filled. Expect: validation error.

---

## Task #8 — Admin Payout Void/Approve Actions

### What It Does

The admin financial dashboard currently shows a read-only list of payouts. Admin needs to be able to void fraudulent payouts and manually approve payouts that are stuck.

### Current State

`server/app/routers/admin/financial.py` has:
- `GET /admin/financial` — payout list with stats, filtering by status, search by email
- `POST /admin/financial/run-billing` — trigger billing cycle
- `POST /admin/financial/run-payout` — trigger payout processing
- `POST /admin/financial/run-earning-promotion` — promote pending → available
- `POST /admin/financial/run-payout-processing` — process available → paid

**Missing:** Per-payout actions (void, approve, reject).

### Actions to Add

#### Void Payout
- Admin clicks "Void" on a pending or available payout
- Payout status changes to `"voided"`
- `payout.amount_cents` is returned to `campaign.budget_remaining`
- `user.earnings_balance_cents` is decremented by the voided amount
- Audit log entry created with admin action + reason

**When to void:** Suspected fake metrics, post was deleted, user violated terms.

#### Force-Approve Payout
- Admin clicks "Approve" on a pending payout to skip the 7-day hold
- Payout status changes from `"pending"` to `"available"` immediately
- No change to amounts — just accelerates the hold period

**When to force-approve:** User request, manual verification completed, time-sensitive situation.

### Implementation

Add two POST endpoints to `server/app/routers/admin/financial.py`:

```python
@router.post("/financial/void/{payout_id}")
async def void_payout(payout_id: int, request: Request, ...):
    reason = (await request.form()).get("reason", "Admin voided")
    payout = await db.get(Payout, payout_id)
    if payout.status not in ("pending", "available"):
        # Can't void already-paid or already-voided payouts
        return error

    old_status = payout.status
    payout.status = "voided"

    # Return funds to campaign budget
    campaign = await db.get(Campaign, payout.campaign_id)
    if campaign:
        campaign.budget_remaining += payout.amount  # or amount_cents

    # Decrement user balance
    user = await db.get(User, payout.user_id)
    if user and old_status == "available":
        user.earnings_balance_cents -= payout.amount_cents

    await log_admin_action(db, request, "payout_voided", "payout", payout_id, {"reason": reason})
    await db.commit()

@router.post("/financial/approve/{payout_id}")
async def force_approve_payout(payout_id: int, request: Request, ...):
    payout = await db.get(Payout, payout_id)
    if payout.status != "pending":
        return error
    payout.status = "available"
    payout.available_at = func.now()
    await log_admin_action(db, request, "payout_force_approved", "payout", payout_id, {})
    await db.commit()
```

### UI Changes

In `server/app/templates/admin/financial.html`, add action buttons per payout row:

- **Void button** (red) — shown for `pending` and `available` payouts. Clicking opens a modal/prompt for reason.
- **Approve button** (green) — shown only for `pending` payouts. Immediately moves to `available`.
- **Neither** for `paid`, `voided`, or `failed` payouts (terminal states).

### Verification

1. Payout with `status=pending`. Click Void with reason "Suspected fake metrics". Expect: status → "voided", campaign budget restored, audit log entry.
2. Payout with `status=pending`. Click Approve. Expect: status → "available" immediately (hold period skipped).
3. Payout with `status=paid`. Expect: no Void or Approve buttons shown (terminal state).
4. Void an `available` payout. Expect: status → "voided", user's earnings_balance_cents decremented, campaign budget restored.
5. Check audit log. Expect: both actions logged with admin details and timestamp.
