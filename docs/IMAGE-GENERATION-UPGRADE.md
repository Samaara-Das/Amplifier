# Image Generation Upgrade — Complete Specification

**Date**: April 3, 2026
**Status**: Planned — ready to implement
**Dependency**: Requires GEMINI_API_KEY (already configured)

---

## 1. Why This Matters

Amplifier generates content for campaigns that real people post on their real social media accounts. If the images look AI-generated, creators won't approve them, followers will scroll past, and companies won't see engagement. The difference between "AI slop" and "genuine UGC" determines whether the platform works.

Currently, our image generation scores ~6/10 on UGC authenticity. This upgrade targets 8/10+ through better models, a post-processing pipeline, image-to-image capability, and smarter prompting — all at zero marginal cost using free-tier APIs.

---

## 2. Current State

### What Exists

**Image generation** lives in `scripts/utils/content_generator.py` as 4 standalone functions with a fallback chain:

| Provider | Function | Free Quota | Quality | Status |
|---|---|---|---|---|
| Cloudflare Workers AI (FLUX.1 Schnell, 4 steps) | `_cloudflare_image()` | ~20-50/day | 6/10 | Primary |
| Together AI (FLUX.1 Schnell) | `_together_image()` | $25 one-time credit | 6/10 | Secondary |
| Pollinations AI (turbo) | `_pollinations_image()` | Rate-limited, no signup | 5/10 (variable) | Tertiary |
| PIL branded template | `_pil_fallback_image()` | Unlimited | 2/10 (text on gradient) | Last resort |

**What's missing:**
- No image-to-image (img2img) — can't use campaign product photos as input
- No post-processing — images come out "too clean," obviously AI-generated
- No Gemini image generation — despite having the API key and it offering 500 free images/day
- No upscaling — small images can't be used on high-res platforms
- No provider abstraction — image providers are bare functions, not pluggable like our new AiManager for text
- The `image_generator.py` source file is missing (only `.pyc` cached) — `generate_landscape_image()` and `generate_tiktok_video()` referenced from `post.py` and `content_generator.py`

### How Images Are Used Today

1. Content generator produces text content + an `image_prompt` field per campaign
2. Each platform posting function (`post_to_x()`, `post_to_linkedin()`, etc.) checks for an `image_path` on the draft
3. If no external image provided and `image_text` exists, it calls `generate_landscape_image()` to create one
4. The image is uploaded to the platform alongside the text content
5. After posting, the temp image is deleted

---

## 3. Target Architecture

### Three Content Modes

| Mode | Input | Output | Use Case |
|---|---|---|---|
| **Text → Text** | Campaign brief | Platform-native captions | Already working via AiManager |
| **Text → Image** | Text prompt (from campaign brief) | Generated lifestyle/product photo | Upgrade: better models, post-processing, UGC prompting |
| **Image → Image** | Product photo (from campaign assets) + prompt | UGC-style scene featuring the real product | New capability: Gemini edit_image / generate_content with image input |

### Image Provider Abstraction

Same pattern as `scripts/ai/manager.py` for text — an `ImageProvider` interface with pluggable implementations:

```python
# scripts/ai/image_provider.py
class ImageProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    async def text_to_image(self, prompt: str, output_path: str,
                            width: int = 1080, height: int = 1080) -> str:
        """Generate image from text prompt. Returns output path."""
        ...

    async def image_to_image(self, source_image_path: str, prompt: str,
                             output_path: str) -> str:
        """Transform source image guided by prompt. Returns output path.
        Raises NotImplementedError if provider doesn't support img2img."""
        raise NotImplementedError(f"{self.name} does not support image-to-image")
```

```python
# scripts/ai/image_manager.py
class ImageManager:
    def register(self, provider: ImageProvider): ...
    def get_default(self) -> ImageProvider | None: ...

    async def generate(self, prompt, output_path, width=1080, height=1080) -> str:
        """Text-to-image with auto-fallback across providers."""

    async def transform(self, source_image, prompt, output_path) -> str:
        """Image-to-image with auto-fallback (only tries providers that support it)."""
```

### Provider Implementations

#### 1. Gemini Flash Image (NEW — Primary)

**Why first**: 500 free images/day, best quality among free tiers (★★★★), supports both text-to-image AND image-to-image natively.

