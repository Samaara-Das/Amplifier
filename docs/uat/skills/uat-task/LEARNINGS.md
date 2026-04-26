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
