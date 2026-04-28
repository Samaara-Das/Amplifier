# Environment Variables — Unified Reference

Every environment variable across all three systems: server, user app, and config files.

---

## Server (`server/app/`)

Loaded via Pydantic `BaseSettings` in `server/app/core/config.py` with `.env` support.

### Required

| Variable | Default | File | Purpose |
|---|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./amplifier.db` | config.py, database.py | Database connection. SQLite for local dev, `postgresql+asyncpg://` for production (Supabase). |
| `JWT_SECRET_KEY` | `change-me-to-a-random-secret` | config.py | JWT token signing. **Change in production.** |
| `ADMIN_PASSWORD` | `admin` | admin router | Admin dashboard login password. **Change in production.** |

### Optional — Features

| Variable | Default | File | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | `""` | campaign_wizard.py, matching.py | Google Gemini API key. Required for AI campaign wizard and AI matching. |
| `STRIPE_SECRET_KEY` | `""` | config.py, payments.py | Stripe API key. Payments disabled if not set. |
| `STRIPE_WEBHOOK_SECRET` | `""` | payments.py | Stripe webhook verification. |
| `SUPABASE_URL` | `""` | config.py | Supabase project URL for file storage. |
| `SUPABASE_SERVICE_KEY` | `""` | config.py | Supabase service role key. |
| `ENCRYPTION_KEY` | (dev fallback) | crypto.py | AES-256-GCM key for server-side encryption. Dev fallback is not secure. |
| `REDIS_URL` | `redis://localhost:6379/0` | config.py | Redis for background jobs (not currently used in production). |

### Optional — Tuning

| Variable | Default | File | Purpose |
|---|---|---|---|
| `PLATFORM_CUT_PERCENT` | `20.0` | config.py | Platform's revenue cut (0-100). |
| `MIN_PAYOUT_THRESHOLD` | `10.0` | config.py | Minimum USD for user withdrawal. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | config.py | JWT token expiry. |
| `HOST` | `0.0.0.0` | config.py | Server bind address. |
| `PORT` | `8000` | config.py | Server bind port. |
| `DEBUG` | `true` | config.py | SQLAlchemy echo logging. Set `false` in production. |
| `SERVER_URL` | `http://localhost:8000` | config.py, payments.py | Public URL (used for Stripe callbacks). |

### Infrastructure

| Variable | Default | File | Purpose |
|---|---|---|---|
| `VERCEL` | (not set) | database.py, main.py | **Legacy** — auto-set by Vercel serverless. When set: SQLite uses `/tmp/`, skips table init on startup. Not relevant for the current Hostinger KVM VPS deployment; code retained for compat. |

---

## User App & Scripts (`scripts/`)

Loaded via `dotenv.load_dotenv("config/.env")` in most scripts.

### AI Text Generation

| Variable | Default | File | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | `""` | content_generator.py, manager.py | **Primary** text + image provider. Free tier: ~60 text req/day, 500 images/day. |
| `MISTRAL_API_KEY` | `""` | content_generator.py, manager.py | **Fallback 1** text provider. |
| `GROQ_API_KEY` | `""` | content_generator.py, manager.py | **Fallback 2** text provider. |

### AI Image Generation

| Variable | Default | File | Purpose |
|---|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | `""` | content_generator.py, image_manager.py | Cloudflare Workers AI account ID. FLUX.1 Schnell (20-50 free/day). |
| `CLOUDFLARE_API_TOKEN` | `""` | content_generator.py, image_manager.py | Cloudflare API token. |
| `TOGETHER_API_KEY` | `""` | content_generator.py, image_manager.py | Together AI for FLUX image gen ($25 credit). |

### Metric Collection API

| Variable | Default | File | Purpose |
|---|---|---|---|
| `X_BEARER_TOKEN` | `""` | metric_collector.py | X API v2 bearer token. Falls back to Playwright scraping if not set. |
| `REDDIT_CLIENT_ID` | `""` | metric_collector.py | Reddit API client ID. Falls back to Playwright. |
| `REDDIT_CLIENT_SECRET` | `""` | metric_collector.py | Reddit API secret. |

### Posting Behavior

| Variable | Default | File | Purpose |
|---|---|---|---|
| `HEADLESS` | `false` | post.py, metric_scraper.py | Browser visibility. `true` for scheduled runs, `false` for debugging. |
| `POST_INTERVAL_MIN_SEC` | `30` | post.py | Min seconds between platform posts. |
| `POST_INTERVAL_MAX_SEC` | `90` | post.py | Max seconds between platform posts. |
| `PAGE_LOAD_TIMEOUT_SEC` | `30` | post.py | Page load timeout. |
| `COMPOSE_FIND_TIMEOUT_SEC` | `15` | post.py | Compose element timeout. |
| `RETRY_DELAY_SEC` | `300` | post.py | Retry delay after failure (5 min). |

### Browsing Emulation

