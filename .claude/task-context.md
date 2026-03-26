# Amplifier — Task Context

**Last Updated**: 2026-03-26 (Session 21)

## Current Status

**New task system**: 36 verification tasks (#15-#50) across 6 tiers. Old SLC tasks #1-#14 all done.

| Tier | Focus | Tasks | Status |
|------|-------|-------|--------|
| 1 Foundation | AI Wizard, Onboarding | #15-#18 | #15 #16 done, #17 #18 pending |
| 2 Core Loop | Matching, Polling, Content Gen, Review | #19-#26 | All pending |
| 3 Delivery | Posting, Metric Scraping | #27-#30 | All pending |
| 4 Money | Billing, Earnings, Stripe, Campaign Detail | #31-#38 | All pending |
| 5 Support | System Tray, Dashboard Stats | #39-#42 | All pending |
| 6 Admin | Overview, Users, Campaigns, Payouts | #43-#50 | All pending |

## Session 21 — What Was Done (Chronological)

### Phase 1: Task Setup
- Extracted Session 20 conversation transcript to `session-20-transcript.md`
- Found Claude Code conversation storage: `~/.claude/projects/<project-path>/<uuid>.jsonl`
- Created 36 new verification tasks (#15-#50): 18 features × 2 tasks each (Explain + Verify)
- Prioritized by dependency chain: Foundation → Core Loop → Delivery → Money → Support → Admin

### Phase 2: Task #15 — Explain: Company AI Wizard
Walked through entire wizard flow. User identified 5 fixes needed:

### Phase 3: Task #15/#16 — Implement AI Wizard Fixes

**1. Supabase Storage for uploads**
- Created `server/app/services/storage.py` — upload/delete/text extraction helper
- Added `supabase`, `PyPDF2`, `python-docx` to requirements.txt
- Added `supabase_url`, `supabase_service_key` to Settings
- Created `campaign-assets` bucket via Supabase REST API
- Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` on Vercel

**2. Image uploads in wizard Step 1**
- Drag-and-drop upload zone with thumbnail previews
- `POST /company/campaigns/upload-asset` route (4MB limit — Vercel body limit)
- Images stored in Supabase Storage, URLs in `Campaign.assets["image_urls"]`

**3. File uploads in wizard Step 1**
- PDF/DOCX/TXT upload with text extraction (PyPDF2, python-docx)
- Extracted text passed to AI prompt for richer brief generation
- Files stored in Supabase Storage, content in `Campaign.assets["file_contents"]`

**4. Deep BFS web crawling**
- Replaced shallow single-page scrape with BFS crawler
- Follows same-domain links up to 10 pages, depth 2
- Uses httpx+BeautifulSoup (works on Vercel, no browser needed)
- Scraped content (up to 20K chars) fed to Gemini prompt

**5. Fixed AI generation**
- Root cause: `product_name`, `product_features` weren't passed to `run_campaign_wizard()`
- Targeting fields were read from wrong nesting level
- Enhanced Gemini prompt: comprehensive 500-1000 word briefs using all sources
- Fallback now clearly marks `[AI generation failed — please edit]`
- Error response shows actual error instead of silently returning defaults

**6. Balance gate**
- Companies with <$50 balance blocked from wizard
- Redirects to campaigns page with prominent error banner + "Go to Billing" link

**7. UI fixes during testing**
- Chip input bug: `handleChipInput`, `addChip`, `removeChip`, `syncChipValues` not exposed to `window`
- Must-avoid changed from chip tags to plain textarea
- Must-include help text: "weave naturally" not "appear in every post"
- Max creators field made required with validation
- Per-click payout removed from UI (can't track clicks — documented in FUTURE.md)
- Stale SQLite DB error (missing `max_users` column) — deleted and recreated

### Key Decisions Made This Session
- **Campaign brief = single content source**: The detailed brief IS what amplifiers use. Must contain everything.
- **httpx+BS4 BFS over Crawl4AI**: Crawl4AI requires Playwright/Chromium, won't work on Vercel serverless. Enhanced existing stack instead.
- **4MB upload limit**: Vercel serverless has 4.5MB body limit. Sized accordingly.
- **Per-click payout deferred**: Can't track clicks without UTM tracking. Backend preserved, UI removed.
- **Must-include items are suggestions**: Woven naturally, not forced into every post.
- **Must-avoid is free text**: Plain textarea better than chip tags for describing what to avoid.
- **Supabase CLI for all ops**: User requested — always use `npx supabase`, never dashboard.

## Bugs Found & Fixed (Session 21)
1. **Stale SQLite DB**: Missing `max_users` column → deleted `amplifier.db`, auto-recreated
2. **Pydantic extra field**: `GEMINI_API_KEY` in `.env` rejected by Settings → set as env var instead
3. **Chip input not working**: Functions defined in closure, not on `window` → exposed all 4 functions
4. **Port already in use**: Server process not killed properly → `taskkill //F //PID`
5. **Balance gate invisible**: Rendered campaigns.html silently → redirect with prominent error banner

## Key Reference Files

### New This Session
- `server/app/services/storage.py` — Supabase Storage upload/delete/text extraction
- `server/vercel.json` — maxLambdaSize for deep crawl timeout
- `FUTURE.md` — Deferred features (per-click payout)

### Modified This Session
- `server/app/services/campaign_wizard.py` — Deep BFS crawling, enhanced AI prompt, all sources
- `server/app/routers/company_pages.py` — Upload route, balance gate, AI generate fix
- `server/app/templates/company/campaign_wizard.html` — Image/file uploads, chip fix, textarea, validation
- `server/app/templates/company/campaigns.html` — Error banner for balance gate
- `server/app/core/config.py` — Supabase Storage settings
- `server/requirements.txt` — supabase, PyPDF2, python-docx
- `server/.env.example` — Supabase Storage env var docs
- `.taskmaster/tasks/tasks.json` — 36 new verification tasks, updated #15 #16 #23 #37

## Task Notes for Future Sessions
- **Task #23 (AI Content Generation)**: Must-include items woven naturally, not forced. Must-avoid always excluded.
- **Task #37 (Campaign Detail Page)**: Needs image/file upload in Edit Campaign modal. Remove per-click from edit modal.
- **Task #35/#36 (Stripe Top-up)**: Deferred — company billing page shows "Stripe not configured"

## Deployed URLs
- **Company**: https://server-five-omega-23.vercel.app/company/login
- **Admin**: https://server-five-omega-23.vercel.app/admin/login (password: admin)
- **Swagger**: https://server-five-omega-23.vercel.app/docs
- **User App**: `python scripts/user_app.py` → http://localhost:5222

## Test Commands
```bash
# Server unit tests (19)
cd server && python -m pytest tests/ -v

# Run server locally (with Gemini key)
cd server && GEMINI_API_KEY=<key> python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Deploy to Vercel
vercel deploy --yes --prod --cwd server

# Supabase CLI
npx supabase projects list
npx supabase projects api-keys --project-ref ozkntsmomkrsnjziamkr
```

## Commits This Session
```
0ad625d feat: AI wizard — image/file uploads, deep crawling, fix AI generation
```
