"""Generate icon.ico from a procedural design — used by Inno Setup + the
final .exe so Windows shows the Amplifier brand glyph.

Design: blue gradient disc with a stylized white megaphone/wave glyph.
Multi-size ICO with 16/32/48/64/128/256 px frames (required by Task #77 AC2).

Run: python scripts/build/installer/generate_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


HERE = Path(__file__).resolve().parent
TARGET = HERE / "icon.ico"
SIZES = [16, 32, 48, 64, 128, 256]


def _draw_master(size: int) -> Image.Image:
    """Render a single frame at the given square size with crisp edges."""
    # Render at 4x oversample for smooth edges, then downsample.
    scale = 4
    w = size * scale
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background disc — vertical gradient via two stacked ellipses with mask
    # (simple, deterministic, no external deps beyond Pillow).
    pad = max(1, w // 32)
    bg_top = (37, 99, 235)        # tailwind blue-600 — brand color
    bg_bot = (29, 78, 216)        # blue-700, slightly darker
    grad = Image.new("RGBA", (w, w), bg_top)
    gradient = Image.linear_gradient("L").resize((w, w))
    blend_top = Image.new("RGBA", (w, w), bg_top)
    blend_bot = Image.new("RGBA", (w, w), bg_bot)
    blended = Image.composite(blend_bot, blend_top, gradient)

    mask = Image.new("L", (w, w), 0)
    ImageDraw.Draw(mask).ellipse((pad, pad, w - pad, w - pad), fill=255)
    img.paste(blended, (0, 0), mask)

    # Inner glyph: bold uppercase 'A' (Amplifier) drawn as a triangle + crossbar.
    # Use vector lines so it scales cleanly down to 16x16 without going muddy.
    cx = w // 2
    base_y = int(w * 0.78)
    apex_y = int(w * 0.22)
    half = int(w * 0.22)
    bar_y = int(w * 0.60)
    stroke = max(2, int(w * 0.10))

    white = (255, 255, 255, 255)
    # Left leg
    draw.line([(cx - half, base_y), (cx, apex_y)], fill=white, width=stroke)
    # Right leg
    draw.line([(cx + half, base_y), (cx, apex_y)], fill=white, width=stroke)
    # Crossbar
    bar_inset = int(w * 0.08)
    draw.line(
        [(cx - half + bar_inset, bar_y), (cx + half - bar_inset, bar_y)],
        fill=white,
        width=stroke,
    )

    # Subtle drop shadow to lift glyph at small sizes
    if size >= 32:
        shadow = img.filter(ImageFilter.GaussianBlur(radius=max(1, w // 120)))
        out = Image.alpha_composite(shadow, img)
    else:
        out = img

    # Downsample with LANCZOS for crisp output
    return out.resize((size, size), Image.LANCZOS)


def main() -> None:
    # Pillow's ICO writer takes ONE master image plus a `sizes=` list and
    # downsamples internally. Render at the largest target size for the
    # cleanest hand-off to Pillow's resizer.
    master = _draw_master(max(SIZES))
    master.save(
        TARGET,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )

    # Verify — Pillow's high-level Image API exposes only the default ICO
    # frame, so use IcoFile to enumerate all embedded sizes.
    from PIL.IcoImagePlugin import IcoFile

    with open(TARGET, "rb") as f:
        seen = IcoFile(f).sizes()
    missing = {(s, s) for s in SIZES} - seen
    assert not missing, f"Missing sizes after save: {missing}"
    assert TARGET.stat().st_size > 5 * 1024, (
        f"icon.ico too small ({TARGET.stat().st_size} B)"
    )

    print(f"Wrote {TARGET} ({TARGET.stat().st_size:,} bytes, {len(seen)} frames)")
    print(f"Sizes: {sorted(seen)}")


if __name__ == "__main__":
    main()
