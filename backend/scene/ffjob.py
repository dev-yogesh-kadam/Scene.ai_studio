"""ffmpeg commands written whole by the agent (or by anyone with the film tool), run on this machine in a folder of their
own: the inputs the job names copied in under those names, its small text files (subtitles, a concat list, a long
filter graph, a colour LUT) written beside them, and the outputs it names taken out when ffmpeg is done. Nothing else is
in that folder but the studio's fonts.

The command is checked before it runs so that it reads and writes nothing outside that folder and reaches no other
machine: no path that leaves the folder, no URL or protocol, no capture device, no screen grab, no shell. ffmpeg is also
told to open only files (-protocol_whitelist file), so a protocol that slipped past the check would not open anyway.
"""

import asyncio
import os
import re
import shutil
import signal
import sys
import tempfile
from pathlib import Path

from .media import MediaError, ffmpeg_path

INPUTS_MOST, SIDECARS_MOST, OUTPUTS_MOST = 10, 5, 4
SIDECAR_CHARS = 200_000
ARGS_MOST, ARG_CHARS = 500, 20_000
TIMEOUT = (30, 600)          # seconds a job may be given; 300 when it says none
LOG_CHARS = 4000             # of what ffmpeg said, kept with the result (a measurement is read from it)
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.[A-Za-z0-9]{1,8}$")
FONTS = Path(__file__).parent / "fonts"   # every .ttf here is in the job's folder too, for drawtext fontfile= and ass fontsdir=.

SIDECAR_TYPES = {".txt", ".ffconcat", ".ass", ".ssa", ".srt", ".vtt", ".cube", ".3dl", ".csv"}
SUBTITLE_TYPES = {".ass", ".ssa", ".srt", ".vtt"}   # read only as subtitles: their words are not checked as paths
# What each output becomes in the library, by its type.
OUTPUT_KINDS = {".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video",
                ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
                ".wav": "audio", ".mp3": "audio", ".m4a": "audio", ".aac": "audio", ".flac": "audio", ".ogg": "audio", ".opus": "audio",
                ".srt": "text", ".ass": "text", ".vtt": "text", ".txt": "text", ".json": "text", ".csv": "text"}
MEDIA_TYPES = set(OUTPUT_KINDS) | SIDECAR_TYPES | {".ttf", ".otf", ".m4v", ".avi", ".ts", ".mxf", ".aif", ".aiff", ".bmp", ".tif", ".tiff"}

# The protocols ffmpeg can open (ffmpeg -protocols), all of which reach past the folder or another machine: file: too,
# so that a path can't hide behind it.
PROTOCOLS = ("async bluray cache concat concatf crypto data dtls fd ffrtmpcrypt ffrtmphttp file ftp gopher gophers hls "
             "http httpproxy https icecast ipfs ipns librist libsrt md5 mmsh mmst pipe prompeg rist rtmp rtmpe rtmps rtmpt "
             "rtmpte rtmpts rtp sctp sftp smb srt srtp subfile tcp tee tls udp udplite unix zmq android_content").split()
PROTOCOL = re.compile(r"(?<![\w.-])(?:{})(?:,[^:\s]*)?:|\b[a-z][a-z0-9+.-]{{1,20}}://".format("|".join(PROTOCOLS)))
DEVICES = {"dshow", "gdigrab", "openal", "vfwcap", "sdl", "sdl2", "tee"}   # -f values: a camera, the screen, a window...
# Filters that grab the screen, listen on the network, or open files by name themselves (give those with -i).
FILTERS = re.compile(r"(?<![\w-])(ddagrab|gfxcapture|zmq|azmq|movie|amovie)(?=\s*(?:=|,|;|\[|'|$))")
SHELL = {"|", "||", "&&", "&", ">", ">>", "<", ";", "2>&1", "1>&2"}
FILE_OPTIONS = {"-filter_script", "-filter_complex_script"}   # options whose value is a file of filter text

