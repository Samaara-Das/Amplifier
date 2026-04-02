# Multi-Agent Content Pipeline for Amplifier User App

**Created**: 2026-03-24 (Session 17)
**Status**: Planning — awaiting approval before implementation

---

## Context

The Amplifier user app currently has a simple single-stage content pipeline:
`poll campaign → single Gemini API call → post to 4 platforms → report metrics`

The goal is a sophisticated multi-agent pipeline that runs 24/7 on the user's desktop:
1. **Profile extraction** — scrape user's social media profiles for voice/style personalization
2. **Research** — daily content research via web crawling/search
3. **Draft** — create platform-specific drafts based on research + past performance + campaign topics + user voice
4. **Quality check** — validate against brand rules, score each draft
5. **Post** — post content with images/video/text at scheduled cadence
6. **Learn** — track engagement and feed learnings back into future content

This requires an agent orchestration framework.

---

## Framework Decision: Detailed Comparison

### Option 1: DeerFlow (bytedance/deer-flow)

**What it gives us:**
- Built on LangGraph — adds skills system (17 built-in), persistent memory (facts with confidence scores), sub-agent spawning, sandboxed code execution, MCP server support
- Gemini support — first-class via `langchain-google-genai`
- Embedded `DeerFlowClient` exists — can call from Python without HTTP stack
- Skills system maps well to our workflow: research skill, drafting skill, posting skill
- Memory system could store learnings from past post performance

**What it costs:**
- Python 3.12+ required (our app uses 3.14, so this is fine)
- Not on PyPI — must clone repo + install from source via `uv` workspaces
- ~30 direct dependencies in the harness (LangGraph, LangChain, kubernetes client, tiktoken, markitdown, etc.)
- **Windows: ACTIVE ISSUES.** GitHub issues #1278, #1210 show Windows problems. A draft PR #1268 for "Windows local startup support" is underway but not merged. The codebase assumes HTTP stack coordination (Gateway API URL, LangGraph Server URL) even in "local" modes.
- Node.js 22+ required for frontend (we could skip this and use our Flask dashboard)
- nginx required as reverse proxy (we could skip this in embedded mode)

**Honest assessment:** DeerFlow CAN work embedded on Windows with `DeerFlowClient` + local sandbox execution. But it's not plug-and-play — expect to fight Windows compatibility issues and contribute fixes upstream. The HTTP stack isn't strictly required but the codebase assumes it in many places.

### Option 2: LangGraph Standalone

**What it gives us:**
- Same graph-based agent orchestration that powers DeerFlow's core
- State checkpointing to SQLite — resume failed workflows exactly where they left off
- Gemini support — seamless via `langchain-google-genai`
- Pure Python, Windows-native, zero platform issues
- Production-ready: 1.0 stable, 6.17M monthly downloads, used at LinkedIn/Replit/Elastic
- We build exactly what we need: research node, draft node, quality node, post node, learn node

