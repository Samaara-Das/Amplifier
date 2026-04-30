# Background Agent Reference

The background agent is an always-running asyncio process that automates campaign polling, content generation, scheduled posting, metric scraping, session health checks, and profile refreshing.

**Source file**: `scripts/background_agent.py`

---

## Architecture

The agent is a singleton `BackgroundAgent` instance stored at module level (`_agent`). It runs as an `asyncio.Task` within the app's event loop. The main loop sleeps 60 seconds between iterations. Each iteration checks which tasks are due based on elapsed time since their last run.

Individual task failures are caught and logged but never crash the agent loop.

### Lifecycle

```python
# Start
agent = await start_background_agent()  # Creates BackgroundAgent + asyncio.Task

# Pause/Resume (tasks stop executing but loop keeps running)
agent.pause()
agent.resume()

# Stop (signals loop exit, waits 5s for current iteration, then cancels)
await stop_background_agent()
```

`start_background_agent()` guards against double-start: if an agent is already running, it returns the existing instance.

`stop_background_agent()` sets `running = False`, then waits up to 5 seconds for the current iteration to finish. If it doesn't finish in time, the task is cancelled.

---

## Task Schedule

| Task | Function | Interval | Runs On |
|------|----------|----------|---------|
| Execute due posts | `execute_due_posts()` | 60s (every iteration) | Every loop tick |
| Metric scraping | `run_metric_scraping()` | 60s (every iteration) | Every loop tick |
| Content generation (text + images) | `generate_daily_content()` | 120s (2 min) | `now - last_content_gen >= 120` |
| Campaign polling | `poll_campaigns()` | 600s (10 min) | `now - last_poll >= 600` |
| Session health check | `check_sessions()` | 1800s (30 min) | `now - last_health_check >= 1800` |
| Profile refresh | `refresh_profiles()` | 604800s (7 days) | `now - last_profile_refresh >= 604800` |
| Local DB backup | `backup_local_db()` | 21600s (6h) | `now - last_db_backup >= 21600` (Task #23, added 2026-04-30) |

All `last_*` timestamps start at `0.0`, so every task runs on the first iteration.

---

## Task Details

### `poll_campaigns()`

**Interval**: Every 10 minutes.

Calls `server_client.poll_campaigns()` to fetch campaigns from the server. For each campaign:
- If not in local DB: inserts via `upsert_campaign()` and increments the new count.
- If already exists: updates the campaign data but preserves the local status (prevents re-polling from resetting progress).

**Returns**: `{"success": bool, "total": int, "new": int}`

**Error handling**: Entire function wrapped in try/except. On failure, returns `{"success": False, "error": str}`.

---

### `generate_daily_content()`

**Interval**: Every 2 minutes (checks if generation is needed).

Generates per-platform content for all active campaigns that don't have today's drafts yet.

**Flow**:
1. Gets all campaigns with status in `(assigned, accepted, content_generated, approved, posted, active)`.
2. For each campaign, checks if today's drafts exist for all 4 platforms (x, linkedin, facebook, reddit).
3. If any platform is missing today's draft:
   - Collects previous draft hooks (last 12) for anti-repetition.
   - Calculates day number from unique draft dates.
   - Calls `ContentAgent.generate()` (4-phase pipeline: Research → Strategy → Creation → Review). Falls back to `ContentGenerator.generate()` if the pipeline fails.
   - **Image generation**: If the campaign has product images, downloads them and uses `ImageManager` for img2img generation (product image as base). Otherwise, generates images via txt2img from the campaign brief. The resulting `image_path` is stored on each draft.
   - **Daily image rotation**: `_pick_daily_image()` selects which campaign product image to use as the base, rotating through available images across days.
   - Stores drafts in `agent_draft` table.
   - Sends a desktop notification ("Content Ready for Review").
   - Updates campaign status to `content_generated` if it was `assigned`.
4. In `full_auto` mode: auto-approves all drafts and schedules them with 30-minute spacing (starting 5 minutes from now, with 0-10 minute random jitter per post). The `image_path` from the draft is passed through to the scheduled post.

**Returns**: `{"success": bool, "generated": int}`

**Error handling**: Per-campaign try/except. One campaign failing doesn't prevent others from being processed.

---

### `execute_due_posts()`

**Interval**: Every 60 seconds (every iteration).

Checks the `post_schedule` table for posts with `status = 'queued'` whose `scheduled_at` time has passed.

**Flow**:
1. Calls `get_due_posts()` to find queued posts that are due.
2. Immediately marks all due posts as `status = 'posting'` to prevent the next loop iteration from picking them up again (prevents duplicate posts).
3. Executes each post via `execute_scheduled_post(post_id)`.
4. After execution, syncs successful posts to the server via `report_posts()` and marks them as synced.

**Returns**: `{"success": bool, "executed": int, "succeeded": int, "failed": int, "failure_details": [{"platform": str, "error": str}]}`

**Error handling**: Per-post try/except. Failed posts are logged with platform and error details. Server sync failures are logged but don't affect the result.

---

### `run_metric_scraping()`

**Interval**: Every 60 seconds (every iteration).

Delegates to `metric_scraper.scrape_all_posts()` which internally decides which posts need scraping based on their age and scraping schedule. After scraping, calls `sync_metrics_to_server()` to report metrics.

**Returns**: `{"success": bool}` or `{"success": False, "error": str}`

**Error handling**: Single try/except around both scrape and sync operations.

---

### `check_sessions()`

**Interval**: Every 30 minutes.

Calls `session_health.check_all_sessions()` to verify that browser sessions for all connected platforms are still valid (not expired).

**Returns**: `{"success": bool, "platforms": {"x": {"status": "green"}, "linkedin": {"status": "red"}, ...}}`

Session statuses:
- `green` -- session is valid
- `red` -- session has expired (triggers a `session_expired` notification)

**Error handling**: Single try/except. Returns empty platforms dict on failure.

---

### `refresh_profiles()`

**Interval**: Every 7 days.

Re-scrapes all connected platform profiles if they are stale (older than 7 days).

**Flow**:
1. Gets all scraped profiles from `local_db.get_all_scraped_profiles()`.
2. Checks each profile's `scraped_at` timestamp against the 7-day threshold.
3. If no profiles exist at all, scrapes all enabled platforms.
4. Calls `profile_scraper.scrape_all_profiles()` for stale platforms.
5. Syncs updated profiles to the server via `sync_profiles_to_server()`.

**Returns**: `{"success": bool, "refreshed": int, "skipped": bool}`

**Error handling**: Server sync failure is a warning (doesn't fail the task). Main function wrapped in try/except.

---

## Notification System

After each iteration, the agent builds notifications from task results and stores them.

### Notification Types

| Type | Trigger | Example Message |
|------|---------|-----------------|
| `new_campaigns` | `poll_campaigns()` returned `new > 0` | "You have 3 new campaign invitations" |
| `post_published` | `execute_due_posts()` had `succeeded > 0` | "Successfully posted to 2 platforms" |
| `post_failed` | `execute_due_posts()` had `failed > 0` | "Failed to post to linkedin: element not found" (one notification per failure) |
| `session_expired` | `check_sessions()` found a platform with `status == "red"` | "Your linkedin session has expired. Re-authenticate to continue posting." |
| `profile_refreshed` | `refresh_profiles()` had `refreshed > 0` | "Refreshed 3 platform profiles" |

### Storage

Notifications are:
1. Persisted to the `local_notification` table via `local_db.add_notification()`.
2. Sent as desktop notifications via `utils.tray.send_notification()` (silent failure if tray is unavailable).

Content generation (`generate_daily_content()`) also sends its own desktop notification directly, separate from the notification system above.

---

## Agent Status

Call `agent.get_status()` to inspect the agent's current state:

```python
{
    "running": True,            # Whether the main loop is active
    "paused": False,            # Whether task execution is paused
    "iteration_count": 42,      # Total loop iterations completed
    "last_poll_ago": 185,       # Seconds since last campaign poll (None if never)
    "last_health_check_ago": 900,   # Seconds since last session check (None if never)
    "last_profile_refresh_ago": 3600,  # Seconds since last profile refresh (None if never)
}
```

---

## Debugging Guide

### Log Messages to Watch

All agent logs use the `background_agent` logger. Key messages:

| Log Level | Message Pattern | Meaning |
|-----------|----------------|---------|
| INFO | `"Background agent started"` | Agent loop began |
| INFO | `"Background agent stopped"` | Agent loop exited cleanly |
| INFO | `"Background agent paused/resumed"` | Pause state changed |
| INFO | `"Campaign poll: %d total, %d new"` | Poll completed with counts |
| INFO | `"Daily content generated for campaign %s (day %d)"` | Content generation succeeded |
| INFO | `"Post execution: %d due, %d succeeded, %d failed"` | Post batch completed |
| INFO | `"Session health: {platform: status}"` | Health check results |
| INFO | `"Profile refresh: %d platform(s) refreshed"` | Profile scrape completed |
| INFO | `"Synced %d posts to server"` | Server sync after posting |
| INFO | `"Generated %d notification(s)"` | Notifications created this iteration |
| ERROR | `"Campaign poll crashed: %s"` | Poll task threw an unhandled exception |
| ERROR | `"Daily content gen failed for campaign %s: %s"` | Content generation failed for one campaign |
| ERROR | `"Failed to execute post %d on %s: %s"` | One scheduled post failed to execute |
| ERROR | `"Metric scraping crashed: %s"` | Scraping task threw an exception |
| ERROR | `"Session health check crashed: %s"` | Health check threw an exception |
| ERROR | `"Profile refresh failed: %s"` | Profile refresh threw an exception |
| WARNING | `"Background agent already running"` | Attempted to start a second agent instance |
| WARNING | `"Desktop notification failed: %s"` | Tray notification couldn't be sent |
| WARNING | `"Profile sync to server failed: %s"` | Server profile sync failed (non-fatal) |

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Posts are being duplicated | Race condition in due post pickup | Check that `status = 'posting'` update is working. The agent marks posts as `'posting'` before execution to prevent re-pickup. |
| Content not generating | Campaign status not in accepted set | Check `local_campaign.status` is one of: `assigned`, `accepted`, `content_generated`, `approved`, `posted`, `active` |
| Metrics not being reported | Posts missing `server_post_id` | Posts must be synced to server first (`synced = 1` and `server_post_id` set). Check if `report_posts()` is succeeding. |
| Session expired notifications | Platform cookie/session expired | Run `python scripts/login_setup.py <platform>` to re-authenticate |
| Agent not starting | Already running instance | Check `get_agent()` -- if it returns non-None, an agent is already active |
| All tasks stopped but agent running | Agent is paused | Check `agent.get_status()["paused"]`. Call `agent.resume()` to restart. |

### Interval Constants

Defined at the top of `background_agent.py` for easy modification:

```python
LOOP_INTERVAL = 60            # Main loop sleep (seconds)
POLL_INTERVAL = 600           # Campaign polling (seconds)
CONTENT_GEN_INTERVAL = 120    # Content generation check (seconds)
HEALTH_CHECK_INTERVAL = 1800  # Session health check (seconds)
PROFILE_REFRESH_INTERVAL = 604800  # Profile refresh (seconds, = 7 days)
```

---

## UAT Mode

The agent supports test-mode env vars that override production defaults. Default behaviour is preserved when these are unset.

| Variable | Effect |
|----------|--------|
| `AMPLIFIER_UAT_INTERVAL_SEC` | Overrides `CONTENT_GEN_INTERVAL` and also shortens the research/strategy cache TTL inside `content_agent.py` (reads the same var). Set to e.g. `30` to run content generation every 30 seconds during UAT. |
| `AMPLIFIER_UAT_FORCE_DAY` | Overrides `day_number` passed to `generate_daily_content()`. Use to test day-N hook diversity without waiting N days. Can also be set via `--day-number` CLI arg when starting the agent. |

These flags are read directly from `os.environ` inside the agent loop — no restart required if you `export` them in the same shell before starting the process.

See `docs/development-setup.md` for the full UAT flag table including `AMPLIFIER_UAT_BYPASS_AI` (content_agent.py) and `AMPLIFIER_UAT_POST_NOW` (user_app.py).