```python
# scripts/ai/image_providers/gemini_image.py

class GeminiImageProvider(ImageProvider):
    name = "gemini_image"

    async def text_to_image(self, prompt, output_path, width=1080, height=1080):
        """Use Gemini generate_images API."""
        response = self.client.models.generate_images(
            model="gemini-2.0-flash-exp",  # or imagen-3.0-generate-002
            prompt=self._enhance_prompt(prompt),
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",  # or "16:9" for landscape
                output_mime_type="image/jpeg",
                output_compression_quality=85,
                person_generation="ALLOW_ADULT",
                safety_filter_level="BLOCK_ONLY_HIGH",
                add_watermark=False,
            ),
        )
        # Save first image to output_path
        image_bytes = response.generated_images[0].image.image_bytes
        Path(output_path).write_bytes(image_bytes)
        return output_path

    async def image_to_image(self, source_image_path, prompt, output_path):
        """Use Gemini edit_image API — transform product photo into UGC scene."""
        from google.genai import types
        from PIL import Image
        import io

        # Load source image
        source_image = Image.open(source_image_path)
        img_bytes = io.BytesIO()
        source_image.save(img_bytes, format="JPEG")
        img_bytes = img_bytes.getvalue()

        response = self.client.models.edit_image(
            model="gemini-2.0-flash-exp",  # or imagen-3.0-capability-001
            prompt=self._enhance_prompt(prompt),
            reference_images=[
                types.RawReferenceImage(
                    reference_image=types.Image(image_bytes=img_bytes),
                    reference_id=0,
                )
            ],
            config=types.EditImageConfig(
                number_of_images=1,
                output_mime_type="image/jpeg",
                output_compression_quality=85,
                person_generation="ALLOW_ADULT",
                safety_filter_level="BLOCK_ONLY_HIGH",
                edit_mode="INPAINT_INSERTION",  # or "PRODUCT_IMAGE" if available
            ),
        )
        image_bytes = response.generated_images[0].image.image_bytes
        Path(output_path).write_bytes(image_bytes)
        return output_path
```

**Available Gemini image methods:**
- `generate_images(model, prompt, config)` — Text-to-image. 500 free/day.
- `edit_image(model, prompt, reference_images, config)` — Image-to-image. Accepts source images + text prompt to guide the edit. Supports modes: INPAINT_INSERTION, INPAINT_REMOVAL, OUTPAINT, PRODUCT_IMAGE.
- `upscale_image(model, image, config)` — 2x/4x upscaling.
- `recontext_image(model, image, prompt)` — Change the background/context of an image while preserving the subject (perfect for placing a product in a new scene).

#### 2. Cloudflare Workers AI (Existing — upgraded to FLUX.2 Klein)

Keep as secondary. Upgrade model from FLUX.1 Schnell to FLUX.2 Klein (sub-second, better quality, same free tier).

```python
class CloudflareImageProvider(ImageProvider):
    name = "cloudflare"

    async def text_to_image(self, prompt, output_path, width=1080, height=1080):
        model = "@cf/black-forest-labs/flux-2-klein"  # upgraded from flux-1-schnell
        # ... same HTTP API call, better model
```

#### 3. Pollinations AI (Existing — keep as-is)

Free fallback, no signup, variable quality. Keep as tertiary.

#### 4. PIL Branded Template (Existing — last resort)

Dark gradient + white text. Only used when all API providers fail.

### Fallback Chain Order

```
1. Gemini Flash Image  (500/day free, ★★★★, txt2img + img2img)
2. Cloudflare FLUX.2 Klein  (20-50/day free, ★★★, txt2img only)
3. Pollinations AI  (rate-limited, ★★★ variable, txt2img only)
4. PIL branded template  (unlimited, ★★, text-on-gradient)
```

For image-to-image, only Gemini supports it — so the fallback for img2img is: try Gemini, if it fails generate a text-to-image from the product description instead.

---

## 4. Post-Processing Pipeline

Every generated image (from any provider) runs through this pipeline before being saved. This is the single biggest quality lever — it transforms "obviously AI" into "could be a phone photo."

### Pipeline Steps

```python
# scripts/ai/image_postprocess.py

async def postprocess_for_ugc(image_path: str, output_path: str = None) -> str:
    """Apply UGC authenticity post-processing to an AI-generated image.

    Steps (in order):
    1. Slight desaturation (reduce vibrancy that screams "AI")
    2. Warm/cool color cast (mimic phone camera processing)
    3. Film grain (models literally cannot generate authentic grain)
    4. Subtle vignetting (mimic phone lens characteristics)
    5. JPEG compression at quality 80 (introduce natural artifacts)
    6. EXIF metadata injection (mimic common phone cameras)
    """
```