**What it costs:**
- We build our own skills/memory/quality system (~200-300 lines total, tailored to Amplifier)
- No built-in sub-agent spawning (but LangGraph has parallel node execution natively)
- No built-in memory persistence (but we add 1 SQLite table — simpler than DeerFlow's fact store)
- Less "out of the box" — more code upfront, but every line serves our exact use case

**Honest assessment:** LangGraph IS what powers DeerFlow under the hood. We get the same graph orchestration + checkpointing without the ~30 extra dependencies and Windows headaches. The tradeoff is writing ~200 lines of our own skill/memory code vs getting DeerFlow's pre-built versions.

### Option 3: CrewAI

**What it gives us:**
- Role-based agent model: "Researcher", "Drafter", "Poster" — most intuitive mental model
- Native Gemini support
- Windows compatible (needs VS Build Tools for chroma dependency)
- Layered memory: ChromaDB (vector embeddings) + SQLite task history
- Many content creation examples in their docs

**What it costs:**
- **No state checkpointing.** If draft generation fails mid-stream, restart from scratch. This is the dealbreaker for a 24/7 desktop app.
- ChromaDB dependency for memory (heavy, requires C++ build tools on Windows)
- Not 1.0 stable yet — fewer battle-tested production deployments than LangGraph

**Honest assessment:** Most intuitive to set up, but the lack of checkpointing makes it fragile for a long-running desktop process. Good for prototyping, not for production 24/7 operation.

### Option 4: Custom Pipeline (no framework)

**What it gives us:**
- Pure Python + Gemini API + webcrawler + Playwright — zero framework dependencies
- Fastest to first working version (2-3 days)
- Full control, easy to debug, easy to understand

**What it costs:**
- Build error recovery, state management, resumption logic ourselves
- As complexity grows (parallel drafting, A/B testing, multi-campaign scheduling), code becomes unmaintainable
- No observability tools — debugging agent decisions is manual
- Essentially reinventing LangGraph poorly

**Honest assessment:** Good for MVP (ship in days). Becomes a liability after 3-6 months as the workflow gets more complex.

### Recommendation

**LangGraph standalone.** Here's the reasoning:

| Criterion | DeerFlow | LangGraph | CrewAI | Custom |
|-----------|----------|-----------|--------|--------|
| Windows native | Uncertain (active issues) | Yes | Yes (with build tools) | Yes |
| Checkpointing/resume | Yes (via LangGraph) | Yes | No | Manual |
| Gemini free tier | Yes | Yes | Yes | Yes |
| Dependencies | ~30 heavy | 2 packages | ~15 + ChromaDB | 0 |
| Production maturity | v2 rewrite (Feb 2026) | 1.0 stable (Oct 2025) | Pre-1.0 | N/A |
| Time to first result | 1-2 weeks (fight Windows) | 3-5 days | 2-3 days | 1-2 days |
| Extensibility | Constrained by lead->sub-agent model | Full control (add any node/edge) | Role-based (add agents) | Unlimited but unmaintainable |
| Memory/learning | Built-in (generic) | Build our own (tailored) | ChromaDB (heavy) | Build our own |

**Key insight:** DeerFlow's architecture IS impressive and DOES match the workflow. But it's the wrong packaging for Amplifier. DeerFlow wraps LangGraph in a general-purpose agent harness with HTTP services, frontend, and sandbox infrastructure we don't need. We should use LangGraph directly — same engine, no baggage, tailored to our exact workflow.

**If DeerFlow fixes Windows support and ships a lightweight pip-installable package**, we should revisit. The skills and memory systems would be genuine value-adds at that point.

---

## Architecture

### Agent Graph (LangGraph)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Profile    │────>│   Research   │────>│    Draft     │────>│   Quality    │
│  Extraction  │     │    Agent     │     │   Agents     │     │    Agent     │
│              │     │              │     │  (4 parallel) │     │              │
│ - Scrape bio │     │ - Web search │     │ - X draft    │     │ - Hard rules │
│ - Recent     │     │ - Past perf  │     │ - LinkedIn   │     │ - Format     │
│   posts      │     │ - Trending   │     │ - Facebook   │     │ - Brand voice│
│ - Style/tone │     │ - Campaign   │     │ - Reddit     │     │ - Scoring    │
│ (weekly)     │     │   context    │     │ + user voice │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                      │
                                                              ┌───────▼───────┐
                                                              │   Decision     │
                                                              │                │
                                                              │ full_auto →    │
                                                              │   post directly│
                                                              │ semi_auto →    │
                                                              │   queue review │
                                                              └───────┬───────┘
                                                                      │
                                                              ┌───────▼───────┐
                                                              │    Post        │
                                                              │                │
                                                              │ - Playwright   │
                                                              │ - Image gen    │
                                                              │ - URL capture  │
                                                              │ - Report sync  │
                                                              └───────┬───────┘
                                                                      │
                                                              ┌───────▼───────┐
                                                              │   Metrics &    │
                                                              │   Learning     │
                                                              │                │
                                                              │ - Scrape T+1-72│
                                                              │ - Analyze perf │
                                                              │ - Update       │
                                                              │   insights DB  │
                                                              └───────────────┘
```

### Profile Extraction (Personalization)

Before the research node, a **profile extraction step** scrapes the user's own social media profiles on each platform required by the campaign. This makes content sound like it was written BY the user, not generically.

**What gets extracted:**
- Bio/about text, tone, and writing style
- Recent post samples (last 5-10 posts) — topics, format, hashtag patterns
- Follower count context (speaks differently to 500 vs 50,000 followers)
- Platform-specific voice (same person sounds different on X vs LinkedIn)

**How it works:**
1. On first campaign or once per week, the profile extraction node visits each platform's profile page using existing Playwright browser profiles
2. Extracts bio + recent posts as markdown (via readability/text extraction)
3. Stores in `agent_user_profile` table (per platform, refreshed weekly)
4. Draft node receives this profile context and generates content that matches the user's existing voice/style

**Privacy:** Profile data stays in local SQLite — never synced to server.

### State Schema

```python
class ContentPipelineState(TypedDict):
    campaign: dict                    # Campaign brief from server
    user_profiles: dict[str, dict]    # Platform -> {bio, recent_posts, style_notes}
    research: list[dict]              # Research findings (topics, data, angles)
    drafts: dict[str, list[str]]      # Platform -> list of draft versions
    quality_scores: dict[str, float]  # Platform -> quality score (0-100)
    approved_drafts: dict[str, str]   # Platform -> final approved draft
    post_results: dict[str, str]      # Platform -> post URL
    metrics: dict[str, dict]          # Platform -> engagement metrics
    insights: list[dict]              # Learnings for future content
    past_performance: list[dict]      # Best-performing posts from DB
```

---

## Files to Create/Modify

### New files
- `scripts/agents/__init__.py` — Package init
- `scripts/agents/pipeline.py` — LangGraph graph definition (profile -> research -> draft -> quality -> decision -> post -> learn)
- `scripts/agents/profile_node.py` — Scrape user's social media profiles for voice/style context (weekly, Playwright)
- `scripts/agents/research_node.py` — Web search via webcrawler + past performance lookup
- `scripts/agents/draft_node.py` — Per-platform content generation with brand voice + user profile context
- `scripts/agents/quality_node.py` — Validate against content-templates.md hard rules, score 0-100
- `scripts/agents/learn_node.py` — Analyze metrics, update insights database

### Modified files
- `scripts/utils/local_db.py` — Add 4 new tables (agent_user_profile, agent_research, agent_draft, agent_content_insights)
- `scripts/campaign_runner.py` — Route to agent pipeline when enabled (feature flag in settings table)
- `scripts/utils/content_generator.py` — Keep as fallback when agent pipeline is disabled
- `requirements.txt` — Add `langgraph`, `langchain-google-genai`

### Reuse existing (no changes needed)
- `scripts/post.py` — Posting functions (agents feed content to same posting logic)
- `scripts/utils/metric_scraper.py` — Metric collection (agents read results for learning)
- `scripts/utils/server_client.py` — Server sync (same endpoints)
- `config/content-templates.md` — Quality agent reads this as verification rules
- `C:\Users\dassa\Work\webcrawler\crawl.py` — Web search + fetch for research node

---

## New DB Tables

```sql
-- User profile snapshots per platform (refreshed weekly)
CREATE TABLE agent_user_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT UNIQUE,       -- "x", "linkedin", "facebook", "reddit"
    bio TEXT,                   -- Profile bio/about text
    recent_posts TEXT,          -- JSON array of last 10 post texts
    style_notes TEXT,           -- AI-extracted style description
    follower_count INTEGER,
    extracted_at TEXT
);

