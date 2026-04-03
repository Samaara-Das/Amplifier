# AmpliFire v2/v3 Upgrade Plan

**Date**: April 3, 2026
**Purpose**: Adopt battle-tested patterns from Dan's v2 (NestJS) and v3 (Android) into our v1 Amplifier (Python/FastAPI + Flask + Playwright).
**Scope**: 15 upgrades across server, posting engine, AI layer, and security.

---

## What We're Adopting and Why

We analyzed 2 complete codebases:
- **v2** (`Devtest-Dan/amplifire-v2`): NestJS + Prisma + Kotlin + Go. 53 models, 24 modules, 46 tests, PayPal payouts, real OAuth, encrypted storage. ~75% complete, shelved because paid AI costs killed unit economics.
- **v3** (`Devtest-Dan/AmpliFire-v3`): Kotlin-only Android app. Free AI via WebView, declarative JSON posting scripts, fallback selector chains, 3-tier reputation system. Phase 1 MVP complete.

We're NOT adopting their tech stacks — our FastAPI server and Playwright engine stay. We're adopting their **business logic, patterns, and architectural innovations** that solve problems we haven't solved yet.

---

## TIER 1: Critical Upgrades (Ship First)

These fix real gaps that would block production use.

---

### Upgrade 1: Declarative JSON Posting Scripts

**Source**: v3's `ScriptExecutor.kt` + `ScriptModel.kt` + `ScriptParser.kt` + JSON script files (`ig-post.json`, `x-post.json`)

**Problem in v1**: Platform posting is hardcoded in `scripts/post.py` as 6 monolithic Python functions (`post_to_x()`, `post_to_linkedin()`, etc.). Each is 150-200 lines of interleaved selectors, waits, and error handling. When a platform changes its UI, we edit Python code, test, and redeploy.

**What v3 does**: Each platform's posting flow is defined as a JSON file — a sequence of declarative steps:

```json
{
  "platform": "instagram",
  "action": "post_with_media",
  "version": "2026.03.11",
  "app_package": "com.instagram.android",
  "steps": [
    {
      "id": "open_app",
      "type": "launch",
      "package": "com.instagram.android",
      "wait_for": { "id": "com.instagram.android:id/tab_bar", "timeout_ms": 5000 }
    },
    {
      "id": "tap_create",
      "type": "click",
      "target": {
        "strategy": "fallback_chain",
        "selectors": [
          { "by": "content_desc", "value": "Create" },
          { "by": "content_desc", "value": "New post" },
          { "by": "id", "value": "com.instagram.android:id/creation_tab" }
        ]
      },
      "delay_before_ms": { "min": 400, "max": 900 },
      "wait_for": { "content_desc": "Gallery", "timeout_ms": 3000 }
    },
    {
      "id": "enter_caption",
      "type": "text_input",
      "target": {
        "strategy": "fallback_chain",
        "selectors": [
          { "by": "id", "value": "com.instagram.android:id/caption_text_view" },
          { "by": "text", "value": "Write a caption..." }
        ]
      },
      "text": "{{caption}}",
      "typing_speed": { "min": 30, "max": 90 }
    },
    {
      "id": "verify_posted",
      "type": "wait_and_verify",
      "success_signals": [
        { "text": "Your reel has been shared" },
        { "text": "Shared" }
      ],
      "timeout_ms": 10000
    }
  ],
  "error_recovery": {
    "on_element_not_found": "retry_with_next_selector",
    "on_unexpected_screen": "press_back_and_retry",
    "on_popup": "dismiss_and_continue",
    "max_retries": 3,
    "on_failure": "queue_for_manual"
  }
}
```

The `ScriptExecutor` reads JSON, iterates steps, and executes each action type (launch, click, text_input, media_select, wait_and_verify, scroll). Variable substitution replaces `{{caption}}`, `{{media_path}}`, `{{hashtags}}` at runtime.

**What we'll build**: A Python `ScriptExecutor` that reads JSON scripts and drives Playwright. Our step types map to Playwright:

| v3 Step Type | Our Playwright Equivalent |
|---|---|
| `launch` | `page.goto(url)` + `page.wait_for_selector()` |
| `click` | `page.locator(selector).click()` with fallback chain |
| `text_input` | Character-by-character `page.keyboard.type()` with random delays |
| `media_select` | `page.set_input_files()` or `expect_file_chooser` |
| `wait_and_verify` | `page.locator(signal).wait_for()` with timeout |
| `scroll` | `page.mouse.wheel()` or `page.evaluate('window.scrollBy()')` |

