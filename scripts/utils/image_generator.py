"""Generate branded text-on-image posts for TikTok and Instagram."""

import random
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


# Color schemes for variety
COLOR_SCHEMES = [
    {"bg": (15, 15, 35), "text": (255, 255, 255), "accent": (0, 212, 255)},
    {"bg": (25, 25, 25), "text": (240, 240, 240), "accent": (255, 107, 107)},
    {"bg": (10, 10, 30), "text": (255, 255, 255), "accent": (138, 43, 226)},
    {"bg": (20, 20, 20), "text": (255, 255, 255), "accent": (0, 255, 136)},
    {"bg": (30, 15, 30), "text": (255, 255, 255), "accent": (255, 165, 0)},
]

# TikTok photo post dimensions (9:16 vertical)
WIDTH = 1080
HEIGHT = 1920


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a clean font, fall back to default."""
    font_paths = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _get_bold_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a bold font."""
    font_paths = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return _get_font(size)


def generate_tiktok_image(image_text: str, output_path: str | Path) -> Path:
    """Generate a branded text-on-image for TikTok.

    Args:
        image_text: 1-3 lines of text to overlay on the image
        output_path: Where to save the PNG

    Returns:
        Path to the generated image
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    scheme = random.choice(COLOR_SCHEMES)
    bg_color = scheme["bg"]
    text_color = scheme["text"]
    accent_color = scheme["accent"]

    img = Image.new("RGB", (WIDTH, HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)

    # Draw subtle gradient overlay
    for y in range(HEIGHT):
        alpha = int(30 * (y / HEIGHT))
        draw.line([(0, y), (WIDTH, y)], fill=(
            min(bg_color[0] + alpha, 255),
            min(bg_color[1] + alpha, 255),
            min(bg_color[2] + alpha, 255),
        ))

    # Draw accent decorations
    draw.rectangle([(0, 0), (WIDTH, 6)], fill=accent_color)
    draw.rectangle([(0, HEIGHT - 6), (WIDTH, HEIGHT)], fill=accent_color)

    # Side accent bar
    draw.rectangle([(40, HEIGHT // 4), (46, 3 * HEIGHT // 4)], fill=accent_color)

    # Main text
    font_size = 72
    font = _get_bold_font(font_size)
    lines = image_text.split("\n")

    # Wrap long lines
    wrapped_lines = []
    for line in lines:
        wrapped = textwrap.wrap(line.strip(), width=22)
        wrapped_lines.extend(wrapped)
        wrapped_lines.append("")  # spacing between original lines
    # Remove trailing empty
    while wrapped_lines and wrapped_lines[-1] == "":
        wrapped_lines.pop()

    # Calculate total text height
    line_height = font_size + 20
    total_height = len(wrapped_lines) * line_height
    start_y = (HEIGHT - total_height) // 2

    for i, line in enumerate(wrapped_lines):
        if not line:
            continue
        y = start_y + i * line_height
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (WIDTH - text_width) // 2

        # Text shadow
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=font)
        draw.text((x, y), line, fill=text_color, font=font)

    # Watermark at bottom
    small_font = _get_font(28)
    watermark = "@autoposter"
    bbox = draw.textbbox((0, 0), watermark, font=small_font)
    wm_width = bbox[2] - bbox[0]
    draw.text(
        ((WIDTH - wm_width) // 2, HEIGHT - 80),
        watermark,
        fill=(*accent_color, 180),
        font=small_font,
    )

    img.save(str(output_path), "PNG", quality=95)
    return output_path


def generate_tiktok_video(image_text: str, output_path: str | Path, duration: int = 7) -> Path:
    """Generate a short video from a branded text-on-image for TikTok.

    TikTok web only supports video uploads, so we create a short MP4
    from the branded image with a subtle slow zoom (Ken Burns) effect.

    Args:
        image_text: 1-3 lines of text to overlay on the image
        output_path: Where to save the MP4 (extension will be forced to .mp4)
        duration: Video duration in seconds (default 7)

    Returns:
        Path to the generated MP4 video
    """
    from moviepy import ImageClip

    output_path = Path(output_path).with_suffix(".mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # First generate the branded image
    img_path = output_path.with_suffix(".png")
    generate_tiktok_image(image_text, img_path)

    # Create video from image with a slow zoom effect
    img_array = np.array(Image.open(img_path))
    clip = ImageClip(img_array, duration=duration)

    # Slow zoom: scale from 1.0x to 1.08x over duration
    def zoom_effect(get_frame, t):
        scale = 1.0 + 0.08 * (t / duration)
        frame = get_frame(t)
        h, w = frame.shape[:2]
        new_h, new_w = int(h * scale), int(w * scale)
        # Resize up
        zoomed = np.array(Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS))
        # Center crop back to original size
        y_start = (new_h - h) // 2
        x_start = (new_w - w) // 2
        return zoomed[y_start:y_start + h, x_start:x_start + w]

    clip = clip.transform(zoom_effect)

    clip.write_videofile(
        str(output_path),
        fps=24,
        codec="libx264",
        audio=False,
        preset="medium",
        logger=None,
    )

    # Clean up temp image
    try:
        img_path.unlink()
    except Exception:
        pass

    return output_path


def generate_instagram_image(caption_text: str, output_path: str | Path) -> Path:
    """Generate a square branded image for Instagram posts.

    Args:
        caption_text: Text to overlay on the image (truncated to ~100 chars)
        output_path: Where to save the PNG

    Returns:
        Path to the generated image
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    size = 1080  # Square format
    scheme = random.choice(COLOR_SCHEMES)
    bg_color = scheme["bg"]
    text_color = scheme["text"]
    accent_color = scheme["accent"]

    img = Image.new("RGB", (size, size), bg_color)
    draw = ImageDraw.Draw(img)

    # Gradient overlay
    for y in range(size):
        alpha = int(25 * (y / size))
        draw.line([(0, y), (size, y)], fill=(
            min(bg_color[0] + alpha, 255),
            min(bg_color[1] + alpha, 255),
            min(bg_color[2] + alpha, 255),
        ))

    # Accent borders
    draw.rectangle([(0, 0), (size, 5)], fill=accent_color)
    draw.rectangle([(0, size - 5), (size, size)], fill=accent_color)
    draw.rectangle([(0, 0), (5, size)], fill=accent_color)
    draw.rectangle([(size - 5, 0), (size, size)], fill=accent_color)

    # Main text — use first ~120 chars
    display_text = caption_text[:120].rsplit(" ", 1)[0] if len(caption_text) > 120 else caption_text
    # Strip trailing hashtags for the image
    if "#" in display_text:
        display_text = display_text[:display_text.index("#")].strip()

    font_size = 56
    font = _get_bold_font(font_size)

    wrapped_lines = []
    for line in display_text.split("\n"):
        wrapped = textwrap.wrap(line.strip(), width=24)
        wrapped_lines.extend(wrapped)
    # Limit to 5 lines
    wrapped_lines = wrapped_lines[:5]

    line_height = font_size + 16
    total_height = len(wrapped_lines) * line_height
    start_y = (size - total_height) // 2

    for i, line in enumerate(wrapped_lines):
        y = start_y + i * line_height
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (size - text_width) // 2

        # Text shadow
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=font)
        draw.text((x, y), line, fill=text_color, font=font)

    # Watermark
    small_font = _get_font(24)
    watermark = "@autoposter"
    bbox = draw.textbbox((0, 0), watermark, font=small_font)
    wm_width = bbox[2] - bbox[0]
    draw.text(
        ((size - wm_width) // 2, size - 60),
        watermark,
        fill=(*accent_color, 180),
        font=small_font,
    )

    img.save(str(output_path), "PNG", quality=95)
    return output_path
