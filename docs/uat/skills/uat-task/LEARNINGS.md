# UAT Skill Learnings — appended over time, oldest first

This file is read FIRST by the `uat-task` skill on every invocation. Corrections from the user during UAT runs land here permanently. Future runs apply these corrections automatically — they override default skill behavior.

**Format rule**: each entry is 1-4 crystal-clear sentences. Long enough to be unambiguous, short enough to be re-read at every invocation.

---

## 2026-04-26 — Ask the user before running expensive introspection of "is this data real?"

**Rule**: If a scraped value looks suspicious but the user can confirm in 5 seconds ("does that field show on your profile?"), ask first. Reserve introspection scripts (Playwright probes, custom selectors) for cases where the user can't easily check (selector drift, async timing).
**Trigger**: any time scraped output looks "wrong" and the user is the source of truth for what's actually on their account.

## 2026-04-26 — Auto-detect Playwright browser closure via log markers; never ask the user to type "closed"

**Rule**: After a manual Playwright login, tail the daemon/app log for post-close markers (`Auto-scraped <platform>` / `Auto-scrape failed` / `<Platform> Connected`) — they fire only after the browser closes AND the scraper finishes. Never ask the user to confirm closure with a typed message.
**Trigger**: any UAT step that opens a Playwright browser for manual user interaction.

## 2026-04-26 — Spec ACs are the floor, not the ceiling — derive the rest yourself

**Rule**: Walk the feature's full lifecycle and cover every variant the product actually exercises (platforms, tiers, modes, days, formats, recurring loops, async side-effects). Never narrow an AC to a "safe" subset to dodge cleanup work — real posts/charges get real ACs, never mocks. If the spec's listed ACs miss obvious dimensions, ADD them before running the UAT.
**Trigger**: before writing or reviewing any `## Verification Procedure` block, AND before declaring any individual AC PASS.

## 2026-04-26 — Seed campaigns must score ≥85 on the live quality gate

**Rule**: `scripts/uat/seed_campaign.py` defaults must produce a campaign that activates: `rate_per_1k_views_cents=200`, `niche_tags=["trading","finance"]`, `required_platforms=["linkedin","facebook","reddit"]`, `target_regions=[]`. Confirm the seeded campaign reaches `status='active'` before the seeder exits — never leave drafts behind during UAT.
**Trigger**: every UAT that creates a test campaign on the live server.

## 2026-04-26 — Resize browser to 1920×1080 before any DOM capture

**Rule**: Default Chrome DevTools MCP page size is too small. Immediately after `new_page(...)`, call `mcp__chrome-devtools__resize_page(width=1920, height=1080)` BEFORE any `take_snapshot` or `take_screenshot`.
**Trigger**: every AC that uses Chrome DevTools MCP.

## 2026-04-29 — Run UI ACs unconditionally; never defer them

**Rule**: ACs whose Action describes a DevTools MCP sequence OR whose Automation says `chrome-devtools-mcp` are NOT optional. Run them in the same loop as the pytest ACs, even if pytest fails — UI ACs are independent evidence. Screenshots are proof.
**Trigger**: any AC with a DevTools-driven Action field.

## 2026-04-29 — Retry transient AI infrastructure errors before declaring FAIL

**Rule**: On 503 / 429 from Gemini/Mistral/Groq, retry the AC up to 3× with 30s/60s/90s gaps before marking. If still failing after 3, mark INCONCLUSIVE (not FAIL — external infra flake). FAIL is only for reproducible failures.
**Trigger**: any AC whose Expected requires real AI-review behavior.

## 2026-04-29 — Drive the UI like a user; API shortcuts hide the bugs you exist to catch

**Rule**: For any feature with a UI surface, at least one AC MUST drive the actual app via DevTools MCP — log in, fill the form by typing+clicking each field, click Submit, verify rendered output. Direct API calls (curl, httpx) are scaffolding, never a replacement. Before declaring PASS, ask: "if a JS bug prevented the form from submitting, would my AC catch it?" — if no, the AC is incomplete.
**Trigger**: any task with a company/admin/user dashboard form, wizard, or action button that triggers backend work.

## 2026-05-02 — Click every button in onboarding flows; never URL-jump between steps

**Rule**: Every clickable element a first-time user sees (Continue / Skip / Open Desktop App / Connect Platform) MUST be clicked button-driven, not bypassed via URL bar. Drive every cross-tab handoff (web → localhost:5222 → web) and confirm state propagates across surfaces. Daemon-required ACs are NOT deferrable — start the daemon as part of setup phase.
**Trigger**: any /uat-task for an onboarding/wizard/setup flow.

## 2026-05-02 — Walk the cascading-impact chain when verifying a fix, not just the proximate symptom

**Rule**: If a task was filed because "without this fix, X happens to users", the UAT MUST verify X end-to-end — not just "the mechanical fix works". Re-read the task's "CASCADING IMPACT" / "Why" section before declaring PASS, and write down each downstream link that must be checked. For daemon tasks, observe all three: log line + local SQLite row + server-side row written via daemon's API call. The check: "if I were a fresh user installing today, would the user-visible outcome this fix was supposed to enable actually happen?" — if you can't trace it, the AC is incomplete.
**Trigger**: any /uat-task whose spec mentions "cascading impact", "this unblocks X", or "launch blocker for Y".
