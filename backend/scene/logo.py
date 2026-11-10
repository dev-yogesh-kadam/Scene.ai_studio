"""A brand's logo, as a motion graphic needs it, from whatever the user gave: a PNG with transparency, a JPEG or PNG on a
flat ground, or an SVG. The result is a transparent PNG cut to the mark (the ground taken away with soft edges, and its
colour taken out of the edge pixels), the SVG itself cleaned (so its shapes can be animated one by one), and what the
pages need to know: the brand's colours, whether the mark wants a dark or a light ground, its shape, and how many shapes
an SVG has. A logo is never redrawn: what is not in the file is not invented.
"""

import asyncio
import re
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

from . import media, motion

LONGEST = 2000       # pixels: the longest side of the PNG made
FLAT = 22            # how far apart (0 to 441) the four corners of a picture may be and still be one flat ground...
GENTLE = 70          # ...and still be one soft ground (a vignette, a falloff of light), taken away as their blend
EDGE = (14, 60)      # how far (in the channel furthest from the ground) a pixel starts to show, and is solid
COLOURS = 6


class LogoError(ValueError):
    pass


def clean_svg(text):
    """An SVG with nothing in it that runs or reaches out: no scripts, no event handlers, no foreign objects, no links
    off the file. Raises LogoError when it is not an SVG."""
    if not re.search(r"<svg\b", text or "", re.IGNORECASE):
        raise LogoError("That text is not an SVG.")
    text = re.sub(r"<script\b.*?</script\s*>|<script\b[^>]*/>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<foreignObject\b.*?</foreignObject\s*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*')", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(\b(?:xlink:)?href\s*=\s*)([\"'])\s*(?:javascript:|https?:|//)[^\"']*\2", r"\1\2#\2", text, flags=re.IGNORECASE)
    return text[text.lower().index("<svg"):] if "<?xml" in text[:200].lower() or "<!doctype" in text[:300].lower() else text


def _distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a[:3], b[:3])) ** 0.5


def cut_out(picture):
    """A picture of a logo as a transparent RGBA image cut to the mark, and how its ground was found: "transparent"
    (it had one), "#rrggbb" (a flat ground taken away), "gradient" (a soft ground, a vignette or a light falloff, taken
    away as the blend of its corners) or "kept" (a ground that is neither: a photo, a pattern)."""
    im = picture.convert("RGBA")
    if im.getchannel("A").getextrema()[0] < 250:
        ground = "transparent"
    else:
        w, h = im.size
        patch = max(2, min(w, h) // 40)
        corners = [im.crop(box).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))[:3]
                   for box in ((0, 0, patch, patch), (w - patch, 0, w, patch), (0, h - patch, patch, h), (w - patch, h - patch, w, h))]
        mean = tuple(sum(c[i] for c in corners) / 4 for i in range(3))
        spread = max(_distance(c, mean) for c in corners)
        if spread > GENTLE:
            ground = "kept"
        else:
            ground = "#{:02x}{:02x}{:02x}".format(*(round(v) for v in mean)) if spread <= FLAT else "gradient"
            # the ground at every pixel: the four corners blended across the picture (one colour when it is flat)
            corner_image = Image.new("RGB", (2, 2))
            corner_image.putdata(corners)
            under = corner_image.resize((w, h), Image.Resampling.BILINEAR)
            rgb = im.convert("RGB")
            far = ImageChops.difference(rgb, under).split()
            distance = ImageChops.lighter(ImageChops.lighter(far[0], far[1]), far[2])
            low, high = EDGE
            alpha = distance.point(lambda d: 0 if d <= low else 255 if d >= high else round((d - low) / (high - low) * 255))
            # an edge pixel holds some of the ground: take it out, so no halo shows on another ground
            pixels, grounds, alphas = list(rgb.getdata()), under.getdata(), alpha.getdata()
            for i, a in enumerate(alphas):
                if 0 < a < 255:
                    k = a / 255
                    pixels[i] = tuple(max(0, min(255, round((c - (1 - k) * m) / k))) for c, m in zip(pixels[i], grounds[i]))
            rgb.putdata(pixels)
            im = Image.merge("RGBA", (*rgb.split(), alpha))
    box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if box is None:
        raise LogoError("The picture is empty once its ground is taken away.")
    pad = max(2, round(max(box[2] - box[0], box[3] - box[1]) * 0.02))
    im = im.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad), min(im.height, box[3] + pad)))
    if max(im.size) > LONGEST:
        im.thumbnail((LONGEST, LONGEST), Image.Resampling.LANCZOS)
    return im, ground


