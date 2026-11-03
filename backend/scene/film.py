"""The frame-exact work of a film made on its own audio (the Pocket Motion skill and the like), done with ffmpeg on this
machine: a reference image at 1500 px, a slice of the master audio, the timing track a clip is edited from, a clip
trimmed (stretched, or retimed so the lips meet the master's words) to exactly its frames, a proof sheet, subtitles
burned in, the clips joined on the master audio, and the spans where speech is heard.

A film is counted in frames, 24 a second, as its plan is: a clip covers f_in to f_out of the master. Nothing here
guesses a time; what cannot be done exactly is refused with the reason.
"""

import array
import asyncio
import json
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path

from .media import FPS, MediaError, _ffmpeg, ffmpeg_path, probe

REF_SIDE = 1500        # the longer side of an image used as a reference
SQUARE = (1080, 1080)  # the size a trimmed clip is made at unless another is asked
TRACK_SIDE = 720       # a timing track is a square of this size
MIN_FRAMES = 96        # 4 s: the shortest clip a video model makes; a shorter track is padded to it
MAX_PAD = 12           # frames a trimmed clip may be short and have its last frame held; more is refused
SHEET_TILE = 384       # proof sheets: the width of one frame, six to a row, sixty to a sheet
SHEET_ROW, SHEET_MAX = 6, 60
FONTS = Path(__file__).parent / "fonts"
FONT = "Poppins-Bold.ttf"
ENCODE = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p"]

# Retiming the lips (see segment_map): how far one stretch of speech may be slowed or sped, and how much faster a gap
# may play before its excess is cut instead.
SPEECH_FACTOR = (0.67, 2.0)
GAP_SPEEDUP = 1.4
SMOOTH_FROM = 1.15     # a stretch slowed more than this gets motion-interpolated frames


def _secs(value):
    return "{:.6f}".format(value)


def _fit(size):
    """Scale into a frame of `size`, keeping the shape, centred on black."""
    w, h = size
    return "scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1".format(w=w, h=h)


async def frames_of(video):
    """How many video frames a file holds, counted, not estimated from its length."""
    text = await _ffmpeg("-i", video, "-map", "0:v:0", "-c", "copy", "-f", "null", "-", check=False)
    found = re.findall(r"frame=\s*(\d+)", text)
    if not found:
        raise MediaError("{} has no video to count.".format(Path(video).name))
    return int(found[-1])


# ---------------------------------------------------------------- references and audio

async def reference(image, target, side=REF_SIDE):
    """The image with its longer side at most `side` pixels, shape kept, never made larger, as a PNG."""
    scale = "scale=w='min({0},iw)':h='min({0},ih)':force_original_aspect_ratio=decrease:flags=lanczos".format(side)
    await _ffmpeg("-loglevel", "error", "-i", image, "-map", "0:v:0", "-vf", scale, "-frames:v", "1", "-update", "1", target)
    found = await probe(target)
    return {"seconds": 0, "width": found["width"], "height": found["height"]}


async def audio_slice(source, f_in, f_out, target, pad=0.0):
    """The master's sound from frame f_in to frame f_out, exactly, as a WAV file (an MP3 would add a few milliseconds
    of silence at its start and move every word). pad: a slice shorter than this many seconds has silence added at its
    end up to it (a short line given to a model that needs a few seconds of sound)."""
    if not 0 <= f_in < f_out:
        raise MediaError("A slice runs from a frame to a later one.")
    start, end = f_in / FPS, f_out / FPS
    padded = max(float(pad or 0), end - start)
    if padded > end - start and (await probe(source))["seconds"] < end - 1 / FPS:   # padding must not hide a short master
        raise MediaError("The audio ends before the slice's end at {:.2f} s.".format(end))
    await _ffmpeg("-loglevel", "error", "-i", source, "-map", "0:a:0",
                  "-af", "atrim=start={}:end={},asetpts=PTS-STARTPTS{}".format(
                      _secs(start), _secs(end), ",apad=whole_dur={}".format(_secs(padded)) if padded > end - start else ""),
                  "-c:a", "pcm_s16le", target)
    found = await probe(target)
    if found["seconds"] < padded - 1 / FPS:
        raise MediaError("The audio ends at {:.2f} s, before the slice's end at {:.2f} s.".format(start + found["seconds"], end))
    return {"seconds": padded, "width": 0, "height": 0, **({"padded": round(padded - (end - start), 3)} if padded > end - start else {})}


