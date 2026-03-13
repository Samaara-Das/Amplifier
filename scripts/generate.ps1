# Auto-Poster Content Generator
# Calls Claude Code CLI to generate social media drafts

param(
    [int]$count = 0
)

# Config
$ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$ENV_FILE = Join-Path $ROOT "config\.env"
$TEMPLATES_FILE = Join-Path $ROOT "config\content-templates.md"
$PENDING_DIR = Join-Path $ROOT "drafts\pending"
$POSTED_DIR = Join-Path $ROOT "drafts\posted"
$LOG_DIR = Join-Path $ROOT "logs"
$LOG_FILE = Join-Path $LOG_DIR "generator.log"

# Ensure directories exist
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
if (Test-Path $PENDING_DIR) {
    $existingDrafts += Get-ChildItem -Path $PENDING_DIR -Filter "draft-*.json" | Select-Object -ExpandProperty Name
}
if (Test-Path $POSTED_DIR) {
    $existingDrafts += Get-ChildItem -Path $POSTED_DIR -Filter "draft-*.json" | Select-Object -ExpandProperty Name
}
$existingList = if ($existingDrafts.Count -gt 0) { $existingDrafts -join ", " } else { "(none yet)" }

# Generate drafts
for ($i = 1; $i -le $count; $i++) {
    $draftId = Get-Date -Format "yyyyMMdd-HHmmss"
    # Add index suffix if generating multiple in same second
    if ($i -gt 1) { $draftId = "$draftId-$i" }
    $draftFile = "draft-$draftId.json"
    $draftPath = Join-Path $PENDING_DIR $draftFile

    Write-Log "INFO" "Generating draft $i of $count (ID: $draftId)..."

    $prompt = @"
You are a social media marketer and content manager. You are NOT a coder or technical assistant.

Your task: Create a JSON file at this exact path: $draftPath

The file must contain ONE social media post with DIFFERENT versions for ALL 6 platforms.

CONTENT GUIDELINES:
$templates

EXISTING DRAFTS (avoid repeating these topics):
$existingList

Write the file with EXACTLY this JSON structure (all 6 platform keys required):

{
  "id": "$draftId",
  "created_at": "$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')",
  "status": "pending",
  "topic": "brief topic label",
  "content": {
    "x": "X/Twitter version (max 280 chars, punchy, 1-3 hashtags)",
    "linkedin": "LinkedIn version (500-1500 chars, professional tone, line breaks, 3-5 hashtags at end)",
    "facebook": "Facebook version (200-800 chars, conversational, 0-2 hashtags)",
    "instagram": "Instagram caption (300-1200 chars, emojis, hashtags at end)",
    "reddit": {"title": "concise descriptive title 60-120 chars", "body": "detailed informative body 200-1500 chars, no hashtags, no emojis"},
    "tiktok": {"caption": "short punchy caption 100-300 chars with 3-5 hashtags", "image_text": "1-3 short punchy lines for text overlay on image"}
  }
}

CRITICAL RULES:
- Write the file to: $draftPath
- The "content" object MUST have exactly 6 keys: x, linkedin, facebook, instagram, reddit, tiktok
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

Write-Log "INFO" "=== Content Generator finished ==="
