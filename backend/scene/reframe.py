"""A video in another shape (16:9 to 9:16, 1:1, 4:5...), two ways, both done with ffmpeg on this machine but for one
step:

- crop: the window of the new shape that holds what matters (x, y: where it sits, 0 to 1), scaled to the new size.
  Free and quick. Nothing is invented, so it is often the right choice for Reels.
- extend (outpainting): the video kept whole and the new space filled in by Wan VACE on the render server.
  1. prepare(): the video at 16 fps, shrunk to fit inside the new shape on a grey canvas, cut in parts of at most
     PART_FRAMES frames, each with a mask video (white where Wan fills in, black where the video is). The mask reaches
     EDGE pixels into the picture, so the seam is drawn again rather than left as a line.
  2. The render server fills each part in (workflow video/video_outpaint_wan_vace: the part and its mask).
  3. join(): the filled parts in order, brought to 24 fps, made full size, with the original video laid back over the
     middle with a soft edge, so only the new space is invented and the picture keeps its full quality. The sound is
     the original's.

The parts and the box the video sits in are worked out the same way in prepare() and join() from the video and the
shape, so nothing has to be carried between them.
"""

import math
from pathlib import Path

from .media import FPS, MediaError, _ffmpeg, probe
from .film import ENCODE, frames_of

# shape -> (its finished size, the size Wan fills it in at: multiples of 16, about 480p)
SHAPES = {"portrait": ((1080, 1920), (480, 832)), "landscape": ((1920, 1080), (832, 480)),
          "square": ((1080, 1080), (640, 640)), "4:5": ((1080, 1350), (512, 640))}
GEN_FPS = 16          # Wan makes 16 frames a second
PART_FRAMES = 81      # the longest part Wan VACE fills in at once: 5 s at 16 fps (4n+1)
EDGE = 8              # pixels (at Wan's size) of the picture drawn again at its edge, so no seam shows
GREY = "0x808080"     # what Wan VACE reads as "nothing here yet"


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


def _insets(x, y, w, h, size, edge):
    """How far in from each side (left, top, right, bottom) the picture is drawn again: `edge` on a side that meets new
    space, nothing on a side that is the frame's own edge."""
    return (edge if x > 0 else 0, edge if y > 0 else 0, edge if x + w < size[0] else 0, edge if y + h < size[1] else 0)


def parts(frames):
    """The parts a video of `frames` frames (at 16 fps) is filled in as: [(first frame, frames, frames sent)], frames
    sent being the next 4n+1 (Wan's lengths), the last frame held to reach it."""
    out, start = [], 0
    while start < frames:
        n = min(PART_FRAMES, frames - start)
        out.append((start, n, n + (-(n - 1)) % 4))
        start += n
    return out


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


async def prepare(video, shape, target):
    """The parts and masks Wan fills in, as files beside `target`: [part 1, its mask, part 2, its mask, ...]."""
    _, gen = shape_of(shape)
    found = await probe(video)
    if not found["width"]:
        raise MediaError("The video's frame size can't be read.")
    x, y, w, h = box(found["width"], found["height"], gen)
    if (w, h) == gen:
        raise MediaError("The video is already that shape: there is nothing to fill in.")
    target = Path(target)
    whole = target.with_name(target.stem + "_16fps.mp4")
    await _ffmpeg("-loglevel", "error", "-i", video, "-map", "0:v:0", "-an", "-vf",
                  "fps={},scale={}:{}:flags=lanczos,setsar=1,pad={}:{}:{}:{}:color={},format=yuv420p".format(
                      GEN_FPS, w, h, gen[0], gen[1], x, y, GREY), *ENCODE, whole)
    try:
        total = await frames_of(whole)
        files = []
        left, top, right, bottom = _insets(x, y, w, h, gen, EDGE)
        for n, (start, frames, sent) in enumerate(parts(total), start=1):
            part = target.with_name("{}_part{}.mp4".format(target.stem, n))
            mask = target.with_name("{}_part{}_mask.mp4".format(target.stem, n))
            await _ffmpeg("-loglevel", "error", "-i", whole, "-vf",
                          "trim=start_frame={}:end_frame={},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop={}".format(
                              start, start + frames, sent - frames), "-frames:v", sent, "-r", GEN_FPS, *ENCODE, part)
            await _ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s={}x{}:r={}".format(gen[0], gen[1], GEN_FPS),
                          "-vf", "drawbox=x={}:y={}:w={}:h={}:color=black:t=fill,format=yuv420p".format(
                              x + left, y + top, w - left - right, h - top - bottom), "-frames:v", sent, *ENCODE, mask)
            files += [part, mask]
    finally:
        whole.unlink(missing_ok=True)
    return {"seconds": total / GEN_FPS, "width": gen[0], "height": gen[1], "files": files,
            "parts": [{"frames": f, "sent": s} for _, f, s in parts(total)], "box": [x, y, w, h]}


