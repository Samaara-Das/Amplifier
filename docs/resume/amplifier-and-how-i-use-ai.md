# Amplifier — What It Is, and How I Use AI to Build It

*A plain-English explanation written for non-technical readers.*

---

## See It Live

Anyone can open these in a browser and look around:

- **Company dashboard (where businesses launch campaigns):** https://api.pointcapitalis.com/company/login
- **Admin dashboard (the back-office I use to run the marketplace):** https://api.pointcapitalis.com/admin/login
- **Public API documentation (every feature, auto-generated):** https://api.pointcapitalis.com/docs
- **Health check (proves the server is up right now):** https://api.pointcapitalis.com/health
- **Source code on GitHub:** https://github.com/Samaara-Das/Auto-Posting-System

The server runs 24/7 on a Hostinger virtual machine in Mumbai, behind an automatically-renewing HTTPS certificate, with the database hosted on Supabase in the US East region.

---

## Part 1 — What is Amplifier?

Amplifier is a **two-sided online marketplace** I'm building. Think of it like Uber, but instead of connecting drivers and riders, it connects two different groups:

- **Companies** that want their products talked about on social media (X, LinkedIn, Facebook, Reddit).
- **Everyday people** who want to earn money by posting on their existing social media accounts.

### The problem it solves

Social media marketing today is broken in two ways:

1. **Companies can't afford it.** Hiring an Instagram influencer costs anywhere from $500 to $50,000 per post — way out of reach for most small businesses. Running ads means bidding against giants with deep pockets.
2. **Normal people can't earn from social media.** YouTube requires 1,000 subscribers before they pay you. TikTok needs 10,000 followers. The 99% of social media users with smaller followings get nothing — even though they spend hours a day on these platforms.

Amplifier fills that gap. A company pays a few dollars per thousand views. A regular person with 300 Facebook friends and 500 LinkedIn connections downloads an app, lets the AI write and post content for them, and earns real money — passively.

### How it actually works

There are three parts:

1. **The Amplifier Server** — a website where companies sign up, describe their product, set a budget, and launch a "campaign." This is live at **api.pointcapitalis.com**.
2. **The User App** — a program that everyday people install on their computer. It connects to their social accounts, listens for campaigns they're a good fit for, and handles everything automatically.
3. **The AI Brain** — the part that does the actual work. It writes posts, designs images, picks the best time to post, hits "publish," and tracks how the post performs so the company can be billed and the user can be paid.

A user signs up once, connects their accounts, and from then on the system runs by itself. They wake up, see new campaigns the AI accepted overnight, and watch their balance grow.

### Why it's hard to build

This isn't a simple app. To make it work, the system has to:

- **Write content that doesn't sound like AI.** People scroll past anything that smells like a bot. The AI has to sound like a real person genuinely recommending something.
- **Post on six different social platforms** (X, LinkedIn, Facebook, Reddit, Instagram, TikTok), each with its own rules, design quirks, and ways of detecting and banning automation.
- **Pay people accurately.** Every view, every like, every comment has to be tracked, deduplicated, and converted into cents — without rounding errors that lose someone a penny over thousands of posts.
- **Avoid getting accounts banned.** Social platforms hate automation. The system has to behave like a human: type one character at a time, scroll randomly, take breaks, vary its timing.
- **Detect fraud.** Some users will try to game the system — fake views, deleted posts, stolen identities. The AI watches for that and adjusts.

It's the kind of project that would normally take a team of 5–10 engineers a year or more. I'm building it solo.

---

## Part 2 — How I Use AI to Build It

Here's the part most people don't understand: **I don't write most of the code myself**. I build and ship Amplifier by directing AI agents the way a film director directs actors. I'm the one with the vision, the priorities, and the final word — but the AI does the actual typing.

### The AI tools I use every day

**1. Claude Code (my main tool).** Claude Code is a command-line program made by Anthropic that lets me have a conversation with an AI that can read my project's files, write code, run programs, click through web pages, and test what it just built. It's the difference between asking ChatGPT a question in a browser tab and having a teammate sitting next to you who can actually open your laptop and make changes.

**2. Different AI "personalities" for different jobs.** Claude has multiple model sizes — Opus (the smartest, slowest, most expensive) and Sonnet (faster, cheaper, almost as good). I use Opus to **plan** — to think through architecture, decide what to build next, and review tricky problems. I use Sonnet to **execute** — to write the actual code, fix small bugs, run tests. This saves money and runs faster.