def facts(im):
    """What a page needs to know of a mark: its colours ([{"hex", "share"}], the most used first), the ground it wants
    ("dark": light ink, "light": dark ink, "any"), and its shape (width / height)."""
    solid = [p[:3] for p in im.getdata() if p[3] > 200]
    if not solid:
        return {"palette": [], "wants": "any", "ratio": round(im.width / im.height, 3)}
    solid = solid[:: max(1, len(solid) // 40000)]   # enough to read the colours by
    sample = Image.new("RGB", (len(solid), 1))
    sample.putdata(solid)
    counts = Counter(sample.quantize(colors=COLOURS, method=Image.Quantize.MEDIANCUT).convert("RGB").getdata())
    total = sum(counts.values())
    palette = []
    for colour, n in counts.most_common():
        if all(_distance(colour, tuple(int(p["hex"][i:i + 2], 16) for i in (1, 3, 5))) > 24 for p in palette):
            palette.append({"hex": "#{:02x}{:02x}{:02x}".format(*colour), "share": round(n / total, 3)})
    light = sum((0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 * n for (r, g, b), n in counts.items()) / total
    return {"palette": palette, "wants": "dark" if light > 0.72 else "light" if light < 0.32 else "any", "ratio": round(im.width / im.height, 3)}


async def _draw_svg(svg, target, node="", work_dir=None):
    """An SVG drawn by Chrome on nothing, as a transparent PNG whose longest side is LONGEST."""
    box = re.search(r"viewBox\s*=\s*[\"']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)", svg)
    w, h = (float(box.group(1)), float(box.group(2))) if box else (1000.0, 1000.0)
    scale = LONGEST / max(w, h)
    w, h = max(2, int(w * scale) // 2 * 2), max(2, int(h * scale) // 2 * 2)
    # only the outer <svg> takes the size it is drawn at: its shapes keep their own widths and heights
    opening = re.search(r"<svg\b[^>]*>", svg, re.IGNORECASE)
    tag = re.sub(r"\s(width|height)\s*=\s*[\"'][^\"']*[\"']", "", opening.group(0))
    sized = svg[:opening.start()] + tag[:4] + ' width="{}" height="{}" style="display:block"'.format(w, h) + tag[4:] + svg[opening.end():]
    page = ('<!doctype html><html><head><meta charset="UTF-8"><style>html,body{{margin:0;width:{w}px;height:{h}px;background:transparent}}</style>'
            '</head><body><div id="root" data-composition-id="main" data-start="0" data-duration="0.2" data-width="{w}" data-height="{h}">'
            '<div id="mark" class="clip" data-start="0" data-duration="0.2">{svg}</div></div>'
            '<script>window.__timelines = window.__timelines || {{}}; window.__timelines["main"] = gsap.timeline({{paused: true}});</script>'
            '</body></html>').format(w=w, h=h, svg=sized).replace("<head>", '<head><script src="gsap.min.js"></script>', 1)
    with tempfile.TemporaryDirectory(dir=work_dir, ignore_cleanup_errors=True) as tmp:
        drawn = Path(tmp) / "mark.webm"
        await motion._produce(lambda project: (project / "index.html").write_text(page, encoding="utf-8"), {}, drawn, 10, "Logo",
                              node, work_dir, alpha=True)
        await media._ffmpeg("-loglevel", "error", "-c:v", "libvpx-vp9", "-i", drawn, "-frames:v", "1", "-pix_fmt", "rgba", target)
    return Path(target)


async def prepare(source, kind, target, node="", work_dir=None):
    """The logo in `source` (a picture, or a text that is an SVG) as a transparent PNG at `target`, and, for an SVG, the
    cleaned SVG beside it. Returns {"files": [png, svg?], "ground", "svg", "shapes"?, "palette", "wants", "ratio",
    "width", "height"}."""
    target = Path(target)
    files, extra = [target], {}
    if kind == "text":
        svg = clean_svg(Path(source).read_text(encoding="utf-8-sig", errors="replace"))
        await _draw_svg(svg, target, node, work_dir)
        im, ground = cut_out(Image.open(target))
        kept = target.with_suffix(".svg")
        kept.write_text(svg, encoding="utf-8")
        files.append(kept)
        extra = {"svg": True, "shapes": len(re.findall(r"<(path|circle|rect|ellipse|polygon|polyline|line)\b", svg, re.IGNORECASE))}
    else:
        im, ground = await asyncio.to_thread(lambda: cut_out(Image.open(source)))
        extra = {"svg": False}
    im.save(target)
    return {"files": files, "ground": ground, **extra, **facts(im), "width": im.width, "height": im.height}
