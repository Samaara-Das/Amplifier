# Tasks #77 + #79 — Installer Assets (Icon + EULA)

**Status:** pending  
**Branch:** flask-user-app  

Two blocked assets that prevent a clean installer build and pass of the Inno Setup wizard:

- **Task #77**: `icon.ico` at `scripts/build/installer/icon.ico` — currently a placeholder (`ICON_PLACEHOLDER.md`). Must contain a valid multi-size ICO file with all 6 sizes (16/32/48/64/128/256 px) so the installer and final .exe display the correct icon in Windows File Explorer and taskbar.
- **Task #79**: `scripts/build/installer/eula.rtf` — currently a placeholder stub (7-line placeholder with `TODO: Replace before public release`). Must be replaced with a real EULA covering license grant, no-warranty, US jurisdiction, termination, and governing law. Cross-reference with live `/terms` and `/privacy` pages.

Both assets are build-time only (not deployed to the server). Verification is a mix of automated format checks and a manual installer dry-run.

---

## Features to verify end-to-end (Task #77)

1. `icon.ico` file exists at the correct path and is a valid ICO format — AC1
2. ICO contains all 6 required sizes — AC2
3. `ICON_PLACEHOLDER.md` is deleted (icon is real) — AC3
4. Installer build script runs without error and the installer shows the correct icon — AC4

## Features to verify end-to-end (Task #79)

1. `eula.rtf` exists and has a valid RTF header — AC5
2. EULA contains all required legal sections — AC6
3. Key EULA clauses are consistent with `/terms` and `/privacy` live pages — AC7
4. Inno Setup renders the EULA cleanly as a scrollable License Agreement dialog — AC8

---

## Verification Procedure — Task #77

### Preconditions

