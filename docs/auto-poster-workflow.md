# Auto-Poster E2E Workflow

The complete daily and weekly pipeline for the auto-posting system.

**Daily pipeline:** Content Research (5:00 PM IST) → Content Generation (5:30 PM) → User Review (6:00 PM, ~15 min) → Automated Posting (6:30 PM – 1:30 AM)

**Weekly:** Performance Review (Sunday 7:00 PM IST, ~15 min)

**User's total daily commitment:** ~25 min (15 min review + 10 min manual engagement)

---

## Active Platforms

| Platform | Role | Posts/Week | Engagement | Account Status |
|----------|------|-----------|------------|----------------|
| **X** | Primary growth engine | ~23 (3 tweets/day + 2 threads/week) | Manual — 5 min/day replies on FinTwit | New account (new email) |
| **Reddit** | Built-in distribution, trust builder | 2–3 | Manual — 5 min/day commenting in subreddits | Existing — profile revamp needed |
| **LinkedIn** | Professional credibility, passive growth | 4 (Tue–Fri) | None — auto-post only | Existing (9.5K connections) — revamp for US positioning |
| **Facebook** | Middle-aged audience, monetization target | 7 (daily) | None — auto-post only | Existing (empty) — profile setup needed |

**Paused:** TikTok (until AI video generation ready), Instagram (until TikTok content exists to repurpose)

---

## Phase 1: Content Research Pipeline

**When:** 5:00 PM IST daily (automated)
**Why this time:** 1.5 hours before the first post slot (6:30 PM IST = 8:00 AM EST). US pre-market news is already flowing.

### Content Sources

**1. Coda Notes (primary source)**
User's own notes on trading concepts, indicators, and strategies. The richest source — genuinely the user's perspective. The system reads the Coda doc, picks notes that haven't been used yet, and queues them as content seeds.

**2. Backtest Reports (every 2–3 days)**
From the backtest automater system (192.168.1.11:5050). Pillar 4 gold ("Proof Not Promises"). The system formats key stats — win rate, drawdown, profit factor — into visual content.
- Voice: "I ran this backtest and here's what surprised me"
- NOT: "This strategy has 73% win rate, use it"

**3. Stock Buddy Performance Page Screenshots**
How past signals played out over time. Good for Pillar 3 ("Market Cheat Code") and Pillar 4.
- Voice: "Built a tool that watches for these setups — here's how it's been performing"
- **Signals page is NOT used** — end users won't understand raw signal data. Only the performance page.

**4. Market Events Calendar**
Pre-loaded calendar of known market events: FOMC meetings, CPI/jobs data releases, earnings dates for major tickers ($SPY, $AAPL, $TSLA, $NVDA, $QQQ). On event days, the system prioritizes topical "wildcard" content over standard pillar rotation — these are high-engagement moments.
- Voice: "SPY dropped 2% after the Fed meeting — here's what I think happened"

**5. Weekly Review Insights (week 4+)**
What worked last week feeds into this week's content mix. Top-performing hooks, topics, and formats get weighted higher in generation.

### Future Additions (not v1)
- **Financial newsletters/articles** — curated sources for real insights to rephrase in the user's voice. Extract the core insight, add user's angle.

### Research Pipeline Output
A structured content brief for each day containing:
- 5–7 content topics with assigned content pillars
- Source material for each topic (Coda note, backtest data, performance screenshot, market event)
- Suggested emotional hook angles
- Platform assignments (which topic goes where)

---

## Phase 2: Content Generation

**When:** 5:30 PM IST daily (automated, immediately after research)

### Volume Per Platform

