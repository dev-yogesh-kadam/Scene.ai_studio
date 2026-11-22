"""Video and audio helpers built on ffmpeg: last frame of a clip, joining clips, cutting audio, timeline export.

ffmpeg comes from the imageio-ffmpeg package (a bundled binary for macOS, Windows and Linux),
or from the system if that package is missing.
"""

import asyncio
import contextlib
import glob
import os
import weakref
import re
import time
import shutil
from pathlib import Path

FPS = 24
FFMPEG_LIMIT = 2 * 3600   # seconds one ffmpeg may run: far beyond the longest encode of a film, so only a hung one meets it


class MediaError(Exception):
    pass


def ffmpeg_path():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        if not found:
            raise MediaError("ffmpeg is not installed. Run the start script again to install the packages.")
        return found


async def _ffmpeg(*args, check=True, cwd=None, limit=FFMPEG_LIMIT):
    """Run ffmpeg and return what it said. cwd: the folder it runs in, so a filter can name its files (subtitles, a
    font) without the escaping a full Windows path needs inside a filter. limit: seconds before it is stopped as hung."""
    # No keyboard: ffmpeg reads keys from stdin, and a "c" reaching the studio's console left one waiting for a command for good.
    process = await asyncio.create_subprocess_exec(
        ffmpeg_path(), "-hide_banner", "-nostdin", "-y", *[str(a) for a in args],
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, cwd=cwd)
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), limit)
    except asyncio.CancelledError:   # the job this was for was cancelled: don't leave ffmpeg running
        process.kill()
        raise
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise MediaError("ffmpeg stopped responding and was stopped after {:.0f} seconds.".format(limit))
    text = stderr.decode("utf-8", "replace")
    if check and process.returncode != 0:
        raise MediaError("ffmpeg failed: " + ffmpeg_said(text))
    return text


ERROR_WORDS = re.compile(r"error|fail|invalid|cannot|could not|no such|not found|unable|mismatch", re.I)


def ffmpeg_said(text, most=1500):
    """What a failed ffmpeg said, for the job's error (the admin console shows it whole): the lines that name a problem
    first, as ffmpeg's cause comes before the lines that only say each part stopped, then the end of what it said."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    first = [line for line in lines if ERROR_WORDS.search(line) and "Terminating thread" not in line][:6]
    tail = [line for line in lines[-4:] if line not in first]
    return "\n".join(first + (["…"] if first and tail else []) + tail)[:most]


async def probe(path):
    """Length in seconds, frame size (0 if unknown) and whether the file has an audio stream."""
    text = await _ffmpeg("-i", path, check=False)
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
    seconds = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3)) if match else 0.0
    size = re.search(r"Stream #\S+.*Video:.*?\b(\d{2,5})x(\d{2,5})\b", text)
    return {"seconds": seconds, "audio": bool(re.search(r"Stream #\S+.*Audio:", text)),
            "width": int(size.group(1)) if size else 0, "height": int(size.group(2)) if size else 0}


async def last_frame(video, target):
    """Save the last frame of a video as an image."""
    await _ffmpeg("-loglevel", "error", "-sseof", "-1", "-i", video, "-update", "1", "-q:v", "1", target)
    return target


POSTER_WIDTH = 960


def poster_path(video):
    """Where a video's poster is kept: next to it, in a folder of its own."""
    return video.parent / ".posters" / (video.name + ".jpg")


# Posters made at once, at most: a canvas of new pictures asks for all of theirs together. One limit per event loop.
POSTERS_AT_ONCE = 3
_poster_gates = weakref.WeakKeyDictionary()


def _poster_gate():
    loop = asyncio.get_running_loop()
    if loop not in _poster_gates:
        _poster_gates[loop] = asyncio.Semaphore(POSTERS_AT_ONCE)
    return _poster_gates[loop]


def fresh(target, source):
    """Whether a poster or frame made from `source` is there, whole, and newer than it."""
    try:
        made = target.stat()
    except FileNotFoundError:
        return False
    return made.st_size > 0 and made.st_mtime >= source.stat().st_mtime


# One maker per poster or frame (its path), per event loop: a new result's poster is asked for at once by the studio
# (make_poster_soon) and by the canvas loading it, and two ffmpegs writing one file gave the page an empty or half-made
# picture (a 500 under load). The others wait for it and are given the one made.
_making = weakref.WeakKeyDictionary()


