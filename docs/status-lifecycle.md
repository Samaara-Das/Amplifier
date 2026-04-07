# Status Lifecycle Reference

Every status field across all models and databases, their possible values, valid transitions, and what triggers each transition.

---

## Server Models (Supabase PostgreSQL / SQLite)

### Campaign.status

**Model:** `server/app/models/campaign.py`
**Default:** `"draft"`

```
draft ──→ active ──→ paused ──→ active (resume)
  │         │          │
  │         │          └──→ completed (budget exhausted, auto_complete)
  │         │
  │         ├──→ completed (budget exhausted, auto_complete)
  │         │
  │         └──→ cancelled
  │
  └──→ cancelled
```

| From | To | Trigger | File |
|---|---|---|---|
| `draft` | `active` | Company activates campaign (PATCH /company/campaigns/{id} with status="active"). Deducts budget from company.balance. | campaigns.py |
| `draft` | `cancelled` | Company or admin cancels. Refunds budget if any was allocated. | campaigns.py |
| `active` | `paused` | Company pauses; OR budget exhausted with `budget_exhaustion_action = "auto_pause"` | campaigns.py, billing.py |
| `active` | `completed` | Budget remaining < $1.00 with `budget_exhaustion_action = "auto_complete"` | billing.py |
| `active` | `cancelled` | Admin cancels campaign. Remaining budget refunded. | campaigns.py |
| `paused` | `active` | Company resumes; OR budget top-up on a paused campaign auto-resumes it | campaigns.py |
| `paused` | `completed` | Budget exhausted with `auto_complete` | billing.py |
| `paused` | `cancelled` | Admin cancels | campaigns.py |

**Gates:** Cannot activate if `screening_status` is `flagged` or `rejected`. Must have sufficient company balance.

---

### Campaign.screening_status

**Model:** `server/app/models/campaign.py`
**Default:** `"pending"`

| Value | Meaning |
|---|---|
| `pending` | Awaiting content review (legacy — v2 auto-approves) |
| `approved` | Passed review, can be activated |
| `flagged` | Suspicious content detected, awaiting admin review |
| `rejected` | Admin rejected — campaign must be cancelled |

| From | To | Trigger | File |
|---|---|---|---|
| `pending` | `approved` | Auto-approved on creation in v2; or content edit resets to approved | campaigns.py |
| any | `flagged` | AI content screening detects flagged keywords | campaign_wizard.py |
| `flagged` | `approved` | Admin approves via POST /admin/review-queue/{id}/approve | admin/review.py |
| `flagged` | `rejected` | Admin rejects via POST /admin/review-queue/{id}/reject | admin/review.py |

---

### CampaignAssignment.status

**Model:** `server/app/models/assignment.py`
**Default:** `"pending_invitation"`

```
pending_invitation ──→ accepted ──→ content_generated ──→ posted ──→ paid
        │                │
        ├──→ rejected    └──→ skipped
        │
        └──→ expired (auto, 3-day TTL)
```

| From | To | Trigger | File |
|---|---|---|---|
| `pending_invitation` | `accepted` | User accepts via POST /invitations/{id}/accept (within expiry) | invitations.py |
| `pending_invitation` | `rejected` | User rejects via POST /invitations/{id}/reject | invitations.py |
| `pending_invitation` | `expired` | `expires_at` has passed; auto-expires on next fetch | invitations.py |
| `accepted` | `content_generated` | Content generated for user (workflow stage) | campaigns.py |
| `content_generated` | `posted` | PATCH /campaigns/assignments/{id} with status="posted" | campaigns.py |
| `posted` | `paid` | Billing cycle processes metrics and creates payout | billing.py |
| `accepted`/`content_generated`/`posted` | `skipped` | User skips campaign | campaigns.py |

**Active statuses** (for tier-based campaign cap): `accepted`, `content_generated`, `posted`, `metrics_collected`

---

### Post.status

**Model:** `server/app/models/post.py`
**Default:** `"live"`

| Value | Meaning |
|---|---|
| `live` | Post is published on platform |
| `deleted` | Post removed — triggers earning void |
| `flagged` | Suspicious metrics or policy violation |

| From | To | Trigger | File |
|---|---|---|---|
| `live` | `deleted` | PATCH /posts/{id}/status with status="deleted" — auto-voids pending earnings | metrics.py, billing.py |
| `live` | `flagged` | Admin or system flags post | metrics.py |

---

### Payout.status

**Model:** `server/app/models/payout.py`
**Default:** `"pending"`
**Hold constant:** `EARNING_HOLD_DAYS = 7`

```
pending (7-day hold) ──→ available ──→ processing ──→ paid
        │                                    │
        └──→ voided (fraud)                  └──→ failed ──→ available (retry)
```