| Variable | Default | File | Purpose |
|---|---|---|---|
| `BROWSE_MIN_DURATION_SEC` | `60` | human_behavior.py | Min browsing time per session. |
| `BROWSE_MAX_DURATION_SEC` | `300` | human_behavior.py | Max browsing time per session. |
| `BROWSE_POSTS_TO_VIEW_MIN` | `2` | human_behavior.py | Min posts to scroll through. |
| `BROWSE_POSTS_TO_VIEW_MAX` | `4` | human_behavior.py | Max posts to scroll through. |
| `BROWSE_PROFILES_TO_CLICK_MIN` | `1` | human_behavior.py | Min profiles to visit. |
| `BROWSE_PROFILES_TO_CLICK_MAX` | `2` | human_behavior.py | Max profiles to visit. |

### Engagement Caps (per platform per day)

| Variable | Default | Platform | Action |
|---|---|---|---|
| `MAX_LIKES_X` | `15` | X | Likes/day |
| `MAX_RETWEETS_X` | `3` | X | Retweets/day |
| `MAX_LIKES_LINKEDIN` | `8` | LinkedIn | Likes/day |
| `MAX_REPOSTS_LINKEDIN` | `2` | LinkedIn | Reposts/day |
| `MAX_LIKES_FACEBOOK` | `8` | Facebook | Likes/day |
| `MAX_SHARES_FACEBOOK` | `2` | Facebook | Shares/day |
| `MAX_LIKES_INSTAGRAM` | `15` | Instagram | Likes/day |
| `MAX_UPVOTES_REDDIT` | `15` | Reddit | Upvotes/day |
| `MAX_LIKES_TIKTOK` | `8` | TikTok | Likes/day |

### Other

| Variable | Default | File | Purpose |
|---|---|---|---|
| `AUTO_POSTER_ROOT` | (project path) | post.py | Absolute path to project root. |
| `LOG_LEVEL` | `INFO` | post.py | Python logging level. |
| `GENERATE_COUNT` | `6` | generate.ps1 | Drafts to generate per run (personal brand engine). |
| `CAMPAIGN_SERVER_URL` | `http://localhost:8000` | server_client.py | Amplifier server URL. Production server is `https://api.pointcapitalis.com` — set this in `config/.env` to point at prod. Defaults to localhost for local dev. |
| `FIRST_POST_DATE` | (empty = today) | generate.ps1 | First post date for CTA rotation. Month 1 = 100% value, Month 2+ = 80/15/5 mix. |

---

## Config File Locations

| File | System | Format | Purpose |
|---|---|---|---|
| `config/.env` | User app | dotenv | All user app env vars (AI keys, posting behavior, engagement caps) |
| `server/.env` | Server | dotenv | Server config (DATABASE_URL, JWT_SECRET_KEY, STRIPE, etc.) |
| `server/.env.example` | Server | template | Example server config with all variables listed |
| `config/platforms.json` | User app | JSON | Platform URLs, enable flags, proxy, subreddits |
| `config/server_auth.json` | User app | JSON | JWT token + email (auto-created on login, encrypted) |
| `.taskmaster/config.json` | Dev tools | JSON | Task Master AI model config |

---

## Production Deployment (Hostinger KVM VPS — `https://api.pointcapitalis.com`)

Set via systemd unit environment or `/etc/environment` on the VPS (`ssh -i ~/.ssh/amplifier_vps sammy@31.97.207.162`):

| Variable | Status |
|---|---|
| `DATABASE_URL` | Set — Supabase PostgreSQL (transaction pooler, port 6543) |
| `JWT_SECRET_KEY` | Set — encrypted |
| `ADMIN_PASSWORD` | Set — encrypted |
| `GEMINI_API_KEY` | Set — for campaign wizard + matching |
| `ENCRYPTION_KEY` | Set — AES-256-GCM key |
| `SUPABASE_URL` | Set — `https://ozkntsmomkrsnjziamkr.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Set — service role key |

## UAT Test-Mode Flags (User App / Scripts)

Real production code, gated by env vars. Default behaviour preserved when unset. Set in `config/.env` before running the agent.

| Variable | Where Read | Effect |
|---|---|---|
| `AMPLIFIER_UAT_INTERVAL_SEC` | `content_agent.py`, `background_agent.py` | Shortens content-gen check interval and research/strategy cache TTL (e.g. `30` for fast cache testing) |
| `AMPLIFIER_UAT_BYPASS_AI` | `content_agent.py` | Forces ContentAgent to fail immediately → exercises `ContentGenerator` fallback path (`1` or `true`) |
| `AMPLIFIER_UAT_FORCE_DAY` | `background_agent.py` | Overrides `day_number` in `generate_daily_content()` — tests hook diversity across days |
| `AMPLIFIER_UAT_POST_NOW` | `user_app.py` | Schedules approved drafts ~1 min out instead of next peak-window slot |