# ---------------------------------------------------------------- the timing track

async def timing_track(frames, target, side=TRACK_SIDE):
    """A silent video that is the clock of a clip made by editing it: one block per shot at that shot's exact number
    of frames, grey and white in turn starting grey, each crossed by a dark square — left to right on grey, top to
    bottom on white — that enters on the block's first frame and is leaving on its last. A track shorter than
    MIN_FRAMES has its last block made longer. Returns its frame count, checked."""
    frames = [int(n) for n in frames]
    if not frames or any(n < 1 for n in frames):
        raise MediaError("A timing track needs one block of at least one frame per shot.")
    if sum(frames) < MIN_FRAMES:
        frames[-1] += MIN_FRAMES - sum(frames)
    box = side * 2 // 9   # 160 on a 720 square
    travel = side + box
    parts, labels = [], ""
    for i, n in enumerate(frames, start=1):
        d = n / FPS
        grey = i % 2 == 1
        move = "x='-{b}+{t}*t/{d}':y={c}".format(b=box, t=travel, d=_secs(d), c=(side - box) // 2) if grey else \
               "x={c}:y='-{b}+{t}*t/{d}'".format(b=box, t=travel, d=_secs(d), c=(side - box) // 2)
        parts.append("color=c={bg}:s={s}x{s}:r={r}:d={d}[bg{i}];color=c=0x464646:s={b}x{b}:r={r}:d={d}[sq{i}];"
                     "[bg{i}][sq{i}]overlay={m}:shortest=1,trim=end_frame={n},setpts=PTS-STARTPTS[b{i}]".format(
                         bg="0x808080" if grey else "0xEBEBEB", s=side, r=FPS, d=_secs(d + 1), b=box, i=i, m=move, n=n))
        labels += "[b{}]".format(i)
    graph = ";".join(parts) + ";{}concat=n={}:v=1:a=0,format=yuv420p[v]".format(labels, len(frames))
    await _ffmpeg("-loglevel", "error", "-filter_complex", graph, "-map", "[v]", "-an", "-r", FPS,
                  "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", target)
    made = await frames_of(target)
    if made != sum(frames):
        raise MediaError("The timing track came out at {} frames, not {}.".format(made, sum(frames)))
    return {"seconds": made / FPS, "width": side, "height": side, "frames": made, "blocks": frames}


# ---------------------------------------------------------------- trims

async def trim(video, frames, target, stretch=1.0, size=SQUARE, max_pad=MAX_PAD):
    """The clip cut to exactly `frames` frames from its start, picture only (its own sound is always dropped).
    stretch: the clip is first played that many times slower, for a clip that came back evenly sped up (an edit of a
    timing track). A clip up to `max_pad` frames short has its last frame held; shorter than that is refused."""
    frames, stretch = int(frames), float(stretch)
    if frames < 1 or not 0.5 <= stretch <= 2.0:
        raise MediaError("A trim needs a length in frames and a stretch between 0.5 and 2.")
    have = round(await frames_of(video) * stretch)
    short = frames - have
    if short > max_pad:
        raise MediaError("The clip is {} frames short of its {} frames: make it again rather than hold its last frame.".format(short, frames))
    chain = "{}fps={},tpad=stop_mode=clone:stop={},trim=end_frame={},setpts=PTS-STARTPTS,{},format=yuv420p".format(
        "setpts=PTS*{:.4f},".format(stretch) if stretch != 1 else "", FPS, max(short, 0) + 2, frames, _fit(size))
    await _ffmpeg("-loglevel", "error", "-i", video, "-map", "0:v:0", "-vf", chain, "-an", "-r", FPS, *ENCODE, target)
    return await _checked(target, frames, size, held=max(short, 0))


async def retime(video, segments, frames, target, size=SQUARE):
    """The clip rebuilt from its segments ([[source start, source end, factor], ...] in seconds; factor 2 plays a
    piece twice as long), then cut to exactly `frames`. A piece slowed more than SMOOTH_FROM gets interpolated frames,
    so a slowed mouth moves smoothly. See segment_map for how the segments are found."""
    pieces = [(float(s), float(e), float(f)) for s, e, f in segments if float(e) - float(s) > 0.5 / FPS]
    if not pieces:
        raise MediaError("A retime needs at least one segment.")
    n = len(pieces)
    graph = ["[0:v]fps={},split={}{}".format(FPS, n, "".join("[a{}]".format(i) for i in range(n)))]
    for i, (s, e, f) in enumerate(pieces):
        if e - s < 1.5 / FPS:   # one frame held: cloned to its length
            graph.append("[a{i}]trim=start={s},trim=end_frame=1,loop=loop={k}:size=1:start=0,setpts=N/{r}/TB[s{i}]".format(
                i=i, s=_secs(s), k=max(round((e - s) * f * FPS) - 1, 0), r=FPS))
            continue
        smooth = ",minterpolate=fps={}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1".format(FPS) if f > SMOOTH_FROM else ""
        graph.append("[a{i}]trim=start={s}:end={e},setpts=(PTS-STARTPTS)*{f:.4f}{m}[s{i}]".format(i=i, s=_secs(s), e=_secs(e), f=f, m=smooth))
    graph.append("{}concat=n={}:v=1:a=0,fps={},{},format=yuv420p,tpad=stop_mode=clone:stop={},trim=end_frame={},setpts=PTS-STARTPTS[v]".format(
        "".join("[s{}]".format(i) for i in range(n)), n, FPS, _fit(size), FPS, int(frames)))
    await _ffmpeg("-loglevel", "error", "-i", video, "-filter_complex", ";".join(graph), "-map", "[v]", "-an", "-r", FPS, *ENCODE, target)
    return await _checked(target, int(frames), size)


async def _checked(target, frames, size, **extra):
    made = await frames_of(target)
    if made != frames:
        raise MediaError("The trim came out at {} frames, not {}.".format(made, frames))
    return {"seconds": frames / FPS, "width": size[0], "height": size[1], "frames": frames, **extra}


def segment_map(lines, length, clip_length):
    """How to retime a clip so the lips of its lines meet the master's words.

    lines: [{"master": [s, e], "clip": [s, e]}] in the chunk's own seconds, one per line spoken on screen: where the
    master says it, and where the clip says it. length: the chunk's length; clip_length: the clip's. Returns
    [[source start, source end, factor], ...] that play back to exactly `length` seconds.

    The clip is gap, speech, gap, ..., gap. Each speech is stretched or squeezed onto its master span, by a factor kept
    within SPEECH_FACTOR; past that only its start is aligned and the time left goes to the next gap. Each gap fills the
    time between: a gap with too much source plays up to GAP_SPEEDUP faster, and beyond that its excess is cut at
    normal speed (from the start for the opening gap, from the end for any other); a gap with too little is stretched."""
    spoken = sorted(([float(l["master"][0]), float(l["master"][1]), float(l["clip"][0]), float(l["clip"][1])] for l in lines),
                    key=lambda x: x[2])
    out, src_at, out_at = [], 0.0, 0.0

    def gap(src_from, src_to, room, opening):
        source = src_to - src_from
        if room <= 0:
            return
        if source < 1 / FPS:   # no picture to stretch: one frame is held for the whole gap
            start = min(src_from, max(clip_length - 1 / FPS, 0))
            out.append([start, start + 1 / FPS, room * FPS])
            return
        if source > room and source / room > GAP_SPEEDUP:
            excess = source - room   # played at normal speed, the excess cut away
            src_from, src_to = (src_from + excess, src_to) if opening else (src_from, src_to - excess)
            out.append([src_from, src_to, 1.0])
        else:
            out.append([src_from, src_to, room / source])

    for i, (ms, me, cs, ce) in enumerate(spoken):
        cs, ce = max(cs, src_at), max(ce, cs)
        gap(src_at, cs, ms - out_at, i == 0)
        out_at = max(out_at, ms)
        if ce > cs:
            factor = min(max((me - ms) / (ce - cs), SPEECH_FACTOR[0]), SPEECH_FACTOR[1])
            out.append([cs, ce, factor])
            out_at += (ce - cs) * factor
        src_at = ce
    gap(src_at, clip_length, length - out_at, not spoken)
    return [[round(s, 4), round(e, 4), round(f, 4)] for s, e, f in out]


# ---------------------------------------------------------------- proof sheets, subtitles, the film

async def proof_sheets(video, marks, target):
    """Contact sheets of a film: the frame at each mark's time with its label burned in, SHEET_TILE wide, SHEET_ROW to
    a row, at most SHEET_MAX to a sheet. marks: [{"at": seconds, "label": "u012 00:41.3"}]. The first sheet is
    `target`, the next ones beside it (_2, _3 ...). Returns the paths."""
    marks = [m for m in marks if isinstance(m, dict) and isinstance(m.get("at"), (int, float)) and m["at"] >= 0]
    if not marks:
        raise MediaError("A proof sheet needs at least one frame to show.")
    target, made = Path(target), []
    with tempfile.TemporaryDirectory() as work:
        shutil.copy(FONTS / FONT, Path(work) / FONT)
        for sheet, start in enumerate(range(0, len(marks), SHEET_MAX), start=1):
            batch = marks[start:start + SHEET_MAX]
            args, graph = ["-loglevel", "error"], []
            for i, mark in enumerate(batch):
                (Path(work) / "l{}.txt".format(i)).write_text(str(mark.get("label") or "")[:40], encoding="utf-8")
                args += ["-ss", _secs(mark["at"]), "-i", Path(video).resolve()]
                graph.append("[{i}:v]trim=end_frame=1,setpts=PTS-STARTPTS,scale={w}:-2,setsar=1,drawtext=fontfile={f}:textfile=l{i}.txt:expansion=none:"
                             "fontsize=20:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=6:x=8:y=8[t{i}]".format(i=i, w=SHEET_TILE, f=FONT))
            rows = -(-len(batch) // SHEET_ROW)
            graph.append("{}concat=n={}:v=1:a=0,tile={}x{}:padding=4:color=black[v]".format(
                "".join("[t{}]".format(i) for i in range(len(batch))), len(batch), SHEET_ROW, rows))
            path = target if sheet == 1 else target.with_name("{}_{}{}".format(target.stem, sheet, target.suffix))
            await _ffmpeg(*args, "-filter_complex", ";".join(graph), "-map", "[v]", "-frames:v", "1", "-update", "1",
                          path.resolve(), cwd=work)
            made.append(path)
    return made


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pocket,Poppins,66,&H0004BCFC,&H0004BCFC,&H00101010,&H99000000,-1,0,0,0,100,100,0,0,1,1.8,2.8,2,60,60,45,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
ROW_CHARS, ROWS = 28, 2


def _split_rows(words, chars=ROW_CHARS):
    """The words as one row, or two broken at the word nearest the middle, each at most `chars`: a list of rows (each
    a list of words), or None if they don't fit."""
    if len(" ".join(words)) <= chars:
        return [list(words)]
    best = None
    for k in range(1, len(words)):
        top, bottom = " ".join(words[:k]), " ".join(words[k:])
        if len(top) <= chars and len(bottom) <= chars:
            score = abs(len(top) - len(bottom))
            best = (score, k) if best is None or score < best[0] else best
    return [list(words[:best[1]]), list(words[best[1]:])] if best else None


def _rows(words, chars=ROW_CHARS):
    """The words as one row, or two broken at the word nearest the middle, each at most `chars`; None if they don't fit."""
    rows = _split_rows(words, chars)
    return r"\N".join(" ".join(row) for row in rows) if rows else None


def _clock(seconds):
    cs = max(0, round(seconds * 100))
    return "{}:{:02d}:{:02d}.{:02d}".format(cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


def _clean_words(text):
    return str(text or "").replace("{", "(").replace("}", ")").replace("\\", "/").split()


def _pieces(words, chars):
    """The words in cues of at most two rows each, in order."""
    pieces, current = [], []
    for word in words:
        if current and _split_rows(current + [word], chars) is None:
            pieces.append(current)
            current = []
        current.append(word)
    pieces.append(current)
    return pieces


def subtitle_cues(lines, narrator="narrator", chars=ROW_CHARS):
    """The cues of the house subtitle style, from the transcript's lines ({"start", "end", "text", "speaker",
    "lead", "words"?}): a line splits into cues of at most two rows; the cues share the line's speech time by their length.
    A line's speech needs words / 2.5 s (narration) or / 3 s (dialogue); when its span is more than 2 s longer, the
    rest is music or silence — at its front on a "lead" line (the film's first, or the first after a scene cut), at
    its back otherwise — and the cues keep to the speech. A line with the times of its words ("words": [{"word",
    "start", "end"}]) has its cues timed by them instead, and each cue keeps its words' times for karaoke.
    Returns [(start, end, text)], or (start, end, text, [(word, start, end)]) for a cue timed by its words."""
    cues = []
    for line in lines:
        timed = [w for w in (line.get("words") or []) if _clean_words(w.get("word"))]
        if timed:
            flat = [(" ".join(_clean_words(w["word"])), float(w["start"]), float(w["end"])) for w in timed]
            at = 0
            for piece in _pieces([w for w, _, _ in flat], chars):
                these = flat[at:at + len(piece)]
                at += len(piece)
                cues.append((round(these[0][1], 3), round(these[-1][2], 3), _rows(piece, chars) or " ".join(piece),
                             [(w, round(s, 3), round(e, 3)) for w, s, e in these]))
            continue
        words = _clean_words(line.get("text"))
        start, end = float(line["start"]), float(line["end"])
        if not words or end <= start:
            continue
        need = len(words) / (2.5 if str(line.get("speaker") or narrator) == narrator else 3.0)
        if end - start - need > 2:
            start, end = (end - need, end) if line.get("lead") else (start, start + need)
        texts = [_rows(p, chars) or " ".join(p) for p in _pieces(words, chars)]
        total, at = sum(len(t) for t in texts), start
        for text in texts:
            span = (end - start) * len(text) / total
            cues.append((round(at, 3), round(at + span, 3), text))
            at += span
    return cues


def words_for(lines, transcript):
    """The lines with the times of their words, from a transcription's JSON text that has them (segments with
    "words": [{"word" or "text", "start", "end"}], as WhisperX writes). A word goes to the line its middle falls in."""
    data = json.loads(transcript)
    segments = data.get("segments") if isinstance(data, dict) else data
    words = []
    for seg in segments if isinstance(segments, list) else []:
        for w in (seg.get("words") or []) if isinstance(seg, dict) else []:
            if isinstance(w, dict) and isinstance(w.get("start"), (int, float)) and isinstance(w.get("end"), (int, float)):
                words.append({"word": str(w.get("word") or w.get("text") or "").strip(), "start": float(w["start"]), "end": float(w["end"])})
    if not words:
        raise MediaError("The transcript has no times for its words, so there is nothing to light word by word.")
    out = []
    for line in lines:
        mine = [w for w in words if line["start"] - 0.05 <= (w["start"] + w["end"]) / 2 <= line["end"] + 0.05 and w["word"]]
        out.append(dict(line, words=mine) if mine else line)
    return out


# ---------------------------------------------------------------- the look of subtitles

SUB_FONT_DIRS = [FONTS, Path(r"C:\Windows\Fonts"), Path("/usr/share/fonts"), Path("/Library/Fonts"), Path("/System/Library/Fonts")]
SUB_FONTS = {   # the name a subtitle asks for -> the files that hold it (the first found is used), in the folders above
    "Poppins": ["Poppins-Bold.ttf"],
    "Arial": ["arialbd.ttf", "Arial Bold.ttf", "arial.ttf"],
    "Arial Black": ["ariblk.ttf", "Arial Black.ttf"],
    "Impact": ["impact.ttf", "Impact.ttf"],
    "Georgia": ["georgiab.ttf", "Georgia Bold.ttf", "georgia.ttf"],
    "Verdana": ["verdanab.ttf", "Verdana Bold.ttf", "verdana.ttf"],
    "Segoe UI": ["segoeuib.ttf", "segoeui.ttf"],
    "Calibri": ["calibrib.ttf", "calibri.ttf"],
    "Bahnschrift": ["bahnschrift.ttf"],
    "Trebuchet MS": ["trebucbd.ttf", "trebuc.ttf"],
    "Times New Roman": ["timesbd.ttf", "times.ttf"],
    "Comic Sans MS": ["comicbd.ttf", "comic.ttf"],
    "Courier New": ["courbd.ttf", "cour.ttf"],
    "DejaVu Sans": ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"],
}
PLACES = {"bottom": 2, "middle": 5, "top": 8}   # ASS alignments, centred
HOUSE = {"font": "Poppins", "size": 66, "colour": "#FCBC04", "outline_colour": "#101010", "outline": 1.8,
         "shadow": 2.8, "shadow_colour": "#00000066", "bold": True, "place": "bottom", "margin": 45,
         "box": None, "highlight": "#FFFFFF", "karaoke": None}
KARAOKE = ("word", "fill")   # word: only the word being said is lit; fill: each word lights as it is said and stays


def _font_file(name):
    """The file of a font for subtitles: one of SUB_FONTS, or a .ttf / .otf put in the fonts folder (named like
    OpenSans-Bold.ttf). None when it is not on this machine."""
    for file in SUB_FONTS.get(name, []):
        for folder in SUB_FONT_DIRS:
            for found in ([folder / file] if folder.is_dir() else []):
                if found.is_file():
                    return found
    for found in sorted(FONTS.glob("*.[ot]tf")):
        if _family(found) == name:
            return found
    return None


def _family(path):
    """OpenSans-Bold.ttf -> "Open Sans": the name a font dropped in the fonts folder goes by."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", Path(path).stem.split("-")[0])


def subtitle_fonts():
    """The font names subtitles may ask for on this machine."""
    names = [name for name in SUB_FONTS if _font_file(name)]
    return names + [n for n in sorted({_family(f) for f in FONTS.glob("*.[ot]tf")}) if n not in names]


def ass_colour(value, what="A colour"):
    """"#RRGGBB" or "#RRGGBBAA" (AA how solid: ff solid, 00 clear) as ASS writes it, &HAABBGGRR with AA how clear."""
    found = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", str(value or ""))
    if not found:
        raise MediaError("{} is written #RRGGBB or #RRGGBBAA.".format(what))
    rgb, solid = found.group(1), int(found.group(2) or "ff", 16)
    return "&H{:02X}{}".format(255 - solid, (rgb[4:6] + rgb[2:4] + rgb[0:2]).upper())


def subtitle_style(asked):
    """A subtitle look, checked: the house look with what is asked laid over it. Raises MediaError."""
    style = dict(HOUSE)
    for key, value in (asked or {}).items():
        if key not in HOUSE:
            raise MediaError("A subtitle look has no '{}'; it has: {}.".format(key, ", ".join(HOUSE)))
        style[key] = value
    if not _font_file(style["font"]):
        raise MediaError("The font '{}' is not on this machine; there are: {}.".format(style["font"], ", ".join(subtitle_fonts())))
    if style["place"] not in PLACES:
        raise MediaError("place is bottom, middle or top.")
    if style["karaoke"] not in (None, *KARAOKE):
        raise MediaError("karaoke is word or fill.")
    for key, low, high in (("size", 16, 200), ("outline", 0, 12), ("shadow", 0, 12), ("margin", 0, 600)):
        if isinstance(style[key], bool) or not isinstance(style[key], (int, float)) or not low <= style[key] <= high:
            raise MediaError("{} is a number from {} to {}.".format(key, low, high))
    for key in ("colour", "outline_colour", "shadow_colour", "highlight") + (("box",) if style["box"] else ()):
        ass_colour(style[key], key)
    style["bold"] = style["bold"] is not False
    return style


def ass_head(style, width, height):
    """The head of a subtitle file in this look, laid out for a frame of width x height (sizes are given for a frame
    1080 high and scaled to it)."""
    k = height / 1080
    karaoke_fill = style["karaoke"] == "fill"
    primary = ass_colour(style["highlight"] if karaoke_fill else style["colour"])
    secondary = ass_colour(style["colour"])
    if style["box"]:   # a box behind the words: ASS draws it in the outline colour, the outline width its padding
        border, outline_colour, outline, shadow = 3, ass_colour(style["box"]), max(style["outline"], 8) * k, 0
    else:
        border, outline_colour, outline, shadow = 1, ass_colour(style["outline_colour"]), style["outline"] * k, style["shadow"] * k
    line = ("Style: Pocket,{font},{size:.0f},{p},{s},{o},{b},{bold},0,0,0,100,100,0,0,{border},{outline:.1f},{shadow:.1f},{align},"
            "{ml:.0f},{ml:.0f},{mv:.0f},1").format(
        font=style["font"], size=style["size"] * k, p=primary, s=secondary, o=outline_colour, b=ass_colour(style["shadow_colour"]),
        bold=-1 if style["bold"] else 0, border=border, outline=outline, shadow=shadow, align=PLACES[style["place"]],
        ml=60 * k, mv=style["margin"] * k)
    top, rest = ASS_HEAD.split("Style: Pocket")
    top = top.replace("PlayResX: 1080", "PlayResX: {}".format(width)).replace("PlayResY: 1080", "PlayResY: {}".format(height))
    return top + line + rest[rest.index("\n"):]


def row_chars(style, width):
    """How many letters fit in a row in this look: 28 at the house size on a square, more on a wider frame."""
    wider = max(width / 1080, 1) if width else 1
    return max(12, int(ROW_CHARS * 66 / style["size"] * wider))


def _events(cues, style):
    """The Dialogue lines for the cues; a cue with its words' times is lit word by word when karaoke is asked."""
    out = []
    for cue in cues:
        start, end, text = cue[:3]
        words = cue[3] if len(cue) > 3 else None
        if not words or not style or not style.get("karaoke"):
            out.append("Dialogue: 0,{},{},Pocket,,0,0,0,,{}\n".format(_clock(start), _clock(end), text))
            continue
        rows = text.split(r"\N")
        breaks = {len(rows[0].split())} if len(rows) == 2 else set()
        if style["karaoke"] == "fill":
            parts, at = [], start
            for i, (word, ws, we) in enumerate(words):
                lead = max(0, round((ws - at) * 100))
                nxt = words[i + 1][1] if i + 1 < len(words) else end
                parts.append("{}{}{{\\kf{}}}{}".format(r"\N" if i in breaks else (" " if i else ""), "{{\\k{}}}".format(lead) if lead else "",
                                                      max(1, round((nxt - ws) * 100)), word))
                at = nxt
            out.append("Dialogue: 0,{},{},Pocket,,0,0,0,,{}\n".format(_clock(start), _clock(end), "".join(parts)))
            continue
        lit = ass_colour(style["highlight"])
        for i, (word, ws, we) in enumerate(words):
            a = start if i == 0 else ws
            b = words[i + 1][1] if i + 1 < len(words) else end
            if b <= a:
                continue
            shown = "".join("{}{}".format(r"\N" if j in breaks else (" " if j else ""),
                                          "{{\\1c{}}}{}{{\\r}}".format(lit, w) if j == i else w) for j, (w, _, _) in enumerate(words))
            out.append("Dialogue: 0,{},{},Pocket,,0,0,0,,{}\n".format(_clock(a), _clock(b), shown))
    return "".join(out)


async def burn_subtitles(video, cues, target, style=None):
    """The film with its cues burned in, its sound copied: in the house style (Poppins, yellow, bottom centre) when no
    look is given, or in `style` (see subtitle_style: font, size, colours, outline, shadow, place, margin, a box behind
    the words, karaoke word by word on cues that keep their words' times)."""
    if not cues:
        raise MediaError("There are no subtitles to burn in.")
    if style:
        found = await probe(video)
        head = ass_head(style, found["width"] // 2 * 2 or 1080, found["height"] // 2 * 2 or 1080)
        font = _font_file(style["font"])
    else:
        head, font = ASS_HEAD, FONTS / FONT
    with tempfile.TemporaryDirectory() as work:
        (Path(work) / "fonts").mkdir()
        shutil.copy(font, Path(work) / "fonts" / font.name)
        (Path(work) / "subs.ass").write_text(head + _events(cues, style), encoding="utf-8")
        await _ffmpeg("-loglevel", "error", "-i", Path(video).resolve(), "-map", "0:v:0", "-map", "0:a?",
                      "-vf", "ass=subs.ass:fontsdir=fonts:shaping=complex", "-r", FPS, *ENCODE, "-c:a", "copy",
                      "-movflags", "+faststart", Path(target).resolve(), cwd=work)
    found = await probe(target)
    return {"seconds": found["seconds"], "width": found["width"], "height": found["height"], "cues": len(cues),
            **({"font": style["font"], "karaoke": style["karaoke"]} if style else {})}


async def join_on_master(clips, master, target):
    """The trimmed clips in order, their pictures copied as they are (they share one encoding), with the master
    audio as the only sound. Refuses when the pictures and the master differ by more than one frame."""
    if not clips:
        raise MediaError("There is nothing to join.")
    total = 0
    for clip in clips:
        total += await frames_of(clip)
    with tempfile.TemporaryDirectory() as work:
        listing = Path(work) / "clips.txt"
        listing.write_text("ffconcat version 1.0\n" + "".join(
            "file '{}'\n".format(Path(c).resolve().as_posix().replace("'", r"'\''")) for c in clips), encoding="utf-8")
        await _ffmpeg("-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing, "-i", master,
                      "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                      "-t", _secs(total / FPS), "-movflags", "+faststart", target)
    sound = (await probe(master))["seconds"]
    if abs(sound - total / FPS) > 1 / FPS + 0.01:
        raise MediaError("The clips last {:.3f} s and the master {:.3f} s: they must match within a frame.".format(total / FPS, sound))
    found = await probe(target)
    return {"seconds": total / FPS, "width": found["width"], "height": found["height"], "frames": total}


# ---------------------------------------------------------------- where speech is heard

async def _envelope(path):
    """The sound's loudness every 10 ms (RMS of 160 samples at 16 kHz, mono), as a list. Plain Python: a 30-minute
    episode takes about two seconds, which is nothing beside the run it is part of."""
    process = await asyncio.create_subprocess_exec(
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
        "-f", "s16le", "-", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        raw, err = await process.communicate()
    except asyncio.CancelledError:
        process.kill()
        raise
    if process.returncode != 0:
        raise MediaError("ffmpeg could not read the sound: " + err.decode("utf-8", "replace").strip()[-300:])
    samples = array.array("h")
    samples.frombytes(raw[:len(raw) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()   # ffmpeg wrote little-endian
    n = len(samples) // 160
    if not n:
        raise MediaError("{} has no sound to measure.".format(Path(path).name))
    return [math.sqrt(sum(v * v for v in samples[k * 160:(k + 1) * 160]) / 160) / 32768 for k in range(n)]


def _percentile(values, share):
    """The value `share` of the way up the sorted values, between two neighbours where it falls between them."""
    ordered = sorted(values)
    at = share * (len(ordered) - 1)
    low = int(at)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def _threshold(r):
    peak = max(r)
    # 3% of the peak, or 12 dB over the noise floor — but never over half the peak, so a sound loud from end to end
    # (no quiet floor to measure) is still heard
    return max(peak * 0.03, min(_percentile(r, 0.10) * 4, peak * 0.5), 0.002)


def _runs(r, a, b, thr, gap=0.25):
    """The stretches between a and b seconds where the sound is over thr, joined across pauses up to `gap` s."""
    out, s, last = [], None, None
    for k in range(max(0, int(a * 100)), min(int(b * 100), len(r))):
        if r[k] >= thr:
            s = k if s is None else s
            last = k
        elif s is not None and (k - last) / 100 > gap:
            out.append([s / 100, (last + 1) / 100])
            s = None
    if s is not None:
        out.append([s / 100, (last + 1) / 100])
    return out


async def speech_runs(path, windows):
    """For each window [a, b] in seconds, the runs of sound in it: [[[s, e], ...], ...]."""
    r = await _envelope(path)
    thr = _threshold(r)
    return [_runs(r, float(a), float(b), thr) for a, b in windows]


async def speech_spans(path, lines):
    """The measured speech of every character line: {n: [s, e]}. lines: the whole transcript, [{"n", "start", "end",
    "speaker"}] in seconds, the narrator's speaker written "narrator". Runs of sound are split where a character's
    line meets their own next line, and each piece goes to the line it overlaps most; narration around a line is
    dropped. A character line with no piece gets no span (it keeps its transcript times)."""
    r = await _envelope(path)
    thr = _threshold(r)
    ordered = sorted(lines, key=lambda l: float(l["start"]))
    cuts = [(float(a["end"]) + float(b["start"])) / 2 for a, b in zip(ordered, ordered[1:])
            if a["speaker"] == b["speaker"] != "narrator"]
    pieces = []
    for s, e in _runs(r, 0, len(r) / 100, thr):
        points = [s] + [c for c in cuts if s < c < e] + [e]
        pieces += list(zip(points, points[1:]))

    def overlap(piece, line):
        return min(piece[1], float(line["end"])) - max(piece[0], float(line["start"]))

    spans = {}
    for piece in pieces:
        best = max(ordered, key=lambda l: overlap(piece, l))
        if overlap(piece, best) > 0 and best["speaker"] != "narrator":
            s0, e0 = spans.get(best["n"], piece)
            spans[best["n"]] = [round(min(s0, piece[0]), 2), round(max(e0, piece[1]), 2)]
    return spans


def write_json(data, target):
    Path(target).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