@contextlib.asynccontextmanager
async def making(target):
    locks = _making.setdefault(asyncio.get_running_loop(), {})
    key = str(target)
    lock, users = locks.get(key) or (asyncio.Lock(), 0)
    locks[key] = (lock, users + 1)
    try:
        async with lock:
            yield
    finally:
        lock, users = locks[key]
        if users <= 1:
            del locks[key]
        else:
            locks[key] = (lock, users - 1)


def _partial(target):
    """Where a poster or frame is written before it is put in place whole: "shot.mp4.jpg" -> "shot.mp4.partial.jpg"
    (ffmpeg picks its format from the last suffix)."""
    return target.with_name(target.name[:-len(target.suffix)] + ".partial" + target.suffix)


def _put_in_place(partial, target, tries=20):
    """Move a finished file over the one the page is given. On Windows a file still being sent (an older poster) can't
    be replaced: tried again for two seconds. Call it off the event loop."""
    for attempt in range(tries):
        try:
            return os.replace(partial, target)
        except PermissionError:
            if attempt == tries - 1:
                partial.unlink(missing_ok=True)
                raise
            time.sleep(0.1)


async def poster(video):
    """A small still from the start of a video, or a small copy of a picture, for its thumbnail. Made once and kept."""
    target = poster_path(video)
    if fresh(target, video):
        return target
    async with making(target):
        if fresh(target, video):   # made while this one waited
            return target
        async with _poster_gate():
            return await _make_poster(video, target)


def remove_result(path):
    """Delete a finished file and what was made from it for its thumbnail: its poster and a video's keyframes. On
    Windows a file ffmpeg still reads (its poster being made, a moment after it was) is tried again for two seconds:
    call it off the event loop (db.offload) from async code."""
    path = Path(path)
    _gone(path)
    posters = path.parent / ".posters"
    if posters.is_dir():
        for made in [*posters.glob(glob.escape(path.name) + "*.jpg"), *posters.glob(glob.escape(path.name) + "*.webp")]:   # <name>.jpg, <name>.<tenth>.jpg, <name>.webp
            _gone(made)


def _gone(path, tries=20):
    for attempt in range(tries):
        try:
            return path.unlink(missing_ok=True)
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.1)


def webp_of(poster_file):
    """Where a poster's WebP copy is kept: beside it ("shot.mp4.jpg" -> "shot.mp4.webp")."""
    return Path(poster_file).with_suffix(".webp")


def make_webp(poster_file, quality=80):
    """A poster's WebP copy (a third smaller than its JPEG, for the same picture), made once. None if it can't be."""
    target = webp_of(poster_file)
    if target.is_file() and target.stat().st_mtime >= Path(poster_file).stat().st_mtime:
        return target
    try:
        from PIL import Image
        with Image.open(poster_file) as picture:
            partial = target.with_name(target.name + ".partial")
            picture.save(partial, "WEBP", quality=quality, method=4)
        partial.replace(target)
        return target
    except (OSError, ValueError):
        return None


async def make_poster_soon(path):
    """Make a new result's poster now, so its thumbnail is ready when the page asks. Best effort."""
    try:
        made = await poster(path)
        await asyncio.to_thread(make_webp, made)   # a smaller copy for the browsers that take it, made once
    except (MediaError, OSError):
        pass


async def _make_poster(video, target):
    target.parent.mkdir(exist_ok=True)
    partial = _partial(target)
    partial.unlink(missing_ok=True)
    scale = "scale='min({},iw)':-2".format(POSTER_WIDTH)
    # A clip shorter than 0.1 s has no frame there. A still picture (a JPEG) gives nothing after any -ss, even 0, so the
    # last try reads it without one.
    for start in ("0.1", "0", None):
        seek = ("-ss", start) if start else ()
        await _ffmpeg("-loglevel", "error", *seek, "-i", video, "-frames:v", "1", "-vf", scale, "-q:v", "3",
                      "-update", "1", partial, check=False)
        if partial.is_file() and partial.stat().st_size:
            await asyncio.to_thread(_put_in_place, partial, target)
            return target
    partial.unlink(missing_ok=True)
    raise MediaError("That video can't be read.")


