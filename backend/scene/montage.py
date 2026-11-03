"""Cutting and showing what exists, on this machine with ffmpeg, no model: keyframes from a stretch of a clip, a numbered
board of stills, a cut that switches between virtual cameras of one clip, clips cut on the beats of a song, a looping
GIF, and a see-through overlay laid over a video.
"""

import math
import shutil
import tempfile
from pathlib import Path

from .media import FPS, MediaError, _ffmpeg, frame_rate, probe

ENCODE = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-profile:v", "high", "-pix_fmt", "yuv420p"]
FONTS = Path(__file__).parent / "fonts"
FONT = "Poppins-Bold.ttf"


def _secs(value):
    return "{:.6f}".format(value)


async def _picture(video):
    """(width, height, seconds, fps) of a video, refused when it has no picture."""
    found = await probe(video)
    if not found["width"] or not found["seconds"]:
        raise MediaError("{} can't be read as a video.".format(Path(video).name))
    return found["width"], found["height"], found["seconds"], await frame_rate(video)


# ---------------------------------------------------------------- keyframes

KEYFRAMES_MOST = 48
KEYFRAME_SIDE = 1920   # the longer side of a keyframe at most; a smaller video keeps its own size


def keyframe_times(length, fps, start=0.0, end=None, count=None, every=None, times=None, shots=None, pick="first"):
    """The times of the keyframes asked for, in the clip's seconds, each with what it is: [(seconds, {"shot"?})].
    One way of asking at a time: `times` (given seconds), `count` (spread evenly from the first frame of the stretch
    to its last), `every` (seconds apart from its start), or `shots` ([{"n"?, "start", "end"}] or [[s, e]]: one frame
    of each shot, its first, middle or last as `pick` says). A time past the clip's end is dropped."""
    end = min(end if end is not None else length, length)
    if end <= start:
        raise MediaError("The stretch to take keyframes from ends before it starts.")
    last = max(start, end - 1.0 / fps)   # the time of the stretch's last frame
    found = []
    if times is not None:
        found = [(float(t), {}) for t in times]
    elif shots is not None:
        for i, shot in enumerate(shots, start=1):
            if isinstance(shot, dict):
                n, a, b = shot.get("n", i), float(shot["start"]), float(shot["end"])
            else:
                n, (a, b) = i, (float(shot[0]), float(shot[1]))
            a, b = max(a, start), min(b, end)
            if b <= a:
                continue
            at = {"first": a, "middle": (a + b) / 2, "last": max(a, b - 1.0 / fps)}[pick]
            found.append((at, {"shot": n}))
    elif every is not None:
        at = start
        while at <= last + 1e-6 and len(found) < KEYFRAMES_MOST:
            found.append((at, {}))
            at += float(every)
    else:
        count = int(count or 1)
        found = [(start if count == 1 else start + (last - start) * k / (count - 1), {}) for k in range(count)]
    found = [(round(t, 3), extra) for t, extra in found if 0 <= t <= max(last, 0)]
    if not found:
        raise MediaError("None of the keyframes asked for falls inside the clip.")
    if len(found) > KEYFRAMES_MOST:
        raise MediaError("That is {} keyframes; take at most {} at once.".format(len(found), KEYFRAMES_MOST))
    return found


async def keyframes(video, marks, target, side=KEYFRAME_SIDE, captions=None):
    """The frame at each mark ([(seconds, extra)], see keyframe_times) as a JPEG of high quality, its longer side at
    most `side`: `target`, then beside it _2, _3 ... captions: a label for each mark, or None. A labelled keyframe
    gets a second copy with its label in a dark strip under the frame (never over it), named ..._caption; the clean
    one is what a video model starts from. Returns [(path, {"at", **extra}, captioned path or None)]."""
    target, made = Path(target), []
    scale = "scale=w='min({0},iw)':h='min({0},ih)':force_original_aspect_ratio=decrease:flags=lanczos".format(side)
    captions = list(captions or [])
    for k, (at, extra) in enumerate(marks, start=1):
        path = target if k == 1 else target.with_name("{}_{}{}".format(target.stem, k, target.suffix))
        await _ffmpeg("-loglevel", "error", "-ss", _secs(at), "-i", video, "-map", "0:v:0", "-vf", scale,
                      "-frames:v", "1", "-q:v", "2", "-update", "1", path)
        if not path.is_file() or not path.stat().st_size:
            raise MediaError("The clip has no frame at {:.2f} s.".format(at))
        label = " ".join(str(captions[k - 1] if k - 1 < len(captions) else "").split())[:80]
        captioned = await caption_strip(path, label, path.with_name(path.stem + "_caption" + path.suffix)) if label else None
        made.append((path, {"at": at, **extra}, captioned))
    return made


