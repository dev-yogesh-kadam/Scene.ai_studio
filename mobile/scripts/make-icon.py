"""Draws the phone site's icons from the studio's logo, "The Clapper Gate" (frontend/assets/img/logo.svg): a
clapperboard, its stick lifted for the take, and on the board the studio's frame. Same shapes and colours.

Run from the repo root:  .venv/Scripts/python mobile/scripts/make-icon.py

Writes the sign-in logo and the tab icon (mobile/assets/images), and the icons a phone uses when the site is added to
its home screen (mobile/public/icons).
"""
from pathlib import Path

from PIL import Image, ImageDraw

MOBILE = Path(__file__).resolve().parent.parent
S = 4096                 # drawn at 4x, scaled down for smooth edges
GROUND = (14, 15, 18)    # #0E0F12
PAPER = (244, 244, 244)  # #F4F4F4
FRAME = (140, 203, 255)  # #8CCBFF


def mark(size):
    """The clapperboard on transparent, as in the logo's 48-unit box, filling `size` (the box, not just the shapes)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = size / 48
    # The stick: a line from (11, 15.5) to (36.5, 10.3), 4.5 wide, round ends.
    w = 4.5 * u
    a, b = (11 * u, 15.5 * u), (36.5 * u, 10.3 * u)
    d.line([a, b], fill=PAPER, width=round(w))
    for x, y in (a, b):
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=PAPER)
    # The board: a rounded rectangle at (11, 21), 26 x 17, corners 3.5, drawn as a 4-wide outline.
    d.rounded_rectangle([(11 - 2) * u, (21 - 2) * u, (37 + 2) * u, (38 + 2) * u], radius=(3.5 + 2) * u, fill=PAPER)
    d.rounded_rectangle([(11 + 2) * u, (21 + 2) * u, (37 - 2) * u, (38 - 2) * u], radius=max(0.5, 3.5 - 2) * u, fill=(0, 0, 0, 0))
    # The frame on the board: (20, 25.5), 8 x 8, corners 1.4.
    d.rounded_rectangle([20 * u, 25.5 * u, 28 * u, 33.5 * u], radius=1.4 * u, fill=FRAME)
    return img


def tile(size, rounded=True, inner=1.0):
    """The logo as the studio shows it: the mark on its dark square, rounded (corners 11 of 48) or full bleed."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, size - 1, size - 1], radius=size * 11 / 48 if rounded else 0, fill=GROUND + (255,))
    m = int(size * inner)
    img.alpha_composite(mark(m), ((size - m) // 2, (size - m) // 2))
    return img


def save(img, path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((size, size), Image.LANCZOS).save(path)
    print("wrote", path.relative_to(MOBILE), size)


images, icons = MOBILE / "assets" / "images", MOBILE / "public" / "icons"
save(tile(S), images / "logo.png", 512)
save(tile(S), images / "favicon.png", 48)
# Home screen: Android crops a "maskable" icon to its own shape, keeping the middle 80%; iPhones round a square one.
save(tile(S, rounded=False), icons / "icon-192.png", 192)
save(tile(S, rounded=False), icons / "icon-512.png", 512)
save(tile(S, rounded=False, inner=0.8), icons / "maskable-512.png", 512)
save(tile(S, rounded=False), icons / "apple-touch-icon.png", 180)