async def frame_at(video, seconds, target, width=POSTER_WIDTH):
    """Save the frame of a video at `seconds` as a JPEG no wider than `width`. Returns the target, or None when the
    video has no frame there. Written beside it and put in place whole, so a page never reads half of one."""
    partial = _partial(target)
    partial.unlink(missing_ok=True)
    await _ffmpeg("-loglevel", "error", "-ss", "{:.3f}".format(max(0.0, seconds)), "-i", video, "-frames:v", "1",
                  "-vf", "scale='min({},iw)':-2".format(width), "-q:v", "3", "-update", "1", partial, check=False)
    if not (partial.is_file() and partial.stat().st_size):
        partial.unlink(missing_ok=True)
        return None
    await asyncio.to_thread(_put_in_place, partial, target)
    return target


async def changes(video):
    """How much the picture changes into each frame of a video: [(seconds, score)], the score 0 (the same picture) to
    1 (a different one), measured on a small copy, so it is quick (a tenth of a second for a 10 s clip)."""
    text = await _ffmpeg("-i", video, "-an", "-vf", r"scale=160:-2,select='gte(scene\,0)',metadata=print", "-f", "null", "-", check=False)
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", text)]
    scores = [float(s) for s in re.findall(r"lavfi\.scene_score=([\d.]+)", text)]
    return list(zip(times, scores))


async def cut_audio(source, start, seconds, target):
    """Save a piece of an audio (or video) file's sound as a WAV file."""
    await _ffmpeg("-loglevel", "error", "-ss", "{:.3f}".format(start), "-t", "{:.3f}".format(seconds),
                  "-i", source, "-vn", "-c:a", "pcm_s16le", target)
    return target


async def join(clips, target):
    """Join chained clips into one video.

    Each clip after the first starts on the last frame of the clip before it, so that repeated
    frame (and its one frame of sound: 1/24 s at 24 fps, 1/48 s at 48) is dropped.
    """
    with_audio = all([(await probe(clip))["audio"] for clip in clips])
    args, filters, labels = ["-loglevel", "error"], [], ""
    for i, clip in enumerate(clips):
        args += ["-i", clip]
        skip = "trim=start_frame=1," if i else ""
        filters.append("[{0}:v]{1}setpts=PTS-STARTPTS[v{0}]".format(i, skip))
        labels += "[v{}]".format(i)
        if with_audio:
            askip = "atrim=start={:.5f},".format(1 / await frame_rate(clip)) if i else ""
            filters.append("[{0}:a]{1}asetpts=PTS-STARTPTS[a{0}]".format(i, askip))
            labels += "[a{}]".format(i)
    filters.append("{}concat=n={}:v=1:a={}[v]{}".format(labels, len(clips), int(with_audio), "[a]" if with_audio else ""))
    args += ["-filter_complex", ";".join(filters), "-map", "[v]"]
    if with_audio:
        args += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    args += ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", target]
    await _ffmpeg(*args)
    return target


STILL_BITRATE = 60   # kb/s: a picture this thin may be one frame held still; anything richer is a real video

# A sound kept as it is, in the file type its codec belongs in; any other sound is made AAC in an .m4a.
SOUND_FILES = {"aac": ".m4a", "mp3": ".mp3", "flac": ".flac", "opus": ".ogg", "vorbis": ".ogg", "pcm_s16le": ".wav", "pcm_s24le": ".wav"}


async def sound_only(path):
    """Whether a video file is really a sound: it has sound, and its picture is cover art, or one frame that never
    changes from start to end (what some apps make when they export audio "as a video")."""
    text = await _ffmpeg("-i", path, check=False)
    if not re.search(r"Stream #\S+.*Audio:", text):
        return False
    video = re.search(r"Stream #\S+.*Video:.*", text)
    if not video:
        return True
    if "(attached pic)" in video.group(0):
        return True
    rate = re.search(r"(\d+) kb/s", video.group(0))
    if not rate or int(rate.group(1)) > STILL_BITRATE:
        return False
    # Thin enough to be a still: check that the picture really never moves.
    seconds = (await probe(path))["seconds"]
    said = await _ffmpeg("-i", path, "-map", "0:v:0", "-vf", "freezedetect=n=0.003:d=0.5", "-f", "null", "-", check=False)
    starts = [float(s) for s in re.findall(r"freeze_start: ([\d.]+)", said)]
    ends = [float(s) for s in re.findall(r"freeze_end: ([\d.]+)", said)]
    return bool(starts) and starts[0] <= 0.1 and (not ends or ends[-1] >= seconds - 0.2)