- Windows machine with PIL (Pillow) available: `python -c "from PIL import Image; print('ok')"` → `ok`.
- Inno Setup 6 installed at default path (`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`) OR `ISCC` on PATH.
- `scripts/build/installer/icon.ico` has been placed (Task #77 work complete before running UAT).

### Test data setup

None — the file is the deliverable.

### Test-mode flags

None.

---

### AC1 — icon.ico exists and is a valid ICO file

| Field | Value |
|-------|-------|
| **Setup** | `scripts/build/installer/icon.ico` file placed by implementer. |
| **Action** | `python -c "from PIL import Image; img=Image.open('scripts/build/installer/icon.ico'); print('format:', img.format, '\| size:', img.size)"` |
| **Expected** | Prints `format: ICO` (not PNG, BMP, or error). No exception raised. File size > 5 KB (sanity — a real multi-size ICO is never tiny). |
| **Automated** | yes |
| **Automation** | `python -c "from PIL import Image; img=Image.open('scripts/build/installer/icon.ico'); assert img.format=='ICO', f'Expected ICO got {img.format}'; print('PASS')"` |
| **Evidence** | stdout showing `format: ICO` and file size; no exception |
| **Cleanup** | none |

---

### AC2 — ICO contains all 6 required sizes (16/32/48/64/128/256 px)

| Field | Value |
|-------|-------|
| **Setup** | AC1 passed. |
| **Action** | `python -c "from PIL import Image; img=Image.open('scripts/build/installer/icon.ico'); sizes=[f.size for f in Image.open('scripts/build/installer/icon.ico').seek(i) or Image.open('scripts/build/installer/icon.ico') for i in range(getattr(img, 'n_frames', 1))]; print(sizes)"` — OR use the multi-frame enumerate approach: `python -c "from PIL import Image; img=Image.open('C:/Users/dassa/Work/Auto-Posting-System/scripts/build/installer/icon.ico'); sizes=set(); [sizes.add(img.size) or img.seek(i) for i in range(getattr(img, 'n_frames', 1)) if not img.seek(i) is None]; print(sorted(sizes))"` |
| **Expected** | Set of frame sizes includes all of: `(16,16)`, `(32,32)`, `(48,48)`, `(64,64)`, `(128,128)`, `(256,256)`. Any missing size → FAIL. |
| **Automated** | yes |
| **Automation** | `python -c "from PIL import Image; img=Image.open('scripts/build/installer/icon.ico'); n=getattr(img,'n_frames',1); sizes=set(); [img.seek(i) or sizes.add(img.size) for i in range(n)]; req={(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)}; missing=req-sizes; assert not missing, f'Missing sizes: {missing}'; print('PASS all 6 sizes present:', sorted(sizes))"` |
| **Evidence** | stdout showing all 6 sizes; script exit 0 |
| **Cleanup** | none |

---

### AC3 — ICON_PLACEHOLDER.md is deleted

| Field | Value |
|-------|-------|
| **Setup** | Task #77 implementation complete. |
| **Action** | `python -c "import os; exists=os.path.exists('scripts/build/installer/ICON_PLACEHOLDER.md'); print('EXISTS:', exists); assert not exists, 'Placeholder not deleted'"` |
| **Expected** | Prints `EXISTS: False`. Script exits 0. The placeholder file is gone — `icon.ico` has replaced it. |
| **Automated** | yes |
| **Automation** | python one-liner above |
| **Evidence** | stdout `EXISTS: False` |
| **Cleanup** | none |

---

### AC4 — Installer build runs cleanly and installer shows correct icon (manual)

| Field | Value |
|-------|-------|
| **Setup** | Inno Setup installed. `scripts/build/installer/icon.ico` and `scripts/build/installer/eula.rtf` both in place. |
| **Action** | Run the installer build wrapper: `powershell scripts/build/build_windows_installer.ps1 2>&1`. Then locate the output installer `.exe` in `scripts/build/dist/`. Right-click the installer `.exe` in File Explorer → Properties → General tab — screenshot shows the embedded icon. |
| **Expected** | `build_windows_installer.ps1` exits 0 with no `Error` lines in output (warnings OK). Installer `.exe` appears in `scripts/build/dist/`. File Explorer Properties tab shows the Amplifier icon (not a generic executable icon). |
| **Automated** | partial — automated for build exit code; manual for icon visual inspection |
| **Automation** | PowerShell: `powershell scripts/build/build_windows_installer.ps1; if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }` |
| **Evidence** | ISCC stdout (build log); manual y/n prompt: "Does the installer .exe show the Amplifier icon in File Explorer? (y/n)" |
| **Cleanup** | `Remove-Item scripts/build/dist/*.exe -ErrorAction SilentlyContinue` after confirmation |

---

### Aggregated PASS rule for Task #77

Task #77 is marked done in task-master ONLY when:
1. AC1–AC3 all PASS (automated)
2. AC4 PASS — build exits 0 AND user says `y` on icon visual check
3. `ICON_PLACEHOLDER.md` confirmed deleted (AC3)
4. UAT report `docs/uat/reports/task-77-<yyyy-mm-dd>.md` written with PIL output and build log excerpt

---

## Verification Procedure — Task #79

### Preconditions

- `scripts/build/installer/eula.rtf` exists with real EULA content (Task #79 work complete).
- Server live at `https://api.pointcapitalis.com/terms` and `https://api.pointcapitalis.com/privacy` (for cross-reference check).
- Inno Setup 6 available (same as Task #77).

### Test data setup

None — the file is the deliverable.

### Test-mode flags

None.

---

### AC5 — eula.rtf exists and has valid RTF header

| Field | Value |
|-------|-------|
| **Setup** | Task #79 implementation complete. |
| **Action** | `python -c "content=open('scripts/build/installer/eula.rtf','r',errors='replace').read(); assert content.startswith('{\\\\rtf1\\\\ansi'), f'Invalid RTF header: {content[:40]}'; print('PASS: valid RTF header'); print('file size:', len(content), 'chars')"` |
| **Expected** | File starts with `{\rtf1\ansi`. File size > 2 000 chars (real legal text, not the 7-line placeholder). No exception raised. |
| **Automated** | yes |
| **Automation** | python one-liner above |
| **Evidence** | stdout showing `PASS: valid RTF header` and char count > 2000 |
| **Cleanup** | none |

---

### AC6 — EULA contains all required legal sections

| Field | Value |
|-------|-------|
| **Setup** | AC5 passed. |
| **Action** | `python -c "import re; content=open('scripts/build/installer/eula.rtf','r',errors='replace').read(); sections=['license grant','no warranty','without warranty','governing law','jurisdiction','termination','contact']; missing=[s for s in sections if not re.search(s,content,re.IGNORECASE)]; print('missing:', missing); assert not missing, f'Missing sections: {missing}'; print('PASS')"` |
| **Expected** | All 7 patterns found (case-insensitive): `license grant`, `no warranty` or `without warranty`, `governing law`, `jurisdiction`, `termination`, `contact`. `missing` list is empty. |
| **Automated** | yes |
| **Automation** | python one-liner above |
| **Evidence** | stdout showing `missing: []` and `PASS` |
| **Cleanup** | none |

---

### AC7 — Key EULA clauses are consistent with /terms and /privacy live pages

| Field | Value |
|-------|-------|
| **Setup** | AC6 passed. Server live. Python `httpx` available. |
| **Action** | Fetch live terms and cross-check manually: `python -c "import httpx; terms=httpx.get('https://api.pointcapitalis.com/terms').text; privacy=httpx.get('https://api.pointcapitalis.com/privacy').text; print('Terms length:', len(terms)); print('Privacy length:', len(privacy))"`. The UAT skill then displays the EULA governing-law clause and the `/terms` governing-law clause side-by-side and asks: "Are the jurisdiction / governing law statements consistent? (y/n)". |
| **Expected** | `/terms` and `/privacy` both return HTTP 200 with non-empty bodies. Governing law/jurisdiction in both the EULA and `/terms` reference the same state/country (no conflict). Contact email in EULA matches contact email on `/terms` or `/privacy`. |
| **Automated** | partial — automated for HTTP 200 + non-empty; manual for clause consistency |
| **Automation** | httpx probe (automated) + side-by-side display for manual y/n |
| **Evidence** | httpx stdout; manual y/n response |
| **Cleanup** | none |

---

### AC8 — Inno Setup renders EULA as clean scrollable License Agreement dialog (manual)

| Field | Value |
|-------|-------|
| **Setup** | Inno Setup installed. `windows.iss` references `LicenseFile=eula.rtf`. Build from AC4 (Task #77) OR rebuild now. |
| **Action** | Launch the output installer .exe → progress through setup wizard to the License Agreement page → `take_screenshot("data/uat/screenshots/79_ac8_eula_dialog.png")`. Scroll the EULA text. |
| **Expected** | License Agreement page renders without garbled text, missing characters, or encoding errors (common RTF pitfall). Text is scrollable. "I accept the agreement" radio button is present and functional. RTF formatting is clean (bold headings, readable paragraphs). |
| **Automated** | no — manual visual inspection |
| **Automation** | manual |
| **Evidence** | screenshot `data/uat/screenshots/79_ac8_eula_dialog.png`; manual y/n: "Does the EULA render cleanly with readable text and correct formatting? (y/n)" |
| **Cleanup** | Cancel out of installer after screenshot. `Remove-Item scripts/build/dist/*.exe -ErrorAction SilentlyContinue`. |

---

### Aggregated PASS rule for Task #79

Task #79 is marked done in task-master ONLY when:
1. AC5–AC7 all PASS (AC7 requires user `y` on the clause-consistency check)
2. AC8 PASS — user says `y` on the EULA dialog visual check
3. Placeholder stub text (`Placeholder license text. Replace before public release`) is NOT present anywhere in the file: `python -c "assert 'Placeholder' not in open('scripts/build/installer/eula.rtf').read(); print('PASS')"`
4. UAT report `docs/uat/reports/task-79-<yyyy-mm-dd>.md` written with screenshot of EULA dialog embedded