# A path that leaves the folder: rooted, on a drive, on another machine, or up out of it.
ROOTED = re.compile(r"(?:^|[\s='\"\[,;:|(])[\\/](?![\\/:,;'\"\[\]=\s)]|$)")
DRIVE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|(?<![\w-])[A-Za-z]:(?![\\/])[\w-]+\.[A-Za-z0-9]{2,5}(?!\w)")
SHARE = re.compile(r"\\\\[A-Za-z0-9.?]")
UP = re.compile(r"(?:^|[\\/=:'\"\s,;|\[])\.\.(?:[\\/]|$)")
# A path relative to another drive's own folder (E:SceneBackups/x is E:\SceneBackups\x when the job's folder is on
# C:): a word that starts with one, or in a filter's text one with its colon escaped (E\:x) or in quotes ('E:x'). A
# filter's own w:h is neither, and words such as "Plan B\: go" keep a space after the colon.
DRIVE_WORD = re.compile(r"^[A-Za-z]:")
DRIVE_IN_TEXT = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]\\+:(?=[\w.~%$-])|['\"][A-Za-z]:(?=[\w.~%$-])")


class JobError(MediaError):
    pass


NO_WINDOW = 0x08000000   # CREATE_NO_WINDOW: no console window on Windows


def own_group():
    """What a program started here takes so that stop() can end it with everything it starts: no console window on
    Windows; elsewhere, a process group of its own (os.killpg ends that group, never the studio's)."""
    return {"creationflags": NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}


async def stop(process, wait=15):
    """End a program and every program it started, and wait for it (at most `wait` seconds). HyperFrames starts Chrome
    and ffmpeg, which Windows' kill of HyperFrames alone would leave running, holding the job's folder. Safe to call on
    a program that has already ended."""
    if process.returncode is None:
        if sys.platform == "win32":   # /T: the whole tree, found by its parent's id, so before the parent is gone
            try:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/T", "/PID", str(process.pid), stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, creationflags=NO_WINDOW)
                await asyncio.wait_for(killer.wait(), wait)
            except (OSError, asyncio.TimeoutError):
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)   # its own group (own_group), so only it and what it started
            except (OSError, AttributeError):
                pass
        try:
            process.kill()
        except (ProcessLookupError, OSError):
            pass
    try:
        await asyncio.wait_for(process.wait(), wait)
    except asyncio.TimeoutError:
        pass


def _unescaped(text):
    """ffmpeg's own escapes taken off (C\\:/ is C:/ to a filter), as a filter reads the text."""
    return re.sub(r"\\(.)", r"\1", text)


def _paths_in(text, subtitles=False):
    """What in a piece of a command (or a text file of the job) names something outside the folder: [problem].
    subtitles: the text of a subtitle file, whose words may say anything ("data: 42", "the movie, then") but which is
    still checked for paths, after its own marks ({\\an8}, \\N) are taken out."""
    if subtitles:
        if re.match(r"\s*(#EXTM3U|ffconcat)", text, re.IGNORECASE):
            return ["a playlist or a list of files"]
        text = re.sub(r"\{[^}\n]*\}|\\[Nnh]", " ", text)
    found = []
    for form in dict.fromkeys((text, _unescaped(text))):
        if UP.search(form):
            found.append("a path up out of the folder (..)")
        if DRIVE.search(form) or ROOTED.search(form) or SHARE.search(text) or (not subtitles and DRIVE_IN_TEXT.search(form)):
            found.append("a path outside the folder")
        if not subtitles and PROTOCOL.search(form):
            found.append("a URL or protocol ({})".format(PROTOCOL.search(form).group(0)))
        if not subtitles and FILTERS.search(form):
            found.append("the {} filter".format(FILTERS.search(form).group(1)))
    return list(dict.fromkeys(found))


def _names(entries, what, most):
    """The bare file names of a list of {"name": ...}, checked: [name]."""
    if not isinstance(entries, list) or len(entries) > most:
        raise JobError("{} must be a list of at most {}.".format(what, most))
    names = []
    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not NAME.match(name):
            raise JobError("{} names a file \"{}\": use a bare file name like clip.mp4, with no folder.".format(what, str(name)[:80]))
        names.append(name)
    return names