### Step Details

#### 1. Desaturation
AI images are oversaturated by default. Reduce saturation by 10-15%.

```python
from PIL import ImageEnhance
enhancer = ImageEnhance.Color(img)
img = enhancer.enhance(0.87)  # 13% desaturation
```

#### 2. Color Cast
Phone cameras apply processing that gives a warm or cool tone. Randomly apply one.

```python
import numpy as np
# Warm cast: +5 red, +3 green, -2 blue
# Cool cast: -3 red, +2 green, +5 blue
arr = np.array(img).astype(np.int16)
if random.random() < 0.5:
    arr[:,:,0] = np.clip(arr[:,:,0] + 5, 0, 255)   # warm
    arr[:,:,2] = np.clip(arr[:,:,2] - 2, 0, 255)
else:
    arr[:,:,0] = np.clip(arr[:,:,0] - 3, 0, 255)   # cool
    arr[:,:,2] = np.clip(arr[:,:,2] + 5, 0, 255)
```

#### 3. Film Grain
Diffusion models are architecturally designed to remove noise — they literally cannot generate authentic grain. This is the #1 tell of AI images.

```python
noise = np.random.normal(0, 8, arr.shape).astype(np.int16)  # Gaussian noise, sigma=8
arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
```

#### 4. Vignetting
Phone lenses naturally darken corners. Apply a radial gradient mask.

```python
rows, cols = arr.shape[:2]
Y, X = np.ogrid[:rows, :cols]
center_y, center_x = rows / 2, cols / 2
radius = max(rows, cols) * 0.7
vignette = 1.0 - 0.3 * ((X - center_x)**2 + (Y - center_y)**2) / radius**2
vignette = np.clip(vignette, 0.7, 1.0)
arr = (arr * vignette[:,:,np.newaxis]).astype(np.uint8)
```

#### 5. JPEG Compression
Save as JPEG at quality 80 (not PNG). The absence of compression artifacts is suspicious.

```python
img.save(output_path, "JPEG", quality=80)
```

#### 6. EXIF Metadata
Inject metadata mimicking common phone cameras. Most social platforms strip EXIF on upload, but some don't — and it adds to the authenticity if the image is inspected.

```python
import piexif
exif_dict = {
    "0th": {
        piexif.ImageIFD.Make: "Apple",
        piexif.ImageIFD.Model: "iPhone 15 Pro",
        piexif.ImageIFD.Software: "17.4.1",
    },
    "Exif": {
        piexif.ExifIFD.DateTimeOriginal: datetime.now().strftime("%Y:%m:%d %H:%M:%S"),
        piexif.ExifIFD.FocalLength: (4200, 1000),  # 4.2mm = iPhone main lens
        piexif.ExifIFD.ISOSpeedRatings: random.choice([100, 200, 400, 800]),
    },
}
```

### Platform-Specific Sizing

| Platform | Ideal Size | Aspect Ratio |
|---|---|---|
| X | 1200x675 | 16:9 |
| LinkedIn | 1200x627 | ~1.91:1 |
| Facebook | 1200x630 | ~1.91:1 |
| Reddit | 1080x1080 | 1:1 |
| Instagram | 1080x1080 | 1:1 |
| TikTok | 1080x1920 | 9:16 |

The post-processing pipeline should resize to platform-optimal dimensions before applying effects.

---

## 5. UGC Prompt Engineering

### The 8-Category Photorealism Framework

Every image prompt should include these 8 elements:

```
[Realism trigger] + [Subject] + [Camera/lens] + [Lighting] +
[Texture] + [Color] + [Composition] + [Grain/quality]
```

### Prompt Template for Campaign Images

