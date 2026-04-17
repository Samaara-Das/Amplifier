# Configuration Reference

All configuration files used by the Amplifier engine and user app.

---

## `config/.env`

Loaded by the engine scripts. Controls API keys, posting behavior, browsing emulation, and engagement caps.

### General

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_POSTER_ROOT` | (project path) | Absolute path to the project root directory |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `GENERATE_COUNT` | `6` | Number of content drafts to generate per run |
| `CAMPAIGN_SERVER_URL` | `https://server-five-omega-23.vercel.app` | Amplifier server URL. Override with `http://localhost:8000` for local dev |

### Content Generation API Keys

Used by `scripts/utils/content_generator.py`. Fallback chain: Gemini (primary) -> Mistral -> Groq for text. Cloudflare Workers AI and Together AI for images.

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key. Free at https://ai.google.dev |
| `MISTRAL_API_KEY` | No | Mistral API key. Free at https://console.mistral.ai. Used as fallback for text generation |
| `GROQ_API_KEY` | No | Groq API key. Free at https://console.groq.com. Used as second fallback for text generation |

### Image Generation API Keys

Used by `scripts/utils/content_generator.py` for AI-generated images. Need at least one provider configured.

| Variable | Required | Description |
|----------|----------|-------------|
| `CLOUDFLARE_ACCOUNT_ID` | No | Cloudflare account ID. Free at https://dash.cloudflare.com |
| `CLOUDFLARE_API_TOKEN` | No | Cloudflare API token with Workers AI permissions |
| `TOGETHER_API_KEY` | No | Together AI API key for FLUX image generation. Free at https://api.together.ai |

### Metric Collection API Keys

Used by `scripts/utils/metric_collector.py`. Optional -- falls back to Playwright scraping if not set.

| Variable | Required | Description |
|----------|----------|-------------|
| `X_BEARER_TOKEN` | No | X API v2 bearer token. Get at developer.twitter.com |
| `REDDIT_CLIENT_ID` | No | Reddit API client ID. Get at reddit.com/prefs/apps |
| `REDDIT_CLIENT_SECRET` | No | Reddit API client secret |

### Posting Behavior

Controls timing during the Playwright posting flow in `scripts/post.py`.

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `POST_INTERVAL_MIN_SEC` | `30` | seconds | Minimum wait between posting to different platforms |
| `POST_INTERVAL_MAX_SEC` | `90` | seconds | Maximum wait between posting to different platforms |
| `PAGE_LOAD_TIMEOUT_SEC` | `30` | seconds | Timeout for page loads |
| `COMPOSE_FIND_TIMEOUT_SEC` | `15` | seconds | Timeout for finding the compose/text box element |

### Browsing Behavior (Human Emulation)

Controls pre- and post-posting browsing in `scripts/utils/human_behavior.py`. Designed to make automation look like natural user activity.

| Variable | Default | Unit | Description |
|----------|---------|------|-------------|
| `BROWSE_MIN_DURATION_SEC` | `60` | seconds | Minimum browsing duration per session |
| `BROWSE_MAX_DURATION_SEC` | `300` | seconds | Maximum browsing duration per session |
| `BROWSE_POSTS_TO_VIEW_MIN` | `2` | count | Minimum posts to scroll through and view |
| `BROWSE_POSTS_TO_VIEW_MAX` | `4` | count | Maximum posts to scroll through and view |
| `BROWSE_PROFILES_TO_CLICK_MIN` | `1` | count | Minimum profiles to click on during browsing |
| `BROWSE_PROFILES_TO_CLICK_MAX` | `2` | count | Maximum profiles to click on during browsing |

### Browser Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `HEADLESS` | `true` | `true` for invisible browser (scheduled runs), `false` to see the browser (manual testing/debugging) |

### CTA Rotation

| Variable | Default | Description |
|----------|---------|-------------|
| `FIRST_POST_DATE` | (empty = today) | Date of first real post in `YYYY-MM-DD` format. Month 1 from this date = 100% pure value content. Month 2+ = 80% value / 15% soft CTA / 5% direct CTA. Used in `scripts/generate.ps1`. |

### Auto-Engagement Daily Caps

Maximum engagement actions per platform per day. Used by `scripts/utils/human_behavior.py`. Set to `0` to disable engagement for a platform.

