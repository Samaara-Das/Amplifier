# Post-MVP Roadmap

## User App Distribution Rethink

**Problem:** The current user app ships as a Windows desktop installer (PyInstaller + Inno Setup). This creates high onboarding friction:
- "Download an .exe from an unknown creator" is a trust killer for non-technical users
- Windows Defender flags it
- Mac/mobile users are excluded
- Every user's machine is different — support burden is high

**Solution:** Split the user app into two parts: a web dashboard and a local posting agent.

### Phase 1: Web Dashboard
Move campaign browsing, earnings, and post history to a hosted web app on the server. Zero install, zero friction. This unblocks user acquisition immediately.

Currently local-only pages to migrate:
- Campaigns tab (browse available campaigns, accept/reject)
- Posts tab (view posted content, status)
- Earnings tab (earnings breakdown, payout history)
- Settings tab (platform connections, preferences)

### Phase 2: Lightweight Desktop Agent
Replace the PyInstaller bundle with a Tauri app:
- Smaller binary, faster startup
- Auto-updates
- System tray icon — runs in background
- Clean native UI
- Handles posting only — the web dashboard tells it what to post

### Phase 3: Cloud Posting (Optional)
Server-side browser sessions for users who don't want to install anything:
- Requires explicit credential consent
- Liability and security considerations
- Only pursue if Phase 1+2 show demand for it

**Core tension:** Architecture is built for security (local execution, credentials never leave device) but growth requires zero-friction onboarding. The split (web dashboard + local agent) preserves both.