```python
UGC_IMAGE_PROMPT_TEMPLATE = """
{realism_trigger}, {subject_with_product},
shot on {camera}, {lens_spec},
{lighting_description},
{texture_details},
{color_palette},
{composition_style},
{quality_markers}
"""

# Randomized pools for each category
REALISM_TRIGGERS = [
    "raw unedited phone photo",
    "candid snapshot",
    "casual photo taken in passing",
    "authentic everyday photo",
    "real-life candid moment",
]

CAMERAS = [
    "iPhone 15 Pro front camera",
    "Samsung Galaxy S24 Ultra",
    "iPhone 14",
    "Google Pixel 8 Pro",
    "smartphone selfie camera",
]

LIGHTING = [
    "natural window light with soft shadows",
    "overhead fluorescent lighting with strong shadows",
    "warm golden hour light from the side",
    "dimly lit room with single window",
    "bright midday sun with harsh shadows",
    "mixed indoor lighting, slightly warm",
]

TEXTURES = [
    "visible skin pores, natural fabric grain",
    "slightly wrinkled shirt, authentic fabric texture",
    "natural oiliness, subtle redness, nothing airbrushed",
    "real hair texture, casual appearance",
]

COMPOSITIONS = [
    "slightly off-center framing, casual snapshot feel",
    "product held at a natural angle, partial hand visible",
    "cluttered desk in background, everyday setting",
    "product on a kitchen counter, morning routine",
    "bathroom counter with natural mess, real-life setting",
]

QUALITY = [
    "slight motion blur, not perfectly sharp",
    "natural bokeh from phone portrait mode",
    "slightly overexposed in bright areas",
    "minor lens flare from light source",
]
```

### Prompt Construction Flow

```
Campaign brief → extract product name, key features, setting
    ↓
Build subject: "person casually using [product] at [setting]"
    ↓
Randomly select one from each category pool
    ↓
Assemble into 8-category prompt
    ↓
For img2img: prefix with "realistic photo featuring this product, "
             + pass product image as reference
```

### Negative Prompt (for providers that support it)

```
"stock photo, commercial lighting, studio backdrop, professional model,
perfect skin, symmetrical composition, centered framing, HDR, oversaturated,
AI-generated, digital art, illustration, 3D render, cartoon, anime,
watermark, text overlay, logo"
```

---

## 6. Image-to-Image Workflow

### When to Use img2img vs txt2img

| Scenario | Mode | Input |
|---|---|---|
| Campaign has product photos in assets | **img2img** | Product photo + scene prompt |
| Campaign has no images, only description | **txt2img** | Generated prompt from brief |
| Campaign has logos but no product photos | **txt2img** | Logo not suitable for img2img |

### img2img Flow

```
1. Campaign has assets.image_urls → download product photos
2. Pick the best product photo (highest resolution, clearest product shot)
3. Build img2img prompt:
   "Authentic lifestyle photo featuring this product.
    [Person/hand] using the product in [natural setting].
    Shot on iPhone, natural lighting, casual composition.
    The product should be clearly visible but the scene should feel candid."
4. Call image_manager.transform(product_photo, prompt, output_path)
5. Post-process result (grain, compression, EXIF, etc.)
6. Save as platform-sized JPEG
```

### Gemini's img2img Options

| Method | Best For |
|---|---|
| `edit_image()` with INPAINT_INSERTION | Place product into a new scene |
| `recontext_image()` | Change the background while keeping the product identical |
| `generate_content()` with image input | Flexible: describe what you want, include reference image |

For MVP, `generate_content()` with image input is the simplest — send the product photo + prompt to Gemini's multimodal model and ask for a new image. This uses the same API and quota as text generation.

---

## 7. Integration Points

### Where Image Generation Gets Called

1. **Background agent** (`generate_daily_content()`) — generates content + image for each campaign daily
2. **Platform posting functions** (`post_to_x()`, etc.) — generate image on-the-fly if draft has `image_text` but no `image_path`
3. **User app** ("Regenerate" button) — regenerate content including image

### What Changes in Existing Code

| File | Change |
|---|---|
| `scripts/ai/image_provider.py` | NEW: Abstract ImageProvider base class |
| `scripts/ai/image_manager.py` | NEW: ImageManager with registry + fallback |
| `scripts/ai/image_providers/gemini_image.py` | NEW: Gemini text-to-image + image-to-image |
| `scripts/ai/image_providers/cloudflare_image.py` | NEW: Cloudflare FLUX.2 Klein (extracted from content_generator.py) |
| `scripts/ai/image_providers/pollinations_image.py` | NEW: Pollinations (extracted from content_generator.py) |
| `scripts/ai/image_providers/pil_fallback.py` | NEW: PIL branded template (extracted from content_generator.py) |
| `scripts/ai/image_postprocess.py` | NEW: UGC post-processing pipeline |
| `scripts/ai/image_prompts.py` | NEW: 8-category prompt builder with randomized pools |
| `scripts/utils/content_generator.py` | MODIFIED: Replace inline `_cloudflare_image()`, `_together_image()`, etc. with `image_manager.generate()` call |
| `scripts/post.py` | MODIFIED: Replace `from utils.image_generator import generate_landscape_image` with `image_manager.generate()` |
| `scripts/background_agent.py` | MODIFIED: Use img2img when campaign has product photos in assets |