**Files created**: `scripts/engine/script_executor.py`, `scripts/engine/script_parser.py`, `config/scripts/x_post.json`, `config/scripts/linkedin_post.json`, `config/scripts/facebook_post.json`, `config/scripts/reddit_post.json`

**Files modified**: `scripts/post.py` (refactored to use script executor instead of hardcoded functions), `scripts/utils/post_scheduler.py` (calls script executor)

**Benefit**: When LinkedIn changes a button label, update one line in a JSON file. No Python changes, no testing the whole posting engine.

---

### Upgrade 2: Fallback Selector Chains

**Source**: v3's `NodeFinder.kt` — `findNode()` method that tries multiple selectors before failing

**Problem in v1**: Each platform function has single hardcoded selectors. When a selector breaks (platform UI update), the entire post fails immediately.

**What v3 does**: Every element has a `fallback_chain` — an ordered list of selectors. The finder tries each one until something matches:

```kotlin
fun findNode(root: AccessibilityNodeInfo?, target: SelectorTarget): AccessibilityNodeInfo? {
    val selectors = if (target.strategy == "fallback_chain") target.selectors
        else target.by?.let { listOf(Selector(it, target.value ?: "")) } ?: target.selectors
    for (selector in selectors) {
        val node = findBySelector(root, selector)
        if (node != null) return node  // First match wins
    }
    return null  // Fail only if ALL selectors miss
}
```

**What we'll build**: A `SelectorChain` class that wraps Playwright's `page.locator()`:

```python
class SelectorChain:
    def __init__(self, selectors: list[dict]):
        self.selectors = selectors  # [{"by": "css", "value": "button.post"}, ...]

    async def find(self, page, timeout=2000) -> Locator:
        for sel in self.selectors:
            try:
                locator = self._resolve(page, sel)
                await locator.wait_for(state="visible", timeout=timeout)
                return locator
            except TimeoutError:
                continue
        raise AllSelectorsFailedError(self.selectors)
```

Supports selector types: `css`, `text`, `role`, `testid`, `aria-label`, `xpath`. Integrated into the JSON script system (Upgrade 1).

**Benefit**: A single broken selector no longer kills posting. The chain catches 80%+ of minor UI changes without any config updates.

---

### Upgrade 3: Structured Error Recovery

**Source**: v3's `ScriptExecutor.kt` — per-script `error_recovery` config with retry strategies

**Problem in v1**: Posting functions use try/catch with generic error handling. If any step fails, the whole post fails. No retry logic, no popup dismissal, no graceful degradation.

**What v3 does**: Each JSON script has an `error_recovery` block defining strategies for different failure types:

```json
"error_recovery": {
    "on_element_not_found": "retry_with_next_selector",
    "on_unexpected_screen": "press_back_and_retry",
    "on_popup": "dismiss_and_continue",
    "max_retries": 3,
    "on_failure": "queue_for_manual"
}
```

The executor applies the appropriate strategy at each step:
- `retry_with_next_selector`: Move to next fallback selector
- `press_back_and_retry`: Navigate back, wait, retry the step
- `dismiss_and_continue`: Detect and close popups/modals, then retry
- `queue_for_manual`: After max retries, mark post as failed and notify user

v3's executor uses exponential backoff between retries: `delay(1000 * (2 ** attempt))`.

**What we'll build**: An `ErrorRecovery` class that the script executor calls on step failure:

```python
class ErrorRecovery:
    async def handle(self, page, step, error_type, attempt, config):
        strategy = config.get(f"on_{error_type}", "queue_for_manual")
        if strategy == "retry_with_next_selector":
            await asyncio.sleep(1.0 * (2 ** attempt))  # Exponential backoff
            return attempt < config.get("max_retries", 3)
        elif strategy == "dismiss_and_continue":
            await self._dismiss_popups(page)
            return True
        elif strategy == "press_back_and_retry":
            await page.go_back()
            await asyncio.sleep(2.0)
            return True
        else:
            return False  # Give up
```

**Benefit**: Catches ~30-40% of transient failures (popups, slow loads, temporary UI glitches) that currently kill posts. Failed posts get queued for manual intervention instead of silently lost.

---