-- Research findings per campaign
CREATE TABLE agent_research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    research_type TEXT,     -- "trending_topic", "competitor_angle", "data_point", "market_event"
    content TEXT,           -- JSON with findings
    source_url TEXT,
    created_at TEXT
);

-- Draft versions with quality scores
CREATE TABLE agent_draft (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    platform TEXT,
    draft_text TEXT,
    pillar_type TEXT,       -- content pillar 1-5
    quality_score REAL,     -- 0-100 from quality agent
    iteration INTEGER,      -- draft version
    approved INTEGER DEFAULT 0,
    posted INTEGER DEFAULT 0,
    created_at TEXT
);

-- Performance insights (feedback loop)
CREATE TABLE agent_content_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT,
    pillar_type TEXT,
    hook_type TEXT,         -- "fear", "freedom", "competence", etc.
    avg_engagement_rate REAL,
    sample_count INTEGER,
    best_performing_text TEXT,
    last_updated TEXT
);
```

---

## Dependencies

```
langgraph>=0.4.0
langchain-google-genai>=4.2.0
```

No Node.js, no nginx, no DeerFlow. Pure Python, Windows-compatible.

---

## Implementation Sequence

### Phase 1: LangGraph skeleton (campaign content pipeline)
Build the core graph that replaces the single-API-call approach. All nodes as independent, stateless functions communicating via state schema (split-ready for server deployment later).

1. Install `langgraph`, `langchain-google-genai`
2. Create `scripts/agents/pipeline.py` with graph: profile -> research -> draft -> quality -> decision -> post
3. Profile node: scrape user's bio + recent posts from each platform using Playwright (weekly cache)
4. Research node: webcrawler search for campaign-relevant topics + crawl any company links from campaign brief + past performance from local DB
5. Draft node: per-platform content using Gemini with research + user profile context + brand voice from `config/content-templates.md`
6. Quality node: validate against content-templates.md hard rules, score 0-100, flag low scores
7. Decision node: route to post (full_auto) or queue for dashboard review (semi_auto)
8. Post node: call existing `post_to_*` functions from `post.py`
9. Wire into `campaign_runner.py` behind feature flag
10. Extend `local_db.py` with all 4 new agent tables

### Phase 2: Content variety + scheduling
Add content types, hooks, cadence scheduling, and CTA rotation.

11. **Content types in draft node** — Support multiple formats: educational, funny, ragebait, text+image, story/narrative. Reuse hooks and format rules from `config/content-templates.md` (emotion-first hooks, content pillars, platform format rules already documented).
12. **Audience-aware scheduling** — Analyze user's follower activity patterns (from profile extraction) to propose optimal posting times per platform. Store as editable schedule in local DB. User can override in dashboard.
13. **CTA rotation** — More aggressive than personal brand: rotate between value-only, soft CTA (mention product), and direct CTA. Configurable ratio per campaign (e.g., 50/30/20 instead of 80/15/5).
14. **Post-post engagement** — After posting, browse feed + click profiles on the platform. No liking/retweeting/commenting (user might not want to engage with random content from their account). Just human-like browsing to appear natural.

### Phase 3: Learning loop
Close the feedback loop — metrics inform future content.

15. Learn node: after metrics come in (T+24h+), analyze what worked — which content types, hooks, posting times drove highest engagement per platform
16. Update `agent_content_insights` table with performance data
17. Research node reads insights to inform future campaign content (e.g., "educational posts with fear hooks perform 3x better on X for this user")
18. Draft node uses insights to weight content type selection

### Phase 4: Dashboard integration
Surface agent artifacts in the user dashboard.

19. Add "Research" view — show what the research node found for each campaign
20. Add "Drafts" view — show all draft versions with quality scores, content type labels
21. Add "Schedule" view — show proposed posting times, let user edit
22. Semi-auto mode: ranked drafts with quality scores -> user picks best -> confirms schedule -> post

### Phase 5: Personal brand pipeline (separate from campaigns)
Build the personal posting workflow as a separate LangGraph graph that reuses the same nodes.

23. Personal content source: 5 content pillars (from content-templates.md), market research, backtest results, indicator signals
24. Daily cadence: 6 posts/day across US time slots (reuse scheduling node from Phase 2)
25. Pillar rotation: specific daily mix (2x education, 1x automation, 1x proof, 1x AI, 1x wildcard)
26. CTA rotation: month 1 = 100% value, month 2+ = graduated
27. Legal disclaimers on all content
28. Same draft/quality/post/learn nodes shared with campaign pipeline

---

## Verification

1. **Phase 1**: Run full graph with test campaign -> verify content quality vs old single-prompt approach. Chrome DevTools MCP on dashboard.
2. **Phase 2**: Generate content with different types (educational vs ragebait) -> verify variety. Check scheduling proposes reasonable times.
3. **Phase 3**: Submit mock metrics -> verify insights table updates -> verify next run's content is influenced.
4. **Phase 4**: Chrome DevTools MCP on dashboard -> verify research, drafts, schedule views render correctly.
5. **Phase 5**: Run personal pipeline -> verify pillar rotation, CTA rotation, 6 daily posts generated.
6. **Regression**: Old `ContentGenerator` still works when feature flag is off.

---

## Confirmed Decisions

1. **Framework**: LangGraph standalone. DeerFlow evaluated but skipped (Windows issues, heavy deps, HTTP stack assumptions). Revisit if DeerFlow ships lightweight pip package.
2. **Architecture**: Desktop-first, but nodes are independent stateless functions communicating via state schema — split-ready for server deployment later.
3. **Research approach**: Topic-based DuckDuckGo searches + crawl company links from campaign brief. No daily site crawling.
4. **Quality loop**: Score and move on (no re-draft loops). Quality agent scores 0-100, low scores flagged but proceed.
5. **Personalization**: User's social media profiles extracted weekly and used to personalize content per platform.
6. **Campaign vs Personal**: Separate pipelines, shared nodes. Campaign pipeline built first (Phases 1-4), personal brand pipeline later (Phase 5).
7. **Post-post engagement**: Browse feed + click profiles only. No liking/retweeting/commenting on behalf of user.
8. **Content types**: Educational, funny, ragebait, text+image, story/narrative. Hooks and format rules reused from `config/content-templates.md`.
