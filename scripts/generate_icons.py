"""Generate smiley face PNG icons for all required sizes.

Usage: python scripts/generate_icons.py
Requires: pip install Pillow
"""
import math
import os
from PIL import Image, ImageDraw

# Output directory
ICONS_DIR = "static/icons"
# Bubblewrap TWA store icon (used by Android build, separate from PWA manifest icons)
STORE_ICON = "twa-project/store_icon.png"
# Also referenced by twa-config.json as "icon": "static/icons/icon-512x512.png"
# Both paths are kept in sync — the script regenerates both automatically.

# Sizes needed (from manifest.json)
SIZES = [48, 72, 96, 144, 168, 192, 512]

# Colors - matching Tailwind amber/orange gradient
BG_START = (251, 191, 36)   # amber-400 #fbbf24
BG_END = (217, 119, 6)      # amber-600 #d97706
STROKE_COLOR = (255, 255, 255)  # white
CORNER_RADIUS_RATIO = 0.22   # ~22% of size for rounded corners


def draw_smiley(draw, cx, cy, scale, color):
    """Draw a smiley face centered at (cx, cy) with given scale."""
    r = 10 * scale

    # Face circle
    draw.ellipse(
        [(cx - r, cy - r), (cx + r, cy + r)],
        outline=color,
        width=max(1, int(2 * scale))
    )

    # Smile arc
    smile_width = 4 * scale
    smile_height = 2 * scale
    smile_y_offset = 2 * scale

    sx1 = cx - smile_width
    sy1 = cy + smile_y_offset
    sx2 = cx + smile_width

    draw.arc(
        [(sx1, sy1 - smile_height), (sx2, sy1 + smile_height)],
        start=225,
        end=315,
        fill=color,
        width=max(1, int(2 * scale))
    )

    # Eyes
    eye_width = 0.5 * scale
    eye_offset_x = 3 * scale
    eye_offset_y = -3 * scale

    for ex in [cx - eye_offset_x, cx + eye_offset_x]:
        draw.line(
            [(ex - eye_width, cy + eye_offset_y), (ex + eye_width, cy + eye_offset_y)],
            fill=color,
            width=max(1, int(2 * scale))
        )


def in_rounded_rect(x, y, size, radius):
    """Check if point (x, y) is inside a rounded rectangle."""
    if radius <= 0:
        return True

    # Inside main rectangle area
    if radius <= x < size - radius and radius <= y < size - radius:
        return True

    # Top-left corner
    if x < radius and y < radius:
        dx = radius - x - 0.5
        dy = radius - y - 0.5
        return dx * dx + dy * dy <= radius * radius

    # Top-right corner
    if x >= size - radius and y < radius:
        dx = x - (size - radius) + 0.5
        dy = radius - y - 0.5
        return dx * dx + dy * dy <= radius * radius

    # Bottom-left corner
    if x < radius and y >= size - radius:
        dx = radius - x - 0.5
        dy = y - (size - radius) + 0.5
        return dx * dx + dy * dy <= radius * radius

    # Bottom-right corner
    if x >= size - radius and y >= size - radius:
        dx = x - (size - radius) + 0.5
        dy = y - (size - radius) + 0.5
        return dx * dx + dy * dy <= radius * radius

    # Edge areas (not corners) - inside
    return True


def create_icon(size):
    """Create a single icon of the given size with gradient bg and smiley."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    radius = int(size * CORNER_RADIUS_RATIO)

    # Draw pixel-by-pixel gradient with rounded corners
    for y in range(size):
        ratio = y / max(size - 1, 1)
        r = int(BG_START[0] + (BG_END[0] - BG_START[0]) * ratio)
        g = int(BG_START[1] + (BG_END[1] - BG_START[1]) * ratio)
        b = int(BG_START[2] + (BG_END[2] - BG_START[2]) * ratio)

        for x in range(size):
            if in_rounded_rect(x, y, size, radius):
                img.putpixel((x, y), (r, g, b, 255))

    # Draw smiley face centered
    draw = ImageDraw.Draw(img)
    face_diameter = size * 0.70
    scale = face_diameter / 20.0

    draw_smiley(draw, size / 2, size / 2, scale, STROKE_COLOR)

    return img


def main():
    os.makedirs(ICONS_DIR, exist_ok=True)

    for size in SIZES:
        filename = os.path.join(ICONS_DIR, f"icon-{size}x{size}.png")
        print(f"Generating {filename}...")
        img = create_icon(size)
        img.save(filename, "PNG")
        print(f"  Saved ({img.size[0]}x{img.size[1]})")

    # Copy 512x512 as store_icon.png
    store_src = os.path.join(ICONS_DIR, "icon-512x512.png")
    if os.path.exists(store_src):
        import shutil
        shutil.copy2(store_src, STORE_ICON)
        print(f"Copied to {STORE_ICON}")

    print("\nAll icons generated successfully!")


if __name__ == "__main__":
    main()
