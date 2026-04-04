# Amplifier User App — Gap Analysis Backlog

> Generated 2026-04-02. Items marked DONE were fixed in the same session.
> Items below are organized by priority tier for future implementation.

---

## DONE (Fixed 2026-04-02)

- [x] **Metrics never marked final** — `is_final` hardcoded to `False` in scraping logic. Billing only processes final metrics. Users can't get paid.
- [x] **Silent agent failures** — Agent errors logged but never surfaced. Dashboard has no activity feed or alerts.
- [x] **Assignment status out of sync** — Company cancels campaign, user's local status stays `accepted`. User keeps posting for dead campaigns.
- [x] **Failed posts never retried** — Transient failures permanently kill posts. No retry mechanism.
- [x] **XSS in campaign briefs** — Audit all `|safe` filter usage in user app templates. Campaign data could contain scripts.
- [x] **Platform login not verified during onboarding** — Browser opens, user closes without logging in, onboarding marks as connected.
- [x] **No content regeneration** — If user rejects all drafts, stuck until tomorrow. No regenerate button.

---

## HIGH PRIORITY — Fix Before Public Launch

### Authentication & Security
- [ ] **No password reset flow** — Users locked out permanently if they forget password. Add email-based reset with time-limited tokens.
- [ ] **No CSRF protection** — Flask forms don't use CSRF tokens. Add `flask-wtf` or manual CSRF tokens to all POST forms.
- [ ] **Auth tokens stored unencrypted** — `server_auth.json` has plaintext JWT. Encrypt at rest or use OS keychain.
- [ ] **No rate limiting on auth endpoints** — Login/register vulnerable to brute force. Add rate limiting (e.g., 5 attempts per minute).
- [ ] **API keys stored in plaintext** — Gemini/Mistral/Groq keys in local SQLite unencrypted. Use OS keychain or encrypted storage.
- [ ] **No API key validation on save** — User can paste invalid key, content gen fails silently. Test key on save.

### Dashboard & Visibility
- [ ] **No campaign search/filter** — All campaigns loaded as flat list. Add search by title, filter by status.
- [ ] **Dashboard stats incomplete** — Missing: pending earnings, next scheduled post, agent running/stopped indicator.
- [ ] **Platform health is binary** — Shows connected/not but not session validity or auth expiry. Add session health check display.

### Content & Drafts
- [ ] **Content guidance not shown during review** — User reviews draft without seeing campaign's content guidance. Show it alongside.
- [ ] **No draft versioning** — Can't compare AI-generated vs user-edited. Store original + edited versions.
- [ ] **Reddit content format fragile** — JSON `{title, body}` parsing has no error handling. Add try/except with fallback.
- [ ] **No character count for all platforms** — Only X has char limit. Add LinkedIn (3000), Facebook (63206), Reddit (40000) limits.

### Posting
- [ ] **No preview before posting** — Approved drafts go straight to scheduler. Add "preview exactly what will be posted" step.
- [ ] **No edit after approval** — Must unapprove, edit, re-approve (loses schedule). Allow inline edit of approved drafts.
- [ ] **Platform logout not detected immediately** — App keeps trying for 30 min. Check session before each post attempt.
- [ ] **No duplicate post detection** — Fast double-click could approve same draft twice. Add dedup check.

### Invitation Flow
- [ ] **No expiry countdown** — Show countdown timer ("expires in 2h 15m") instead of raw timestamp.
- [ ] **Expired invitations not clearly marked** — Add "EXPIRED" badge and gray out expired invitations.
- [ ] **No decline reason feedback** — Capture optional reason when user rejects. Send to company.

### Onboarding
- [ ] **Niche selection not required** — User can skip. Require at least 1 niche for campaign matching to work.
- [ ] **Multiple platform connections not explained** — Add brief explanation of what each platform enables.

---

## MEDIUM PRIORITY — Post-Launch Improvements