| Platform | Daily Volume | Weekly Total | Formats |
|----------|-------------|-------------|---------|
| **X** | 3 tweets + 1 thread (Tue & Thu) | ~23 | Single tweet (text only, 280 chars), tweet + image (chart/backtest visual), thread (3–7 tweets) |
| **Reddit** | 1 post (2–3 days/week only) | 2–3 | Long-form text (500–1500 words), text + image (backtest results). Title is critical — must be specific and intriguing, not clickbait. |
| **LinkedIn** | 1 post (Tue–Fri only) | 4 | Text post (800–1300 chars, story-driven), text + image, document/carousel (multi-slide — gets 3x engagement) |
| **Facebook** | 1 post (daily) | 7 | Text + image, text only (conversational — shortest, most casual tone of all platforms) |
| **Total** | | **~36** | |

### Voice Rules (NON-NEGOTIABLE)

Every post must sound like **"I learnt this and maybe you can try this too."**
Posts must NEVER sound like the user has trading experience or is ordering people what to do.

| Do | Don't |
|----|-------|
| "I've been studying X and found something interesting" | "Here's how X works" |
| "I ran a backtest and this surprised me" | "This strategy has 73% win rate, use it" |
| "Maybe worth trying if you're exploring this" | "You should do this" |
| "I built a tool for this — here's how it's been doing" | "Use my indicator to make money" |
| "One thing I wish I understood earlier" | "In my experience trading..." |

- Discovery-oriented, sharing a learning journey
- NEVER say "I traded," "my trades," "when I was trading," "in my experience trading"
- Every post opens with an emotional hook (fear, greed, freedom, security, competence)
- Every post delivers one specific actionable takeaway
- Simple language — explain so anyone can understand
- No jargon without an immediate plain-English explanation

### Content Pillar Rotation (daily, across all platforms)

| Slots | Pillar | Theme |
|-------|--------|-------|
| 2 | Pillar 1 or 3 | "Stop Losing Money" (fear) or "The Market Cheat Code" (competence) |
| 1 | Pillar 2 | "Make Money While You Sleep" (automation, passive income) |
| 1 | Pillar 4 | "Proof, Not Promises" (backtest results, data) |
| 1 | Pillar 5 | "Future-Proof Your Income" (AI fear, job security) |
| 1 | Wildcard | Engagement question, trending market event, or pillar rotation |

### Cross-Platform Repurposing

One research topic spawns content for multiple platforms, each adapted to the platform's culture and format:

**Example — backtest result:**
- **X tweet:** Key stat + chart image. Punchy hook. "Tested this strategy on 5 years of SPY data. The result surprised me." + image
- **Reddit post:** Full methodology breakdown — what was tested, why, parameters, results, what it means. 800+ words. Data-first.
- **LinkedIn post:** Story format — "I was curious whether [concept] actually works. So I tested it. Here's what the data showed." 800–1300 chars.
- **Facebook post:** Conversational — "Did you know most [strategy type] strategies actually lose money? I ran the numbers and found something interesting..." Short, question-ending.

Same core insight. Four completely different posts.

### Image & Slideshow Quality (NON-NEGOTIABLE)

- All images and slideshows must be **visually striking and scroll-stopping**
- Branded, consistent color scheme and typography across all content
- Clean, modern design — never cluttered, never generic
- Bold text readable at small sizes (mobile-first — most users see content on phones)
- Charts and data visualized clearly — not raw numbers dumped on screen
- Slideshows: 3–7 slides max, one key point per slide, clear visual flow
- Every image must grab attention in under 2 seconds of scrolling

### CTA Rotation

| Period | Mix |
|--------|-----|
| **Month 1** | 100% pure value. Zero CTAs. Build trust first. |
| **Month 2+** | 80% pure value, 15% soft CTA ("Free indicator — link in bio"), 5% direct CTA ("Premium version coming — DM if interested") |

### Content Series (Recurring Formats)

| Series | Day | Platforms | Description |
|--------|-----|-----------|-------------|
| **Backtest Wednesday** | Wednesday | Reddit + X (thread) | A backtest result with full methodology and key findings |
| **Setup of the Week** | Monday | X + LinkedIn | Stock Buddy performance screenshot with analysis |
| **One Thing I Learned This Week** | Friday | All platforms | Reflection post — one insight from the week's research |

