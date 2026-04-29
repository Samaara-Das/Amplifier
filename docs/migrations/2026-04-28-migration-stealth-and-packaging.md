# Migration: Stealth + Packaging (Patchright + Nuitka + Installers)

**Date**: 2026-04-28
**Status**: Planned
**Phase**: D (Business Launch + Tech Stack Migration)
**Estimated effort**: 5-7 days

---

## Why this migration exists

Two production risks must be solved before launching to paying users:

1. **Vanilla Playwright is detected.** The project already recorded 2 X account lockouts traced to Playwright automation detection. X is now hardcoded-disabled. Without a stealth migration, LinkedIn, Facebook, and Reddit are all at risk of the same fate as platform detection improves.

2. **The current "distribution" is `git clone + pip install`.** This is unshippable to paying users. A real installer is launch-blocking, not optional.

This migration solves both with the smallest possible scope:

- **Patchright** — drop-in replacement for Playwright (Chromium-based). Same Python API. Existing JSON scripts and selector inventory work unchanged. ~67% bypass rate on CreepJS vs Playwright's 0%. The pragmatic choice.
- **Nuitka** — compile Python to a native binary. Faster startup than PyInstaller (sub-1-second), fewer antivirus false positives, smaller binary.
- **Inno Setup (Windows)** + **pkgbuild (Mac)** — real installers with Start Menu/Applications entries, uninstallers, optional auto-start.
- **GitHub Releases** — free, public, supports semantic versioning, easy auto-update via HTTP version check.
- **No code signing in v1** — accepts SmartScreen warnings on Windows (users click "More info" → "Run anyway") and Gatekeeper blocks on Mac (users right-click → Open). Signing added post-launch when revenue justifies the ~$400/yr cost.

## Decisions and rationale

