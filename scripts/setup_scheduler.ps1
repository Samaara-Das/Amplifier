# Auto-Poster Windows Task Scheduler Setup
# Registers scheduled tasks for content generation and posting

$ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

# ─── Configuration ──────────────────────────────────────────────────────────
# Generation times (3x daily)
$GenerateTimes = @("08:00", "13:00", "18:00")
$GenerateCount = 2

# Posting interval (every 2 hours starting at 9 AM)
$PostStartTime = "09:00"
$PostIntervalHours = 2

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

$generateTriggers = @()
foreach ($time in $GenerateTimes) {
    $trigger = New-ScheduledTaskTrigger -Daily -At $time
    $generateTriggers += $trigger
}

$generateSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $GenerateTaskName `
    -Action $generateAction `
    -Trigger $generateTriggers `
    -Settings $generateSettings `
    -Description "Auto-Poster: Generate social media drafts via Claude Code CLI" `
    -RunLevel Limited | Out-Null

Write-Host "Registered $GenerateTaskName (runs at: $($GenerateTimes -join ', '))"

# ─── Register Post Task ────────────────────────────────────────────────────

Write-Host "`n=== Setting up $PostTaskName ==="
Remove-ExistingTask $PostTaskName

$postScript = Join-Path $ROOT "scripts\post.py"
$postAction = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument "`"$postScript`"" `
    -WorkingDirectory $ROOT

$postTrigger = New-ScheduledTaskTrigger -Daily -At $PostStartTime
$postRepetition = New-TimeSpan -Hours $PostIntervalHours
$postDuration = New-TimeSpan -Hours 14

$postSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90)

Register-ScheduledTask `
    -TaskName $PostTaskName `
    -Action $postAction `
    -Trigger $postTrigger `
    -Settings $postSettings `
    -Description "Auto-Poster: Post pending drafts to social media platforms" `
    -RunLevel Limited | Out-Null

# Add repetition interval via CIM (not available in New-ScheduledTaskTrigger)
$task = Get-ScheduledTask -TaskName $PostTaskName
$task.Triggers[0].Repetition.Interval = "PT${PostIntervalHours}H"
$task.Triggers[0].Repetition.Duration = "PT14H"
$task | Set-ScheduledTask | Out-Null

Write-Host "Registered $PostTaskName (every ${PostIntervalHours}h starting at $PostStartTime)"

# ─── Summary ───────────────────────────────────────────────────────────────

Write-Host "`n=== Setup Complete ==="
Write-Host "Tasks registered:"
Get-ScheduledTask -TaskName "AutoPoster-*" | Format-Table TaskName, State, @{L="Triggers";E={($_.Triggers | ForEach-Object { $_.StartBoundary }) -join ", "}} -AutoSize