### Upgrade 4: AES-256-GCM Encryption for Sensitive Data

**Source**: v2's `server/src/common/utils/crypto.util.ts`

**Problem in v1**: API keys, OAuth tokens, and payment details stored in plaintext in the database and config files.

**What v2 does**: AES-256-GCM authenticated encryption with separate IV and auth tag per value:

```typescript
// v2's crypto utility
export function encrypt(text: string): string {
    const iv = randomBytes(16);
    const key = deriveKey(process.env.ENCRYPTION_KEY, 'amplifire-salt');
    const cipher = createCipheriv('aes-256-gcm', key, iv);
    let encrypted = cipher.update(text, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    const authTag = cipher.getAuthTag();
    return `${iv.toString('hex')}:${authTag.toString('hex')}:${encrypted}`;
}

export function decrypt(encryptedText: string): string {
    const [ivHex, authTagHex, encrypted] = encryptedText.split(':');
    // ... reverse process with auth tag verification
}

export function isEncrypted(value: string): boolean {
    const parts = value.split(':');
    return parts.length === 3 && parts[0].length === 32;
}
```

Key features:
- Auth tag prevents tampering (GCM mode)
- `isEncrypted()` helper for migration — detect if a value is already encrypted before re-encrypting
- Key derived from env var, never hardcoded

**What we'll build**: `server/app/utils/crypto.py` using Python's `cryptography` library:

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os, hashlib

def encrypt(plaintext: str) -> str:
    key = _derive_key()
    iv = os.urandom(16)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode(), None)
    return f"{iv.hex()}:{ciphertext.hex()}"

def decrypt(encrypted: str) -> str:
    key = _derive_key()
    iv_hex, ct_hex = encrypted.split(":")
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(bytes.fromhex(iv_hex), bytes.fromhex(ct_hex), None).decode()

def is_encrypted(value: str) -> bool:
    parts = value.split(":")
    return len(parts) == 2 and len(parts[0]) == 32
```

**Applied to**: User API keys (Gemini, Mistral, Groq) stored in local settings, OAuth tokens if/when we add real OAuth, Stripe payment method IDs, any future bank account or PayPal data.

**Benefit**: Defense-in-depth. If the database is compromised, encrypted fields remain protected.

---

### Upgrade 5: Earning Hold Periods

**Source**: v2's `server/src/modules/earnings/earnings.service.ts` — 7-day hold with PENDING → AVAILABLE promotion

**Problem in v1**: Earnings are credited immediately on metric submission. If a creator deletes their post after the first metric scrape, we've already credited earnings for engagement that will disappear. No way to claw back.

**What v2 does**: Earnings go through a multi-state lifecycle:

```
PENDING (created on metric submission)
    ↓ 7 days pass
AVAILABLE (can be withdrawn)
    ↓ user requests payout
PROCESSING (payment in progress)
    ↓ payment confirms
PAID (done)

VOIDED (if fraud detected during hold period)
```

A background cron runs every 10 minutes to promote PENDING → AVAILABLE:

```typescript
// v2's earning promotion
@Cron(CronExpression.EVERY_10_MINUTES)
async promoteEarnings() {
    const holdDays = 7;
    const cutoff = new Date(Date.now() - holdDays * 86400000);
    
    const promoted = await this.prisma.earning.updateMany({
        where: { status: 'PENDING', earnedAt: { lte: cutoff } },
        data: { status: 'AVAILABLE' },
    });
}
```

**What we'll build**: Add `status` and `available_at` fields to the Payout model:

```python
# Updated Payout model
class Payout(Base):
    # ... existing fields ...
    status = Column(String(20), default="pending")  # pending → available → processing → paid → voided
    available_at = Column(DateTime(timezone=True))   # earned_at + 7 days
```

Billing service sets `available_at = now() + 7 days` when creating payout. Background task promotes pending → available. Withdrawal endpoint only considers `status='available'` earnings.

Fraud detection during the hold period can void earnings before they become available — this is the whole point. If the trust system detects post deletion within 24h, the associated earnings get voided instead of paid out.

**Benefit**: 7-day fraud window. If a creator games metrics or deletes posts, earnings are voided before payout. Dramatically reduces financial risk.

---

### Upgrade 6: Human-Like Timing Engine

**Source**: v3's `HumanLikeTiming.kt`

**Problem in v1**: We already have `human_delay()` and `human_type()` functions in `post.py`, but they're basic — fixed ranges, no per-step configuration, no typing speed variation.

**What v3 does**: Configurable per-step timing with randomized ranges:

```kotlin
object HumanLikeTiming {
    suspend fun randomDelay(range: DelayRange?) {
        if (range == null) return
        val ms = Random.nextInt(range.min, range.max + 1).toLong()
        delay(ms)
    }

