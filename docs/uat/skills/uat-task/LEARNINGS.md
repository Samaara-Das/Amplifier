# UAT Skill Learnings — appended over time, oldest first

This file is read FIRST by the `uat-task` skill on every invocation. Corrections from the user during UAT runs land here permanently. Future runs apply these corrections automatically — they override default skill behavior.

Format per entry:

```
## YYYY-MM-DD — short title

**Mistake**: what the skill did wrong
**Correction**: what the skill should do instead
**Trigger**: when this learning applies (e.g., "any AC that involves background agent")
```

---

## 2026-04-26 — Ask the user before running expensive verification of "is this data real?"

**Mistake**: Wrote a Playwright introspection script to confirm whether a missing field on a third-party profile (Reddit follower count) was a scraper bug vs platform reality. The user could have confirmed in 5 seconds: "no, that platform doesn't show that on my profile."

**Correction**: When a scraped value looks suspicious but the cheapest test is one question to the user, ask first. Reserve introspection scripts for cases where the user can't easily check (selector drift, async timing, etc.).

**Trigger**: Any time scraped output looks "wrong" but the user is the source of truth for what's actually on their account.

## 2026-04-26 — Auto-detect browser closure via log markers; never ask the user to type "closed"

**Mistake**: Asked the user to type "closed" after closing a Playwright login window. Slow + error-prone.

**Correction**: Tail agent.log for the post-close markers the connect flow already emits (`Auto-scraped <platform>` / `Auto-scrape failed` / `<Platform> Connected`). They fire only AFTER the browser closes AND the scraper finishes — perfect trigger.

**Trigger**: Any UAT step that opens a Playwright browser for manual user interaction.

## 2026-04-26 — Don't artificially narrow an AC to a "safe" subset of what the product does

**Mistake**: Wrote AC17 as "approve a LinkedIn draft, watch it post" — limited to one platform out of three "to avoid spam." But the product posts to all 3 platforms, so testing one only proves the LinkedIn path. Facebook and Reddit posting could be silently broken and the AC would still pass.

**Correction**: An AC must cover every variant the product actually exercises. If the product posts to N platforms, the AC posts to N platforms. If the product handles M user tiers, the AC tests M tiers. If the product runs over K days, the AC verifies K days. The cost (real posts on real accounts) is the same cost the user pays at runtime — that's the right level of testing. Cleanup handles the noise; never narrow the AC to dodge cleanup work.

**Trigger**: When sizing any AC, list every dimension the product varies over (platforms, modes, tiers, regions, days, formats). If the AC doesn't cover all of them, justify why in the AC's text or expand it. Default expand.

## 2026-04-26 — Spec ACs are the floor, not the ceiling. Derive the rest yourself.

**Mistake**: Treated the spec's "Acceptance Criteria" list as the complete AC set. Missed obvious product-level checks: per-platform coverage, recurring-loop stability, end-to-end posting. User had to point them out.

**Correction**: For every AC block, walk the feature's full lifecycle (trigger → ... → final user-visible side-effect). For each stage ask: works once? works on a schedule? composes with the next stage? Cover every platform variant, every mode, every async behavior. The product's external side-effects (real posts, real charges) get real-world ACs — never mocks.

**Trigger**: Before writing or reviewing any `## Verification Procedure` block. Apply BEFORE the first `/uat-task` run.

## 2026-04-26 — UAT test campaigns must pass the Task #15 quality gate

**Mistake**: `seed_campaign.py`'s defaults (CPM $0.50, no niche_tags, no required_platforms) score 64/100 against the live quality gate, blocking activation. UAT seed data was written before the gate was active and never updated.

**Correction**: Default seed_campaign.py to values that score >=85: `rate_per_1k_views_cents=200` ($2/1K), `niche_tags=["trading","finance"]`, `required_platforms=["linkedin","facebook","reddit"]`, `target_regions=[]` (no region restriction so test users in any region match). When seeding, also confirm campaign reaches `status='active'` before exiting — never leave draft campaigns behind during UAT.