async def keep_sound(path, stem):
    """The sound of a file, without its picture, as a file of its own next to it: its codec copied when it fits a sound
    file, made AAC otherwise. stem: the new file's name without its type. Returns the new path."""
    text = await _ffmpeg("-i", path, check=False)
    codec = re.search(r"Stream #\S+.*Audio: (\w+)", text)
    suffix = SOUND_FILES.get(codec.group(1) if codec else "", ".m4a")
    target = Path(path).with_name(stem + suffix)
    copy = codec and codec.group(1) in SOUND_FILES
    await _ffmpeg("-loglevel", "error", "-i", path, "-map", "0:a:0", "-vn", *(["-c:a", "copy"] if copy else ["-c:a", "aac", "-b:a", "192k"]), target)
    return target


MUSIC_UNDER = 0.35   # how loud added music is against the video's own sound
DUCK_THRESHOLD = 0.01   # the video's own sound louder than this (-40 dB: speech, an effect) turns the music down
DUCK_RATIO = 10         # how far it goes down: about 9 dB under a voice at -22 dB, measured
LOUDNESS = "loudnorm=I=-14:TP=-1.5:LRA=11"   # what a finished film is levelled to: the loudness the social apps play at


async def level(video, target):
    """The video with its sound levelled to LOUDNESS, so a film of shots made at different levels plays at one, as
    loud as the apps it is posted to expect. The picture is copied. Returns the target."""
    await _ffmpeg("-loglevel", "error", "-i", video, "-map", "0:v", "-map", "0:a", "-c:v", "copy",
                  "-af", LOUDNESS + ",aresample=48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", target)
    return target