    suspend fun typeText(node: AccessibilityNodeInfo, text: String) {
        val sb = StringBuilder()
        for (char in text) {
            sb.append(char)
            node.performAction(ACTION_SET_TEXT, Bundle().apply { putString(key, sb.toString()) })
            delay(Random.nextLong(30, 120))  // 30-120ms per character
        }
    }
}
```

Each JSON script step has its own `delay_before_ms: { "min": 400, "max": 900 }` and `typing_speed: { "min": 30, "max": 90 }`. Different steps simulate different human behaviors:
- Clicking a button: 300-700ms pause (scanning UI)
- Starting to type: 500-1500ms pause (thinking about what to write)
- After uploading image: 1000-3000ms pause (reviewing the image)
- After clicking post: 800-2000ms pause (double-checking)

**What we'll build**: Integrate per-step timing config into the script executor. The JSON scripts already define `delay_before_ms` and `typing_speed` per step — the executor reads and applies them. This replaces our current flat `human_delay(min, max)` calls.

**Benefit**: More realistic automation behavior. Per-step timing tuned to each action type reduces detection risk.

---

## TIER 2: High-Value Upgrades (Ship Next)

These add significant capability but aren't blocking production.

---

### Upgrade 7: Content Post Lifecycle State Machine

**Source**: v2's `server/src/modules/content-posts/content-posts.service.ts`

**Problem in v1**: Our `post_schedule` table has basic status tracking (`queued`, `posting`, `posted`, `failed`) but lacks retry logic, error categorization, and debugging metadata.

**What v2 does**: Full lifecycle with retries and rich metadata:

```
QUEUED → POSTING → POSTED (success)
                 → FAILED → RETRYING → POSTED (retry success)
                                     → FAILED (final failure after max retries)
```

Each post record stores:
- `retryCount` / `maxRetries` (default 3)
- `errorCode` + `errorMessage` (categorized: SELECTOR_FAILED, TIMEOUT, AUTH_EXPIRED, RATE_LIMITED)
- `automationLog` (step-by-step execution trace)
- `platformPostId` (platform's native ID for the post)
- `platformUrl` (direct URL to the post on the platform)
- `screenshotUrl` (proof of posting)
- `postedAt` (exact timestamp of successful post)

The retry logic: on failure, status goes to RETRYING, retry_count increments, and the post re-enters the queue with exponential backoff delay.

**What we'll build**: Extend our `post_schedule` table with these fields and add retry logic to `execute_scheduled_post()`. The background agent already checks for failed posts — we'll enhance it to implement the retry state machine with categorized errors.

**Benefit**: Failed posts automatically retry instead of requiring manual intervention. Error categorization tells us whether to retry (timeout) or alert the user (auth expired).

---

### Upgrade 8: Tracking Links with Click Analytics

**Source**: v2's `server/src/modules/tracking/tracking.service.ts`

**Problem in v1**: We track post URLs and engagement metrics, but we have no way to measure if a post actually drives traffic to the company's website. Companies want to see click-through rates and conversions, not just likes.

**What v2 does**: Generates short tracking URLs for each post. When someone clicks the link, it's recorded before redirecting:

```typescript
// v2's tracking link generation
async createLink(contentPostId: string, originalUrl: string): Promise<TrackingLink> {
    const shortCode = this.generateShortCode();  // 6-char base64
    return this.prisma.trackingLink.create({
        data: {
            contentPostId,
            originalUrl,
            shortUrl: `${process.env.TRACKING_BASE_URL}/${shortCode}`,
            shortCode,
        }
    });
}

