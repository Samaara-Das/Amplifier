"""Pipeline state schema — shared by all nodes."""

from typing import TypedDict


class PipelineState(TypedDict, total=False):
    # Input
    campaign: dict                      # Campaign brief from server
    enabled_platforms: list[str]        # Platforms to generate for

    # Profile extraction
    user_profiles: dict[str, dict]      # Platform -> {bio, recent_posts, style_notes}

    # Research
    research: list[dict]                # Research findings

    # Drafts
    drafts: dict[str, str]              # Platform -> draft text
    image_prompt: str                   # Image generation prompt
    image_path: str                     # Generated image path

    # Quality
    quality_scores: dict[str, float]    # Platform -> quality score (0-100)
    quality_issues: dict[str, list]     # Platform -> list of issues found

    # Output (same format as ContentGenerator for backward compat)
    output: dict                        # Final content dict matching old format
