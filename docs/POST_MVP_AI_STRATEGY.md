# Post-MVP: AI Strategy for Content Generation

**Status**: Planning (to be discussed in future session)

## Core Thesis

AI models are getting cheaper fast. Some are already free. The Amplifier content generation and posting architecture should be designed around this trajectory — optimize for **quality and multi-step intelligence**, not cost minimization.

## Current State (Session 16, 2026-03-22)

- **Text generation**: Gemini 2.5 Flash Lite (free tier) — single-shot prompt, no research, no multi-step
- **Image generation**: Cloudflare Workers AI FLUX.1 schnell (free) → Together AI (free) → Pollinations → PIL fallback
- **Content quality**: Generic, reads like an ad. No market awareness, no research, not emotion-first

## Future Direction

### 1. Multi-Agent Content Pipeline

Instead of single-shot LLM calls, use a multi-agent pipeline:
- **Research agent** — scans market news, trending topics, platform engagement patterns
- **Content agent** — drafts posts using research + brand voice
- **Image agent** — generates or selects visuals matching the content
- **Platform adaptation agent** — reformats for X vs LinkedIn vs Reddit (not just character limits — tone, hook style, hashtag strategy)

### 2. Frameworks to Evaluate

- **DeerFlow** (ByteDance) — open-source super-agent framework. Orchestrates sub-agents, has skills system, sandbox execution, persistent memory. #1 on GitHub Trending (Feb 2026). Could power the multi-agent pipeline.
- **Build our own** — simpler, more control, no external dependency. Could be lighter-weight than DeerFlow.
- **Evaluate both** before deciding.

### 3. Models to Explore

- **Xiaomi MiMo v2 Flash** — super cheap, free on Kiko Claw. Evaluate for content generation quality.
- **Free/cheap models** — the architecture should be model-agnostic. Swap models as better/cheaper ones emerge.
- **Design principle**: Never hardcode to one model. Always have a fallback chain. Optimize for quality, not provider lock-in.

### 4. Architecture Principles

- **Model-agnostic**: Provider interface that any LLM can plug into
- **Multi-step over single-shot**: Research → draft → refine → adapt beats one prompt
- **Cost will approach zero**: Design for quality differentiation, not cost savings
- **User-side compute**: AI runs on user device (current design) — this gets cheaper as models get smaller/faster
- **Fallback chains**: Always have 3+ providers. If one goes down or changes pricing, auto-switch.

## Decision Log

- **2026-03-22**: Explored DeerFlow. Decided to defer integration until existing pipeline is tested E2E. Will revisit post-MVP alongside alternatives and custom build option.