// Redirect handler
async handleClick(shortCode: string, req: Request): Promise<string> {
    const link = await this.prisma.trackingLink.findUnique({ where: { shortCode } });
    // Record click event
    await this.prisma.trackingEvent.create({
        data: {
            trackingLinkId: link.id,
            eventType: 'LINK_CLICK',
            ipAddress: req.ip,
            userAgent: req.headers['user-agent'],
            deviceType: this.detectDevice(req),
            country: this.geolocate(req.ip),
        }
    });
    // Increment counter
    await this.prisma.trackingLink.update({
        where: { id: link.id },
        data: { clickCount: { increment: 1 } },
    });
    return link.originalUrl;  // Redirect
}
```

**New models**:
- `TrackingLink`: id, content_post_id, short_code (unique, 6 chars), original_url, short_url, click_count, expires_at
- `TrackingEvent`: id, tracking_link_id, event_type (LINK_CLICK, CONVERSION), ip_address, user_agent, device_type, country, conversion_value

**What we'll build**: New server models + API endpoints (POST /api/tracking/links, GET /t/{short_code} redirect, GET /api/tracking/links/{id}/analytics). The content generator will embed tracking links in post content when the campaign includes company URLs.

**Benefit**: Companies see actual click-through data per creator per platform. This is the metric that justifies their spend — "your $500 campaign drove 2,340 clicks to your product page."

---

### Upgrade 9: Notifications System

**Source**: v2's `server/src/modules/notifications/notifications.service.ts`

**Problem in v1**: The user app has a basic `local_notification` table for desktop notifications, but there's no server-side notification system. Users don't get notified when earnings are credited, when campaigns are cancelled, or when payouts complete.

**What v2 does**: Typed notifications with multi-channel delivery:

```typescript
// v2's notification types
enum NotificationType {
    EARNING = 'EARNING',                   // "$X earned from your post"
    PAYOUT = 'PAYOUT',                     // "Payout of $X processed"
    CONTENT_APPROVED = 'CONTENT_APPROVED', // "Your content was approved"
    CONTENT_POSTED = 'CONTENT_POSTED',     // "Posted to Instagram"
    APPROVAL_NEEDED = 'APPROVAL_NEEDED',   // "Review your campaign content"
    SUBSCRIPTION = 'SUBSCRIPTION',         // "Your plan renews in 3 days"
    REFERRAL = 'REFERRAL',                 // "Someone joined with your code"
    SYSTEM = 'SYSTEM',                     // "Maintenance window tonight"
    PROMO = 'PROMO',                       // "New campaign matches you!"
}

enum NotificationChannel {
    PUSH = 'PUSH',       // FCM push notification
    EMAIL = 'EMAIL',     // Email via SendGrid/SMTP
    IN_APP = 'IN_APP',   // In-app notification bell
}
```

Each notification has: `type`, `title`, `body`, `data` (JSON metadata like amount, campaign name), `channels` (which delivery methods), `isRead`, `readAt`, `sentAt`.

v2 calls notification service from billing (EARNING), payout processing (PAYOUT), content posting (CONTENT_POSTED), and matching (APPROVAL_NEEDED).

**What we'll build**: 
- Server model: `Notification` (user_id, type, title, body, data JSON, is_read, created_at)
- Server endpoints: GET /api/users/me/notifications, PATCH /api/users/me/notifications/{id}/read, POST /api/users/me/notifications/read-all
- Triggered from: billing (new earnings), payout processing (payout status), campaign matching (new invitations), trust system (penalties)
- User app: poll notifications endpoint, show in dashboard alerts section

**Benefit**: Users know what's happening without checking the app. New earnings, payout confirmations, and campaign invitations surface immediately.

---

### Upgrade 10: Payout Processing Automation

**Source**: v2's `server/src/modules/payouts/payout-processing.service.ts`

**Problem in v1**: Our payout cycle (`payments.py:run_payout_cycle()`) is a stub. It finds pending payouts but doesn't actually send money. An admin has to manually process each one.

**What v2 does**: Automated PayPal payout cron:

```typescript
// v2's payout processing (runs every 5 minutes)
@Cron('*/5 * * * *')
async processPayouts() {
    const pending = await this.prisma.payout.findMany({
        where: { status: 'PENDING' },
        include: { user: { include: { paymentMethods: true } } },
    });

    for (const payout of pending) {
        const method = payout.user.paymentMethods.find(m => m.isDefault);
        if (!method) continue;

        // Mark as PROCESSING
        await this.prisma.payout.update({
            where: { id: payout.id },
            data: { status: 'PROCESSING' },
        });

        // Send via PayPal Payouts API
        const result = await this.sendPayPalPayout(payout, method);
        
        if (result.success) {
            await this.prisma.payout.update({
                where: { id: payout.id },
                data: { 
                    status: 'COMPLETED',
                    processorRef: result.batchId,  // PayPal batch ID for tracking
                    processedAt: new Date(),
                },
            });
        } else {
            await this.prisma.payout.update({
                where: { id: payout.id },
                data: { 
                    status: 'FAILED',
                    failureReason: result.error,
                },
            });
            // Return funds to user's available balance
        }
    }
}
```

A separate cron checks PayPal batch status every 30 minutes for PROCESSING payouts (PayPal batches can take time to settle).

**What we'll build**: Complete the `payments.py` implementation with actual Stripe Connect transfers (our existing Stripe integration) and add a background task to process pending payouts. State machine: PENDING → PROCESSING → COMPLETED/FAILED. On failure, funds return to user's available balance.

**Benefit**: Payouts happen automatically. No admin intervention for routine cash-outs.

---

### Upgrade 11: AI Provider Abstraction Layer

**Source**: v3's `AiProvider.kt` interface + `AiManager.kt` registry + `AiProviderConfig.kt` config

**Problem in v1**: Our `content_generator.py` has the provider fallback chain baked in — the Gemini/Mistral/Groq logic is interleaved with prompt construction and output parsing. Adding a new provider means editing a 560-line file.

**What v3 does**: Clean provider interface with pluggable implementations:

```kotlin
interface AiProvider {
    val name: String
    val isConnected: Boolean
    val isRateLimited: Boolean
    suspend fun generate(prompt: String): Result<String>
    fun openLoginPage()
}

