# Task #72 — Reversal Record

**Date:** 2026-04-30
**Branch:** flask-user-app
**Status:** REVERTED

## Rationale

Task #72 added a NICHE MISMATCH RULE to `_build_review_prompt()` that caused the AI review to veto campaign activation when it judged the brief's category didn't match the company's chosen niches. This is the wrong direction.

**Principle:** Companies decide who they target — niches, region, follower count, audience demographics, anything they fill in. The AI must not second-guess those choices. A finance company wanting to target fashion creators is a legitimate business decision. The AI review exists to catch harmful content, scams, and gibberish briefs — not to override targeting strategy.

The original Task #15 spec also had this flaw (concern #4: "Does the targeting make sense for the product?") — it has been removed from the spec as well.

## What Was Removed

### `server/app/services/quality_gate.py` — `_build_review_prompt()`

- **Removed** concern #3: `"Does the targeting make sense for the product? (finance product targeting fashion = mismatch)"`
- **Removed** the full NICHE MISMATCH RULE block (7 lines prescribing caution/reject for mismatched niches)
- **Removed** `"niche mismatch"` and `"targeting mismatch"` from the example concerns list
- **Removed** `Niche Tags / Target Audience: {niche_tags}` line from the prompt context (AI no longer needs to see niches)
- **Renumbered** concerns from 4 down to 3

AI review now checks only:
1. Brief is actual content, not empty/gibberish/placeholder text
2. Content guidance contains harmful instructions (fake reviews, competitor attacks, defamation, misleading claims)
3. Legitimacy — does this look like a scam or spam?

### `docs/specs/batch-2-ai-brain.md`

- **Removed** Task #15 spec concern #4 ("Does the targeting make sense for the product?"), renumbered from 5 to 4 concerns
- **Removed** Task #15 spec AC7 ("campaign targeting fashion but brief describes financial product is caught as targeting mismatch"), renumbered AC8→AC7 (now the last AC)
- **Removed** `targeting_mismatch` from seed-fixture key list
- **Removed** Task #15 Verification Procedure AC9 (`### AC9 — Targeting mismatch caught by AI review`) block entirely; renumbered AC10–AC15 → AC9–AC14; Aggregated PASS rule updated to "AC1–AC14"
- **Replaced** Task #72 entire spec + Verification Procedure with this REVERTED stub
- **Fixed** Task #71 AC4 forced-caution example: changed `concerns=["niche mismatch"]` to `concerns=["aggressive promotional tone borders on misleading"]`

### `.taskmaster/tasks/tasks.json`

- Task #72 `status`: `done` → `deferred`
- Task #72 `title`: prefixed with `[REVERTED]`
- Task #72 `description`: appended reversal note

## Historical Record

The original Task #72 UAT report remains in the repo at `docs/uat/reports/task-72-2026-04-29-2301.md`. Its conclusions (productivity SaaS + fashion niches = caution) are superseded by this reversal. The test fixture behavior documented there is now intentionally not enforced.

## Confirmation

After this reversal, running:
```bash
cd server && python -c "
from types import SimpleNamespace
from app.services.quality_gate import _build_review_prompt
c = SimpleNamespace(title='Test', brief='B', content_guidance='G', payout_rules={}, targeting={'niche_tags':['fashion']})
p = _build_review_prompt(c)
assert 'niche mismatch' not in p.lower()
assert 'targeting mismatch' not in p.lower()
assert 'targeting make sense' not in p.lower()
assert 'niche tags' not in p.lower()
print('prompt clean: targeting/niche review removed')
"
```
should print `prompt clean: targeting/niche review removed`.