---

## Phase 3: User Review

**When:** 6:00 – 6:15 PM IST daily (manual, ~15 min)
**Why this time:** All drafts are generated. First post goes out at 6:30 PM IST. 15–30 min buffer.

### Review Dashboard

The review dashboard (localhost:5111) shows:
- All drafts grouped by platform
- Each draft displays: platform, format, pillar tag, character count, image preview (if applicable)
- User can approve, reject, or edit each draft
- Only approved drafts enter the posting queue
- Rejected drafts move to `drafts/rejected/`

### Content Buffer

The system maintains a **1-day buffer** of approved posts so it doesn't break if the user misses a review day.

- **Day 1:** Generate 2 days of content (today + tomorrow buffer)
- **Day 2+:** Generate tomorrow's content (today's is already in the buffer from yesterday)
- **If buffer drops to 0 and no review happens:** System pauses posting and notifies the user — never posts unreviewed content

---

## Phase 4: Automated Posting

**When:** Throughout the day, platform-specific timing aligned to US hours

### Posting Schedule

| Time (IST) | Time (EST) | What Gets Posted |
|------------|------------|------------------|
| 6:30 PM | 8:00 AM | X tweet #1 + LinkedIn post (Tue–Fri only) |
| 8:30 PM | 10:00 AM | Facebook post |
| 11:30 PM | 1:00 PM | X tweet #2 + Reddit post (2–3x/week) |
| 1:30 AM | 3:00 PM | X tweet #3 or thread |
| 4:30 AM | 6:00 PM | *(Reserved for future TikTok)* |
| 6:30 AM | 8:00 PM | *(Reserved for future Instagram)* |

### Posting Behavior

