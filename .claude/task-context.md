# Amplifier — Task Context

**Last Updated**: 2026-03-27 (Session 22)

## Current Status

**8 verification tasks complete** (Tasks #15-22). Working through feature verification flow.

| Tier | Focus | Tasks | Status |
|------|-------|-------|--------|
| 1 Foundation | AI Wizard, Onboarding | #15-#18 | All done |
| 2 Core Loop | Matching, Polling, Content Gen, Review | #19-#22 done, #23-#26 pending | 4/8 done |
| 3 Delivery | Posting, Metric Scraping | #27-#30 | All pending |
| 4 Money | Billing, Earnings, Stripe, Campaign Detail | #31-#38 | All pending |
| 5 Support | System Tray, Dashboard Stats | #39-#42 | All pending |
| 6 Admin | Overview, Users, Campaigns, Payouts | #43-#50 | All pending |
| Future | AI scrapers, content gen, video gen | #51-#56 | All pending |

## Session 22 — What Was Done

### Task #19/#20: Campaign Matching (Explain + Verify)
- Required platforms changed from ALL to AT LEAST 1
- AI scoring fully AI-driven (no static formula)
- Full scraped profile data in AI prompt (bio, posts, engagement, experience)
- AI told most users are normal people — don't penalize low numbers
- Niche lists unified (21 niches, both sides match)
- Platform format bug fixed (`True` vs `{connected: True}`)
- Scraped profiles sync to server during onboarding (was missing)
- Removed hardcoded top-10 cap (respects campaign max_users)
- E2E test: 3 fake users x 3 campaigns, 6/7 passed
- SLC spec updated

### Task #21/#22: Campaign Polling (Explain + Verify)
- **Critical bug fixed**: Polled campaigns stored as `assigned` (accepted) instead of `pending_invitation`. Content generated for campaigns user never accepted. Fixed default status.
- **upsert_campaign rewrite**: No longer overwrites local status on re-poll. Accepted campaigns stay accepted.
- **Accept route**: Updates local status to `assigned`, triggers content generation
- **Reject route**: Removes campaign from local DB
- **Rich invitation display**: Full brief (truncated + Read More), content guidance, product images, uploaded files, payout rates (hides $0 rates)
- **Clickable invitation titles**: Link to campaign detail page for full info before accepting
- **Auto-reload**: Campaigns page + detail page poll for state changes every 10s, reload when new content appears
- **Per-campaign desktop notifications**: "Content Ready for Review — [Title] — N drafts generated"
- **Campaign detail page**: Read More on brief + guidance, product images, uploaded files

### Other Fixes This Session
- LinkedIn reconnect: auto-reset corrupted browser profiles (TargetClosedError)
- Mistral import: `from mistralai.client import Mistral` (v2.1 API change)
- Reddit onboarding text updated
- API keys saved to memory for re-use
- tasks.json encoding fixed (mojibake, smart quotes, double CRLF)
- Task #56 added: video generation (Seedance 2) integration
- 8 comprehensive docs created in docs/
- FUTURE.md expanded with AI content gen tools + pipeline

### Bugs Found & Fixed
1. **Campaign status overwrite on re-poll** — upsert_campaign used INSERT OR REPLACE, resetting accepted campaigns
2. **Content generated for pending campaigns** — default status was "assigned" instead of "pending_invitation"
3. **LinkedIn corrupted profile** — Playwright Chromium crashes with corrupt profile dir. Auto-reset + retry.
4. **Mistral import error** — `from mistralai import Mistral` broke in v2.1, changed to `from mistralai.client import Mistral`
5. **Platform format mismatch** — matching checked `{connected: True}` but user app sends `True`. Accept both.

## Key Decisions
- Matching is fully AI-driven — no static scoring formula
- Most Amplifier users are normal people, not influencers — AI scoring accounts for this
- Campaign brief is the single content source for amplifiers
- Per-campaign desktop notifications (not batch)
- Auto-reload pages via hash polling (10s interval)
- Corrupted browser profiles auto-reset on failure

## Next Task
**#23 — Explain: AI Content Generation**

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **User App**: http://localhost:5222

## Test Commands
```bash
# Run user app
python scripts/user_app.py

# Run server locally
cd server && GEMINI_API_KEY=<key> python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# E2E matching test
python scripts/tests/test_matching_e2e.py setup
python scripts/tests/test_matching_e2e.py test
python scripts/tests/test_matching_e2e.py cleanup

# Deploy
vercel deploy --yes --prod --cwd server
```