def check(argv, inputs, sidecars, outputs, timeout=None):
    """A job, checked before it runs: (argv without a leading "ffmpeg", {sidecar name: text}, timeout). inputs:
    [{"name", "item"}] (the items are checked by whoever queues the job), sidecars: [{"name", "content"}], outputs:
    [{"name"}]. Raises JobError with everything wrong at once."""
    in_names = _names(inputs, "inputs", INPUTS_MOST)
    side_names = _names(sidecars or [], "sidecars", SIDECARS_MOST)
    out_names = _names(outputs, "outputs", OUTPUTS_MOST)
    every = in_names + side_names + out_names
    if len(set(n.lower() for n in every)) != len(every):
        raise JobError("Every input, sidecar and output needs a name of its own.")
    for name in out_names:
        if Path(name).suffix.lower() not in OUTPUT_KINDS:
            raise JobError("{} can't be an output: make one of {}.".format(name, ", ".join(sorted(OUTPUT_KINDS))))
    texts = {}
    for entry, name in zip(sidecars or [], side_names):
        content = entry.get("content")
        if Path(name).suffix.lower() not in SIDECAR_TYPES:
            raise JobError("{} can't be a sidecar: a sidecar is a text file, one of {}.".format(name, ", ".join(sorted(SIDECAR_TYPES))))
        if not isinstance(content, str) or len(content) > SIDECAR_CHARS:
            raise JobError("{}'s content must be text of at most {:,} characters.".format(name, SIDECAR_CHARS))
        texts[name] = content
    if not isinstance(argv, list) or not argv or not all(isinstance(a, (str, int, float)) and not isinstance(a, bool) for a in argv):
        raise JobError("argv must be a list of the command's words, one string each.")
    argv = [str(a) for a in argv]
    if Path(argv[0]).stem.lower() == "ffmpeg":
        argv = argv[1:]
    if not argv or len(argv) > ARGS_MOST or any(len(a) > ARG_CHARS for a in argv):
        raise JobError("argv must have 1 to {} words of at most {:,} characters (put a long filter graph in a sidecar).".format(ARGS_MOST, ARG_CHARS))
    if timeout is None:
        timeout = 300
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not TIMEOUT[0] <= timeout <= TIMEOUT[1]:
        raise JobError("timeout must be {} to {} seconds.".format(*TIMEOUT))

    problems, fonts = [], {p.name for p in FONTS.glob("*.ttf")}
    known = set(every) | fonts
    for i, word in enumerate(argv):
        before = argv[i - 1] if i else ""
        if word in SHELL:
            problems.append("\"{}\" (argv is run as it is, with no shell)".format(word))
        problems += ["{} in \"{}\"".format(p, word[:80]) for p in _paths_in(word)]
        if DRIVE_WORD.match(word) and not _paths_in(word):
            problems.append("a path outside the folder in \"{}\" (a drive's own folder)".format(word[:80]))
        if before == "-f" and word.lower() in DEVICES:
            problems.append("-f {} (no devices, screens or tee outputs)".format(word))
        if word in ("-protocol_whitelist", "-protocol_blacklist"):
            problems.append("{} (the job sets it)".format(word))
        if before == "-safe" and word.strip() == "0":
            problems.append("-safe 0 (leave -safe out: a concat list names the clips by their bare names)")
        if (before in FILE_OPTIONS or before.startswith("-/")) and Path(word).suffix.lower() != ".txt":
            problems.append("{} {} (a file of filter text is a .txt sidecar)".format(before, word))
        if re.fullmatch(r"[\w-]+\.[A-Za-z0-9]{1,8}", word) and Path(word).suffix.lower() in MEDIA_TYPES and word not in known:
            problems.append("{} is not one of the job's inputs, sidecars or outputs".format(word))
    for name in out_names:
        if name not in argv:
            problems.append("the output {} is not written by argv (name it as its own word)".format(name))
    for name, text in texts.items():
        subtitles = Path(name).suffix.lower() in SUBTITLE_TYPES
        problems += ["{} in the sidecar {}".format(p, name) for p in _paths_in(text, subtitles)]
        if subtitles:   # read only as subtitles: never as a list of files or a filter graph
            for i, word in enumerate(argv):
                given = [argv[k + 1] for k in range(max(0, i - 4), i - 1) if argv[k] == "-f"] if word == name and argv[i - 1:i] == ["-i"] else []
                if (given and given[-1] not in ("srt", "ass", "webvtt")) or (name in word and "sendcmd" in word):
                    problems.append("{} is read as subtitles only".format(name))
    if problems:
        raise JobError("The command can't run: {}.".format("; ".join(dict.fromkeys(problems))))
    return argv, texts, int(timeout)


