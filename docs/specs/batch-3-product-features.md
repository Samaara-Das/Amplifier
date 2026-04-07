# Batch 3: Product Feature Specifications

**Tasks:** #16 (content formats), #5 (invitation UX), #7 (repost campaign UI), #8 (admin payout actions)

---

## Task #16 -- Content Formats (Threads, Polls, Carousels)

### What It Does

Expand posting beyond single text + image to the most-used content formats per platform. The content agent decides which format to use based on the campaign goal and platform strategy.

### Research Requirement

Before implementing, research the most-used content formats on each platform in 2026 by actual engagement data. Build formats people use, not an exhaustive list.

### Content Formats by Platform

| Platform | Format | Priority | Description |
|----------|--------|----------|-------------|
| **X** | Text post | Already working | Single post, 280 character limit |
| **X** | Text + image | Already working | Post with attached image |
| **X** | Thread | HIGH | Multiple linked posts published together. 3-5 posts typical. |
| **X** | Poll | MEDIUM | Post with poll options. Duration 1-7 days. |
| **LinkedIn** | Text post | Already working | Single post |
| **LinkedIn** | Text + image | Already working | Post with attached image |
| **LinkedIn** | Poll | HIGH | Poll with question + 2-4 options. Duration 1-2 weeks. |
| **Facebook** | Text post | Already working | Single post |
| **Facebook** | Text + image | Already working | Post with attached image |
| ~~**Facebook**~~ | ~~Poll~~ | ~~REMOVED~~ | ~~Not possible on Facebook~~ |
| **Facebook** | Photo album | LOW | Multiple images in one post |
| **Reddit** | Text post | Already working | Title + body |
| **Reddit** | Image post | Already working | Title + image |
| **Reddit** | Link post | MEDIUM | Title + external URL |

### Format Selection Logic

The content agent's strategy phase decides for each post:
- Which format to use (text, image+text, thread, poll, link post)
- Whether to include image only, text only, or image+text
- This is per-post, per-platform -- not a global setting

The AI makes this decision based on campaign goal, platform norms, and what format best serves the content angle for that day. Examples:
- A stat-heavy post on X --> text only (no image needed)
- A product showcase on Facebook --> image + text
- An educational deep-dive on X --> thread (3-5 posts)
- An engagement play on LinkedIn --> poll

### Content Structure per Format

| Format | Required Fields |
|--------|----------------|
| Text | Platform, text body |
| Text + image | Platform, text body, image |
| Thread (X only) | Platform, ordered list of post texts (each within 280 chars) |
| Poll (X, LinkedIn) | Platform, question text, 2-4 option labels, duration in days |
| Link post (Reddit only) | Platform, title, external URL |

### Graceful Fallback

If a format is not supported on a given platform (e.g., thread on Reddit), the system must gracefully fall back to the default text post format for that platform.

### Acceptance Criteria

1. The content agent can generate thread content for X consisting of 3-5 linked posts. The thread appears on X as properly linked posts.
2. The content agent can generate a poll for LinkedIn with a question and 2-4 options. The poll appears on LinkedIn with all options functional.
3. The content agent can generate a link post for Reddit with a title and external URL. The link post appears on Reddit correctly.
4. When a format is requested on an unsupported platform, the system falls back to a text post without errors.
5. All existing text + image posting continues to work with no regressions.
6. The scheduled post record stores which format was selected so the posting engine uses the correct automation flow.

---

## Task #5 -- Invitation UX (Countdown, Expired Badge, Decline Reason)

### What It Does

Improve the campaign invitation interface so users can see how much time they have to respond, clearly identify expired invitations, and provide feedback when declining.

### Current State

The invitation card shows:
- Campaign title, company name, brief, content guidance, product images, payout rates
- "Expires {date}" as static text
- Accept and Reject buttons

### What's Missing

1. **Countdown timer** -- show time remaining that updates in real-time
2. **Expired visual state** -- clear badge, dimmed card, disabled buttons
3. **Decline reason** -- optional feedback when rejecting

### Countdown Timer Behavior

Each invitation card must display a live countdown showing time remaining until expiry:

| Time Remaining | Display Format | Visual Treatment |
|----------------|---------------|------------------|
| More than 24 hours | "Xd Yh remaining" | Default color |
| 6-24 hours | "Xh Ym remaining" | Default color |
| 1-6 hours | "Xh Ym remaining" | Warning color (yellow/amber) |
| Less than 1 hour | "Xh Ym remaining" | Urgent color (red) |
| Expired | "EXPIRED" | Red text |

