# Nvidia free-tier API for Amplifier — research note (filed 2026-04-29)

**Status:** DEFERRED. MVP-only consideration. Currently using Gemini → Mistral → Groq fallback chain (server) and same chain on user-side via AiManager. Re-evaluate post-MVP if cost/reliability becomes a problem.

## Question asked

Can a single Nvidia free-tier API key (80–100+ LLMs via build.nvidia.com NIM APIs) be exposed to Amplifier users for content generation / quality-gate / matching?

## Grok's response (verbatim, 2026-04-29)

**Yes, one person (or one account) gets a single API key that unlocks free access to many (80–100+) LLMs via NVIDIA's hosted NIM APIs at build.nvidia.com.**
It's exactly as Perplexity described: the key works with the OpenAI-compatible endpoint (`https://integrate.api.nvidia.com/v1`), so you can swap it into any OpenAI SDK, LangChain, Cursor, etc. You pick models like MiniMax, GLM-5, DeepSeek, Kimi, Nemotron, etc., right from their catalog.

### Current Limits (as of April 2026)
- **Rate limit**: ~40 requests per minute (RPM) on the free tier. This is the main enforcement now (rate limits vary slightly by model and load; you can see your exact limit in your account dashboard on build.nvidia.com).
- **No daily or monthly hard cap** for light usage. The old credit system (1,000–5,000 credits) has largely been replaced by these ongoing rate limits for trial/prototyping use.
- **No expiration**: As long as you stay under the rate limit, you can keep calling the API every day indefinitely for **light, personal prototyping/testing**.

**So yes — for a single person doing a couple of requests a day (or even a few dozen spread out), it effectively feels "unlimited" for everyday personal use.** The 40 RPM resets continuously (every minute), so you'd have to be bursting hundreds of calls in a short window to hit it.

### For Amplifier — Big Caveats

This setup **does NOT** safely turn into a free backend for a multi-user app like Amplifier (where users paste their NVIDIA key and the app runs regular/automated content generation, research, and social-profile mining/scraping on their behalf every day).

Here's why, based on NVIDIA's official stance:

- **Explicitly for prototyping only**
  NVIDIA's Developer Program FAQ and API Trial Terms state the free hosted NIM APIs are for **development, research, testing, and prototyping** — **not production use**. Production = anything serving real end-users, running business workflows, or generating content on a regular/ongoing basis for others. Amplifier's daily social-media automation falls squarely into production.

- **Cannot be used to provide a service to others**
  The trial terms prohibit copying, sublicensing, distributing, or **making the API (or generated content) available to others**. Even if each user supplies their own key, the app is effectively proxying and offering NVIDIA's inference as a core feature of a commercial product. NVIDIA views this as "providing a service" — which is not allowed on the free tier.

- **Risks for the app**
  - User keys could get rate-limited or suspended if NVIDIA detects high/automated usage patterns (especially scraping/mining loops or scheduled jobs).
  - The free tier has no SLA, no guaranteed uptime, and can get throttled under load.
  - If NVIDIA flags the usage as production, they can block the keys (or the whole app's traffic).
  - Onboarding friction: Users need an NVIDIA Developer Program account + API key (some reports mention phone verification).

**Bottom line for Amplifier**: It *technically* works for very light per-user usage if users bring their own key and the app keeps calls infrequent. But it violates the spirit (and likely the letter) of NVIDIA's terms. We'd be building on top of a free prototyping sandbox that NVIDIA subsidizes specifically to avoid exactly this kind of usage.

### Better/Safer Options for a Free-for-Users Model
- Stick with truly personal-key-only flows but clearly tell users it's for light/testing use only.
- Self-host NIM containers (free for research on your own GPUs under the Developer Program) — but that costs infra.
- For production-grade free tier, look at other providers (Groq, Together.ai, Fireworks, etc.) that explicitly allow BYOK (bring-your-own-key) or have more permissive free tiers — though most still ban heavy SaaS proxying on free plans.
- Ultimately, if the app is to be reliably free for users with heavy daily use, someone (the platform or the user) will need a paid plan somewhere.

## User's note (2026-04-29)

> "this will be just for the MVP of amplifier — so no terms that grok reported are violated."

User's reading: at MVP scale (very few users, light usage), the per-user-key Nvidia path may stay within the spirit of the trial terms. To be re-evaluated when usage grows.

## Implications for current stack

- **Server-side AI** (matching, campaign_wizard, quality_gate): currently Gemini server key + Mistral + Groq fallback chain (added 2026-04-29 in Task #15). No change needed for MVP.
- **User-side AI** (content_agent, profile_scraper, image generation): currently AiManager with Gemini → Mistral → Groq + image providers. Users provide their own Gemini/Mistral/Groq keys during onboarding (encrypted in `data/local.db`).
- **Adding Nvidia as a 4th fallback** would extend the AiManager chain. Would unlock more models (MiniMax, GLM-5, DeepSeek, Kimi, Nemotron) for users who can be bothered to get an Nvidia Developer key.

## Decision (2026-04-29)

**Defer.** Reasons:
1. Current 3-provider chain (Gemini + Mistral + Groq) is working in production after Task #15 — Mistral picked up when Gemini was 503-throttled. Adding a 4th provider increases test surface without solving a known problem.
2. Onboarding friction: Nvidia Developer Program signup + phone verification adds a step. Free Gemini/Groq keys are easier to get.
3. Terms-of-service ambiguity: 1 user OK, 1000 users probably not. Hard to scale Nvidia integration cleanly without revisiting at every growth threshold.
4. The MVP doesn't need 80+ models — it needs 3 reliable fallbacks. We have that.

## Revisit triggers

- Gemini + Mistral + Groq chain consistently fails in production over a 1-week window (would warrant a 4th provider)
- User onboarding friction data shows users don't have any of Gemini/Mistral/Groq keys (would warrant adding Nvidia as an alternative entry point)
- Nvidia changes terms to explicitly allow BYOK consumer-app proxying (changes the calculus)
- A specific Nvidia-only model (Nemotron, GLM-5, etc.) becomes critical for a feature that can't be matched on Gemini/Mistral/Groq

## File location

This doc lives at `docs/research/nvidia-free-tier-for-amplifier.md`. Linked from STATUS.md "deferred" considerations once that section is updated.