@Singleton
class AiManager {
    private val providers = mutableMapOf<String, AiProvider>()
    
    fun registerProvider(provider: AiProvider) {
        providers[provider.name] = provider
    }
    
    fun getDefaultProvider(): AiProvider? =
        providers.values.firstOrNull { it.isConnected && !it.isRateLimited }
            ?: providers.values.firstOrNull { it.isConnected }
    
    suspend fun generate(prompt: String, preferredProvider: String? = null): Result<String> {
        val provider = preferredProvider?.let { getProvider(it) } ?: getDefaultProvider()
        return provider?.generate(prompt) ?: Result.failure(Exception("No AI provider available"))
    }
}
```

Each provider (Gemini, Copilot, ChatGPT, DeepSeek) implements the same interface. The manager picks the best available one (connected + not rate-limited), with explicit fallback.

v3 also stores provider selectors in config, not code:

```kotlin
data class AiProviderConfig(
    val name: String,
    val url: String,
    val inputSelector: String,
    val submitSelector: String,
    val responseSelector: String,
    val rateLimitSelector: String,
    val loginDetectUrl: String,
    val sessionCheckSelector: String
)
```

**What we'll build**: Refactor `content_generator.py` into:
- `scripts/ai/provider.py` — Abstract `AiProvider` base class with `generate()`, `is_connected`, `is_rate_limited`
- `scripts/ai/gemini_provider.py`, `scripts/ai/mistral_provider.py`, `scripts/ai/groq_provider.py` — Concrete implementations
- `scripts/ai/manager.py` — `AiManager` with provider registry, auto-fallback, rate limit tracking
- Prompt construction stays in `content_generator.py` but calls `ai_manager.generate()` instead of inline API calls

**Benefit**: Clean separation. Adding a new AI provider = one new file implementing the interface. Rate limit tracking per provider enables smarter fallback.

---

### Upgrade 12: Money Stored as Integer Cents

**Source**: v2's convention — all amounts stored as integers (cents), never floats

**Problem in v1**: We use `Numeric(12,2)` for money fields (budget_total, budget_remaining, earnings_balance, payout amounts). While Numeric avoids float precision issues, integer cents is the industry standard and eliminates any rounding concerns.

**What v2 does**: All money is cents:
```typescript
// v2: $25.50 stored as 2550
earning.amountCents = Math.round(viewDelta / 1000 * cpmRateCents);
```

Display formatting happens only at the API response layer (`amountCents / 100`).

**What we'll build**: Add `_cents` integer columns alongside existing Numeric columns, migrate data, then drop the old columns. All new financial logic uses cents. API responses format to dollars for display.

**Benefit**: Eliminates any possibility of floating-point rounding in financial calculations. Consistent with Stripe (which operates in cents).

---

## TIER 3: Future Upgrades (Backlog)

These add value but depend on Tier 1-2 being in place.

---

### Upgrade 13: Config-as-Data for AI Provider Selectors

**Source**: v3's `AiProviderConfig.kt` + `ProviderConfigs` object

**Problem**: If we ever adopt v3's WebView-based free AI approach (Playwright navigating gemini.google.com instead of calling the API), the selectors for interacting with the web UI need to be configurable — Gemini changes its UI monthly.

**What v3 does**: All selectors in a config object:
```kotlin
val GEMINI = AiProviderConfig(
    inputSelector = """.ql-editor[contenteditable], [role="textbox"], rich-textarea .ql-editor""",
    submitSelector = """button[aria-label="Send message"], button.send-button""",
    responseSelector = """message-content .markdown, .response-container .markdown""",
    rateLimitSelector = ".error-message, .rate-limit-banner",
)
```

**What we'd build**: A `config/ai_providers.json` file with per-provider selector configs. The WebView AI provider reads from config instead of hardcoding selectors.

**Applicability**: Only matters if we add WebView-based AI as a fallback (relevant when free API tiers get restricted). Low priority for now since our API-based approach works.

---

### Upgrade 14: Three-Tier Reputation System

**Source**: v3's design spec — Seedling / Grower / Amplifier tiers

**Problem in v1**: We have a flat trust score (0-100) that affects campaign priority but doesn't gate features or change earning rates. There's no progression system to incentivize good behavior.

**What v3 designs**:

| Tier | Name | Unlock Criteria | Capabilities | CPM Rate |
|---|---|---|---|---|
| 1 | Seedling | Default (new user) | Full approval required on every post. Max 3 campaigns. 30% of posts spot-checked. | Standard |
| 2 | Grower | 20 successful posts | Auto-post toggle available. Max 10 campaigns. 10% spot-checked. | Standard |
| 3 | Amplifier | 100 posts + 4.5-star rating | Full auto unlocked. Unlimited campaigns. 5% spot-checked. Priority matching. | 2x premium |

Tier demotion on fraud. Tier affects matching priority (higher tier = matched first for premium campaigns).

**What we'd build**: Add `tier` field to User model (SEEDLING/GROWER/AMPLIFIER), `successful_post_count` counter, tier promotion logic in billing service (after each successful post), tier-gated features in the user app (auto-post only for Grower+), tier-based CPM multiplier in billing.

**Applicability**: Matters once we have enough users that differentiation drives behavior. Not needed for launch.

---

### Upgrade 15: Server-Side Metrics Cron

**Source**: v2's `server/src/modules/metrics/metrics-sync.service.ts`

**Problem in v1**: Metric collection is entirely client-side (the user's Playwright scrapes engagement from platform pages). If the user's app is offline, metrics stop. The server has no independent way to verify metric accuracy.

**What v2 does**: Hourly server-side cron fetches metrics from platform APIs:

```typescript
@Cron(CronExpression.EVERY_HOUR)
async syncMetrics() {
    const posts = await this.prisma.contentPost.findMany({
        where: {
            status: 'POSTED',
            platformPostId: { not: null },
            postedAt: { lt: new Date(Date.now() - 5 * 60000) },  // >5min old
        },
    });

    for (const batch of chunk(posts, 10)) {
        await Promise.all(batch.map(post => this.syncPostMetrics(post)));
        await sleep(1000);  // Rate limit between batches
    }
}
```

Uses platform-specific metric providers (TikTok API, Instagram Insights API, YouTube Analytics API) with a provider-agnostic interface.

**What we'd build**: Server-side metric collection using platform APIs (requires OAuth tokens stored securely — Upgrade 4). Runs as a background task. Cross-validates against client-reported metrics. Flags discrepancies for fraud detection.

**Applicability**: Requires real platform OAuth first. Medium-term priority. Currently our client-side scraping works but can't be independently verified.

---

## Implementation Sequence

```
PHASE 1 — Posting Engine Hardening (Upgrades 1-3, 6)
├── 1. Build ScriptExecutor + ScriptParser
├── 2. Create JSON scripts for X, LinkedIn, Facebook, Reddit
├── 3. Implement SelectorChain with fallback logic
├── 4. Add ErrorRecovery with retry strategies
├── 5. Integrate per-step HumanLikeTiming
└── 6. Refactor post.py to use script executor

