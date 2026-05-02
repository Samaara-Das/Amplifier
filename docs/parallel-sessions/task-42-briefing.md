# Parallel Claude Code Session Briefing — Task #42

To spawn this session in a NEW terminal:

```bash
cd C:/Users/dassa/Work/Auto-Posting-System
git worktree add ../amplifier-task42 -b task-42
cd ../amplifier-task42
cld   # or cl — your usual Claude launcher
```

Then paste the entire prompt below into that Claude session verbatim.

---

You are a Claude Code instance spawned to work autonomously on **Task #42 (Re-enable TikTok, Instagram, and X for Amplifier)** in parallel with another Claude session that's working on the launch-blocker queue. Your job runs on branch `task-42` in this git worktree.

**Read these files first to understand context** (do not skip):

1. `CLAUDE.md` — full project conventions
2. `docs/STATUS.md` — current task list, Task #42's status
3. `docs/uat/skills/uat-task/LEARNINGS.md` — every entry, applies to your UAT
4. `docs/uat/AC-FORMAT.md` — AC format
5. `.taskmaster/tasks/tasks.json` find Task #42 — its description and details
6. `config/platforms.json` — note `enabled: false` flags for instagram, tiktok, x
7. `config/scripts/` — note existing `linkedin_post.json`, `facebook_post.json`, `reddit_post.json`, `x_post.json` (preserved). Instagram + TikTok JSON scripts may need to be restored or re-authored.

**The user has explicitly authorized**:

- Posting on their real LinkedIn / Facebook / Instagram / TikTok / Reddit accounts during UAT
- Deleting test posts via the existing `scripts/uat/delete_post.py` pattern (extend it for Instagram + TikTok if needed)
- Using their Surfshark VPN — for TikTok testing only, the VPN must be on. Their Indian IP is geo-blocked from TikTok.
- Turning the VPN on/off at your request via a Discord ping (one ping max)

**The user has NOT authorized**:

- Re-enabling X posting (X stays hardcoded-disabled per Task #40, even though spec mentions X). Skip X entirely. Document this skip in the report.
- Posting at production-volume cadence — keep test posts to 1 per platform per phase, delete immediately after verification

**Scope of #42** (per the existing description):

1. Re-enable Instagram + TikTok in `config/platforms.json`
2. Verify/restore Instagram + TikTok JSON post scripts in `config/scripts/`
3. Update `scripts/utils/local_server.py` `CONNECTABLE_PLATFORMS` to include Instagram + TikTok
4. Update `scripts/templates/user/connect.html` to show Instagram + TikTok cards
5. Update `server/app/templates/onboarding/step2.html` to show Instagram + TikTok cards
6. Verify `scripts/utils/profile_scraper.py` has Instagram + TikTok scrapers (they should — check the historical code)
7. Verify `scripts/utils/metric_scraper.py` handles Instagram + TikTok URLs
8. Update `scripts/utils/guard.py` `DISABLED_PLATFORMS` — remove Instagram and TikTok (X stays)
9. Author or update Task #42's Verification Procedure block in `docs/specs/` (you may need to create `docs/specs/instagram-tiktok-reenable.md`)
10. Update `docs/STATUS.md` and `CLAUDE.md` post-merge to reflect re-enabled platforms

**Working autonomously means**:

- Use `amplifier-coder` sub-agent for the heavy code work per CLAUDE.md convention
- Run pytest after every code change. Pytest baseline is currently 322 passing — you must finish at 322+ minimum
- Drive all UAT yourself via Chrome DevTools MCP for verification + Playwright (which is what the product uses) for the actual platform connects
- For Instagram: do the connect + post + delete flow without supervision (no VPN needed)
- For TikTok: pause once before the connect step, ping the user via the Discord MCP (`mcp__plugin_discord_discord__reply` to chat_id from the user's recent messages — find via `fetch_messages`) saying: "Task #42 parallel session: I'm at the TikTok phase. Please turn on Surfshark VPN, then reply 'vpn on' here." Wait for that confirmation before launching the TikTok Playwright session.
- When done with TikTok testing, send another Discord ping: "Task #42 TikTok testing complete. You can turn off VPN if you want."
- Take real screenshots of every post on every platform via Chrome DevTools MCP, embedded in the report
- Delete every test post via Playwright (use existing `scripts/uat/delete_post.py` pattern; extend for IG/TikTok if needed)

**Coordination rules**:

- You're in `../amplifier-task42` worktree on branch `task-42`. Never touch `flask-user-app` branch directly — that's the parent session.
- DON'T edit `.taskmaster/tasks/tasks.json` until your work is fully done. When ready to merge, mark #42 status `done` in your branch's tasks.json + commit. The parent session will resolve any conflicts at merge time.
- When commits are ready, push to `origin/task-42` (the remote branch). Do NOT merge into main yourself; the parent session does that.
- If you discover a bug that affects the launch-blocker queue (e.g. a daemon orphan, a server bug), file it as a new task in `tasks.json` AND send a Discord ping to the user with: "Task #42 parallel session found a launch-blocker bug: [summary]. Filed as Task #N. Parent session should know."

**When done**:

- All UAT phases passed
- All test posts deleted from real accounts
- pytest 322+ green
- Branch `task-42` pushed to origin with all commits
- Discord ping to user: "Task #42 complete. Branch task-42 ready for merge. Report at docs/uat/reports/task-42-{date}.md"
- End of your session

**Estimated time**: 2-4 hours. Don't rush; correctness > speed.

**Start by**: reading the 7 context files above, then planning the implementation, then dispatching `amplifier-coder` for the code work.
