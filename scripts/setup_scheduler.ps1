# Auto-Poster Windows Task Scheduler Setup
# Registers scheduled tasks for content generation and posting
# Posting times aligned to US audience: IST 6:30PM-6:30AM = EST 8AM-8PM

$ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

# ─── Configuration ──────────────────────────────────────────────────────────
# Generation: once daily, 1 hour before first posting slot
$GenerateTime = "09:00"          # IST 9:00 AM → user reviews during the day, posts start at 18:30
$GenerateCount = 6               # 6 drafts per day (one per posting slot)

# Posting slots — per-platform cadence (IST times → EST equivalents)
# Each slot runs post.py with --slot N so it posts only to that slot's platforms
$PostSlots = @(
    @{ Slot = 1; Time = "18:30"; EST = "8:00 AM";  Platforms = "X tweet #1 + LinkedIn (Tue-Fri)" },
    @{ Slot = 2; Time = "20:30"; EST = "10:00 AM"; Platforms = "Facebook post" },
    @{ Slot = 3; Time = "23:30"; EST = "1:00 PM";  Platforms = "X tweet #2 + Reddit (2-3x/week)" },
    @{ Slot = 4; Time = "01:30"; EST = "3:00 PM";  Platforms = "X tweet #3 or thread" },
    @{ Slot = 5; Time = "04:30"; EST = "6:00 PM";  Platforms = "TikTok" },
    @{ Slot = 6; Time = "06:30"; EST = "8:00 PM";  Platforms = "Instagram" }
)

# Task names
$GenerateTaskName = "AutoPoster-Generate"
$PostTaskPrefix = "AutoPoster-Post-Slot"

# ─── Helpers ────────────────────────────────────────────────────────────────

function Remove-ExistingTask {
    param([string]$Name)
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "Removed existing task: $Name"
    }
}

# ─── Register Generate Task ────────────────────────────────────────────────

Write-Host "`n=== Setting up $GenerateTaskName ==="
Remove-ExistingTask $GenerateTaskName

$generateScript = Join-Path $ROOT "scripts\generate.ps1"
$generateAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$generateScript`" -count $GenerateCount" `
    -WorkingDirectory $ROOT

$generateTrigger = New-ScheduledTaskTrigger -Daily -At $GenerateTime

$generateSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $GenerateTaskName `
    -Action $generateAction `
    -Trigger $generateTrigger `
    -Settings $generateSettings `
    -Description "Auto-Poster: Generate 6 social media drafts via Claude Code CLI (runs 1h before first post)" `
    -RunLevel Limited | Out-Null

Write-Host "Registered $GenerateTaskName (daily at $GenerateTime IST, generates $GenerateCount drafts)"

# ─── Register Post Tasks (one per slot) ───────────────────────────────────
# Each slot gets its own task so it can pass --slot N to post.py,
# which posts only to that slot's assigned platforms.

# Remove old single-task format if it exists
Remove-ExistingTask "AutoPoster-Post"

$postScript = Join-Path $ROOT "scripts\post.py"

$postSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90)

foreach ($slot in $PostSlots) {
    $taskName = "$PostTaskPrefix-$($slot.Slot)"
    Write-Host "`n=== Setting up $taskName ==="
    Remove-ExistingTask $taskName

    $postAction = New-ScheduledTaskAction `
        -Execute "python" `
        -Argument "`"$postScript`" --slot $($slot.Slot)" `
        -WorkingDirectory $ROOT

    $postTrigger = New-ScheduledTaskTrigger -Daily -At $slot.Time

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $postAction `
        -Trigger $postTrigger `
        -Settings $postSettings `
        -Description "Auto-Poster Slot $($slot.Slot): $($slot.Platforms) ($($slot.Time) IST = $($slot.EST) EST)" `
        -RunLevel Limited | Out-Null

    Write-Host "Registered $taskName ($($slot.Time) IST = $($slot.EST) EST) — $($slot.Platforms)"
}

# ─── Summary ───────────────────────────────────────────────────────────────

Write-Host "`n=== Setup Complete ==="
Write-Host ""
Write-Host "Schedule (IST → EST):"
Write-Host "  Generate:  $GenerateTime IST → creates $GenerateCount drafts"
foreach ($slot in $PostSlots) {
    Write-Host "  Slot $($slot.Slot):  $($slot.Time) IST = $($slot.EST) EST — $($slot.Platforms)"
}
Write-Host ""
Write-Host "Registered tasks:"
Get-ScheduledTask -TaskName "AutoPoster-*" | Format-Table TaskName, State, @{L="Triggers";E={($_.Triggers | ForEach-Object { $_.StartBoundary }) -join ", "}} -AutoSize