The countdown must update automatically every minute without requiring a page refresh.

### Expired Invitation Behavior

When an invitation's expiry time has passed:
- A red "EXPIRED" badge appears next to the campaign title
- The entire invitation card is visually dimmed (grayed out)
- The Accept and Reject buttons are disabled and non-clickable
- Expired invitations are sorted to the bottom of the invitation list
- If a countdown is running and the invitation expires while the user is viewing the page, the card must transition to the expired state automatically

### Decline Reason

When a user clicks "Reject" on an invitation:
1. A small input area appears with the prompt: "Why are you declining? (optional)"
2. Quick-select reason buttons are available: "Not relevant to my audience", "Payout too low", "Don't have time", "Other"
3. The user can select a quick reason, type a custom reason, or skip entirely
4. The decline reason is sent to the server with the rejection
5. The server stores the reason on the invitation record
6. Companies can see aggregated decline reasons on their campaign detail page to improve future targeting

### Acceptance Criteria

1. An invitation expiring in 2 hours displays "2h 0m remaining" in the warning color, and the countdown updates every minute.
2. An invitation that expired 1 hour ago shows a red "EXPIRED" badge, the card is dimmed, and both buttons are disabled.
3. Declining with the reason "Payout too low" stores the reason on the server. The company can see it on their campaign detail page.
4. Declining without a reason (leaving it blank) succeeds without error; the stored reason is empty.
5. Expired invitations appear at the bottom of the list, below all active invitations.
6. If a user is viewing the page and an invitation expires, the card transitions to the expired state without a page refresh.

---

## Task #7 -- [DEFERRED] Repost Campaign

**Status: Deferred to post-launch.** Full spec preserved in the task-master task description (task #7). Some foundational code exists (CampaignPost model, creation form, background agent repost branch) but the feature is not complete or in scope for launch.

---

## Task #8 -- Admin Payout Void/Approve Actions

### What It Does

The admin financial dashboard currently shows a read-only list of payouts. Admins need the ability to void fraudulent payouts and manually approve payouts that are stuck in the hold period.

### Current State

The admin financial dashboard supports:
- Viewing the payout list with stats, filtering by status, and searching by email
- Triggering a billing cycle
- Triggering payout processing
- Promoting pending earnings to available
- Processing available payouts to paid

**Missing:** Per-payout actions (void, approve).

### Void Payout Action

**When to use:** Suspected fake metrics, post was deleted, user violated terms.

**Who can trigger:** Admin only.

**Eligible payout statuses:** Pending or Available.

**What happens when a payout is voided:**

| Step | Effect |
|------|--------|
| 1 | Payout status changes to "voided" |
| 2 | The payout amount is returned to the campaign's remaining budget |
| 3 | If the payout was in "available" status, the user's earnings balance is decremented by the voided amount |
| 4 | An audit log entry is created recording the admin, the action, and the reason provided |

The admin must provide a reason when voiding (e.g., "Suspected fake metrics").

### Force-Approve Payout Action

**When to use:** User request, manual verification completed, time-sensitive situation.

**Who can trigger:** Admin only.

**Eligible payout status:** Pending only.

**What happens when a payout is force-approved:**

| Step | Effect |
|------|--------|
| 1 | Payout status changes from "pending" to "available" immediately |
| 2 | The 7-day hold period is skipped |
| 3 | No change to amounts -- the funds are simply made available sooner |
| 4 | An audit log entry is created recording the admin and the action |

### Button Visibility Rules

| Payout Status | Void Button | Approve Button |
|---------------|-------------|----------------|
| Pending | Shown | Shown |
| Available | Shown | Hidden |
| Paid | Hidden | Hidden |
| Voided | Hidden | Hidden |
| Failed | Hidden | Hidden |

Paid, voided, and failed are terminal states with no available actions.

### Void Reason Input

When an admin clicks "Void", a prompt or modal appears requesting a reason before the action is confirmed. The reason is stored in the audit log.

### Acceptance Criteria

1. A payout with status "pending" is voided with reason "Suspected fake metrics". The payout status becomes "voided", the campaign's remaining budget increases by the payout amount, and an audit log entry is created with the reason.
2. A payout with status "pending" is force-approved. The payout status becomes "available" immediately, skipping the 7-day hold. An audit log entry is created.
3. A payout with status "paid" has no Void or Approve buttons visible (terminal state).
4. A payout with status "available" is voided. The payout status becomes "voided", the user's earnings balance is decremented by the voided amount, and the campaign budget is restored.
5. Both void and force-approve actions appear in the audit log with the admin's identity and a timestamp.