### New Dependencies

| Package | Purpose | Already Installed? |
|---|---|---|
| `google-genai` | Gemini image generation | Yes (used for text gen) |
| `Pillow` | Post-processing pipeline | Yes (used for PIL fallback) |
| `numpy` | Grain, vignetting, color cast math | Yes (common dependency) |
| `piexif` | EXIF metadata injection | **No — needs `pip install piexif`** |

---

## 8. Implementation Sequence

```
Step 1: Image provider abstraction
├── Create ImageProvider base class
├── Create ImageManager with registry + fallback
├── Extract existing providers into provider classes
└── Wire ImageManager into content_generator.py

Step 2: Add Gemini image provider
├── Implement text_to_image via generate_images API
├── Implement image_to_image via edit_image / generate_content API
├── Test with real Gemini API key
└── Make it the primary provider

Step 3: Post-processing pipeline
├── Build postprocess_for_ugc() with all 6 steps
├── Add platform-specific resize
├── Integrate into ImageManager (auto-runs after every generation)
└── Test before/after quality comparison

Step 4: UGC prompt engineering
├── Build 8-category prompt template with randomized pools
├── Build img2img prompt template for product photos
├── Add negative prompt support
└── Integrate into content_generator.py prompt building

Step 5: Image-to-image integration
├── Detect campaign product photos in assets
├── Download and cache product photos locally
├── Route to img2img when product photos available
├── Fall back to txt2img when no product photos
└── Test with real campaign data

Step 6: Clean up legacy code
├── Remove _cloudflare_image(), _together_image(), etc. from content_generator.py
├── Remove references to missing image_generator.py
├── Update post.py to use ImageManager instead of generate_landscape_image()
└── Add piexif to requirements.txt
```

---

## 9. Cost Analysis

### At Launch (50-200 images/day)

| Provider | Daily Images | Monthly Cost |
|---|---|---|
| Gemini Flash Image | 500 (free tier) | **$0** |
| Cloudflare FLUX.2 Klein | 20-50 overflow | **$0** |
| Pollinations | ~10 overflow | **$0** |
| **Total** | 200/day max | **$0/month** |

### At Growth (500-2,000 images/day)

| Provider | Daily Images | Monthly Cost |
|---|---|---|
| Gemini Flash Image | 500 (free tier) | **$0** |
| Gemini paid overflow | 500-1,500 | **$19.50-$58.50** ($0.039/image) |
| Cloudflare (burst) | ~50 | **$0** |
| **Total** | 2,000/day max | **$0-$59/month** |

### At Scale (5,000+ images/day)

Self-host FLUX.1 Dev on SaladCloud RTX 4090 ($0.16/hr). 5,000 images/day = 4.2 GPU-hours = **$0.67/day = $20/month**. Keep Gemini as primary for img2img (API-only feature), self-hosted for bulk txt2img.

---

## 10. Quality Metrics

### How to Measure UGC Authenticity

| Metric | How to Test | Target |
|---|---|---|
| Human eval | Show 10 AI images + 10 real UGC to 5 people, ask which are real | >60% misidentification rate |
| AI detector score | Run through Hive Moderation or Illuminarty AI detector | <70% "AI-generated" confidence |
| Creator approval rate | Track what % of generated images creators approve vs reject | >70% approval |
| Engagement comparison | Compare engagement on posts with AI images vs text-only | AI image posts ≥ text-only |

### Before/After Benchmarks to Run

1. Generate 20 images with current pipeline (FLUX.1 Schnell, no post-processing)
2. Generate 20 images with new pipeline (Gemini Flash, post-processed)
3. Run both sets through an AI detector
4. Show both sets to 5 people — which ones could be real photos?
5. Post both types to a test account — compare engagement

---

## 11. What We're NOT Building

| Feature | Why Not |
|---|---|
| On-device inference | FLUX on CPU = 15-60 min/image. API is 3 seconds. |
| LoRA fine-tuning | Requires GPU infrastructure. Quality gains from prompting + post-processing are larger and cheaper. |
| Video generation | Separate feature (Task #56 in backlog). Images first. |
| Self-hosted GPU | Overkill at launch volume. Build when we hit 2,000+ images/day. |
| Portkey/LiteLLM gateway | Over-engineering for 4 providers. Simple Python fallback chain works. |
| IP-Adapter/ControlNet | Requires custom model pipelines. Gemini's native img2img is simpler and free. |
