# Auto-Poster Content Generator
# Calls Claude Code CLI to generate social media drafts
# Generates per-slot drafts with platform-specific content

param(
    [int]$count = 0,
    [int]$slot = 0      # 0 = all slots, 1-6 = specific slot only
)

# Config
$ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$ENV_FILE = Join-Path $ROOT "config\.env"
$TEMPLATES_FILE = Join-Path $ROOT "config\content-templates.md"
$REVIEW_DIR = Join-Path $ROOT "drafts\review"
$PENDING_DIR = Join-Path $ROOT "drafts\pending"
$POSTED_DIR = Join-Path $ROOT "drafts\posted"
$LOG_DIR = Join-Path $ROOT "logs"
$LOG_FILE = Join-Path $LOG_DIR "generator.log"

# Ensure directories exist
New-Item -ItemType Directory -Path $REVIEW_DIR -Force | Out-Null
New-Item -ItemType Directory -Path $PENDING_DIR -Force | Out-Null
New-Item -ItemType Directory -Path $POSTED_DIR -Force | Out-Null
New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null

function Write-Log {
    param([string]$Level, [string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp - $Level - $Message"
    Add-Content -Path $LOG_FILE -Value $entry -Encoding UTF8
    Write-Host $entry
}

# ─── Slot Schedule (mirrors post.py SLOT_SCHEDULE) ─────────────────────────
# Day of week: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6 (Python-style)

$SlotSchedule = @{
    1 = @{
        TimeEST = "8:00 AM"
        Platforms = @{
            "x"        = @(0,1,2,3,4,5,6)    # daily
            "linkedin" = @(1,2,3,4)           # Tue-Fri
        }
    }
    2 = @{
        TimeEST = "10:00 AM"
        Platforms = @{
            "facebook" = @(0,1,2,3,4,5,6)    # daily
        }
    }
    3 = @{
        TimeEST = "1:00 PM"
        Platforms = @{
            "x"      = @(0,1,2,3,4,5,6)      # daily
            "reddit" = @(1,3,5)               # Tue, Thu, Sat
        }
    }
    4 = @{
        TimeEST = "3:00 PM"
        Platforms = @{
            "x" = @(0,1,2,3,4,5,6)           # daily
        }
    }
    5 = @{
        TimeEST = "6:00 PM"
        Platforms = @{
            "tiktok" = @(0,1,2,3,4,5,6)      # daily
        }
    }
    6 = @{
        TimeEST = "8:00 PM"
        Platforms = @{
            "instagram" = @(0,1,2,3,4,5,6)   # daily
        }
    }
}

# Platform content format instructions for prompts
$PlatformFormats = @{
    "x_tweet"  = @{
        Key = 'x'
        Desc = 'X/Twitter tweet (max 280 chars, punchy, 1-3 hashtags). Can be a plain string (text-only) OR a JSON object with "text" and "image_text" keys (text + branded image).'
        Example = '    "x": "your tweet text here"'
    }
    "x_thread" = @{
        Key = 'x'
        Desc = 'X/Twitter THREAD (3-7 tweets). Must be a JSON array of strings, each max 280 chars. First tweet is the hook. Last tweet has CTA or summary.'
        Example = '    "x": ["Hook tweet...", "Second tweet...", "Third tweet...", "Final tweet..."]'
    }
    "linkedin"  = @{
        Key = 'linkedin'
        Desc = 'LinkedIn post (800-1300 chars, professional story-driven tone, line breaks, 3-5 hashtags at end). Can be a plain string OR {"text", "image_text"} object.'
        Example = '    "linkedin": "Your LinkedIn post text here..."'
    }
    "facebook"  = @{
        Key = 'facebook'
        Desc = 'Facebook post (200-800 chars, conversational and casual, 0-2 hashtags). Can be a plain string OR {"text", "image_text"} object.'
        Example = '    "facebook": "Your Facebook post text here..."'
    }
    "reddit"    = @{
        Key = 'reddit'
        Desc = 'Reddit post -- MUST be a JSON object with "title" (60-120 chars, specific, no clickbait) and "body" (500-1500 chars, detailed, data-first, no hashtags, no emojis).'
        Example = '    "reddit": {"title": "your title", "body": "your detailed body text"}'
    }
    "tiktok"    = @{
        Key = 'tiktok'
        Desc = 'TikTok post -- MUST be a JSON object with "caption" (100-300 chars, short punchy, 3-5 hashtags) and "image_text" (1-3 short punchy lines for text overlay on video).'
        Example = '    "tiktok": {"caption": "your caption", "image_text": "BOLD\nPUNCHY\nLINES"}'
    }
    "instagram" = @{
        Key = 'instagram'
        Desc = 'Instagram caption (300-1200 chars, emojis OK, hashtags at end, visually-oriented language).'
        Example = '    "instagram": "Your Instagram caption here..."'
    }
}

# ─── Content Pillar Rotation ──────────────────────────────────────────────
# Daily mix: 2x Pillar 1/3, 1x Pillar 2, 1x Pillar 4, 1x Pillar 5, 1x Wildcard
# Pillars: 1="Stop Losing Money", 2="Make Money While You Sleep", 3="Market Cheat Code",
#          4="Proof Not Promises", 5="Future-Proof Your Income", wildcard=engagement/trending

$PillarDescriptions = @{
    "1"        = "Pillar 1: Stop Losing Money - common mistakes, what losing traders do wrong, fear/pain avoidance"
    "3"        = "Pillar 3: The Market Cheat Code - simplified education framed as giving them an EDGE, competence"
    "2"        = "Pillar 2: Make Money While You Sleep - automation, passive income, side hustle, freedom"
    "4"        = "Pillar 4: Proof Not Promises - backtest results, strategy performance, data, credibility"
    "5"        = "Pillar 5: Future-Proof Your Income - AI fear, job security, trading as a skill AI cant take"
    "wildcard" = "Wildcard - engagement question, trending market event, reflection, or rotate any pillar"
}

# Default pillar per slot (even days alternate Pillar 1/3 split)
# Slot 1: Pillar 1 or 3 (alternates), Slot 2: Pillar 2, Slot 3: Pillar 4
# Slot 4: Pillar 3 or 1 (opposite of slot 1), Slot 5: Pillar 5, Slot 6: Wildcard
$DefaultPillarMap = @{
    1 = @{ Even = "1"; Odd = "3" }  # alternates by day-of-month
    2 = @{ Even = "2"; Odd = "2" }
    3 = @{ Even = "4"; Odd = "4" }
    4 = @{ Even = "3"; Odd = "1" }  # opposite of slot 1
    5 = @{ Even = "5"; Odd = "5" }
    6 = @{ Even = "wildcard"; Odd = "wildcard" }
}

# Content series overrides: (dayOfWeek, slot) -> series name + pillar
# Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
$ContentSeries = @{}
$ContentSeries["0-1"] = @{
    Series = "Setup of the Week"
    Pillar = "3"
    Desc = "CONTENT SERIES: Setup of the Week (Monday). Show YOUR indicator signal screenshot with annotated analysis. Before/after format: signal flagged then what price did after. Voice: My indicator flagged this setup on `$SPY - here is what happened next."
}
$ContentSeries["2-3"] = @{
    Series = "Backtest Wednesday"
    Pillar = "4"
    Desc = "CONTENT SERIES: Backtest Wednesday. Share a backtest result with full methodology and key findings. Data-heavy, transparent. Voice: I ran this backtest and here is what surprised me."
}
$ContentSeries["4-1"] = @{
    Series = "One Thing I Learned This Week"
    Pillar = "wildcard"
    Desc = "CONTENT SERIES: One Thing I Learned This Week (Friday). Reflection post - one insight from the weeks research. Personal, authentic, discovery-oriented."
}

# ─── Determine today's schedule ────────────────────────────────────────────

# Convert PowerShell DayOfWeek (Sun=0..Sat=6) to Python-style (Mon=0..Sun=6)
$psDow = [int](Get-Date).DayOfWeek
$today = ($psDow + 6) % 7
$dayNames = @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")
$todayName = $dayNames[$today]
$dayOfMonth = (Get-Date).Day
$isEvenDay = ($dayOfMonth % 2 -eq 0)

function Get-PillarForSlot {
    param([int]$SlotNum)
    # Check content series override first
    $seriesKey = "$today-$SlotNum"
    if ($ContentSeries.ContainsKey($seriesKey)) {
        return $ContentSeries[$seriesKey].Pillar
    }
    # Default pillar based on even/odd day
    $mapping = $DefaultPillarMap[$SlotNum]
    if ($isEvenDay) { return $mapping.Even } else { return $mapping.Odd }
}

function Get-SeriesForSlot {
    param([int]$SlotNum)
    $seriesKey = "$today-$SlotNum"
    if ($ContentSeries.ContainsKey($seriesKey)) {
        return $ContentSeries[$seriesKey]
    }
    return $null
}

# Scan existing today's drafts for pillar tracking
function Get-TodaysPillars {
    $todayPrefix = Get-Date -Format "yyyyMMdd"
    $usedPillars = @()
    foreach ($dir in @($REVIEW_DIR, $PENDING_DIR)) {
        if (Test-Path $dir) {
            Get-ChildItem -Path $dir -Filter "draft-$todayPrefix*.json" -ErrorAction SilentlyContinue | ForEach-Object {
                try {
                    $content = Get-Content -Path $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($content.pillar) { $usedPillars += $content.pillar }
                } catch {}
            }
        }
    }
    return $usedPillars
}

# Unset CLAUDECODE to allow nested CLI calls
$env:CLAUDECODE = $null

# Read content templates
if (-not (Test-Path $TEMPLATES_FILE)) {
    Write-Log "ERROR" "Content templates not found at $TEMPLATES_FILE"
    exit 1
}
$templates = Get-Content -Path $TEMPLATES_FILE -Raw -Encoding UTF8

# List existing draft filenames for topic dedup
$existingDrafts = @()
foreach ($dir in @($REVIEW_DIR, $PENDING_DIR, $POSTED_DIR)) {
    if (Test-Path $dir) {
        $existingDrafts += Get-ChildItem -Path $dir -Filter "draft-*.json" | Select-Object -ExpandProperty Name
    }
}
$existingList = if ($existingDrafts.Count -gt 0) { $existingDrafts -join ", " } else { "(none yet)" }

# ─── Determine which slots to generate ─────────────────────────────────────

if ($slot -gt 0 -and $slot -le 6) {
    $slotsToGenerate = @($slot)
} elseif ($count -gt 0) {
    # Legacy: -count N generates first N slots (backward compat with scheduler)
    $slotsToGenerate = @(1..[Math]::Min($count, 6))
} else {
    $slotsToGenerate = @(1..6)
}

# Build list of active slots with their platforms for today
$activeSlots = @()
foreach ($s in $slotsToGenerate) {
    $slotInfo = $SlotSchedule[$s]
    $activePlatforms = @()
    foreach ($platform in $slotInfo.Platforms.Keys) {
        if ($slotInfo.Platforms[$platform] -contains $today) {
            $activePlatforms += $platform
        }
    }
    if ($activePlatforms.Count -gt 0) {
        $activeSlots += @{ Slot = $s; Platforms = $activePlatforms; TimeEST = $slotInfo.TimeEST }
    }
}

Write-Log "INFO" "=== Content Generator started ($todayName, $($activeSlots.Count) active slots) ==="
foreach ($as in $activeSlots) {
    Write-Log "INFO" "  Slot $($as.Slot) ($($as.TimeEST) EST): $($as.Platforms -join ', ')"
}

if ($activeSlots.Count -eq 0) {
    Write-Log "INFO" "No active slots for today. Exiting."
    exit 0
}

# ─── Generate one draft per active slot ────────────────────────────────────

$generated = 0
foreach ($as in $activeSlots) {
    $s = $as.Slot
    $platforms = $as.Platforms

    $draftId = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-s$s"
    $draftFile = "draft-$draftId.json"
    $draftPath = Join-Path $REVIEW_DIR $draftFile

    # Determine X format: thread on Tue/Thu in slot 4, tweet otherwise
    $xFormat = "tweet"
    if ($s -eq 4 -and ($today -eq 1 -or $today -eq 3)) {
        $xFormat = "thread"
    }

    # Build platform-specific content instructions
    $platformInstructions = @()
    $jsonKeys = @()
    $validationKeys = @()
    foreach ($p in $platforms) {
        $formatKey = $p
        if ($p -eq "x") { $formatKey = "x_$xFormat" }
        $fmt = $PlatformFormats[$formatKey]
        $platformInstructions += "- $($fmt.Key.ToUpper()): $($fmt.Desc)"
        $jsonKeys += "    $($fmt.Example)"
        $validationKeys += $fmt.Key
    }
    $platformBlock = $platformInstructions -join "`n"
    $jsonBlock = $jsonKeys -join ",`n"
    $platformsList = ($platforms | Sort-Object) -join ", "
    $formatLabel = if ($xFormat -eq "thread" -and $platforms -contains "x") { "thread" } else { "post" }

    # Determine pillar and series for this slot
    $slotPillar = Get-PillarForSlot -SlotNum $s
    $slotSeries = Get-SeriesForSlot -SlotNum $s
    $pillarDesc = $PillarDescriptions[$slotPillar]
    $usedPillars = Get-TodaysPillars
    $usedPillarsList = if ($usedPillars.Count -gt 0) { $usedPillars -join ", " } else { "(none yet)" }

    $seriesBlock = ""
    if ($slotSeries) {
        $seriesBlock = @"

$($slotSeries.Desc)
This is a RECURRING SERIES - make it feel like part of a regular series, not a one-off.
"@
        Write-Log "INFO" "Generating slot $s draft ($platformsList, format=$formatLabel, pillar=$slotPillar, series=$($slotSeries.Series))..."
    } else {
        Write-Log "INFO" "Generating slot $s draft ($platformsList, format=$formatLabel, pillar=$slotPillar)..."
    }

    $prompt = @"
You are a social media marketer and content manager. You are NOT a coder or technical assistant.

Your task: Create a JSON file at this exact path: $draftPath

This draft is for POSTING SLOT $s ($($as.TimeEST) EST, $todayName).
Generate content ONLY for these platforms: $platformsList

CONTENT PILLAR FOR THIS DRAFT: $pillarDesc
$seriesBlock
Pillars already used today: $usedPillarsList
Make sure this draft's topic and angle is DIFFERENT from any pillar already used today.

CONTENT GUIDELINES:
$templates

EXISTING DRAFTS (avoid repeating these topics):
$existingList

PLATFORMS FOR THIS DRAFT:
$platformBlock

IMAGE VS TEXT-ONLY RULES:
- Pillar 4 (Proof/Results) posts: ALWAYS use image format for x, linkedin, facebook (stats and data are visual)
- Pillar 1 (Stop Losing Money) and Pillar 3 (Cheat Code): ~50% chance use image format (bold claims work as images)
- Pillar 2 (Freedom) and Pillar 5 (AI Fear): mostly text-only (narrative/story format)
- Engagement/wildcard posts: always text-only
- When using image format, image_text should be DIFFERENT and PUNCHIER than the text — not a copy

Write the file with EXACTLY this JSON structure:

{
  "id": "$draftId",
  "created_at": "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')",
  "status": "review",
  "slot": $s,
  "platforms": $('["' + ($validationKeys -join '", "') + '"]'),
  "format": "$formatLabel",
  "topic": "brief topic label",
  "pillar": "$slotPillar",
  "content": {
$jsonBlock
  }
}

CRITICAL RULES:
- Write the file to: $draftPath
- The "content" object MUST have ONLY these keys: $($validationKeys -join ", ")
- Do NOT include platforms not listed above
- reddit value MUST be a JSON object with "title" and "body" keys
- tiktok value MUST be a JSON object with "caption" and "image_text" keys
$(if ($xFormat -eq "thread") { '- x value MUST be a JSON array of 3-7 tweet strings (this is a THREAD)' } else { '- x can be a string (text-only) OR a JSON object with "text" and "image_text" keys' })
- Each platform version must be DIFFERENT in tone, length, and style
- Be specific, opinionated, and authentic — never sound like generic AI
- Every post must contain at least one concrete detail (a tool name, a number, a real scenario)
"@

    try {
        $output = claude --dangerously-skip-permissions -p $prompt 2>&1

        # Validate the file was created
        if (Test-Path $draftPath) {
            $fileContent = Get-Content -Path $draftPath -Raw -Encoding UTF8
            try {
                $parsed = $fileContent | ConvertFrom-Json
                if (-not $parsed.content) {
                    throw "Missing 'content' field"
                }
                # Validate expected platform keys exist
                foreach ($vk in $validationKeys) {
                    $val = $parsed.content.$vk
                    if ($null -eq $val) {
                        throw "Missing required platform key '$vk' in content"
                    }
                }
                Write-Log "INFO" "Draft saved: $draftFile (slot=$s, topic=$($parsed.topic), platforms=$platformsList)"
                $existingList = "$existingList, $draftFile"
                $generated++
            } catch {
                Write-Log "ERROR" "Draft file created but invalid JSON: $_"
                Remove-Item -Path $draftPath -Force
            }
        } else {
            Write-Log "ERROR" "Claude did not create the draft file at $draftPath"
            Write-Log "ERROR" "Claude output: $($output -join ' ')"
        }

    } catch {
        Write-Log "ERROR" "Failed to generate draft for slot ${s}: $_"
    }

    # Small delay between generations
    if ($as -ne $activeSlots[-1]) {
        Start-Sleep -Seconds 2
    }
}

# ─── Toast notification ────────────────────────────────────────────────────

try {
    $reviewCount = (Get-ChildItem -Path $REVIEW_DIR -Filter "draft-*.json" -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($reviewCount -gt 0) {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).InnerText = "Auto-Poster: $reviewCount drafts ready for review"
        $textNodes.Item(1).InnerText = "Open http://localhost:5111 to review and approve"
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        [Windows.UI.Notifications.ToastNotifier]::new("AutoPoster").Show($toast)
    }
} catch {
    Write-Log "WARN" "Could not send toast notification: $_"
}

Write-Log "INFO" "=== Content Generator finished ($generated/$($activeSlots.Count) drafts generated) ==="