**3. Sub-agents.** When a task is big enough to fill up the AI's short-term memory (its "context window"), I send it off as a sub-agent. The sub-agent goes off, does the work, and comes back with a one-paragraph summary. This keeps the main conversation focused. It's like having interns I can dispatch on side errands.

**4. MemPalace — a memory system I built for the AI.** AI assistants normally forget everything between sessions. I built a long-term memory system (using a database and semantic search) that the AI reads at the start of every session and writes to at the end. It remembers decisions I made three weeks ago, bugs we already fixed, and what I was working on yesterday. So every session feels like the AI already knows the project — because it does.

**5. Slash commands and skills.** I've written my own custom commands the AI can run on demand. For example:
- `/get-context` loads the AI up with everything it needs to know about Amplifier from memory.
- `/uat-task <id>` makes the AI test a feature end-to-end on the real, live system — opening a browser, posting to real social accounts, then deleting the post — and refusing to mark the feature as "done" unless every single check passes.
- `/commit-push` saves my work, uploads it to GitHub, and automatically deploys it to my live server.

### The actual workflow — what a day looks like

Here's how I shipped a feature called the "4-phase content agent" — the part of Amplifier that writes the actual social media posts:

1. **Plan it together.** I describe what I want in plain English: "I want the AI to first research the company, then design a content strategy, then write the posts, then review them for quality." Opus turns that into a detailed technical specification with files, functions, and step-by-step instructions.

2. **Hand off to Sonnet.** Once I'm 95% sure the plan is right, I tell the cheaper, faster Sonnet model to actually write the code, following the spec.

3. **Test it for real.** I run `/uat-task 14`. The AI starts the live server, opens a real browser, creates a real campaign, accepts it as a fake user, lets the content agent generate posts, posts them to real LinkedIn, Facebook, and Reddit accounts, scrapes the engagement, then deletes the posts. While it's running, it's also taking screenshots and writing a report.

4. **Find and fix bugs.** That single test run found **seven real bugs** that ordinary unit tests had missed for over a week. The AI surfaced each one, I confirmed the fix, and Sonnet patched them — sometimes editing files directly on the live server over SSH because the bug was urgent.

5. **Save the lessons.** At the end of the session, I run `/update-context` and the AI writes a journal entry into MemPalace describing what we did, what broke, and what to remember next time.

That entire feature — research, strategy, writing, posting, billing — went from idea to fully verified on live social media in a few intense days. With a traditional team it would have taken weeks.

### The principles I work by

I treat the AI like a sharp but junior teammate, not a magic box:

- **I plan before I let it code.** "Strong opinions, loosely held." If I can't explain the goal in one sentence, neither can the AI.
- **I push back when it overbuilds.** AI loves to add unnecessary features, fallbacks, and abstractions. I keep it focused on what ships now.
- **I make it test on the real product, not on mocks.** Mocked tests passed for over a week while the real system was quietly broken. Now every important feature has to be verified end-to-end on the live system before it counts as done.
- **I make it commit and push every time.** Every fix, every doc update, every feature gets saved to GitHub the moment it's done. No work in limbo.
- **I save its lessons.** When the AI discovers a quirk ("this social platform's button is hidden behind an invisible overlay"), that goes straight into the memory system so the next session — or a future agent on a similar problem — already knows.

### The numbers, today

- **65 tasks tracked**, 26 done, organized into themed "batches" (Money Loop, AI Brain, Product Features, Business Launch, Polish).
- **About 90 web addresses** on the server, **11 database tables**, **6 social platforms** integrated.
- **One person building it**, with AI doing the heavy lifting — no co-founder, no engineering team.
- **Live and running** at api.pointcapitalis.com on a small server I rent for a flat monthly fee.
- **Multiple AI providers chained together** for content generation — Google Gemini first, then Mistral, then Groq if those fail, then a Python image-fallback as a last resort. Free tier on all of them.

---

## In one paragraph

Amplifier is a marketplace where companies pay everyday people to post about products on their social media, and AI handles the writing, posting, and payouts automatically. I'm building it solo by directing Claude — Anthropic's coding AI — through a structured workflow: a smart "planner" model designs each feature, faster "worker" models write the code, a custom long-term memory system keeps the AI in sync across sessions, and every feature is end-to-end tested on the real, live system before it ships. It's a working demonstration that one focused person, with the right AI tooling, can build and run a product that traditionally requires a team.
