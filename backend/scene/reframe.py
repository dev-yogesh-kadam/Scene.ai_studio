"""A video in another shape (16:9 to 9:16, 1:1, 4:5...), cropped with ffmpeg on this machine: the window of the new
shape that holds what matters (x, y: where it sits, 0 to 1), scaled to the new size. Free and quick. Nothing is
invented, so it is often the right choice for Reels.

(Extending a video into a new shape, the new space filled in, is a provider's video model that edits a clip: the
agent's recipe in agent.py. The parts and masks once made here for ComfyUI's Wan VACE workflow went with ComfyUI.)
"""

from pathlib import Path

from .media import FPS, MediaError, _ffmpeg, probe
from .film import ENCODE

# shape -> (its finished size, a smaller size of the same shape: multiples of 16, about 480p)
SHAPES = {"portrait": ((1080, 1920), (480, 832)), "landscape": ((1920, 1080), (832, 480)),
          "square": ((1080, 1080), (640, 640)), "4:5": ((1080, 1350), (512, 640))}


def shape_of(name):
    if name not in SHAPES:
        raise MediaError("The shape must be one of: {}.".format(", ".join(SHAPES)))
    return SHAPES[name]


def _even(n):
    """A size: even, and 2 at least."""
    return max(2, int(n) // 2 * 2)


def _at(n):
    """A place: even, and 0 at least."""
    return max(0, int(n) // 2 * 2)


def box(width, height, size):
    """Where a width x height picture sits when shrunk to fit inside `size`, centred: (x, y, w, h), all even."""
    scale = min(size[0] / width, size[1] / height)
    w, h = min(_even(width * scale), size[0]), min(_even(height * scale), size[1])
    return _at((size[0] - w) / 2), _at((size[1] - h) / 2), w, h


async def crop(video, shape, target, x=0.5, y=0.5):
    """The window of the shape at (x, y) of the video (0 to 1: left to right, top to bottom), at the shape's finished
    size, with the video's sound."""
    size, _ = shape_of(shape)
    found = await probe(video)
    if not found["width"]:
        raise MediaError("The video's frame size can't be read.")
    want = size[0] / size[1]
    w, h = found["width"], found["height"]
    cw, ch = (_even(h * want), _even(h)) if w / h > want else (_even(w), _even(w / want))
    cx, cy = _at((w - cw) * min(max(float(x), 0), 1)), _at((h - ch) * min(max(float(y), 0), 1))
    chain = "crop={}:{}:{}:{},scale={}:{}:flags=lanczos,setsar=1,format=yuv420p".format(cw, ch, cx, cy, *size)
    await _ffmpeg("-loglevel", "error", "-i", video, "-map", "0:v:0", "-map", "0:a?", "-vf", chain, "-r", FPS, *ENCODE,
                  "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", target)
    return {"seconds": (await probe(target))["seconds"], "width": size[0], "height": size[1], "window": [cx, cy, cw, ch]}
