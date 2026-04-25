# Brief for Claude Desktop — Amplifier hosting decision (Task #41)

> Paste the section below this line into Claude Desktop. Everything after the horizontal rule is the prompt.

---

You are being brought in as an outside technical advisor on a hosting decision for a project called **Amplifier**. Before you give an opinion, you must build a deep, accurate picture of what Amplifier actually is, what's been built, what's pending, and what failed about the previous hosting setup. Skim is not enough — read the source docs in full where I name them.

## Ground rules (read before anything else)

- **You can and should search the web** for anything you're unsure about — Hostinger plan tiers and what they include, Vercel free-tier limits and overage behavior in 2026, Caddy / systemd / ARQ specifics, pricing pages, current docs. Don't rely on training-data memory for prices, limits, or tier features. Look them up.
- **You can and should ask me questions.** If a fact you need is something only I can answer (which Hostinger plan I actually have, what's installed on the box, what subdomain I own, what Daniel/Nili told me, etc.), STOP and ask. Don't guess and proceed.
- **Never assume anything about my Hostinger plans.** I have referenced two distinct Hostinger accounts/plans below — you do NOT know what tier either one is, what OS they run, what's installed, what RAM/CPU they have, whether they're VPS or shared web hosting, or what their billing model is. If your recommendation depends on any of these facts, you must either ask me or tell me to find out before you finalize the recommendation. A sentence like "assuming the KVM is a KVM 2 with 8GB RAM…" is exactly what I do NOT want — replace it with "I need you to confirm the plan tier before I lock this in."
- **Flag your assumptions explicitly.** Anywhere you make a working assumption to keep the analysis moving, prefix it with `ASSUMPTION:` so I can correct it.

## Step 1 — Read these files in this order to get context

The repo is at `C:/Users/dassa/Work/Auto-Posting-System` (Windows). All paths below are relative to that root.

**Top-level orientation (read first, in order):**
1. `CLAUDE.md` — project overview, commands, architecture summary, decision-making philosophy. This is the single best entry point.
2. `README.md` — public-facing summary.
3. `docs/concept.md` — what Amplifier is at a product level.
4. `docs/AMPLIFIER-SPEC.md` — full product spec.
5. `docs/PRD.md` — product requirements doc with phases.

**Architecture (read after orientation):**
6. `docs/technical-architecture.md` — system architecture across all three components.
7. `docs/amplifier-flow.md` — end-to-end data and control flow.
8. `docs/database-models.md` — server DB schema (12 tables).
9. `docs/local-database-schema.md` — user app SQLite schema (13 tables).
10. `docs/api-reference.md` — server API surface (~90 routes).
11. `docs/server-client-sync-map.md` — how the server and user app exchange data.
12. `docs/status-lifecycle.md` — every status field and transition.

**Key subsystems:**
13. `docs/content-generation.md` — the 4-phase AI content pipeline.
14. `docs/background-agent-reference.md` — the always-on agent on the user device.
15. `docs/campaign-matching.md` — how campaigns get matched to users.
16. `docs/billing-and-earnings.md` — money flow, integer cents, 7-day hold.
17. `docs/platform-posting-playbook.md` — per-platform Playwright posting quirks.
18. `docs/ai-prompt-registry.md` — every AI prompt the system uses.
19. `docs/selector-inventory.md` — 150+ CSS selectors used for posting and scraping.

**Configuration / ops:**
20. `docs/env-vars.md` — every env var across server, user app, engine.
21. `docs/config-reference.md` — config file walkthrough.
22. `docs/deployment-guide.md` — current deployment doc (treat as partially stale; the migration doc below supersedes it).
23. `docs/development-setup.md` — local dev setup.
24. `docs/testing-guide.md` — test approach (note: there is no automated test suite).
25. `docs/troubleshooting.md` — common issues.

**Status of work:**
26. `docs/REMAINING-WORK.md` — what's left.
27. `.taskmaster/tasks/tasks.json` — canonical task list (15/43 done as of 2026-04-25). Read at least the titles + descriptions of pending tasks.
28. `docs/SCHEMA-CHANGES.md` — recent schema changes.
29. `docs/V2-V3-UPGRADE-PLAN.md` — context on the broader Amplifier roadmap (there are sibling versions of Amplifier built by Daniel; do NOT assume those are merged in — ours is v1).

**THE CRITICAL FILE FOR THIS TASK:**
30. `docs/MIGRATION-FROM-VERCEL.md` — full planning doc for the hosting migration. Read every section (~540 lines). It already contains an analysis of Hostinger VPS vs Render vs Railway, but does NOT yet weigh the three options I'm asking you about.

**Note on stale docs (do not rely on these):**
- `docs/EXECUTION-ORDER.md` and `docs/FILE-CHANGE-INDEX.md` — both have **DEPRECATED** banners at the top. The task IDs inside are stale. Skip them.

## Step 2 — Lock in the picture

Before responding, make sure you can answer these to yourself in one sentence each. If you can't, re-read.

1. What are the three components of Amplifier? Which one is currently offline?
2. What is the business model (who pays whom, for what)?
3. What killed the previous Vercel deployment, in dollars and root cause?
4. What stack does the server need to run (runtime, processes, external dependencies)?
5. What is the server's typical request load shape, and why does it matter for the hosting choice?
6. Who are Nili and Daniel in relation to this project, and what do they own?
7. What is the **active branch** right now, and what is the next pending task after #41?
8. What does Task #14 (4-phase content generation) actually do, and is it implemented?

## Step 3 — The decision

Task #41 is the hosting migration. The codebase author and I have already eliminated Vercel-Pro and serverless options. We have **three live options on the table** and need your independent judgment on which to use:

### Option A — A new free Vercel account
- Same product (serverless functions, fluid CPU billing, build-minutes billing).
- Different account (the original was deleted after a billing dispute).
- "Free tier" with overage billing once limits are exceeded.

### Option B — The existing Hostinger KVM VPS that Daniel + Nili already own
- Bought to host **TTE** (`tradingview_to_everywhere` — Python + Selenium signal bridge) and **Stock Buddy** (Next.js trading app, currently on Vercel Pro).
- Amplifier is approved to co-host on the same box.
- Flat monthly cost (already paid — sunk).
- Linux, supports systemd + Caddy + local Redis + ARQ workers cleanly.
- Plan tier (KVM 1/2/4/8) **not yet confirmed** — you can ask me.
- Risk: shared resource contention with TTE (1300+ symbols/day scaling to 14k) and possibly Stock Buddy.

### Option C — A second Hostinger account that Daniel + Nili have used previously to host Wix sites
- A separate Hostinger account, different from the KVM VPS in Option B.
- Was used historically for hosting **Wix-built sites**.
- I do NOT know the plan type, tier, OS, or whether it can run a persistent Python process. **You must ask me what plan it is before judging whether this option is viable.** Don't assume "Wix sites = shared hosting" — Hostinger sells multiple plan types and I haven't told you which one this is. Look up Hostinger's current plan catalog on the web if it helps you ask sharper questions.

### Information you do NOT have and must obtain (either by asking me or by web research)

For Option B (the KVM VPS):
- Plan tier (KVM 1 / 2 / 4 / 8 — or whatever Hostinger currently sells)
- vCPU, RAM, disk, bandwidth allowance
- OS already installed
- What's already running on it (Caddy? nginx? Redis? Python version? systemd units for TTE?)
- SSH access status — do I have it yet?
- Whether a domain/subdomain is already pointed at it

For Option C (the Wix-hosting account):
- Exact plan name and tier
- Whether it's VPS, cloud hosting, business hosting, or shared web hosting
- Whether SSH access is available
- Whether arbitrary processes (Python ASGI, Redis) are permitted
- Current usage / what's deployed on it today

For Option A (new free Vercel):
- Vercel's current 2026 free-tier limits (function invocations, bandwidth, build minutes, fluid CPU)
- Vercel's current overage behavior on free accounts (hard cap, soft cap, forced upgrade?)
- Verify on Vercel's pricing page — do not rely on memory.

If any of the above is missing when you sit down to pick, STOP and ask me. A wrong recommendation built on a guessed plan tier is worse than no recommendation.

### What I want from you

Pick one. Not "it depends." Not "here are the tradeoffs." A specific recommendation with:

1. **Your pick** — A, B, or C.
2. **Why** — the 2-3 reasons that matter most, framed against Amplifier's actual workload (FastAPI + ARQ + Supabase + Gemini calls + 10-min poll loops from every user app instance).
3. **What kills the other two** — be concrete about why they're worse, not just "less ideal."
4. **What you need confirmed before execution** — list the open questions whose answers would change your pick.
5. **Risk you're accepting by going with your pick**, and what triggers a switch to the runner-up.

### Constraints you must respect

- **Cost discipline.** The previous Vercel bill was $47 in one cycle for a project with effectively zero real users. The author has near-zero monthly budget for hosting. "Cheap and predictable" beats "scales beautifully." Anything with usage-based billing and no hard ceiling needs an extremely strong justification.
- **Solo developer.** Sysadmin burden has a real cost. If the choice is "$5/mo with 4 hours/month of ops" vs "$15/mo with 0 hours of ops" — recognize that the author's time has value too.
- **Sunk cost has psychological weight, but only counts if the resource genuinely fits the job.** Don't recommend B just because it's already paid for if the shared resource contention with TTE would cripple Amplifier.
- **The server needs to come back online soon.** The faster the path to a working `https://<domain>/health` returning `{"status":"ok"}`, the better — within reason. Don't trade a one-day setup for a two-week one for marginal gains.
- **Be honest if information is missing.** If you can't decide between B and C without knowing the Hostinger plan tier or whether C is shared hosting vs VPS, say so explicitly and tell me exactly what to find out.

### Tone

Direct. Opinionated. If I'm leaning toward something stupid, say so plainly — I'd rather hear it now than discover it after deploy. Treat this as a peer technical review, not a customer service interaction.

---

End of brief.