def kind_of(name):
    """What an output becomes in the library: video, image, audio or text."""
    return OUTPUT_KINDS[Path(name).suffix.lower()]


def _whitelisted(argv):
    """argv with every input told to open files only."""
    out = []
    for i, word in enumerate(argv):
        if word == "-i" and argv[i - 1:i] != ["-protocol_whitelist"]:
            out += ["-protocol_whitelist", "file"]
        out.append(word)
    return out


def _env(folder):
    """The few variables ffmpeg needs on this machine, and none of the studio's own (its keys and settings)."""
    keep = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH", "FONTCONFIG_FILE", "FONTCONFIG_PATH", "LANG", "LC_ALL")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update(TEMP=str(folder), TMP=str(folder), TMPDIR=str(folder), HOME=str(folder))
    return env


def _log(text):
    """What ffmpeg said, without its progress lines."""
    lines = [line for line in text.splitlines() if line.strip() and not re.match(r"\s*(frame|size)=\s*\S", line)]
    return "\n".join(lines)


async def run(argv, inputs, sidecars, outputs, target, timeout=300, work_dir=None):
    """Run a checked job (see check). inputs: {name: path of the file}, sidecars: {name: text}, outputs: [name].
    The outputs are kept next to `target` as <target's stem>_<name>; with none, what ffmpeg said is kept in `target`
    (a measurement: loudness, cuts, black frames). All or nothing: a failure keeps no file.

    Returns {"files": [path], "names": [output name], "log": what ffmpeg said, its end}."""
    target = Path(target)
    if work_dir:
        Path(work_dir).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work_dir, ignore_cleanup_errors=True) as tmp:   # a cleanup error never hides the job's own
        box = Path(tmp) / "job"
        box.mkdir()
        for font in FONTS.glob("*.ttf"):
            shutil.copy(font, box / font.name)
        for name, path in inputs.items():
            shutil.copy(path, box / name)   # a copy: a command that writes over an input changes only the copy
        for name, text in sidecars.items():
            (box / name).write_text(text, encoding="utf-8")
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path(), "-hide_banner", "-nostdin", "-nostats", "-y", *_whitelisted(argv), cwd=str(box), env=_env(box),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, **own_group())
        try:
            _, said = await asyncio.wait_for(process.communicate(), timeout)
        except asyncio.CancelledError:   # the job was cancelled: ffmpeg ended before its folder is taken away
            await stop(process)
            raise
        except asyncio.TimeoutError:
            await stop(process)
            raise JobError("ffmpeg took longer than {} s and was stopped: give the job a longer timeout, or split it.".format(timeout))
        log = _log(said.decode("utf-8", "replace"))
        if process.returncode:
            raise JobError("ffmpeg stopped with an error: {}".format(log[-800:] or "it said nothing"))
        missing = [n for n in outputs if not (box / n).is_file() or not (box / n).stat().st_size]
        if missing:
            raise JobError("ffmpeg finished without writing {}. What it said: {}".format(", ".join(missing), log[-500:] or "nothing"))
        target.parent.mkdir(parents=True, exist_ok=True)
        files = []
        if not outputs:
            target.write_text(log or "(ffmpeg said nothing)", encoding="utf-8")
            files.append(target)
        for name in outputs:
            path = target.with_name("{}_{}".format(target.stem, name))
            shutil.move(str(box / name), str(path))
            files.append(path)
    return {"files": files, "names": list(outputs), "log": log[-LOG_CHARS:]}