| Variable | Default | Platform | Action |
|----------|---------|----------|--------|
| `MAX_LIKES_X` | `15` | X | Likes per day |
| `MAX_RETWEETS_X` | `3` | X | Retweets per day |
| `MAX_LIKES_LINKEDIN` | `8` | LinkedIn | Likes per day |
| `MAX_REPOSTS_LINKEDIN` | `2` | LinkedIn | Reposts per day |
| `MAX_LIKES_FACEBOOK` | `8` | Facebook | Likes per day |
| `MAX_SHARES_FACEBOOK` | `2` | Facebook | Shares per day |
| `MAX_LIKES_INSTAGRAM` | `15` | Instagram | Likes per day |
| `MAX_UPVOTES_REDDIT` | `15` | Reddit | Upvotes per day |
| `MAX_LIKES_TIKTOK` | `8` | TikTok | Likes per day |

---

## `config/platforms.json`

Defines all 6 supported platforms. Read by `scripts/post.py` and other engine scripts to determine which platforms to post to and their URLs.

### Per-Platform Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable platform name (e.g., `"X (Twitter)"`) |
| `compose_url` | string | URL to the compose/create post page. Only present for X (`https://x.com/compose/post`) |
| `home_url` | string | Platform home/feed URL. Used for browsing and login checks |
| `upload_url` | string | URL to the upload page. Only present for TikTok |
| `timeout_seconds` | integer | Page load timeout in seconds. Default `30` for all platforms |
| `enabled` | boolean | `true` to include in posting runs, `false` to skip. Code is preserved for disabled platforms |
| `subreddits` | string[] | Reddit only. List of subreddit names to post to (one random pick per run) |
| `note` | string | Optional human note. TikTok has a VPN requirement note |

### Current Platform Configuration

| Platform | Enabled | Key URLs |
|----------|---------|----------|
| X (Twitter) (DISABLED 2026-04-14) | No | compose: `x.com/compose/post`, home: `x.com/home` |
| LinkedIn | Yes | home: `linkedin.com/feed/` |
| Facebook | Yes | home: `facebook.com/` |
| Instagram | No | home: `instagram.com/` |
| Reddit | Yes | home: `reddit.com/`, subreddits: Daytrading, Forex, StockMarket, SwingTrading, AlgoTrading |
| TikTok | No | home: `tiktok.com/`, upload: `tiktok.com/creator#/upload?scene=creator_center` (requires VPN, blocked in India) |

---

## `config/server_auth.json`

Stores the user's authentication credentials for the Amplifier server. Written by `scripts/onboarding.py` after registration or login.

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | JWT access token for authenticating API requests to the server. Issued by `POST /api/auth/login`. Expires after 24 hours (1440 minutes). |
| `email` | string | The registered user's email address |

Used by `scripts/utils/server_client.py` to authenticate all server API calls. The token is sent as a `Bearer` token in the `Authorization` header.

---

## `.taskmaster/config.json`

Task Master CLI configuration. Controls AI models used for task planning and analysis.

### `models` Section

Three model configurations for different Task Master operations:

| Model | Provider | Model ID | Max Tokens | Temperature | Used For |
|-------|----------|----------|------------|-------------|----------|
| `main` | anthropic | `claude-sonnet-4-20250514` | 64000 | 0.2 | Primary task operations (expand, update, add-task) |
| `research` | anthropic | `claude-sonnet-4-20250514` | 64000 | 0.1 | Research-backed operations (analyze-complexity, --research flag) |
| `fallback` | anthropic | `claude-3-7-sonnet-20250219` | 120000 | 0.2 | Fallback when primary model is unavailable |

### `global` Section

| Setting | Default | Description |
|---------|---------|-------------|
| `logLevel` | `"info"` | Logging verbosity |
| `debug` | `false` | Enable debug output |
| `defaultNumTasks` | `10` | Number of tasks generated from PRD by default |
| `defaultSubtasks` | `5` | Number of subtasks per task when expanding |
| `defaultPriority` | `"medium"` | Default priority for new tasks |
| `projectName` | `"Task Master"` | Project display name |
| `ollamaBaseURL` | `"http://localhost:11434/api"` | Ollama API endpoint (if using local models) |
| `bedrockBaseURL` | `"https://bedrock.us-east-1.amazonaws.com"` | AWS Bedrock endpoint (if using Bedrock models) |
| `responseLanguage` | `"English"` | Language for AI responses |
| `enableCodebaseAnalysis` | `true` | Whether Task Master can analyze the codebase for context |
| `enableProxy` | `false` | Route AI calls through a proxy |
| `anonymousTelemetry` | `true` | Send anonymous usage telemetry |
| `userId` | `"1234567890"` | Telemetry user identifier |
| `defaultTag` | `"master"` | Default tag for tasks |

### `grokCli` Section

| Setting | Default | Description |
|---------|---------|-------------|
| `timeout` | `120000` | Grok CLI timeout in milliseconds |
| `workingDirectory` | `null` | Working directory override |
| `defaultModel` | `"grok-4-latest"` | Default Grok model ID |
