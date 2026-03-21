# Amplifier Campaign Content Generator
# Takes a campaign brief from the server and generates platform-specific content
# Uses Claude Code CLI (same as generate.ps1 but driven by campaign data instead of content-templates)

param(
    [Parameter(Mandatory=$true)]
    [string]$CampaignFile   # Path to campaign JSON file (from local DB export)
)

# Config
$ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$ENV_FILE = Join-Path $ROOT "config\.env"
$REVIEW_DIR = Join-Path $ROOT "drafts\campaign_review"
$LOG_DIR = Join-Path $ROOT "logs"
$LOG_FILE = Join-Path $LOG_DIR "campaign_generator.log"

# Ensure directories exist
New-Item -ItemType Directory -Path $REVIEW_DIR -Force | Out-Null
New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null

function Write-Log {
    param([string]$Level, [string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp - $Level - $Message"
    Add-Content -Path $LOG_FILE -Value $entry -Encoding UTF8
    Write-Host $entry
}

# Load campaign data
if (-not (Test-Path $CampaignFile)) {
    Write-Log "ERROR" "Campaign file not found: $CampaignFile"
    exit 1
}

$campaign = Get-Content -Path $CampaignFile -Raw | ConvertFrom-Json
$campaignId = $campaign.campaign_id
$assignmentId = $campaign.assignment_id
$title = $campaign.title
$brief = $campaign.brief
$contentGuidance = $campaign.content_guidance
$assets = $campaign.assets | ConvertTo-Json -Compress

Write-Log "INFO" "Generating content for campaign '$title' (ID: $campaignId)"

# Platform format instructions
$platformInstructions = @"
Generate content for ALL 6 social media platforms based on the campaign brief below.

OUTPUT FORMAT: Write a single valid JSON object with these keys:
{
    "x": "tweet text (max 280 chars, punchy, 1-3 hashtags)",
    "linkedin": "LinkedIn post (800-1300 chars, professional, line breaks, 3-5 hashtags)",
    "facebook": "Facebook post (200-800 chars, conversational, 0-2 hashtags)",
    "reddit": {"title": "title (60-120 chars)", "body": "detailed body (500-1500 chars, no hashtags)"},
    "tiktok": {"caption": "caption (100-300 chars, 3-5 hashtags)", "image_text": "BOLD\nPUNCHY\nLINES"},
    "instagram": "caption (300-1200 chars, emojis OK, hashtags at end)"
}

RULES:
- Each platform version must feel native to that platform
- Content must promote the campaign naturally — not feel like an ad
- Use the brand's tone/guidance if provided
- Make it engaging, attention-grabbing, and valuable to the reader
- The content should feel like the USER is genuinely recommending this, not a sponsored post
- Include the campaign's key message but adapt it for each platform's audience
- Reddit: be informative and data-driven, no promotional tone
- TikTok: bold and visual, designed for short attention spans
- X: punchy and shareable
- LinkedIn: professional and thought-leadership focused
- Facebook: conversational and community-oriented
- Instagram: visual language, lifestyle-oriented

IMPORTANT: Output ONLY the JSON object. No markdown, no code fences, no explanation.
"@

$prompt = @"
$platformInstructions

CAMPAIGN BRIEF:
Title: $title
Brief: $brief

$(if ($contentGuidance) { "CONTENT GUIDANCE:`n$contentGuidance" } else { "" })

$(if ($assets -ne '{}' -and $assets -ne 'null') { "ASSETS/LINKS:`n$assets" } else { "" })
"@

# Write prompt to temp file
$promptFile = Join-Path $env:TEMP "campaign_prompt_$campaignId.txt"
$prompt | Out-File -FilePath $promptFile -Encoding UTF8

# Unset CLAUDECODE env var to allow nested CLI calls
$savedClaudeCode = $env:CLAUDECODE
$env:CLAUDECODE = $null

Write-Log "INFO" "Invoking Claude CLI for campaign $campaignId..."

# Generate content via Claude CLI
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputFile = Join-Path $REVIEW_DIR "campaign-$campaignId-$timestamp.json"

try {
    $result = claude --dangerously-skip-permissions -p (Get-Content $promptFile -Raw) 2>&1

    # Restore env var
    $env:CLAUDECODE = $savedClaudeCode

    if ($LASTEXITCODE -ne 0) {
        Write-Log "ERROR" "Claude CLI failed for campaign $campaignId : $result"
        exit 1
    }

    # Extract JSON from result (handle potential markdown fences)
    $jsonText = $result -join "`n"
    if ($jsonText -match '```(?:json)?\s*\n([\s\S]*?)\n```') {
        $jsonText = $Matches[1]
    }

    # Validate JSON
    $content = $jsonText | ConvertFrom-Json

    # Build output file with campaign metadata
    $output = @{
        campaign_id = $campaignId
        assignment_id = $assignmentId
        title = $title
        content = @{
            x = $content.x
            linkedin = $content.linkedin
            facebook = $content.facebook
            reddit = $content.reddit
            tiktok = $content.tiktok
            instagram = $content.instagram
        }
        generated_at = (Get-Date -Format "o")
        status = "review"
    }

    $output | ConvertTo-Json -Depth 10 | Out-File -FilePath $outputFile -Encoding UTF8
    Write-Log "INFO" "Content generated for campaign $campaignId -> $outputFile"
    Write-Output $outputFile
}
catch {
    $env:CLAUDECODE = $savedClaudeCode
    Write-Log "ERROR" "Failed to generate content for campaign $campaignId : $_"
    exit 1
}
finally {
    # Clean up temp file
    if (Test-Path $promptFile) { Remove-Item $promptFile -Force }
}