async def caption_strip(image, label, target):
    """The picture with a dark strip added under it that holds `label`: the frame itself is not drawn on."""
    found = await probe(image)
    strip = max(40, found["height"] // 9) // 2 * 2
    with tempfile.TemporaryDirectory() as work:
        shutil.copy(FONTS / FONT, Path(work) / FONT)
        (Path(work) / "label.txt").write_text(label, encoding="utf-8")
        await _ffmpeg("-loglevel", "error", "-i", Path(image).resolve(), "-vf",
                      "pad=iw:ih+{s}:0:0:color=0x111111,drawtext=fontfile={f}:textfile=label.txt:expansion=none:fontsize={z}:"
                      "fontcolor=white:x=(w-text_w)/2:y=h-{s}+({s}-text_h)/2".format(s=strip, f=FONT, z=strip * 11 // 20),
                      "-frames:v", "1", "-q:v", "2", "-update", "1", Path(target).resolve(), cwd=work)
    return Path(target)


# ---------------------------------------------------------------- boards

BOARD_PANELS = (4, 6, 9, 12, 16)
BOARD_RATIO = (0.4, 2.5)   # a board is kept between these widths to its height, so video models take it as a reference
BOARD_WIDTH = 2400         # the longer side of a board at most


def board_layout(panels, still_ratio):
    """(across, down) for a board of `panels` stills of this shape (width / height): of the grids that hold exactly
    that many, the one nearest a square among those whose whole stays within BOARD_RATIO. None when none does."""
    fits = [(c, panels // c) for c in range(1, panels + 1) if panels % c == 0
            and BOARD_RATIO[0] <= c * still_ratio / (panels // c) <= BOARD_RATIO[1]]
    return min(fits, key=lambda g: abs(math.log(g[0] * still_ratio / g[1])), default=None)


def board_plan(count, panels, still_ratio):
    """How `count` stills go on boards of up to `panels` each: [(first, how many, across, down)]. When no grid of
    `panels` keeps BOARD_RATIO, the largest panel count below it that does is used, and the stills go on as many
    boards as they need. For 16:9 stills 6 panels lie 2 across and 3 down, for 9:16 stills 3 across and 2 down."""
    size = next((n for n in sorted(BOARD_PANELS, reverse=True) if n <= panels and board_layout(n, still_ratio)), None)
    if size is None:
        raise MediaError("Stills of that shape can't be laid on a board between {} and {} times as wide as tall.".format(*BOARD_RATIO))
    across, down = board_layout(size, still_ratio)
    return [(start, min(size, count - start), across, down) for start in range(0, count, size)]


async def board(stills, target, panels=6, numbered=True, width=BOARD_WIDTH):
    """Numbered boards of stills, for a model to take as a reference or a start image: the stills in a grid, each
    fitted to the shape of the first, its number in the corner and nothing else drawn on it (what a panel shows goes
    in the words sent with it); empty panels stay dark. Every board stays within BOARD_RATIO (see board_plan: more
    stills than one board holds go on more boards). stills: [(path, seconds or None)], a video's frame at those
    seconds, a picture as it is. The first board is `target`, the next _2, _3 ... Returns {"seconds", "width",
    "height", "boards": [{"file", "stills": [first number, last number], "across", "down"}]}."""
    if panels not in BOARD_PANELS:
        raise MediaError("A board has 4, 6, 9, 12 or 16 panels.")
    if not stills:
        raise MediaError("A board needs at least one still.")
    first = await probe(stills[0][0])
    if not first["width"]:
        raise MediaError("The first still can't be read.")
    ratio = first["width"] / first["height"]
    target, made = Path(target), []
    for k, (start, count, across, down) in enumerate(board_plan(len(stills), panels, ratio), start=1):
        path = target if k == 1 else target.with_name("{}_{}{}".format(target.stem, k, target.suffix))
        whole = across * ratio / down   # the board's longer side is `width`
        cell_w = int((width if whole >= 1 else width * whole) // across - 8) // 2 * 2
        cell_h = max(2, round(cell_w / ratio / 2) * 2)
        await _one_board(stills[start:start + count], start, across * down, across, down, cell_w, cell_h, numbered, path)
        made.append({"file": path, "stills": [start + 1, start + count], "across": across, "down": down})
    found = await probe(made[0]["file"])
    return {"seconds": 0, "width": found["width"], "height": found["height"], "boards": made}


async def _one_board(stills, offset, panels, across, down, cell_w, cell_h, numbered, target):
    with tempfile.TemporaryDirectory() as work:
        shutil.copy(FONTS / FONT, Path(work) / FONT)
        args, graph = ["-loglevel", "error"], []
        for i, (path, at) in enumerate(stills):
            if at is not None:
                args += ["-ss", _secs(at)]
            args += ["-i", Path(path).resolve()]
            number = ""
            if numbered:
                (Path(work) / "n{}.txt".format(i)).write_text(str(offset + i + 1), encoding="utf-8")
                number = (",drawtext=fontfile={f}:textfile=n{i}.txt:expansion=none:fontsize={s}:fontcolor=black:box=1:"
                          "boxcolor=white@0.9:boxborderw={b}:x={b}:y={b}").format(f=FONT, i=i, s=max(14, cell_h // 9), b=max(6, cell_h // 40))
            graph.append("[{i}:v]trim=end_frame=1,setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                         "pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x101010,setsar=1,format=yuv444p{t}[p{i}]".format(
                             i=i, w=cell_w, h=cell_h, t=number))
        for i in range(len(stills), panels):   # the empty panels
            graph.append("color=c=0x1c1c1c:s={}x{}:d=0.04,format=yuv444p,trim=end_frame=1[p{}]".format(cell_w, cell_h, i))
        graph.append("{}concat=n={}:v=1:a=0,tile={}x{}:padding=8:margin=8:color=0x050505[v]".format(
            "".join("[p{}]".format(i) for i in range(panels)), panels, across, down))
        await _ffmpeg(*args, "-filter_complex", ";".join(graph), "-map", "[v]", "-frames:v", "1", "-update", "1",
                      Path(target).resolve(), cwd=work)


# ---------------------------------------------------------------- virtual cameras

CAMERAS = {   # how close each camera is (1 the whole frame) and where it looks (0 to 1 across and down)
    "wide": {"zoom": 1.0, "x": 0.5, "y": 0.5},
    "medium": {"zoom": 1.4, "x": 0.5, "y": 0.45},
    "close": {"zoom": 2.0, "x": 0.5, "y": 0.4},
}
MAX_ZOOM = 4.0
MAX_PUSH = 0.5   # a slow push ends at most this much closer than it starts


def _window(width, height, zoom, x, y):
    """The part of the frame a camera sees: (left, top, w, h), kept inside the frame, the frame's shape kept."""
    w, h = width / zoom, height / zoom
    left = min(max(x * width - w / 2, 0), width - w)
    top = min(max(y * height - h / 2, 0), height - h)
    return left, top, w, h


async def multicam(video, cuts, target, cameras=None):
    """One clip cut as if filmed by several cameras: each cut ({"at": seconds, "camera": name, "push"?: 0 to 0.5})
    switches to that camera from its time until the next cut. "wide" is the whole frame; "medium" and "close" (or any
    camera given in `cameras` as {"zoom", "x", "y"}) crop in and scale back up with lanczos to the clip's own size,
    so the shape never changes. A push moves slowly closer through its stretch (by `push` of the zoom). The clip's
    sound plays on unbroken. Returns {"seconds", "width", "height", "frames", "cuts"}."""
    width, height, length, fps = await _picture(video)
    width, height = width // 2 * 2, height // 2 * 2
    known = dict(CAMERAS, **(cameras or {}))
    cuts = sorted(cuts, key=lambda c: c["at"])
    if not cuts or cuts[0]["at"] > 0:
        cuts.insert(0, {"at": 0.0, "camera": "wide"})
    spans = []
    for here, after in zip(cuts, cuts[1:] + [None]):
        a = round(here["at"] * fps) / fps
        b = round(after["at"] * fps) / fps if after else length
        if here["camera"] not in known:
            raise MediaError("There is no camera called '{}'; there are: {}.".format(here["camera"], ", ".join(known)))
        if b - a >= 1 / fps:
            spans.append((a, min(b, length), known[here["camera"]], float(here.get("push") or 0), here["camera"]))
    if not spans:
        raise MediaError("The cuts leave nothing of the clip.")
    graph = ["[0:v]setsar=1,split={}{}".format(len(spans), "".join("[s{}]".format(i) for i in range(len(spans))))]
    for i, (a, b, cam, push, _) in enumerate(spans):
        zoom = min(max(float(cam.get("zoom", 1)), 1.0), MAX_ZOOM)
        x, y = float(cam.get("x", 0.5)), float(cam.get("y", 0.5))
        cut = "[s{i}]trim=start={a}:end={b},setpts=PTS-STARTPTS,".format(i=i, a=_secs(a), b=_secs(b))
        if push > 0:   # zoom from `zoom` to zoom * (1 + push): the window shrinks frame by frame, sub-pixel smooth
            frames = max(1, round((b - a) * fps) - 1)
            z1 = min(zoom * (1 + min(push, MAX_PUSH)), MAX_ZOOM)
            l0, t0, w0, h0 = _window(width, height, zoom, x, y)
            l1, t1, w1, h1 = _window(width, height, z1, x, y)
            lerp = lambda p, q: "({p:.3f}+({q:.3f}-{p:.3f})*min(in/{f},1))".format(p=p, q=q, f=frames)
            left, top, right, bottom = lerp(l0, l1), lerp(t0, t1), lerp(l0 + w0, l1 + w1), lerp(t0 + h0, t1 + h1)
            graph.append(cut + "scale={w}:{h}:flags=lanczos,perspective=x0='{l}':y0='{t}':x1='{r}':y1='{t}':x2='{l}':y2='{b}':"
                         "x3='{r}':y3='{b}':interpolation=cubic:eval=frame,format=yuv420p[c{i}]".format(
                             w=width, h=height, l=left, t=top, r=right, b=bottom, i=i))
        elif zoom > 1:
            left, top, w, h = _window(width, height, zoom, x, y)
            graph.append(cut + "crop={w}:{h}:{l}:{t},scale={W}:{H}:flags=lanczos,setsar=1,format=yuv420p[c{i}]".format(
                w=int(w), h=int(h), l=int(left), t=int(top), W=width, H=height, i=i))
        else:
            graph.append(cut + "scale={}:{}:flags=lanczos,format=yuv420p[c{}]".format(width, height, i))
    graph.append("{}concat=n={}:v=1:a=0[v]".format("".join("[c{}]".format(i) for i in range(len(spans))), len(spans)))
    has_sound = (await probe(video))["audio"]
    await _ffmpeg("-loglevel", "error", "-i", video, "-filter_complex", ";".join(graph), "-map", "[v]",
                  *(["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"] if has_sound else ["-an"]),
                  *ENCODE, "-movflags", "+faststart", target)
    from .film import frames_of
    made = await frames_of(target)
    return {"seconds": round(made / fps, 3), "width": width, "height": height, "frames": made,
            "cuts": [{"at": round(a, 3), "camera": name, **({"push": push} if push else {})} for a, _, _, push, name in spans]}


# ---------------------------------------------------------------- cut on the beats

MAX_HOLD = FPS * 2   # frames a clip shorter than its beats may have its last frame held; more is refused


async def beat_cut(clips, points, music, target, size=None):
    """The clips in order, each cut to the time between two beats (points: the cut times in the music's seconds, one
    more than the clips; see detect.cut_points), on the music from the first point to the last. Counted in frames at
    24 a second so nothing drifts; each clip plays from its start, fitted to `size` (the first clip's own, unless
    given), and a clip a little short of its beats has its last frame held. Returns {"seconds", "width", "height",
    "frames", "parts": [{"n", "start", "end", "frames", "held"}]}."""
    if len(points) != len(clips) + 1:
        raise MediaError("Give one more cut time than clips.")
    edges = [round(float(p) * FPS) for p in points]
    if any(b <= a for a, b in zip(edges, edges[1:])):
        raise MediaError("The cut times must rise, at least a frame apart.")
    if size is None:
        first = await probe(clips[0])
        size = ((first["width"] or 1080) // 2 * 2, (first["height"] or 1080) // 2 * 2)
    w, h = size
    args, graph, parts = ["-loglevel", "error"], [], []
    for i, clip in enumerate(clips):
        frames = edges[i + 1] - edges[i]
        have = round((await probe(clip))["seconds"] * FPS)
        held = max(0, frames - have)
        if held > MAX_HOLD:
            raise MediaError("Clip {} lasts {:.2f} s but its beats need {:.2f} s: give a longer clip or cut on more beats.".format(
                i + 1, have / FPS, frames / FPS))
        args += ["-i", clip]
        graph.append("[{i}:v]fps={r},tpad=stop_mode=clone:stop={p},trim=end_frame={n},setpts=PTS-STARTPTS,"
                     "scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                     "format=yuv420p[v{i}]".format(i=i, r=FPS, p=held + 2, n=frames, w=w, h=h))
        parts.append({"n": i + 1, "start": round((edges[i] - edges[0]) / FPS, 3), "end": round((edges[i + 1] - edges[0]) / FPS, 3),
                      "frames": frames, "held": held})
    total = edges[-1] - edges[0]
    args += ["-i", music]
    graph.append("{}concat=n={}:v=1:a=0[v]".format("".join("[v{}]".format(i) for i in range(len(clips))), len(clips)))
    graph.append("[{m}:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,aresample=48000[a]".format(
        m=len(clips), s=_secs(edges[0] / FPS), e=_secs(edges[-1] / FPS)))
    await _ffmpeg(*args, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", "-r", FPS, *ENCODE,
                  "-c:a", "aac", "-b:a", "192k", "-t", _secs(total / FPS), "-movflags", "+faststart", target)
    from .film import frames_of
    made = await frames_of(target)
    if made != total:
        raise MediaError("The cut came out at {} frames, not {}.".format(made, total))
    return {"seconds": total / FPS, "width": w, "height": h, "frames": total, "parts": parts,
            "music_from": round(edges[0] / FPS, 3)}


# ---------------------------------------------------------------- GIFs and overlays

GIF_MOST = 30.0   # seconds: a GIF is for a short loop


def _alpha_decoder(path):
    """ffmpeg's own VP9 decoder drops a WebM's alpha; libvpx keeps it."""
    return ["-c:v", "libvpx-vp9"] if Path(path).suffix.lower() == ".webm" else []


async def gif(video, target, fps=12, width=480, loop=0, start=0.0, end=None):
    """A looping GIF of a clip (or a stretch of it), made with a palette of its own colours so it looks clean.
    loop: 0 plays for ever, n plays n + 1 times. A see-through clip (a WebM or MOV with alpha) stays see-through.
    Returns {"seconds", "width", "height"}."""
    found = await probe(video)
    if not found["width"]:
        raise MediaError("{} can't be read as a video.".format(Path(video).name))
    end = min(end or found["seconds"], found["seconds"])
    if end - start <= 0:
        raise MediaError("The stretch for the GIF ends before it starts.")
    if end - start > GIF_MOST:
        raise MediaError("A GIF lasts {:.0f} s at most; this would be {:.1f} s. Give a shorter stretch.".format(GIF_MOST, end - start))
    graph = ("[0:v]fps={f},scale={w}:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff:reserve_transparent=1[p];"
             "[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle:alpha_threshold=128[v]").format(f=fps, w=int(width) // 2 * 2)
    await _ffmpeg("-loglevel", "error", *_alpha_decoder(video), "-ss", _secs(start), "-t", _secs(end - start), "-i", video,
                  "-filter_complex", graph, "-map", "[v]", "-loop", int(loop), target)
    made = await probe(target)
    return {"seconds": round(end - start, 3), "width": made["width"], "height": made["height"]}


async def composite(video, overlay, target, at=0.0, x=0.5, y=0.5, scale=1.0):
    """A see-through overlay (a WebM or MOV with alpha, or a PNG) laid over a video from `at` seconds: fitted to the
    video's width times `scale`, centred on (x, y) of the frame (0 to 1). The video's sound is kept; the result
    lasts as long as the video. Returns {"seconds", "width", "height"}."""
    width, height, length, fps = await _picture(video)
    width, height = width // 2 * 2, height // 2 * 2
    picture = Path(overlay).suffix.lower() in (".png", ".webp")
    ow = max(2, int(width * min(max(scale, 0.05), 1.0)) // 2 * 2)
    graph = ("[1:v]scale={ow}:-2:flags=lanczos,format=rgba,setpts=PTS-STARTPTS+{at}/TB[o];"
             "[0:v]scale={w}:{h},setsar=1[base];"
             "[base][o]overlay=x='{x}*W-w/2':y='{y}*H-h/2':eof_action=pass:format=auto,format=yuv420p[v]").format(
                 ow=ow, at=_secs(at), w=width, h=height, x=x, y=y)
    has_sound = (await probe(video))["audio"]
    await _ffmpeg("-loglevel", "error", "-i", video, *(["-loop", "1", "-t", _secs(length)] if picture else _alpha_decoder(overlay)),
                  "-i", overlay, "-filter_complex", graph, "-map", "[v]",
                  *(["-map", "0:a:0", "-c:a", "copy"] if has_sound else ["-an"]), *ENCODE, "-t", _secs(length),
                  "-movflags", "+faststart", target)
    made = await probe(target)
    return {"seconds": made["seconds"], "width": made["width"], "height": made["height"]}