| From | To | Trigger | File |
|---|---|---|---|
| (new) | `pending` | Billing cycle creates Payout with `available_at = now + 7 days` | billing.py |
| `pending` | `available` | `promote_pending_earnings()` — runs periodically, moves payouts where `available_at <= now` | billing.py |
| `pending` | `available` | Admin force-approves (skips hold period) | admin/financial.py |
| `pending` | `voided` | `void_earnings_for_post()` — fraud detected during hold period. Funds return to campaign budget. | billing.py |
| `available` | `processing` | `run_payout_cycle()` — batches eligible users ($10+ balance) | payments.py |
| `available` | `voided` | Admin voids — user earnings balance decremented, funds return to campaign | admin/financial.py |
| `processing` | `paid` | `process_pending_payouts()` — Stripe Connect transfer succeeds | payments.py |
| `processing` | `failed` | Stripe transfer fails — funds return to user's available balance | payments.py |

**Terminal states:** `paid`, `voided`

---

### User.status

**Model:** `server/app/models/user.py`
**Default:** `"active"`

| Value | Meaning |
|---|---|
| `active` | Normal state — can participate in campaigns |
| `suspended` | Temporarily blocked (under review) |
| `banned` | Permanently blocked |

| From | To | Trigger |
|---|---|---|
| `active` | `suspended` | Admin suspends user |
| `suspended` | `active` | Admin unsuspends user |
| `active`/`suspended` | `banned` | Admin bans user |

---

### User.tier (Reputation)

**Model:** `server/app/models/user.py`
**Default:** `"seedling"`

```
seedling ──→ grower ──→ amplifier
                ↑           │
                └───────────┘ (demotion on fraud)
```

| From | To | Trigger | File |
|---|---|---|---|
| `seedling` | `grower` | 20+ successful posts (`_check_tier_promotion()`) | billing.py |
| `grower` | `amplifier` | 100+ successful posts AND trust_score >= 80 | billing.py |
| `amplifier` | `grower` | Trust score drops below threshold | trust.py |
| `grower` | `seedling` | Trust score drops further | trust.py |

| Tier | Max Campaigns | CPM Multiplier |
|---|---|---|
| `seedling` | 3 | 1x |
| `grower` | 10 | 1x |
| `amplifier` | Unlimited | 2x |

---

## Local SQLite Database (scripts/utils/local_db.py)

### local_campaign.status

**Default:** `"assigned"`

| Value | Meaning |
|---|---|
| `pending_invitation` | Just received from server |
| `assigned` | User accepted campaign |
| `content_generated` | AI drafts created |
| `approved` | Drafts approved |
| `posted` | Content posted |
| `active` | Campaign ongoing |
| `skipped` | User opted out |
| `cancelled` | Campaign cancelled (synced from server) |

**Key behavior:** On upsert from server polling, the local `status` field is **preserved** — prevents re-polling from resetting user's progress (e.g., accepted back to pending).

---

### local_campaign.invitation_status

**Default:** `"pending_invitation"`

| Value | Meaning |
|---|---|
| `pending_invitation` | Awaiting response |
| `accepted` | User accepted |
| `rejected` | User declined |
| `expired` | TTL passed |

Mirrors server `CampaignAssignment.status` for invitation-specific states.

---

### post_schedule.status

**Default:** `"queued"`

```
queued ──→ posting ──→ posted
                │      posted_no_url
                │
                └──→ failed ──→ queued (retry, max 3x, exponential backoff)
                         │
                         └──→ (terminal if AUTH_EXPIRED or max retries)
```

| From | To | Trigger | File |
|---|---|---|---|
| `queued` | `posting` | Background agent picks up due posts; marks `posting` immediately to prevent duplicates | background_agent.py |
| `posting` | `posted` | Post succeeded, URL captured | local_db.py |
| `posting` | `posted_no_url` | Post succeeded but URL extraction failed | local_db.py |
| `posting` | `failed` | Error during execution | local_db.py |
| `failed` | `queued` | `requeue_failed_posts()` — exponential backoff (30min x 2^retry_count), max 3 retries | local_db.py |

---

### post_schedule.error_code

Set by `classify_error()` when status becomes `failed`:

| Code | Meaning | Retried? |
|---|---|---|
| `SELECTOR_FAILED` | No CSS selector matched on platform | Yes |
| `TIMEOUT` | Page or element wait timed out | Yes |
| `AUTH_EXPIRED` | Login session expired | **No** — user must re-login |
| `RATE_LIMITED` | Platform throttling (429) | Yes (longer backoff) |
| `UNKNOWN` | Unclassified error | Yes |

---

### agent_draft.approved

**Default:** `0`

| Value | Meaning |
|---|---|
| `0` | Pending approval |
| `1` | Approved for posting |
| `-1` | Rejected by user |

Transitions: `0 → 1` (approve), `0 → -1` (reject), `-1 → 0` (restore)

### agent_draft.posted

**Default:** `0`

| Value | Meaning |
|---|---|
| `0` | Not yet posted |
| `1` | Posted to platform |

---

### local_post.status

**Default:** `"posted"`

| Value | Meaning |
|---|---|
| `posted` | Successfully published |
| `deleted` | Detected as removed from platform |

---

### local_earning.status

**Default:** `"pending"`

| Value | Meaning |
|---|---|
| `pending` | Earnings recorded, not yet confirmed |
| `paid` | Confirmed paid by server |
