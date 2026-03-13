# Auto-Poster Content Generator
# Calls Claude Code CLI to generate social media drafts

param(
    [int]$count = 0
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

# Load .env for GENERATE_COUNT default
$defaultCount = 2
if (Test-Path $ENV_FILE) {
    Get-Content $ENV_FILE | ForEach-Object {
        if ($_ -match '^GENERATE_COUNT=(\d+)') {
            $defaultCount = [int]$Matches[1]
        }
    }
}
if ($count -eq 0) { $count = $defaultCount }

# Unset CLAUDECODE to allow nested CLI calls (e.g. when run from within Claude Code)
$env:CLAUDECODE = $null

Write-Log "INFO" "=== Content Generator started (count=$count) ==="

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

# Generate drafts
for ($i = 1; $i -le $count; $i++) {
    $draftId = Get-Date -Format "yyyyMMdd-HHmmss"
    # Add index suffix if generating multiple in same second
    if ($i -gt 1) { $draftId = "$draftId-$i" }
    $draftFile = "draft-$draftId.json"
    $draftPath = Join-Path $REVIEW_DIR $draftFile

    Write-Log "INFO" "Generating draft $i of $count (ID: $draftId)..."

    $prompt = @"
You are a social media marketer and content manager. You are NOT a coder or technical assistant.

Your task: Create a JSON file at this exact path: $draftPath

The file must contain ONE social media post with DIFFERENT versions for ALL 6 platforms.

CONTENT GUIDELINES:
$templates

EXISTING DRAFTS (avoid repeating these topics):
$existingList

Write the file with EXACTLY this JSON structure (all 6 platform keys required).

For x, linkedin, and facebook: you can provide EITHER a plain string (text-only post) OR a JSON object with "text" and "image_text" keys (text + branded image post).
- Text-only: "x": "your tweet text here"
- Text + image: "x": {"text": "your tweet text here", "image_text": "1-2 BOLD punchy lines for branded image overlay"}

IMAGE VS TEXT-ONLY RULES:
- Pillar 4 (Proof/Results) posts: ALWAYS use image format for x, linkedin, facebook (stats and data are visual)
- Pillar 1 (Stop Losing Money) and Pillar 3 (Cheat Code): ~50% chance use image format (bold claims work as images)
- Pillar 2 (Freedom) and Pillar 5 (AI Fear): mostly text-only (narrative/story format)
- Engagement/wildcard posts: always text-only
- When using image format, image_text should be DIFFERENT and PUNCHIER than the text — not a copy

{
  "id": "$draftId",
  "created_at": "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')",
  "status": "review",
  "topic": "brief topic label",
  "pillar": "1|2|3|4|5|wildcard",
  "content": {
    "x": "X/Twitter version (max 280 chars, punchy, 1-3 hashtags) OR {text, image_text} object",
    "linkedin": "LinkedIn version (500-1500 chars, professional tone, line breaks, 3-5 hashtags at end) OR {text, image_text} object",
    "facebook": "Facebook version (200-800 chars, conversational, 0-2 hashtags) OR {text, image_text} object",
    "instagram": "Instagram caption (300-1200 chars, emojis, hashtags at end)",
    "reddit": {"title": "concise descriptive title 60-120 chars", "body": "detailed informative body 200-1500 chars, no hashtags, no emojis"},
    "tiktok": {"caption": "short punchy caption 100-300 chars with 3-5 hashtags", "image_text": "1-3 short punchy lines for text overlay on image"}
  }
}

CRITICAL RULES:
- Write the file to: $draftPath
- The "content" object MUST have exactly 6 keys: x, linkedin, facebook, instagram, reddit, tiktok
- x, linkedin, facebook can be a string (text-only) OR a JSON object with "text" and "image_text" keys
- reddit value MUST be a JSON object with "title" and "body" keys
- tiktok value MUST be a JSON object with "caption" and "image_text" keys
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
                if (-not $parsed.content.x -or -not $parsed.content.linkedin -or -not $parsed.content.facebook) {
                    throw "Missing required platform keys in 'content' (need x, linkedin, facebook)"
                }
                Write-Log "INFO" "Draft saved: $draftFile (topic: $($parsed.topic))"
                $existingList = "$existingList, $draftFile"
            } catch {
                Write-Log "ERROR" "Draft file created but invalid JSON: $_"
                Remove-Item -Path $draftPath -Force
            }
        } else {
            Write-Log "ERROR" "Claude did not create the draft file at $draftPath"
            Write-Log "ERROR" "Claude output: $($output -join ' ')"
        }

    } catch {
        Write-Log "ERROR" "Failed to generate draft $draftId : $_"
    }

    # Small delay between generations
    if ($i -lt $count) {
        Start-Sleep -Seconds 2
    }
}

# Send Windows toast notification that drafts are ready for review
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

Write-Log "INFO" "=== Content Generator finished ==="
