"""Compare the screenshots look.mjs saved in two folders (before a change and after it), pixel by pixel.

  python -I tests/look-compare.py <before folder> <after folder> [name ...]      (no names: every shot in both)

A pixel differs when one of its colours differs by more than 24 (anti-aliasing and the animated live dot stay under).
Exits 1 when any pair differs.
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops

before, after = Path(sys.argv[1]), Path(sys.argv[2])
names = sys.argv[3:] or sorted(p.stem for p in after.glob("*.png") if (before / p.name).exists())
bad = 0
for name in names:
    a = Image.open(before / "{}.png".format(name)).convert("RGB")
    b = Image.open(after / "{}.png".format(name)).convert("RGB")
    d = ImageChops.difference(a, b) if a.size == b.size else None
    px = (sum(1 for p in d.getdata() if max(p) > 24) if d else a.size[0] * a.size[1])
    bad += px > 0
    print("{:40} {:>7} pixels differ ({:.2f}%)".format(name, px, 100 * px / (a.size[0] * a.size[1])))
sys.exit(1 if bad else 0)