PHASE 2 — Financial Safety (Upgrades 4-5, 12)
├── 7. Build crypto.py (AES-256-GCM)
├── 8. Encrypt sensitive data in local DB and server
├── 9. Add earning hold periods (7-day PENDING → AVAILABLE)
├── 10. Migrate money fields to integer cents
└── 11. Update billing service for new earning lifecycle

PHASE 3 — Automation & Intelligence (Upgrades 7, 10-11)
├── 12. Extend post lifecycle with retry states + error categorization
├── 13. Implement payout processing automation
└── 14. Refactor content_generator into AiManager + providers

PHASE 4 — User Experience (Upgrades 8-9)
├── 15. Build tracking link system (server model + redirect endpoint)
└── 16. Build notifications system (server model + API + user app polling)

PHASE 5 — Growth Features (Upgrades 13-15, backlog)
├── 17. Config-as-data for AI selectors
├── 18. Three-tier reputation system
└── 19. Server-side metrics cron
```

---

## Files Affected Summary

### New Files
| File | Purpose |
|---|---|
| `scripts/engine/script_executor.py` | Declarative JSON script runner for Playwright |
| `scripts/engine/script_parser.py` | JSON parsing + variable substitution |
| `scripts/engine/selector_chain.py` | Fallback selector chain for Playwright locators |
| `scripts/engine/error_recovery.py` | Per-script error recovery strategies |
| `scripts/engine/human_timing.py` | Per-step configurable human-like delays |
| `scripts/ai/provider.py` | Abstract AiProvider base class |
| `scripts/ai/gemini_provider.py` | Gemini API implementation |
| `scripts/ai/mistral_provider.py` | Mistral API implementation |
| `scripts/ai/groq_provider.py` | Groq API implementation |
| `scripts/ai/manager.py` | AiManager with registry + auto-fallback |
| `config/scripts/x_post.json` | X/Twitter posting script |
| `config/scripts/linkedin_post.json` | LinkedIn posting script |
| `config/scripts/facebook_post.json` | Facebook posting script |
| `config/scripts/reddit_post.json` | Reddit posting script |
| `server/app/utils/crypto.py` | AES-256-GCM encrypt/decrypt |
| `server/app/models/tracking.py` | TrackingLink + TrackingEvent models |
| `server/app/models/notification.py` | Notification model |
| `server/app/routers/tracking.py` | Tracking link API + redirect |
| `server/app/routers/notifications.py` | Notification API endpoints |

### Modified Files
| File | Changes |
|---|---|
| `scripts/post.py` | Refactored to use ScriptExecutor instead of hardcoded platform functions |
| `scripts/utils/post_scheduler.py` | Calls ScriptExecutor, adds retry lifecycle |
| `scripts/utils/content_generator.py` | Refactored to use AiManager |
| `scripts/background_agent.py` | Adds earning promotion task, payout processing task |
| `server/app/models/payout.py` | Add status lifecycle (pending/available/processing/paid/voided), available_at |
| `server/app/models/__init__.py` | Register new models |
| `server/app/services/billing.py` | Set earning hold period, integer cents |
| `server/app/services/payments.py` | Complete Stripe Connect payout processing |
| `server/app/main.py` | Register new routers (tracking, notifications) |
| `scripts/utils/local_db.py` | Add retry fields to post_schedule, encrypt API keys |

---

## What We're NOT Adopting

| v2/v3 Feature | Why Not |
|---|---|
| NestJS + Prisma stack | Our FastAPI server works and is deployed. No reason to rewrite. |
| v2's 53-model Prisma schema | Over-engineered for current scale. We'll adopt patterns, not the schema. |
| v2's Go PicoClaw agent | Replaced by v3's free WebView approach and our API-based approach. |
| v2's paid OpenAI pipeline | The reason v2 was shelved. We use free APIs. |
| v2's Redis cache | Not needed until we hit scale issues. SQLite/PostgreSQL handles current load. |
| v2's Google OAuth | Useful later, but not blocking. Email/password auth works for now. |
| v3's Android Accessibility Service | We're desktop-first (Playwright). Android is Dan's domain. |
| v3's WebView AI scraping | Our API-based AI works and is more reliable. WebView is a future fallback option. |
| v3's 3-process architecture | Android-specific (app/ai/engine process split). Not applicable to desktop. |
| v3's Room DB | We already have SQLite with a more complete schema. |