- Randomize platform order within each time slot (don't always post X first)
- 30–90 second random delay between platforms in the same slot
- Human behavior emulation before and after each post (feed browsing, scrolling, mouse movements, profile clicks)
- Character-by-character typing with realistic delays (30–120ms per char, 5% chance of longer pauses)
- Each platform uses its own persistent Chromium browser profile (stored in `profiles/`)

### Failure Handling

1. Post fails → retry once after 5 minutes
2. Retry fails → move draft to `drafts/failed/`, notify user, continue to next platform
3. Failed drafts appear in the review dashboard for manual retry or discard

---

## Phase 5: Daily Manual Engagement

**The auto-poster handles posting only. Engagement is manual.**

**When:** Anytime during the day, 10 min total

### X (5 min)
- Scroll FinTwit, reply to 5–10 posts from accounts with 10K–100K followers
- Leave genuinely useful takes, not generic "great post!" replies
- This is where real growth happens — one great reply on a viral FinTwit post sends people to your profile

### Reddit (5 min)
- Check comments on your own posts, reply thoughtfully
- Comment on 3–5 other posts in target subreddits (r/daytrading, r/stocks, r/algotrading)
- Builds karma AND the 9:1 comment-to-post ratio Reddit requires to not flag you as a spammer
- Never mention your tools or TradingView in comments unless someone directly asks

---

## Phase 6: Weekly Performance Review

**When:** Sunday 7:00 PM IST (~15–20 min)

### Automated Analysis
The system pulls metrics from each platform and generates a report:
- Impressions, engagement rate, likes, comments, shares, follows gained per post
- Top 5 and bottom 5 posts across all platforms
- Pattern detection: which pillar performed best, which hook style, which format, which posting time

### Manual Review (~15 min)
1. Read the weekly summary (5 min)
2. Confirm or override system recommendations (5 min)
3. Note content ideas inspired by what worked (5 min)

### Feedback Loop — What Changes Next Week
- **Pillar weights:** If Pillar 1 ("Stop Losing Money") consistently outperforms, it gets more slots next week
- **Hook templates:** Hooks that worked get reused with variations
- **Formats:** Formats that flopped get reduced (e.g., text-only bombs on Facebook → shift to text+image)
- **Topics:** Topics that resonated get expanded into multi-post series
- **Platform-specific:** Adjust tone/length/format per platform based on what each platform's audience responds to

### Data Maturity

| Period | Action |
|--------|--------|
| **Weeks 1–3** | Collect data only. Don't adjust anything. Sample size too small — 3 likes vs 1 like is noise, not signal. |
| **Week 4+** | Start making data-driven adjustments to pillar mix, hook styles, formats, and posting times. |
| **Month 3+** | Enough data for confident A/B testing — same topic, different hooks, measure which wins. |

---

## Account Warmup Plan

New accounts can't go from 0 to full cadence without being flagged as spam. Gradual ramp-up:

### X (New Account)

| Week | Tweets/Day | Threads | Replies/Day |
|------|-----------|---------|-------------|
| 1 | 1 | 0 | 10 |
| 2 | 2 | 0 | 10 |
| 3+ | 3 | 2/week | 5–10 |

### Reddit

| Period | Activity |
|--------|----------|
| Weeks 1–2 | Comments only (3–5/day). No posts. Build karma and account age. |
| Weeks 3–4 | 1 post every few days + daily comments. |
| Month 2+ | Full cadence — 2–3 posts/week. |

### LinkedIn (Existing — 9.5K Connections)
No warmup needed. Start at full cadence (4 posts/week, Tue–Fri).

### Facebook (Existing — Empty)

| Week | Posts |
|------|-------|
| 1 | 1 every other day |
| 2+ | 1/day |

---

## Market Events Calendar

Pre-loaded calendar of known US market events. On event days, the system prioritizes topical "wildcard" content over standard pillar rotation.

### Events to Track
- **FOMC meetings** — Fed rate decisions (8x/year). Biggest market-moving events.
- **CPI / Jobs data releases** — monthly economic indicators that move markets
- **Earnings dates** — for major tickers: $SPY, $AAPL, $TSLA, $NVDA, $QQQ, $MSFT, $AMZN, $META, $GOOGL
- **Options expiration** — monthly/quarterly OPEX dates (high volatility)

### How Events Affect Content
- Event day: At least 1 post is topical/reactive ("Here's what just happened and what I'm watching")
- Day before: Anticipation post ("Fed meeting tomorrow — here's what happened the last 5 times they raised rates")
- Day after: Analysis post ("SPY dropped 3% after CPI — I ran a quick backtest on what usually happens next")

---

## Draft Lifecycle

```
Content Research (5:00 PM IST)
    ↓
Content Generation (5:30 PM IST)
    ↓ drafts land in drafts/review/
User Review (6:00 PM IST)
    ↓ approve → drafts/pending/
    ↓ reject  → drafts/rejected/
Automated Posting (6:30 PM – 1:30 AM IST)
    ↓ success → drafts/posted/
    ↓ failure → retry once → drafts/failed/
Weekly Review (Sunday 7:00 PM IST)
    ↓ insights feed back into next week's research pipeline
```

---

## System Architecture Summary

| Component | What It Does | Automated? |
|-----------|-------------|------------|
| Content Research Pipeline | Reads Coda notes, backtest reports, Stock Buddy performance, market calendar. Produces content brief. | Yes |
| Content Generator | Takes brief, generates platform-specific drafts with hooks, images, correct formats. | Yes |
| Review Dashboard | Shows drafts for approval/rejection/editing. | Manual (~15 min/day) |
| Posting Engine | Posts approved drafts at scheduled times with human behavior emulation. | Yes |
| Performance Tracker | Pulls metrics, ranks posts, identifies patterns. | Yes |
| Weekly Review | Summarizes performance, recommends adjustments. | Semi-auto (~15 min/week) |
| Manual Engagement | X replies, Reddit comments. | Manual (~10 min/day) |
