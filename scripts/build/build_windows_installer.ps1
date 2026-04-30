# build_windows_installer.ps1
# Full Windows release pipeline: Nuitka compile -> Inno Setup installer.
# Run from the repo root: powershell scripts\build\build_windows_installer.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── 1. Read version from spec.json ──────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = (Resolve-Path "$ScriptDir\..\..").Path
$SpecPath  = Join-Path $RepoRoot "scripts\build\spec.json"

if (-not (Test-Path $SpecPath)) {
    Write-Error "spec.json not found at $SpecPath"
    exit 1
}

$Spec    = Get-Content $SpecPath -Raw | ConvertFrom-Json
$Version = $Spec.version
$AppName = $Spec.name

Write-Host "[installer] Building $AppName v$Version for Windows"

# ── 2. Run Nuitka build ──────────────────────────────────────────────
Write-Host "[installer] Step 1/2 — Nuitka compilation"
$BuildScript = Join-Path $RepoRoot "scripts\build\build_windows.py"

& python $BuildScript
if ($LASTEXITCODE -ne 0) {
    Write-Error "[installer] Nuitka build failed (exit $LASTEXITCODE). Aborting."
    exit $LASTEXITCODE
}

# ── 3. Locate iscc.exe (Inno Setup 6) ───────────────────────────────
$IsccPaths = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

$IsccExe = $null
foreach ($p in $IsccPaths) {
    if (Test-Path $p) {
        $IsccExe = $p
        break
    }
}

if (-not $IsccExe) {
    Write-Host ""
    Write-Host "ERROR: Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php"
    Write-Host "       Expected location: ${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    Write-Host "       On GitHub Actions CI: choco install innosetup -y"
    exit 1
}

Write-Host "[installer] Found ISCC at: $IsccExe"

# ── 4. Compile the installer, injecting version via /D ───────────────
Write-Host "[installer] Step 2/2 — Inno Setup compilation"

$IssPath     = Join-Path $RepoRoot "scripts\build\installer\windows.iss"
$OutDir      = Join-Path $RepoRoot "dist\installers"
$OutFilename = "AmplifierSetup-v$Version"

# Ensure output directory exists
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# ISCC /DMyAppVersion=<ver> overrides the #define in the .iss file
& $IsccExe `
    "/DMyAppVersion=$Version" `
    "/O$OutDir" `
    "/F$OutFilename" `
    $IssPath

if ($LASTEXITCODE -ne 0) {
    Write-Error "[installer] ISCC failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

# ── 5. Report result ─────────────────────────────────────────────────
$InstallerPath = Join-Path $OutDir "$OutFilename.exe"
if (Test-Path $InstallerPath) {
    $SizeMB = [math]::Round((Get-Item $InstallerPath).Length / 1MB, 1)
    Write-Host "[installer] SUCCESS: $InstallerPath ($SizeMB MB)"
} else {
    Write-Host "[installer] WARNING: ISCC reported success but installer not found at expected path."
}
