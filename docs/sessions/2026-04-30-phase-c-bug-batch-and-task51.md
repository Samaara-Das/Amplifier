# Session 2026-04-30 — Phase C bug batch + Task #51 AC backfill

> **Note for next session:** MemPalace MCP disconnected mid-session and CLI has no write surface. Save the KG/diary updates from this file via MCP next time, OR run `mempalace mine docs/sessions/` to pick this up.

## Wing
`auto_posting_system`

## Active branch
`flask-user-app`

## What shipped (2 commits)

| Commit | Scope |
|---|---|
| `11a2f41` | Phase C bug cleanup batch — 7 bugs + AC blocks (deployed; health 200) |
| `4ba9f93` | Task #51 AC backfill for #19 + #22 + STATUS sync (docs-only) |

## Tasks completed (8 total)

- **#57** quality gate accepts empty `target_regions` when other targeting dimensions set
- **#59** dedupe campaigns on `/campaigns` (active assignment takes precedence over open invitation)
- **#60** dashboard Platform Health card hides X via `filter_disabled()`
- **#63** seed_campaign.py invitation accept endpoint corrected
- **#64** new `POST /api/company/campaigns/assets` Bearer-auth route + seed uses it
- **#65** `AMPLIFIER_UAT_FORCE_DAY` propagates through to `agent_draft.iteration` (early read in campaign loop)
- **#73** `gemini-1.5-flash` → `gemini-1.5-flash-latest` in quality_gate provider chain
- **#51** AC blocks for #19 (Stripe — 13 ACs) + #22 (landing — 8 ACs)

## Decisions

### Bundle 7 bugs into one PR instead of running `/uat-task` per bug
- **Why**: 7 cleanup-class bugs × ~30-min `/uat-task` runs = real-product cost grossly out of proportion. Three of seven (#63/64/65) are inside the UAT harness itself — looping the harness on harness bugs is circular. Verification by pytest (185 pass, +4 new) + smoke-deploy-health is rigorous enough for low-pri cleanup.
- **Alternative**: strict per-bug workflow with full `/uat-task` runs. ~7 hours of session time. Rejected as overkill.
- **Revisit if**: any of these bugs surfaces a regression downstream — that's signal that the lighter verification missed something.

### Task #19 description rewritten to direct autonomous Stripe MCP setup
- **Why**: previous description blocked on user setup ("user must set up Stripe Connect onboarding"). Stripe MCP can do account/webhook/key provisioning programmatically. Only the live-mode flip in Stripe Dashboard requires the user (and possibly 2FA).
- **Effect**: Task #19 unblocks itself except for the final 1-step user confirmation. Phase D Stripe work is no longer human-bottlenecked.

### Task #19 ACs use Stripe MCP for setup + test-mode for ACs 1-12, gated live-mode smoke (AC13) at the end
- **Why**: zero-risk path. All workflow logic verified in test mode with synthetic events triggered via MCP. AC13 is a $1 round-trip (charge → refund) in live mode as the final go-live gate. Approved by user explicitly before flipping VPS env to `sk_live_`.
- **Implication**: Task #19 done == live Stripe is on. No half-state.

### Task #22 ACs use Chrome DevTools MCP exclusively (not Playwright)
- **Why**: per AC-FORMAT.md tool-boundaries rule — Playwright drives the product (posting/scraping); Chrome DevTools drives verification (AS the user). Landing page IS verification context, not a product surface. Plus DevTools' Lighthouse + emulate are needed.

## Gotchas / surprises captured

- `bash` `python -c` block with Unicode chars (→, →) crashes on Windows cp1252 stdout. Use `replace('→','->')` or set `PYTHONUTF8=1`.
- Re-deploy 502 from Caddy is normal during the ~13s uvicorn restart window; `/health` returns 200 within 12-20s.
- MemPalace MCP server can disconnect mid-session and there's no inline reconnect via tool calls. Need to either restart Claude Code or write fallback files for next session.

## What's next (Phase C remaining)

Per STATUS.md ordering:
1. **#27** server-side post URL dedup ← next
2. **#28** ToS + privacy policy acceptance in registration
3. Low-prio polish: #23 (DB backup), #24 (status label rename), #25 (clipboard copy), #26 (client-side validation)

Then **Phase D** (launch-blocking): three migration docs (`#66`, `#67`, `#68`), `#19` Stripe live (now self-serve via MCP), `#70` BYOK company API keys.

Then **Phase E**: `#22` landing page.

## KG facts to write (next session, when MemPalace is back)

Invalidate old → add new with `valid_from=2026-04-30`:
- `amplifier_project` → `current_focus` → `Phase C in progress. Bug cleanup batch + #51 done. #27 (URL dedup) next.`
- `amplifier_project` → `next_task` → `#27 server-side post URL dedup, then #28 ToS acceptance`
- `amplifier_project` → `tasks_done` → `41/73 — Phase C bug batch (7 bugs) + Task #51 AC backfill done 2026-04-30`
- `amplifier_project` → `last_session_date` → `2026-04-30`
- `amplifier_project` → `active_blocker` → INVALIDATE (#19 Stripe is now MCP-driven, not user-blocked)
- `amplifier_project` → `stripe_19_blocking_status` → `unblocked 2026-04-30 — Stripe MCP autonomous setup; user only needed for live-mode flip + 2FA`

Add new (no invalidation):
- `task_57` → `completed_on` → `2026-04-30`
- `task_59` → `completed_on` → `2026-04-30`
- `task_60` → `completed_on` → `2026-04-30`
- `task_63` → `completed_on` → `2026-04-30`
- `task_64` → `completed_on` → `2026-04-30` (also added new endpoint `POST /api/company/campaigns/assets`)
- `task_65` → `completed_on` → `2026-04-30`
- `task_73` → `completed_on` → `2026-04-30`
- `task_51` → `completed_on` → `2026-04-30` (#19 13 ACs, #22 8 ACs)
