"""UGC photorealism prompt engineering with 8-category framework.

Every image prompt includes 8 elements that push AI models toward
authentic casual photography rather than "editorial" aesthetics:

    [Realism trigger] + [Subject with product] + [Camera/lens] +
    [Lighting] + [Texture] + [Color] + [Composition] + [Quality markers]

Each category draws from randomized pools so no two prompts feel the same.
"""

from __future__ import annotations

import random

# ── Category Pools ───────────────────────────────────────────────

REALISM_TRIGGERS = [
    "raw unedited phone photo",
    "candid snapshot",
    "casual photo taken in passing",
    "authentic everyday photo",
    "real-life candid moment",
    "unstaged personal photo",
    "genuine unfiltered photograph",
]

CAMERAS = [
    "iPhone 15 Pro main camera",
    "iPhone 14 front camera",
    "Samsung Galaxy S24 Ultra",
    "Google Pixel 8 Pro",
    "smartphone camera",
    "iPhone 13 selfie camera",
    "phone camera portrait mode",
]

LIGHTING = [
    "natural window light with soft shadows",
    "overhead fluorescent lighting with visible shadows",
    "warm golden hour light from the side",
    "dimly lit room with single window",
    "bright midday sun with harsh shadows on face",
    "mixed indoor lighting with slightly warm tone",
    "overcast daylight through a window",
    "soft morning light, slightly blue",
    "kitchen lighting with warm overhead bulb",
    "bathroom vanity lighting, bright and slightly harsh",
]

TEXTURES = [
    "visible skin pores, natural fabric grain, faint blemishes",
    "slightly wrinkled shirt, authentic fabric texture",
    "natural oiliness, subtle redness, nothing airbrushed or plasticky",
    "real hair texture, casual appearance, not styled",
    "visible wood grain on table, fingerprints on glass",
    "slightly dusty surface, natural wear marks",
]

COLORS = [
    "slightly muted colors, not oversaturated",
    "natural color palette, like a phone camera auto-processed",
    "warm tones from indoor lighting",
    "cool blue tones from overcast sky",
    "slightly washed out colors, casual processing",
]

COMPOSITIONS = [
    "slightly off-center framing, casual snapshot feel",
    "product held at a natural angle, partial hand visible",
    "cluttered desk in background, everyday setting",
    "product on a kitchen counter, morning routine context",
    "bathroom counter with everyday items around it",
    "coffee shop table, out-of-focus people in background",
    "product on a nightstand next to a phone",
    "casual flat lay on a messy bed, top-down angle",
    "product held up to camera, selfie perspective",
]

QUALITY_MARKERS = [
    "slight motion blur, not perfectly sharp",
    "natural bokeh from phone portrait mode",
    "slightly overexposed in bright areas",
    "minor lens flare from light source",
    "authentic phone camera quality, not DSLR",
    "very slight tilt, not perfectly level",
]

# Negative prompt — what to avoid
NEGATIVE_PROMPT = (
    "stock photo, commercial lighting, studio backdrop, professional model, "
    "perfect skin, symmetrical composition, centered framing, HDR, oversaturated, "
    "AI-generated, digital art, illustration, 3D render, cartoon, anime, "
    "watermark, text overlay, logo, blurry, low quality"
)


# ── Settings-based subjects ──────────────────────────────────────

PRODUCT_SETTINGS = [
    "on a desk next to a laptop",
    "on a kitchen counter, morning light",
    "in someone's hand, outdoor café",
    "on a bathroom counter with everyday items",
    "on a nightstand next to a coffee mug",
    "in a bag, partially visible, on-the-go",
    "on a table at a coffee shop",
    "on a windowsill with natural light",
    "in a car cupholder, parked",
    "on a gym bench next to a water bottle",
]


# ── Prompt Builders ──────────────────────────────────────────────

def build_ugc_prompt(
    product_description: str,
    setting: str | None = None,
    platform: str | None = None,
) -> str:
    """Build a full 8-category photorealism prompt for text-to-image.

    Args:
        product_description: What the product is (e.g. "Nike Air Max sneakers").
        setting: Optional specific setting. If None, randomly selected.
        platform: Optional platform name for aspect ratio hints.

    Returns: A detailed prompt string.
    """
    if setting is None:
        setting = random.choice(PRODUCT_SETTINGS)

    subject = f"a person casually using {product_description} {setting}"

    prompt = (
        f"{random.choice(REALISM_TRIGGERS)}, {subject}, "
        f"shot on {random.choice(CAMERAS)}, "
        f"{random.choice(LIGHTING)}, "
        f"{random.choice(TEXTURES)}, "
        f"{random.choice(COLORS)}, "
        f"{random.choice(COMPOSITIONS)}, "
        f"{random.choice(QUALITY_MARKERS)}"
    )

    return prompt


def build_img2img_prompt(
    product_name: str,
    campaign_brief: str | None = None,
) -> str:
    """Build a prompt for image-to-image transformation of a product photo.

    The prompt guides the model to generate a UGC-style scene around the product.
    """
    setting = random.choice(PRODUCT_SETTINGS)
    camera = random.choice(CAMERAS)
    lighting = random.choice(LIGHTING)

    prompt = (
        f"Transform this product photo into an authentic lifestyle photograph. "
        f"Show {product_name} {setting}. "
        f"Make it look like a candid {camera} photo with {lighting}. "
        f"The product should be clearly visible but the overall image should feel "
        f"like a casual everyday photo, not a commercial shoot. "
        f"Include natural imperfections: {random.choice(TEXTURES)}."
    )

    if campaign_brief:
        # Add a hint about the campaign tone
        prompt += f" The overall mood should convey: {campaign_brief[:100]}."

    return prompt


def build_simple_prompt(description: str) -> str:
    """Build a simple enhanced prompt from a basic description.

    For cases where the content generator already produced an image_prompt
    and we just want to add UGC authenticity cues.
    """
    return (
        f"{random.choice(REALISM_TRIGGERS)}, {description}, "
        f"shot on {random.choice(CAMERAS)}, "
        f"{random.choice(LIGHTING)}, "
        f"{random.choice(QUALITY_MARKERS)}"
    )


def get_negative_prompt() -> str:
    """Return the standard negative prompt."""
    return NEGATIVE_PROMPT