**Trigger**: Every UAT that involves creating a test campaign on the live server (currently Task #14, will apply to #15, #17, etc.).

## 2026-04-26 — Resize browser to full screen for Chrome DevTools MCP UI verification

**Mistake**: Default Chrome DevTools MCP page size is too small — UI elements may not render the same as a real user sees them, snapshots miss content below the fold, and screenshots are too cramped to be readable as evidence.

**Correction**: Immediately after `new_page(...)`, call `mcp__chrome-devtools__resize_page` with at least `width=1920, height=1080` (full HD). Do this BEFORE any `take_snapshot` or `take_screenshot` so all subsequent captures reflect the full-screen layout.

**Trigger**: Every AC that uses Chrome DevTools MCP for UI verification (in any task, not just Task #14). The first action after opening a new page is always `resize_page` to 1920x1080.

## 2026-04-29 — Run UI ACs via Chrome DevTools MCP unconditionally; never skip them as "deferred"

**Mistake**: During /uat-task 15, started with pytest-only ACs (1, 2, 3, 4, 5, 6, 7, 9, 11) and treated AC12 + AC14 (Chrome DevTools MCP UI ACs) as a follow-on phase to skip when time was tight. The user had to remind me explicitly that the skill mandates browser testing for UI ACs.

**Correction**: The skill's rule #0 ("Screenshots are proof. Take them everywhere.") and the AC's own `Automated: yes (DevTools-driven)` field together mean UI ACs are NOT optional. Run them in the same loop as the pytest ACs — open the company/admin/user app, drive it like a real user, capture screenshots, embed in the report. Even if pytest ACs fail, UI ACs may pass and provide independent evidence the feature works.

**Trigger**: Any AC whose Action field describes a Chrome DevTools MCP sequence (new_page → snapshot → click → wait_for → screenshot) OR whose Automation says `chrome-devtools-mcp`. Run them every time. Order: typically last (so prior ACs set up state to verify visually), but never skip.

## 2026-04-29 — Retry transient Gemini API errors before declaring AI-review FAIL

**Mistake**: AC7 + AC9 of Task #15 failed because Gemini returned 503 UNAVAILABLE due to high demand during the UAT window. The implementation fell back to mechanical-only (per spec) — but the spec ACs assume the AI review actually ran. Skill marked them FAIL on first attempt.

**Correction**: When an AC depends on a real Gemini call AND the server log shows `503 UNAVAILABLE` / `429 RESOURCE_EXHAUSTED`, retry the AC up to 3x with 30-60s gaps before marking FAIL. If still failing after 3x, mark INCONCLUSIVE (not FAIL — external infrastructure). Also: implementations should retry with exponential backoff inside the function before falling back to fallback path. Without function-level retry, transient blips become permanent fallbacks.

**Trigger**: Any AC whose Expected field requires AI-review behavior (brand_safety reject/caution, niche-mismatch detection, AI-driven decisions). Check server logs for 503/429 first; retry the AC; only mark FAIL if reproducible.

## 2026-04-29 — Drive the UI like a user. API shortcuts hide bugs you exist to catch.

**Mistake (repeated 2-3 times now)**: When verifying a feature, used pytest + curl + httpx to hit the API directly because it's faster and "tests the same code." Skipped driving the create form, the wizard, the dashboard click flow. Result: bugs in the form layer (JS validation, field mapping, schema assembly, submit handler) would slip through every AC and only surface when a real user hits the feature.

**Correction**: For ANY feature with a UI surface, the UAT MUST drive that UI via Chrome DevTools MCP — log in, navigate to the create/edit/action page, fill the form by clicking and typing into each field, click Submit, wait for the result, verify the rendered output. **Direct API calls (curl, httpx, pytest with `requests`) are scaffolding and a sanity check — they never replace driving the real user flow.**

The user's literal words: *"you are supposed to test visually — like a user/company using the amplifier app. that's how i would test manually and find bugs to give to you. you are supposed to do my job of manual testing properly and better than i would do."*

The whole point of the UAT skill is to be the human tester — to click through the app, find what breaks, and report it. Bypassing the UI defeats the skill's reason to exist.

**Trigger**: Any task whose feature has a UI flow (any company/admin/user dashboard form, any wizard, any action button that triggers backend work). For every such feature, at least one AC must:
1. Open the actual app page (Chrome DevTools MCP)
2. Drive the form/click flow as a real user (no pre-seeded data via API; create state through the UI)
3. Verify the user-visible result (rendered widget text, status badges, success banners, redirects)
4. Capture screenshots at every state transition (before, after, error)
5. Read console + network panels — flag errors and 5xx loudly

When a task's spec ACs don't include such a flow, ADD ONE before running the UAT. Apply the LEARNING from 2026-04-26 ("ACs are the floor, not the ceiling") together with this rule: derive the missing UI flow AC, surface it to the user before running, then run it.

**The check before declaring an AC PASS**: ask yourself "if there were a JS bug in the form that prevented the field from being submitted, would my AC have caught it?" If the answer is "no — I bypassed the form," your AC is incomplete. Add a UI-driven AC and run it.

## 2026-05-02 — Onboarding UAT must drive EVERY user-visible click, not just the form submissions

**Mistake**: During /uat-task 75 (web onboarding), I:
1. Filled the register form, submitted, watched it redirect to step2 → marked AC3 PASS
2. Navigated DIRECTLY to step3 and step4 via URL bar instead of clicking the "Continue to API Keys →" button on step2 and "Skip for now →" button on step3
3. Tried to defer AC6 (real platform connect) as "PARTIAL/DEFERRED" because it requires daemon + user 2FA
4. Never actually clicked the "Open Desktop App" buttons that the onboarding steps surface

This entirely missed the point. The user pushed back: "won't you be testing if the desktop app opens in the onboarding process via the 'open desktop app' button? won't you be testing if the connecting to platforms part works? won't you be asking me to connect to the different platforms and login to them? this is the whole point of testing the user, admin and company apps."

**Correction**: Every clickable element in an onboarding/setup flow MUST be exercised as a real user would:
- "Continue to..." / "Skip for now" / "Next" / "Continue" buttons → click them, don't URL-jump
- "Open Desktop App" / "Open in Browser" / external-link buttons → click them, verify the target opens (new tab arrival, localhost:5222 page load, OS app launch). Take screenshots of BOTH source and target.
- Platform connect buttons → drive them all the way through real platform login (LinkedIn, Facebook, Reddit). Pause and ask the user to complete 2FA if required. Take a screenshot of the platform's logged-in state to confirm the session was saved.
- After each platform connects → return to the onboarding step that shows that platform's badge → confirm the badge flipped from "Not connected" to "Connected" via SSE → screenshot.
- Cross-tab handoffs (web tab triggers daemon action which triggers SSE update which updates web tab) → both tabs stay open during the verification.

**The check before declaring an onboarding-flow AC PASS**: ask yourself "did I click every button a real first-time user would click, AND did I complete every external-app handoff, AND did I confirm each step's state propagates to subsequent steps?" If any of those is "no," the AC is incomplete.

**Daemon-required ACs are NOT optional for deferral.** When an AC requires the background daemon running (for SSE push, command processing, status updates), the skill MUST start the daemon as part of the AC's setup phase, not punt the AC to "PARTIAL". Cleanup phase kills the daemon afterwards. The "first run" with the user present is exactly when these end-to-end flows must be verified.

**Trigger**: Any /uat-task run for an onboarding flow, setup wizard, or any task whose ACs span web → desktop app → web → SSE → web. Default to driving every interactive element + completing every external handoff + verifying state propagation across surfaces. Defer NOTHING that the spec covers.