### Data Integrity
- [ ] **No local database backup** — If `local.db` corrupts, all data lost. Add periodic backup to a second file.
- [ ] **Drafts not synced to server** — Laptop crash after approval loses the draft. Sync approved drafts to server.
- [ ] **No transaction support** — SQLite operations not wrapped in transactions. Crash could leave inconsistent state.
- [ ] **Campaign data gets stale** — Local cache outdated when company updates brief/rates. Check `campaign_version` on detail view.

### Settings
- [ ] **Follower counts are manual** — Auto-populate from scraped profile data instead of manual entry.
- [ ] **Mode toggle not granular** — Allow per-platform auto/manual mode (e.g., auto on X, manual on LinkedIn).
- [ ] **Settings not synced on startup** — Verify local settings match server record on login.

### Metric Collection
- [ ] **No manual metric entry** — If scraper fails, no fallback. Add manual input form for impressions/likes/reposts.
- [ ] **Metric scraper fragile** — CSS selectors break on platform updates. Add selector version checking and fallback.
- [ ] **Profile scraping only every 7 days** — Reduce to 3 days or add manual refresh button.
- [ ] **Scraped profile data never displayed** — LinkedIn data (location, about, experience) stored but not shown in UI.

### Performance
- [ ] **Campaign list not paginated** — `get_all_posts()` loads ALL posts. Add server-side pagination.
- [ ] **No caching of campaign/profile data** — Every page load re-fetches. Add TTL cache (5 min).
- [ ] **Metric scraping blocks agent loop** — Limit concurrent Playwright instances to 2-3.
- [ ] **Image generation synchronous** — Generate images in parallel per platform.
- [ ] **Static assets not versioned** — Add cache-busting query params to CSS/JS.

### UX/UI
- [ ] **Confusing status names** — Rename: `pending_invitation` → "Invited", `content_generated` → "Draft Ready", etc.
- [ ] **No "copy to clipboard" for post URLs** — Add copy button next to URLs.
- [ ] **Mobile experience broken** — Templates use fixed widths. Add responsive breakpoints.
- [ ] **Form validation server-side only** — Add client-side validation (required fields, min values).
- [ ] **No print/export** — Add CSV export for campaigns, posts, and earnings.

### Integration
- [ ] **Post deduplication not enforced** — Server should reject duplicate post URLs.
- [ ] **Invitation expiry not validated client-side** — Warn user when approaching deadline (< 2 hours).
- [ ] **No conflict detection** — Warn if accepting campaigns with overlapping platform requirements.

---

## LOW PRIORITY — Future Releases

### Compliance & Privacy
- [ ] **No Terms of Service acceptance** — Add ToS checkbox on registration.
- [ ] **No privacy policy** — Create and link privacy policy document.
- [ ] **No GDPR compliance** — Add data export and account deletion features.
- [ ] **No account deletion** — Add "Delete my account" in settings.

### Accessibility
- [ ] **No ARIA labels** — Add proper accessibility attributes to all interactive elements.
- [ ] **Color contrast failures** — Audit and fix WCAG contrast ratios.
- [ ] **No keyboard navigation** — Add tab order and keyboard shortcuts.
- [ ] **Form labels not associated** — Add `<label for="">` to all form inputs.

### Advanced Features
- [ ] **No custom posting schedule** — Let users set preferred posting times per platform.
- [ ] **No bulk operations** — Bulk accept/reject invitations, bulk approve/reject drafts.
- [ ] **No agent pause/resume** — Add dashboard controls for the background agent.
- [ ] **No granular task control** — Toggle individual agent tasks (scraping, posting, polling).
- [ ] **No follower growth tracking** — Store historical follower data and show trends.
- [ ] **No engagement rate trends** — Track engagement performance over time.
- [ ] **No preview of generated content before accepting campaign** — Show sample content.

### Testing
- [ ] **No E2E tests** — Full flow: login → onboard → accept → generate → approve → post → scrape → earn.
- [ ] **No unit tests** — Core logic (scraping, generation, scheduling) untested.
- [ ] **No mock server** — Can't test without real server running. Add mock fixtures.
- [ ] **No load testing** — Unknown scaling behavior with 1000+ users and 100K posts.