async def join(video, filled, shape, target):
    """The filled parts (in order, as Wan made them) as one video of the shape: 24 fps, full size, the original laid
    back over the middle with a soft edge, and the original's sound."""
    size, gen = shape_of(shape)
    found = await probe(video)
    if not found["width"]:
        raise MediaError("The video's frame size can't be read.")
    x, y, w, h = box(found["width"], found["height"], gen)
    expected = parts(round(found["seconds"] * GEN_FPS))
    if abs(len(filled) - len(expected)) > 1 or not filled:
        raise MediaError("The video is filled in as {} parts, and {} were given.".format(len(expected), len(filled)))
    expected = expected[:len(filled)] if len(filled) <= len(expected) else expected + [expected[-1]]
    scale = size[0] / gen[0]
    bx, by, bw, bh = _at(x * scale), _at(y * scale), min(_even(w * scale), size[0]), min(_even(h * scale), size[1])
    left, top, right, bottom = _insets(bx, by, bw, bh, size, max(4, int(EDGE * scale)))
    soft = max(left, top, right, bottom, 1)
    total = await frames_of(video)
    target = Path(target)
    edge = target.with_name(target.stem + "_edge.png")
    await _ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s={}x{}".format(bw, bh), "-vf",
                  "drawbox=x={}:y={}:w={}:h={}:color=white:t=fill,boxblur={}:1,format=gray".format(
                      left, top, bw - left - right, bh - top - bottom, max(soft // 2, 1)), "-frames:v", 1, edge)
    try:
        inputs, graph = [], []
        for i, (path, (_, frames, _)) in enumerate(zip(filled, expected)):
            inputs += ["-i", path]
            graph.append("[{}:v]fps={},trim=end_frame={},setpts=PTS-STARTPTS,scale={}:{}:flags=lanczos,setsar=1[p{}]".format(
                i, GEN_FPS, frames, gen[0], gen[1], i))
        n = len(filled)
        graph.append("{}concat=n={}:v=1:a=0,minterpolate=fps={}:mi_mode=mci:mc_mode=aobmc:vsbmc=1,scale={}:{}:flags=lanczos,"
                     "tpad=stop_mode=clone:stop={}[bg]".format("".join("[p{}]".format(i) for i in range(n)), n, FPS, size[0], size[1], FPS))
        graph.append("[{}:v]fps={},scale={}:{}:flags=lanczos,setsar=1,format=yuva420p[o]".format(n, FPS, bw, bh))
        graph.append("[{}:v]scale={}:{},format=gray[m]".format(n + 1, bw, bh))
        graph.append("[o][m]alphamerge[oa];[bg][oa]overlay={}:{}:eof_action=endall,trim=end_frame={},format=yuv420p[v]".format(bx, by, total))
        await _ffmpeg("-loglevel", "error", *inputs, "-i", video, "-loop", 1, "-i", edge, "-filter_complex", ";".join(graph),
                      "-map", "[v]", "-map", "{}:a?".format(n), "-r", FPS, *ENCODE, "-c:a", "aac", "-b:a", "192k", "-shortest",
                      "-movflags", "+faststart", target)
    finally:
        edge.unlink(missing_ok=True)
    made = await probe(target)
    return {"seconds": made["seconds"], "width": size[0], "height": size[1], "parts": n}