async def add_sound(video, sound, target, replace=False):
    """Put a sound on a video and save the result as `target`. Returns its length in seconds.

    The picture is copied as it is, not encoded again. The sound is looped if it is shorter than the video,
    cut to the video's length, and faded out at the end. With replace it takes the place of the video's own
    sound; otherwise it is mixed under it (music under speech and effects), and goes quieter still while the
    video's own sound is loud (someone speaks), coming back up in the pauses."""
    info = await probe(video)
    if not info["seconds"]:
        raise MediaError("That video can't be read.")
    length = info["seconds"]
    fade = "afade=t=in:d=0.3,afade=t=out:st={:.3f}:d=0.8".format(max(0.0, length - 0.8))
    if info["audio"] and not replace:
        mix = ("[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[own][key];"
               "[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={},{}[music];"
               "[music][key]sidechaincompress=threshold={}:ratio={}:attack=20:release=400[under];"
               "[own][under]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
               .format(MUSIC_UNDER, fade, DUCK_THRESHOLD, DUCK_RATIO))
    else:
        mix = "[1:a]{}[a]".format(fade)
    await _ffmpeg("-loglevel", "error", "-i", video, "-stream_loop", "-1", "-i", sound, "-filter_complex", mix,
                  "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                  "-t", "{:.3f}".format(length), "-movflags", "+faststart", target)
    return length


FADE = 0.5   # seconds of a crossfade between two clips of a cut


async def sequence(parts, target, fades=()):
    """Join any videos into one, each cut to its (start, end) seconds. Returns the length in seconds.

    Unlike join, the clips need not match: every clip is fitted into the frame of the first one,
    and a clip without sound gets silence when any other clip has sound. fades: the positions of the clips that
    crossfade (FADE seconds, picture and sound) from the clip before instead of cutting to it; a clip too short to
    lose that much is cut to.
    """
    infos = [await probe(path) for path, _, _ in parts]
    width, height = (infos[0]["width"] or 1280) // 2 * 2, (infos[0]["height"] or 720) // 2 * 2
    with_audio = any(info["audio"] for info in infos)
    args, filters, lengths = ["-loglevel", "error"], [], []
    for i, ((path, start, end), info) in enumerate(zip(parts, infos)):
        if not info["seconds"]:
            raise MediaError("{} can't be read as a video.".format(path.name))
        end = min(end or info["seconds"], info["seconds"])
        start = max(0.0, min(start or 0.0, end))
        if end - start < 1 / FPS:
            raise MediaError("A clip on the timeline is cut down to nothing.")
        lengths.append(end - start)
        args += ["-i", path]
        filters.append(
            "[{i}:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,fps={fps},"
            "scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,"
            "settb=1/{fps}[v{i}]"
            .format(i=i, s=start, e=end, fps=FPS, w=width, h=height))
        if with_audio:
            # apad: a clip whose sound is shorter than its picture is filled out with silence, or a crossfade or join
            # waiting on its sound gets none and ffmpeg stops ("received no packets")
            sound = ("[{i}:a]apad,atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS,".format(i=i, s=start, e=end)
                     if info["audio"] else "anullsrc=r=48000:cl=stereo,atrim=duration={:.3f},".format(end - start))
            filters.append(sound + "aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a{}]".format(i))
    # Clips joined one at a time onto what is joined so far: a crossfade overlaps the two, a cut puts them end to end.
    video, sound, total = "[v0]", "[a0]", lengths[0]
    for i in range(1, len(parts)):
        fade = i in fades and min(lengths[i - 1], lengths[i]) >= 2 * FADE
        if fade:
            filters.append("{}[v{}]xfade=transition=fade:duration={}:offset={:.3f}[jv{}]".format(video, i, FADE, total - FADE, i))
        else:
            # xfade takes two pictures of one time base only: a join's own is put back to the clips'
            filters.append("{}[v{}]concat=n=2:v=1:a=0,settb=1/{}[jv{}]".format(video, i, FPS, i))
        if with_audio:
            filters.append("{}[a{}]{}[ja{}]".format(sound, i, "acrossfade=d={}".format(FADE) if fade else "concat=n=2:v=0:a=1", i))
        video, sound, total = "[jv{}]".format(i), "[ja{}]".format(i), total + lengths[i] - (FADE if fade else 0)
    filters.append("{}null[v]".format(video))
    if with_audio:
        filters.append("{}anull[a]".format(sound))
    args += ["-filter_complex", ";".join(filters), "-map", "[v]"]
    if with_audio:
        args += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    args += ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", target]
    await _ffmpeg(*args)
    return total


# ---------------------------------------------------------------- measuring what was made

async def frame_rate(path):
    """The frame rate of a video's first picture stream, as ffmpeg reads it (24 when it says none)."""
    text = await _ffmpeg("-i", path, check=False)
    found = re.search(r"Stream #\S+.*Video:.*?(\d+(?:\.\d+)?) fps", text)
    return float(found.group(1)) if found else float(FPS)


async def measure(path):
    """A file's lengths as they are in it, not as they were meant to be: {"seconds" (the container's), "frames" (the
    picture's frames, counted; 0 without a picture), "video_seconds", "audio_seconds" (the sound read to its end; 0
    without sound)}. For the times of a joined or mixed file, which may differ from the sums of what went in."""
    found = await probe(path)
    out = {"seconds": round(found["seconds"], 3), "frames": 0, "video_seconds": 0.0, "audio_seconds": 0.0}
    if found["width"]:
        text = await _ffmpeg("-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-", check=False)
        frames = re.findall(r"frame=\s*(\d+)", text)
        out["frames"] = int(frames[-1]) if frames else 0
        out["video_seconds"] = round(out["frames"] / await frame_rate(path), 3)
    if found["audio"]:
        text = await _ffmpeg("-i", path, "-map", "0:a:0", "-f", "null", "-", check=False)
        times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if times:
            h, m, s = times[-1]
            out["audio_seconds"] = round(int(h) * 3600 + int(m) * 60 + float(s), 3)
    return out


CUT_SEEN = 0.3   # a scene score at least this high where a part should start is the cut, seen in the file


async def part_times(path, lengths, overlaps=()):
    """Where each part of a joined file starts and ends in it: [{"n", "start", "end", "seen"}]. lengths: each part's
    length in seconds as it went in; overlaps: {position: seconds} a part shares with the one before (a crossfade).
    Each start is looked for in the file itself, the sharpest change of picture within a quarter second of where it
    should be; "seen" is False where no cut shows there (a crossfade, or chained shots that meet on one frame), and the
    start is then the reckoned one. The last part ends where the file's picture does."""
    lengths = [float(n) for n in lengths]
    if not lengths:
        return []
    total = (await measure(path))["video_seconds"] or sum(lengths)
    scores = await changes(path)
    starts, at = [], 0.0
    for i, length in enumerate(lengths):
        at -= dict(overlaps).get(i, 0.0) if i else 0.0
        starts.append(at)
        at += length
    out = []
    for i, reckoned in enumerate(starts):
        start, seen = reckoned, i == 0
        if i and not dict(overlaps).get(i):
            near = [(score, t) for t, score in scores if abs(t - reckoned) <= 0.25]
            best = max(near, default=(0, None))
            if best[0] >= CUT_SEEN:
                start, seen = best[1], True
        out.append({"n": i + 1, "start": round(start, 3), "seen": seen})
    for here, after in zip(out, out[1:] + [None]):
        here["end"] = after["start"] if after else round(total, 3)
    return out


SILENCE_DB = -50     # quieter than this is silence
SILENCE_LONG = 1.0   # seconds of it that count as a gap worth saying


async def audio_check(path, silence_db=SILENCE_DB, silence_seconds=SILENCE_LONG):
    """What a sound (or a video's sound) measures, for a check after music or a voice is made: {"seconds",
    "loudness" (integrated, LUFS), "range" (loudness range, LU), "true_peak" (dBFS), "mean_db", "peak_db",
    "silences": [[start, end], ...] of at least `silence_seconds` below `silence_db`, "silent_share" (0 to 1),
    "clipping" (the peak at 0 dB or over), "problems": plain words}. One pass of ffmpeg."""
    found = await probe(path)
    if not found["audio"]:
        raise MediaError("{} has no sound to check.".format(Path(path).name))
    text = await _ffmpeg("-i", path, "-map", "0:a:0", "-af",
                         "silencedetect=n={}dB:d={},volumedetect,ebur128=peak=true".format(silence_db, silence_seconds),
                         "-f", "null", "-", check=False)
    number = lambda pattern: (lambda m: float(m.group(1)) if m else None)(re.search(pattern, text))
    summary = text[text.rfind("Summary:"):] if "Summary:" in text else ""
    in_summary = lambda pattern: (lambda m: float(m.group(1)) if m else None)(re.search(pattern, summary))
    seconds = (await measure(path))["audio_seconds"] or found["seconds"]
    starts = [float(s) for s in re.findall(r"silence_start: (-?[\d.]+)", text)]
    ends = [float(s) for s in re.findall(r"silence_end: ([\d.]+)", text)]
    silences = [[round(max(s, 0.0), 2), round(ends[i] if i < len(ends) else seconds, 2)] for i, s in enumerate(starts)]
    out = {"seconds": round(seconds, 2), "loudness": in_summary(r"I:\s*(-?[\d.]+) LUFS"),
           "range": in_summary(r"LRA:\s*(-?[\d.]+) LU"), "true_peak": in_summary(r"Peak:\s*(-?[\d.]+|-inf) dBFS"),
           "mean_db": number(r"mean_volume: (-?[\d.]+) dB"), "peak_db": number(r"max_volume: (-?[\d.]+) dB"),
           "silences": silences, "silent_share": round(sum(e - s for s, e in silences) / seconds, 3) if seconds else 1.0}
    out["clipping"] = out["peak_db"] is not None and out["peak_db"] >= 0
    problems = []
    if out["silent_share"] > 0.9:
        problems.append("it is silent, or nearly")
    else:
        if out["loudness"] is not None and out["loudness"] < -30:
            problems.append("it is very quiet ({:.0f} LUFS)".format(out["loudness"]))
        if out["clipping"]:
            problems.append("it reaches 0 dB and may be clipped")
        long_gaps = [g for g in silences if g[1] - g[0] >= 3 and 0.5 < g[0] and g[1] < seconds - 0.5]
        if long_gaps:
            problems.append("{} silence{} of 3 s or more inside it".format(len(long_gaps), "" if len(long_gaps) == 1 else "s"))
        if silences and silences[0][0] <= 0.05 and silences[0][1] >= 2:
            problems.append("it starts with {:.1f} s of silence".format(silences[0][1]))
    out["problems"] = problems
    return out
