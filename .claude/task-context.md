# Amplifier — Task Context

**Last Updated**: 2026-03-24 (Session 17, continued)

## Current Task
- **Branch: `main`** — LangGraph agent pipeline built, tested, and E2E verified
- Phase 1 of multi-agent content pipeline complete
- 56 pytest tests passing
- Next: plan MVP features from a business perspective

## Project Overview
Two interconnected systems:
1. **Amplifier Engine** — Personal social media automation (6 platforms, Playwright, Claude CLI)
2. **Amplifier Server** — Two-sided marketplace: companies create campaigns, users earn by posting via Amplifier

## Task Progress Summary

### MVP Phases (All Complete)
- [x] Phase 1-8: All complete (critical fixes, PostgreSQL, content gen, matching, metrics, dashboards, installer, integration testing)

### Session 17 — Early (Metric Pipeline + Webcrawler)
- [x] **Task 31: Content prompt rewrite** — Emotion-first hooks, value-first body, platform rules
- [x] **Task 33: Webcrawler setup** — Installed globally at `C:\Users\dassa\Work\webcrawler\`
- [x] **Task 34: Metric pipeline — 4 bugs fixed** — URL capture, cumulative scraping, inline billing. $75.98 earned E2E.
- [x] **Task 35: Model exploration note** — Deferred: Qwen, Llama, Nvidia, local LLMs

### Session 17 — Late (Agent Pipeline Phase 1)
- [x] **Task 36 (Phase 1): LangGraph agent pipeline** — Built and E2E tested
  - Installed langgraph + langchain-google-genai
  - Created `scripts/agents/` package (7 files): pipeline.py, state.py, profile_node.py, research_node.py, draft_node.py, quality_node.py
  - Extended local_db.py with 4 agent tables + CRUD functions
  - Wired into campaign_runner.py with feature flag (`enable_agent_pipeline`)
  - Legacy ContentGenerator preserved as fallback
  - E2E: poll → agent pipeline → 4 platform drafts (avg quality 88/100) → image gen → posted to Facebook + LinkedIn
  - 56 pytest tests written and passing
- [x] **DeerFlow evaluated and rejected** — Windows issues, ~30 deps, HTTP stack assumptions. LangGraph standalone chosen instead.
- [x] **Task 32 cancelled** — DeerFlow integration

### Agent Pipeline Phase 1 — E2E Results
- **Campaign**: "Smart Money Indicator Beta" (created on live Vercel server)
- **Research**: 5 web search results via webcrawler (DuckDuckGo)
- **Drafts**: X (342 chars, flagged over limit), LinkedIn (897), Facebook (402), Reddit (1032)
- **Quality**: avg 88/100. X too long. Reddit false positive on "ist" in "institutional" — fixed.
- **Image**: Cloudflare FLUX generated
- **Posting**: Facebook posted (real URL captured), LinkedIn posted (fallback URL), Reddit failed (selector), X failed (account locked)
- **Server sync**: 2 posts reported, assignment status "posted"

### Pending (Task-Master Tasks 37-40)
- [ ] **Task 37 (Phase 2)**: Content variety (educational/funny/ragebait/story) + audience-aware scheduling + CTA rotation + post-post engagement (browse only)
- [ ] **Task 38 (Phase 3)**: Learning loop — metrics feed back into content decisions
- [ ] **Task 39 (Phase 4)**: Dashboard views — research, drafts, schedule
- [ ] **Task 40 (Phase 5)**: Personal brand pipeline (separate graph, shared nodes)

### Critical Issues
- [ ] **X account locked** — Playwright automation detected. Must fix before user onboarding: stealth browser, official API, or alternative method.
- [ ] **Reddit posting broken** — `textarea[name="title"]` selector timeout. Reddit UI likely changed.

### Post-MVP Tasks
- [ ] User app distribution — web dashboard + Tauri desktop agent
- [ ] Browser Use migration for posting
- [ ] LinkedIn/Facebook official API migration
- [ ] 18-21: Account Warmup, Profile Revamps, LinkedIn "I'm Back"
- [ ] 22-30: AI Video, Newsletters, Facebook Groups, TradingView, Analytics

## Session History

### Sessions 1-16 (2026-03-07 to 2026-03-22)
- Built entire system: 6-platform posting, server (52 routes, 8 models), dashboards, Vercel deploy
- 9 bugs fixed in E2E testing, Supabase PostgreSQL, UI polish, image gen chain

### Session 17 (2026-03-24) — Metric Pipeline, Agent Pipeline, Tests

**Part 1: Metric pipeline fix + webcrawler**
- Rewrote content generation prompt (emotion-first, value-first, brand voice)
- Installed webcrawler globally, added to CLAUDE.md
- Fixed 4 metric pipeline bugs (URL capture, cumulative scraping, inline billing, content prompt)
- E2E verified: $75.98 earned on dashboard

**Part 2: Framework decision**
- Researched DeerFlow, LangGraph, CrewAI, Custom pipeline
- DeerFlow: Windows issues (#1278, #1210), ~30 deps, HTTP stack assumptions. `DeerFlowClient` exists but not plug-and-play on Windows.
- **Decision: LangGraph standalone** — same engine as DeerFlow, pure Python, Windows-native, 2 packages, production-ready (1.0 stable)
- DeerFlow could be useful later for: company-side campaign brief assistant, general research tool
- Plan documented in `docs/AGENT_PIPELINE_PLAN.md` (5 phases)

**Part 3: Agent pipeline Phase 1 build**
- Created `scripts/agents/` package with 7 files
- State schema: PipelineState TypedDict (campaign, profiles, research, drafts, quality, output)
- Nodes: profile (weekly cache) → research (webcrawler + past perf) → draft (Gemini per-platform) → quality (hard rules, 0-100 score) → output
- Feature flag: `enable_agent_pipeline` in settings table
- Agent pipeline falls back to legacy ContentGenerator on failure
- E2E tested with live Vercel server campaign

**Part 4: Testing**
- 56 pytest tests written across 4 files
- Coverage: DB CRUD (18), quality validation (20), profile node (5), pipeline integration (3+1 skipped)
- All passing

**Part 5: Key decisions**
- User wants Claude as business partner, not just coder
- Campaign + personal brand pipelines will be separate graphs sharing nodes
- Desktop-first architecture, but nodes are stateless/split-ready for server later
- User profiles extracted weekly for content personalization
- X account locked — posting method must be made robust (API or stealth)

## Important Decisions Made
- **LangGraph standalone over DeerFlow** — Same engine, no baggage. Revisit DeerFlow when it ships pip-installable Windows package.
- **Desktop-first, split-ready** — Nodes are independent stateless functions. Can move research/draft/quality to server later.
- **Campaign + personal = separate pipelines, shared nodes** — Built campaign first (Phases 1-4), personal brand later (Phase 5).
- **Feature flag for agent pipeline** — `enable_agent_pipeline` in settings. Legacy ContentGenerator is fallback.
- **Post-post engagement = browse only** — No liking/retweeting on behalf of user.
- **Content personalization** — User profiles scraped weekly, fed into draft prompts.
- **Business partner role** — Claude helps run the business, not just build features.
- **X account security** — Must fix before onboarding: API, stealth browser, or alternative method.

## Key Reference Files

### Agent Pipeline (NEW)
- `scripts/agents/pipeline.py` — LangGraph graph (profile → research → draft → quality → output)
- `scripts/agents/state.py` — PipelineState TypedDict
- `scripts/agents/profile_node.py` — User profile extraction (weekly Playwright cache)
- `scripts/agents/research_node.py` — Webcrawler search + company links + past performance
- `scripts/agents/draft_node.py` — Per-platform Gemini drafting with brand voice + user profile
- `scripts/agents/quality_node.py` — Hard rules validation, 0-100 scoring
- `docs/AGENT_PIPELINE_PLAN.md` — Full 5-phase plan with architecture, DB schema, decisions

### Server
- `server/app/main.py` — Entry point (52 routes)
- `server/app/routers/metrics.py` — Metrics submission + inline billing trigger
- `server/app/services/billing.py` — Earnings calculation

### User App
- `scripts/campaign_runner.py` — Campaign loop with agent pipeline routing (feature flag)
- `scripts/campaign_dashboard.py` — User dashboard (port 5222)
- `scripts/post.py` — Posting functions (return URL strings)
- `scripts/utils/content_generator.py` — Legacy content gen (fallback)
- `scripts/utils/local_db.py` — SQLite with 4 agent tables + CRUD
- `scripts/utils/metric_scraper.py` — Cumulative tier-based scraping

### Tests
- `tests/test_local_db_agent.py` — 18 tests: agent table CRUD + feature flag
- `tests/test_quality_node.py` — 20 tests: banned phrases, length, hooks, scoring
- `tests/test_profile_node.py` — 5 tests: cache, filtering, staleness
- `tests/test_pipeline_integration.py` — 3+1 tests: graph structure, mock pipeline, real API

### Config & Docs
- `config/content-templates.md` — Brand voice rules (quality node reads this)
- `config/platforms.json` — Platform config
- `C:\Users\dassa\Work\webcrawler\crawl.py` — Global webcrawler

## Test Data on Deployed Server
- **Test user**: `testuser_e2e@gmail.com` / `TestPass123!` — $75.98 earned
- **Test company**: `testcorp@gmail.com` / `TestPass123!` — 2 campaigns
- **Campaigns**: "Trading Tools Launch" (4 posts, billed), "Smart Money Indicator Beta" (2 posts, agent pipeline)

## Test Commands
```bash
# Run tests
python -m pytest tests/ -v

# Agent pipeline standalone test
cd scripts && python -m agents.pipeline

# Campaign runner with agent pipeline
python scripts/campaign_runner.py --once

# Dashboard
python scripts/campaign_dashboard.py  # http://localhost:5222

# Webcrawler
python C:/Users/dassa/Work/webcrawler/crawl.py search "trading strategies"

# Vercel Deploy
vercel deploy --yes --prod --cwd "C:/Users/dassa/Work/Auto-Posting-System/server"
```

## Gotchas & Patterns Discovered
- LangGraph `ChatGoogleGenerativeAI` must be imported inside function for mock patching — use `patch("langchain_google_genai.ChatGoogleGenerativeAI")`
- Quality node: "ist" banned phrase must match standalone word (` ist `) not inside "institutional"
- X account gets locked from Playwright automation — need stealth or API approach
- Reddit `textarea[name="title"]` selector may be outdated — Reddit UI changes frequently
- Facebook URL capture works (extracts real permalink from feed after posting)
- LinkedIn URL capture returns fallback — feed link extraction needs improvement
- Vercel cold starts: warm up with `/health` GET before API calls
- `conftest.py` uses `monkeypatch.setattr("utils.local_db.DB_PATH", tmp_path / "test.db")` for test isolation
