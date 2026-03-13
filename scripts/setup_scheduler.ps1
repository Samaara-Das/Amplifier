# Auto-Poster Windows Task Scheduler Setup
# Registers scheduled tasks for content generation and posting
# Posting times aligned to US audience: IST 6:30PM-6:30AM = EST 8AM-8PM

$ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

# ─── Configuration ──────────────────────────────────────────────────────────
# Generation: once daily, 1 hour before first posting slot
$GenerateTime = "09:00"          # IST 9:00 AM → user reviews during the day, posts start at 18:30
$GenerateCount = 6               # 6 drafts per day (one per posting slot)

# Posting slots (IST times → EST equivalents)
# Slot 1: 18:30 IST = 8:00 AM EST — East Coast morning scroll
# Slot 2: 20:30 IST = 10:00 AM EST — Mid-morning, peak LinkedIn + X
# Slot 3: 23:30 IST = 1:00 PM EST — Lunch break, high TikTok/Instagram
# Slot 4: 01:30 IST = 3:00 PM EST — Afternoon, post-market discussion
# Slot 5: 04:30 IST = 6:00 PM EST — Evening scroll, highest TikTok engagement
# Slot 6: 06:30 IST = 8:00 PM EST — Night wind-down, strong Instagram/Facebook
$PostTimes = @("18:30", "20:30", "23:30", "01:30", "04:30", "06:30")

# Task names
$GenerateTaskName = "AutoPoster-Generate"
$PostTaskName = "AutoPoster-Post"

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

# ─── Register Post Task ────────────────────────────────────────────────────

Write-Host "`n=== Setting up $PostTaskName ==="
Remove-ExistingTask $PostTaskName

$postScript = Join-Path $ROOT "scripts\post.py"
$postAction = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument "`"$postScript`"" `
    -WorkingDirectory $ROOT

# Create 6 daily triggers — one per posting slot
$postTriggers = @()
foreach ($time in $PostTimes) {
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    $postTriggers += $trigger
}

$postSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90)

Register-ScheduledTask `
    -TaskName $PostTaskName `
    -Action $postAction `
    -Trigger $postTriggers `
    -Settings $postSettings `
    -Description "Auto-Poster: Post pending drafts to all platforms (6 US-aligned slots daily)" `
    -RunLevel Limited | Out-Null

Write-Host "Registered $PostTaskName (6 daily slots at IST: $($PostTimes -join ', '))"

# ─── Summary ───────────────────────────────────────────────────────────────

Write-Host "`n=== Setup Complete ==="
Write-Host ""
Write-Host "Schedule (IST → EST):"
Write-Host "  Generate:  $GenerateTime IST → creates $GenerateCount drafts"
Write-Host "  Post Slot 1:  18:30 IST = 8:00 AM EST  (East Coast morning)"
Write-Host "  Post Slot 2:  20:30 IST = 10:00 AM EST (Mid-morning peak)"
Write-Host "  Post Slot 3:  23:30 IST = 1:00 PM EST  (Lunch break)"
Write-Host "  Post Slot 4:  01:30 IST = 3:00 PM EST  (Afternoon)"
Write-Host "  Post Slot 5:  04:30 IST = 6:00 PM EST  (Evening scroll)"
Write-Host "  Post Slot 6:  06:30 IST = 8:00 PM EST  (Night wind-down)"
Write-Host ""
Write-Host "Registered tasks:"
Get-ScheduledTask -TaskName "AutoPoster-*" | Format-Table TaskName, State, @{L="Triggers";E={($_.Triggers | ForEach-Object { $_.StartBoundary }) -join ", "}} -AutoSize