| Decision | Choice | Why |
|---|---|---|
| Stealth library | Patchright (Chromium drop-in) | Drop-in for existing Playwright code, JSON scripts work unchanged, no Firefox re-testing of selectors. Camoufox is more stealthy but requires re-validating every selector on Firefox. Save Camoufox for v2 if Patchright proves insufficient. |
| Python compiler | Nuitka 2.x | Native binary, sub-1s startup, fewer AV false positives than PyInstaller. PyInstaller spec fragility is a known pain point this codebase has hit before. |
| Browser bundling | Bundled Chromium via Patchright's installer (`patchright install chromium`) | ~150MB. Avoids "first run downloads stuff" surprise. Users expect large installers for desktop apps. |
| Windows installer | Inno Setup | Industry standard, free, well-documented, scriptable. Handles Start Menu, uninstaller, optional auto-start, registry. |
| Mac installer | `pkgbuild` + `productbuild` (Apple's native tools) | Free, no third-party dependencies, produces `.pkg` that double-clicks to install. Drag-to-Applications `.dmg` requires more scripting; defer to v2 if needed. |
| Linux | Skip in v1 | Target audience is Windows + Mac. Add Linux post-launch if demand emerges. |
| Code signing | None in v1 | Users see warnings, click through. Acceptable for a paid-tier product where users have a financial incentive to install. Add EV cert (Windows ~$300/yr) and Apple Developer ($99/yr) post-launch. |
| Auto-update | HTTP version check + self-replace via GitHub Releases | Daemon polls `https://github.com/Samaara-Das/Amplifier/releases/latest` on startup and once per day. If newer, downloads, replaces self, restarts. ~80 LOC. |
| Build CI | GitHub Actions matrix (Windows + macOS runners) | Free for public repos; private repo gets 2,000 minutes/month. Sufficient for occasional release builds. |

## What changes

### Stealth migration (Playwright → Patchright)

| File / change | Action |
|---|---|
| `requirements.txt` | Replace `playwright` with `patchright` (Patchright is API-compatible). Pin version. |
| `scripts/utils/browser_config.py` | Change import: `from playwright.async_api import ...` → `from patchright.async_api import ...`. The rest of the API surface is identical. |
| `scripts/engine/script_executor.py` | Same import swap. |
| `scripts/utils/post.py` | Same import swap. |
| `scripts/utils/profile_scraper.py` | Same import swap. |
| `scripts/utils/metric_scraper.py` | Same import swap. |
| `scripts/utils/session_health.py` | Same import swap. |
| `scripts/login_setup.py` | Same import swap. |
| `scripts/utils/browser_config.py` | Update launch options — Patchright applies stealth patches automatically; remove `--disable-blink-features=AutomationControlled` flag (now redundant and may interfere with Patchright's patches). |
| `config/scripts/*.json` | NO CHANGES — JSON post scripts are platform-agnostic and continue to work. |
| `docs/platform-posting-playbook.md` | Update header to note Patchright as primary; vanilla Playwright deprecated. |
| `docs/selector-inventory.md` | Add note: selectors validated against Chromium (Patchright). |

### X re-enablement decision (deferred)

X stays hardcoded-disabled in `config/platforms.json` even after Patchright migration. Re-enabling X requires:
1. Live testing on a throwaway X account with Patchright for at least 7 days without lockout.
2. Documented incident response if lockout occurs.
3. Optional: investigation of X API v2 as a parallel posting path.

This is NOT part of this migration. Tracked as a separate post-launch task.

### Packaging — Nuitka build

| File / change | Purpose |
|---|---|
| `scripts/build/build_windows.py` | New — orchestrates the Nuitka compilation for Windows. Includes flag setup for `--onefile`, `--enable-plugin=anti-bloat`, `--include-package=patchright`, `--include-data-dir=config=config`, `--windows-console-mode=disable`. |
| `scripts/build/build_mac.py` | New — same for Mac, uses `--macos-create-app-bundle`. |
| `scripts/build/spec.json` | Configuration shared by both build scripts: app name, version (from `pyproject.toml`), entry point (`scripts/app_entry.py`), data dirs to bundle, packages to include. |
| `scripts/app_entry.py` | Modify — add a startup splash that says "Amplifier starting..." for the first 1-2 seconds. Currently exists; add the splash. |
| `pyproject.toml` | Add Nuitka as a dev dependency. Add `[tool.amplifier]` section with version metadata. |
| `requirements-build.txt` | New — pins Nuitka, Inno Setup script generator, signing tools (placeholder for future). |

### Packaging — Windows installer (Inno Setup)

| File / change | Purpose |
|---|---|
| `scripts/build/installer/windows.iss` | New — Inno Setup script. Defines: app name (Amplifier), version, install location (`C:\Program Files\Amplifier\`), Start Menu entry, optional desktop shortcut, optional auto-start (registers with Task Scheduler, not just `Run` key, to handle restarts robustly), uninstaller, EULA placeholder, post-install action ("Launch Amplifier"). |
| `scripts/build/installer/eula.rtf` | New — placeholder EULA text (replace with real text before launch). |
| `scripts/build/installer/icon.ico` | New — Amplifier app icon (Windows). |
| `scripts/build/build_windows_installer.ps1` | New — PowerShell script that runs Nuitka build, then invokes Inno Setup CLI to produce `AmplifierSetup-vX.Y.Z.exe`. |

### Packaging — Mac installer (pkgbuild)

| File / change | Purpose |
|---|---|
| `scripts/build/installer/mac.plist` | New — Mac Info.plist defining bundle identifier, version, executable, etc. |
| `scripts/build/installer/icon.icns` | New — Amplifier app icon (Mac). |
| `scripts/build/installer/postinstall.sh` | New — runs after install. Registers app for auto-launch via `launchctl` (LaunchAgent plist). |
| `scripts/build/build_mac_installer.sh` | New — bash script that runs Nuitka mac build, then invokes `pkgbuild` and `productbuild` to produce `Amplifier-vX.Y.Z.pkg`. |

### Auto-update mechanism

| File / change | Purpose |
|---|---|
| `scripts/utils/auto_update.py` | New — ~80 LOC. On startup and once per 24h: hits `https://api.github.com/repos/Samaara-Das/Amplifier/releases/latest`, compares tag to local version, if newer downloads the platform-specific installer to a temp dir, shows tray notification "Update available — restart to apply", on next quit launches the installer with `/SILENT` flag. |
| `scripts/background_agent.py` | Add task: `check_for_updates()` — runs every 24h. |
| `scripts/utils/tray.py` | Add menu item: "Check for Updates" — manual trigger. |

### CI/CD — GitHub Actions

| File | Purpose |
|---|---|
| `.github/workflows/release.yml` | New — triggered on git tag push (`v*.*.*`). Matrix: `windows-latest`, `macos-latest`. Builds Nuitka binary, builds installer, attaches to GitHub Release. |
| `.github/workflows/build-test.yml` | New — runs Nuitka build on push to main (without producing an installer) to catch packaging regressions early. |

### Cleanup

| File / dir | Action |
|---|---|
| `tauri-app/` | DELETE — leftover stub from earlier exploration. |
| `dashboards/amplifier-overview.html` | DELETE if not actively used (one-off prototype). |

## Acceptance Criteria

### AC-1: Patchright drop-in works for all platforms
**Given** the codebase has been migrated from Playwright to Patchright
**When** I run the existing UAT suite (`/uat-task` for Tasks #14, #15, etc.)
**Then** all posting flows succeed on LinkedIn, Facebook, and Reddit
**And** session health checks pass
**And** profile scraping works
**And** metric scraping works
**And** no test fails due to a Playwright/Patchright API difference

### AC-2: Browser fingerprinting score improves
**Given** Patchright is in use
**When** I navigate to `https://abrahamjuliot.github.io/creepjs/` via the daemon's Playwright instance
**Then** the trust score is at least 60% (vs <20% on vanilla Playwright)

### AC-3: Nuitka build produces a working binary
**Given** Nuitka is installed and the build script is run on Windows
**When** I execute `python scripts/build/build_windows.py`
**Then** a single `Amplifier.exe` is produced in `dist/windows/`
**And** running `Amplifier.exe` launches the app
**And** the system tray icon appears within 2 seconds
**And** the daemon starts polling normally
**And** Playwright/Patchright successfully launches a browser when the user connects a platform

### AC-4: Mac build produces a working .app bundle
**Given** Nuitka is installed on macOS
**When** I execute `python scripts/build/build_mac.py`
**Then** `Amplifier.app` is produced in `dist/mac/`
**And** double-clicking `Amplifier.app` launches the app
**And** Gatekeeper shows the unsigned warning ("Amplifier cannot be opened because it is from an unidentified developer")
**And** right-click → Open bypasses the warning and launches the app

### AC-5: Windows installer works end-to-end
**Given** Inno Setup is installed and `AmplifierSetup-vX.Y.Z.exe` has been built
**When** a fresh Windows machine downloads and runs the installer
**Then** SmartScreen shows the unsigned warning ("Windows protected your PC")
**And** clicking "More info" → "Run anyway" continues installation
**And** the wizard installs to `C:\Program Files\Amplifier\`
**And** a Start Menu entry "Amplifier" is created
**And** an optional auto-start checkbox (default checked) registers with Task Scheduler
**And** the post-install "Launch Amplifier" checkbox starts the app
**And** "Programs and Features" lists Amplifier with a working uninstaller

### AC-6: Mac installer works end-to-end
**Given** `Amplifier-vX.Y.Z.pkg` has been built
**When** a fresh Mac downloads and double-clicks the .pkg
**Then** Gatekeeper shows the unsigned warning
**And** right-click → Open bypasses the warning
**And** the installer wizard places `Amplifier.app` in `/Applications/`
**And** the postinstall script registers a LaunchAgent for auto-start at login
**And** the app appears in the user's tray after first launch

### AC-7: Auto-update detects and downloads new releases
**Given** the daemon is running on version 1.0.0
**And** GitHub Releases has a new release tagged `v1.0.1` with installer assets
**When** the auto-update task runs
**Then** the daemon detects the new version
**And** downloads the platform-specific installer to a temp directory
**And** displays a tray notification "Update available — restart to install"
**And** on next app quit, the installer is launched with `/SILENT` flag
**And** after installer completes, version 1.0.1 is running

### AC-8: GitHub Actions release workflow produces installers
**Given** the workflow file `.github/workflows/release.yml` is committed
**When** I push a git tag `v1.0.0`
**Then** GitHub Actions runs the matrix build (Windows + macOS)
**And** within 30 minutes, both runs complete successfully
**And** the GitHub Release for `v1.0.0` has both `AmplifierSetup-v1.0.0.exe` and `Amplifier-v1.0.0.pkg` attached
**And** running each installer on its respective platform produces a working app

### AC-9: Installer size is reasonable
**Given** a release build has been produced
**When** I check the installer file sizes
**Then** the Windows installer is between 120 MB and 220 MB
**And** the Mac installer is between 130 MB and 240 MB
**And** the bulk is bundled Chromium (expected)

### AC-10: First-launch startup is fast
**Given** the app has been installed via the Windows installer
**When** I launch Amplifier from the Start Menu
**Then** the system tray icon appears within 2 seconds (Nuitka native binary, not PyInstaller archive extraction)
**And** the local FastAPI on `localhost:5222` is responsive within 3 seconds
**And** there are no antivirus warnings on Windows Defender (acceptable: SmartScreen warning is OK; in-process scanning shouldn't flag)

### AC-11: tauri-app/ is deleted
**Given** the migration is complete
**When** I list the repository root
**Then** `tauri-app/` no longer exists
**And** no references to Tauri remain in any active doc or code

### AC-12: Old PyInstaller artifacts are removed
**Given** the migration is complete
**When** I search the codebase for `pyinstaller`, `*.spec`, or PyInstaller-specific imports
**Then** there are no remaining references except in archived/historical docs

## Out of scope

- Code signing (deferred — accept warnings in v1)
- Linux installer (deferred — target Windows + Mac in v1)
- Camoufox (deferred — Patchright is the v1 choice)
- X re-enablement (deferred — separate task)
- Delta updates / partial patching (full installer download is fine for v1)
- In-app crash reporting / telemetry (deferred)
- App store distribution (Microsoft Store, Mac App Store) — deferred

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Patchright API drift from Playwright (e.g. patch lag for new Playwright features) | Pin Patchright version. Run smoke test of critical posting flows before every release. |
| SmartScreen warning scares users off | Acceptable for v1 paid product (financial incentive to install). Add EV cert post-launch when revenue justifies cost. Document the workaround in onboarding emails. |
| Nuitka compilation breaks on a specific dependency | Maintain a known-good list in `requirements-build.txt`. Test on every dependency upgrade. |
| GitHub Actions runner minutes exceeded | Limit release builds to tagged commits only (not every push). Free tier is 2,000 min/month for private repos — sufficient for ~50 releases. |
| Auto-update download fails (network, GitHub outage) | Daemon retries on next 24h cycle. User can manually "Check for Updates" from tray. Failure is silent unless tray notification fires. |
| Patchright detection rate degrades over time as platforms evolve | Monitor lockout incidents. If LinkedIn/Facebook/Reddit start flagging accounts, escalate to Camoufox migration as a separate task. |

## Test plan

1. Patchright smoke test on Windows + Mac: launch each platform's posting flow, verify success.
2. CreepJS fingerprint test on both platforms.
3. Build pipeline smoke test: tag v1.0.0-rc1, verify both installers produced.
4. Fresh-machine install test: run installer on a Windows VM and a Mac that has never seen Amplifier. Verify no manual setup needed.
5. Auto-update test: install v1.0.0-rc1, manually push v1.0.0-rc2 to GitHub, wait for auto-update detection, verify upgrade succeeds.
6. Uninstall test: run uninstaller on Windows, verify no leftover files except user data dir. Same for Mac.

## Dependencies

- **Creator app split migration** — must be in progress or complete (the strip-down to local FastAPI must happen before Nuitka build, otherwise the Flask templates and CSS bloat the binary).
- **Task #18 (pytest suite)** — must pass before tagging any release.

## Followups

- Add code signing post-launch (Apple Developer $99/yr + Windows EV cert ~$300/yr).
- Add Linux installer (Nuitka supports Linux; package as `.deb` and `.AppImage`).
- Re-evaluate Patchright vs Camoufox after 30 days of production data.
- Investigate Microsoft Store and Mac App Store distribution once user base justifies the review burden.
