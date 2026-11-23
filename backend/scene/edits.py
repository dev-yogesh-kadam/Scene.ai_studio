"""Work done on this machine, not by a provider: joining a timeline, putting a sound on a video, drawing
motion graphics, and the frame-exact work of a film made on its audio (film.py). Each is a job in the queue, filed
under an "edit/..." workflow that has no workflow file.

The request that queues one checks it and writes what is to be done into the job's settings; `run` carries it out.
"""

import time
from pathlib import Path

from . import core, credits, detect, ffjob, film, logo, media, montage, motion, reframe, runs
from .db import as_everyone, offload

TIMELINE = "edit/timeline"   # the clips of a timeline joined into one video
SOUND = "edit/sound"         # a sound put on a video
MOTION = credits.MOTION      # a motion graphic drawn by HyperFrames
ASSEMBLE = "edit/assemble"   # the finished cut: shots in order with a title card, an end card and music
# The film operations: op -> (workflow, title, the result's file type, its kind in the library)
FILM = {
    "reference": ("edit/reference", "Reference at 1500 px", ".png", "image"),
    "slice": ("edit/slice", "Audio slice", ".wav", "audio"),
    "track": ("edit/track", "Timing track", ".mp4", "video"),
    "trim": ("edit/trim", "Trim to frames", ".mp4", "video"),
    "retime": ("edit/retime", "Lips retimed to the master", ".mp4", "video"),
    "proof": ("edit/proof", "Proof sheets", ".png", "image"),
    "subtitles": ("edit/subtitles", "Subtitles burned in", ".mp4", "video"),
    "film": ("edit/film", "Film on the master audio", ".mp4", "video"),
    "speech": ("edit/speech", "Speech spans", ".json", "text"),
    "reframe": ("edit/reframe", "Cropped to a new shape", ".mp4", "video"),
    "shots": ("edit/shots", "Shots found", ".json", "text"),
    "keyframes": ("edit/keyframes", "Keyframes", ".jpg", "image"),
    "board": ("edit/board", "Board of stills", ".png", "image"),
    "beats": ("edit/beats", "Beats found", ".json", "text"),
    "beat_cut": ("edit/beat_cut", "Cut on the beats", ".mp4", "video"),
    "multicam": ("edit/multicam", "Cut between cameras", ".mp4", "video"),
    "gif": ("edit/gif", "Looping GIF", ".gif", "image"),
    "composite": ("edit/composite", "Overlay laid on", ".mp4", "video"),
    "audio_check": ("edit/audio_check", "Sound checked", ".json", "text"),
    "html": ("edit/html", "Motion page", ".mp4", "video"),           # a page written whole, drawn by HyperFrames
    "ffmpeg": ("edit/ffmpeg", "ffmpeg command", ".txt", "text"),     # a command written whole; each output files as its type
    "logo": ("edit/logo", "Logo, cut out", ".png", "image"),          # a brand's logo made ready for motion (logo.py)
}
ANY = ("video", "image", "audio", "text")   # what an ffmpeg command may take in
TITLES = {TIMELINE: "Timeline export", SOUND: "Sound on a video", MOTION: "Motion graphics", ASSEMBLE: "Final cut",
          **{workflow: title for workflow, title, _, _ in FILM.values()}}


def is_edit(workflow_id):
    return workflow_id.startswith("edit/")


async def run(job, folder, db, node_path="", tmp_dir=None):
    """Carry out one edit job. `folder` is where the user's finished work is kept.
    Returns what was made: [(file, kind in the library, context: length and frame size)], most often one file."""
    def item(item_id, kind="video"):
        """One of the user's library items and its file. It may have been deleted since the job was queued.
        kind: "video", "image", "audio", "sound" for an audio item or a video whose sound is wanted, or a tuple of kinds."""
        kinds = ("audio", "video") if kind == "sound" else kind if isinstance(kind, tuple) else (kind,)
        row = db.one("SELECT * FROM generations WHERE id = ? AND user_id = ? AND kind IN ({})".format(", ".join("?" * len(kinds))),
                     (item_id, job["user_id"], *kinds))
        if row is None or not (folder / row["filename"]).is_file():
            raise media.MediaError("{} this was to be made from is no longer in the library.".format(
                {"video": "A video", "image": "A picture", "audio": "The sound", "sound": "The sound"}.get(kind, "A file")))
        return folder / row["filename"]

    op = next((name for name, entry in FILM.items() if entry[0] == job["workflow"]), None)
    make = {TIMELINE: _timeline, SOUND: _sound, MOTION: _motion, ASSEMBLE: _assemble}.get(job["workflow"]) or (_film if op else None)
    if make is None:
        raise media.MediaError("There is no edit named '{}'.".format(job["workflow"]))
    suffix, kind = (FILM[op][2], FILM[op][3]) if op else (".mp4", "video")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "{}_{}_{}{}".format(job["workflow"].split("/", 1)[1], time.strftime("%Y%m%d_%H%M%S"), job["id"][:4], suffix)
    try:
        made = await make(dict(job["settings"], op=op) if op else job["settings"], item, target, node_path, tmp_dir)
    except BaseException:   # a failure or a cancel: leave no half-written file behind
        for path in [target, *target.parent.glob(target.stem + "_*" + suffix)]:
            path.unlink(missing_ok=True)
        raise
    files = made.pop("files", None) or [target]
    each = made.pop("each", None) or [{} for _ in files]   # what is said of each file alone (a keyframe's time)
    found = made.pop("found", None)
    kept_in = job["settings"].get("state_run") or job["settings"].get("run")   # an episode's shared state, or the tab's run
    if found and job["settings"].get("save_to") and kept_in:   # the speech spans, shots or beats, kept in the run
        await offload(runs.write_many, db, job["settings"].get("state_user") or job["user_id"], kept_in, job["settings"]["save_to"],
                        {str(n): span for n, span in found.items()}, op or "edit", replace=True)
    context = {"duration": round(made["seconds"], 1), "width": made["width"], "height": made["height"],
               **{k: v for k, v in made.items() if k not in ("seconds", "width", "height")}}
    # A file that is not of the op's kind says its own ("_kind": an ffmpeg command's audio output, a page made a GIF).
    return [(path, extra.pop("_kind", kind), dict(context, **extra)) for path, extra in zip(files, each)]


def keep_at(db, job, item_id, path, extra=None):
    """A result kept where the job was told (a keyframe for recall: /shots/3/keyframe), as {"url", "item", "made",
    ...extra}, "url" a reference to its record in the catalogue. The job's run was checked when it was queued
    (api/film.py). Returns the path written, or None when nothing could be."""
    settings = job.get("settings") or {}
    run, owner = settings.get("state_run") or settings.get("run"), settings.get("state_user") or job["user_id"]
    if not run or not item_id:
        return None
    try:
        public = core.public_ids(db, "generations", [item_id]).get(item_id, "")
        with as_everyone():
            runs.write(db, owner, run, path, {"url": "$state:/assets/{}/url".format(public), "item": item_id,
                                              "made": round(time.time()), **(extra or {})}, "studio")
    except runs.RunError:
        return None
    return path


async def _measured(target, lengths=None, overlaps=()):
    """What a joined or mixed file measures, for the times that follow it: "measured" (see media.measure) and, for a
    join, "parts" (where each part starts in the file, see media.part_times)."""
    out = {"measured": await media.measure(target)}
    if lengths:
        out["parts"] = await media.part_times(target, lengths, overlaps)
    return out


def _lengths(parts, infos):
    """Each (path, start, end) part's length as the join cuts it."""
    out = []
    for (_, start, end), info in zip(parts, infos):
        end = min(end or info["seconds"], info["seconds"])
        out.append(end - max(0.0, min(start or 0.0, end)))
    return out


async def _timeline(settings, item, target, node_path, tmp_dir):
    parts = [(await offload(item, clip["id"]), clip["start"], clip["end"]) for clip in settings["clips"]]
    seconds = await media.sequence(parts, target)
    lengths = _lengths(parts, [await media.probe(p) for p, _, _ in parts])
    return dict(await media.probe(target), seconds=seconds, **await _measured(target, lengths))


async def _assemble(settings, item, target, node_path, tmp_dir):
    """The shots in order, a title card before and an end card after, music mixed under all of it, the sound levelled
    to one loudness. A clip marked "fade" (the first of a new scene) and the cards crossfade in; the rest cut. The
    cards are drawn by HyperFrames in the shape of the shots; the files made on the way are removed."""
    spare = []

    def between(label):
        path = Path(target).with_name("{}_{}.mp4".format(Path(target).stem, label))
        spare.append(path)
        return path

    async def card(scene, label):
        path = between(label)
        await motion.render_sequence([scene], settings["look"], settings["shape"], path, node_path, tmp_dir)
        return path

    missing = []   # every clip is looked for before anything is drawn or joined: the message names all that are gone
    for n, clip in enumerate(settings["clips"]):
        try:
            await offload(item, clip["id"])
        except media.MediaError:
            missing.append(clip.get("name") or "Clip {}".format(n + 1))
    if missing:
        from .plans import cut_not_ready
        raise media.MediaError(cut_not_ready(missing))
    try:
        parts, fades = [], set()
        if settings.get("title"):
            parts.append((await card(settings["title"], "title"), 0.0, 0.0))
        for clip in settings["clips"]:
            if parts and (clip.get("fade") or len(parts) == 1 and settings.get("title")):
                fades.add(len(parts))
            parts.append((await offload(item, clip["id"]), clip["start"], clip["end"]))
        if settings.get("end"):
            fades.add(len(parts))
            parts.append((await card(settings["end"], "end"), 0.0, 0.0))
        joined = between("joined")
        seconds = await media.sequence(parts, joined, fades)
        lengths = _lengths(parts, [await media.probe(p) for p, _, _ in parts])
        overlaps = {i: media.FADE for i in fades if 0 < i < len(lengths) and min(lengths[i - 1], lengths[i]) >= 2 * media.FADE}
        if settings.get("music"):
            mixed = between("mixed")
            await media.add_sound(joined, await offload(item, settings["music"], "audio"), mixed, False)
            joined = mixed
        if (await media.probe(joined))["audio"]:
            await media.level(joined, target)
        else:
            Path(joined).replace(target)
    finally:
        for path in spare:
            path.unlink(missing_ok=True)
    return dict(await media.probe(target), seconds=seconds, **await _measured(target, lengths, overlaps))


async def _sound(settings, item, target, node_path, tmp_dir):
    seconds = await media.add_sound(await offload(item, settings["video"]), await offload(item, settings["audio"], "audio"), target, settings["replace"])
    return dict(await media.probe(target), seconds=seconds, **await _measured(target))


async def _motion(settings, item, target, node_path, tmp_dir):
    """A see-through render (the "clear" look, or "alpha" asked) is a WebM beside the target: filed as that file."""
    alpha = settings.get("alpha") is True
    if "scenes" in settings:
        made = await motion.render_sequence(settings["scenes"], settings["look"], settings["shape"], target, node_path, tmp_dir,
                                            alpha or settings.get("look") == "clear")
    else:
        source = await offload(item, settings["parent"]) if settings.get("parent") else None
        made = await motion.render(settings["template"], dict(settings["values"]), target, source, node_path, tmp_dir, alpha)
    file = made.pop("file", None)
    return dict(made, files=[file]) if file else made


async def _film(settings, item, target, node_path, tmp_dir):
    """One film operation (film.py), its settings checked when it was queued (api/film.py)."""
    op = settings["op"]
    if op == "reference":
        return await film.reference(await offload(item, settings["image"], "image"), target)
    if op == "slice":
        return await film.audio_slice(await offload(item, settings["audio"], "sound"), settings["f_in"], settings["f_out"], target,
                                      settings.get("pad") or 0)
    if op == "track":
        return await film.timing_track(settings["frames"], target)
    if op == "trim":
        return await film.trim(await offload(item, settings["video"]), settings["frames"], target, settings["stretch"], settings["size"], settings["max_pad"])
    if op == "retime":
        video = await offload(item, settings["video"])
        segments = film.segment_map(settings["lines"], settings["frames"] / media.FPS, (await media.probe(video))["seconds"])
        return dict(await film.retime(video, segments, settings["frames"], target, settings["size"]), segments=segments)
    if op == "proof":
        sheets = await film.proof_sheets(await offload(item, settings["video"]), settings["marks"], target)
        found = await media.probe(sheets[0])
        return {"seconds": 0, "width": found["width"], "height": found["height"], "files": sheets}
    if op == "subtitles":
        video, style = await offload(item, settings["video"]), settings.get("style")
        lines = settings["lines"]
        if settings.get("words_from"):   # a transcription that has its words' times: for karaoke
            lines = film.words_for(lines, (await offload(item, settings["words_from"], "text")).read_text(encoding="utf-8"))
        chars = film.ROW_CHARS
        if style:
            style = film.subtitle_style(style)
            chars = film.row_chars(style, (await media.probe(video))["width"])
        cues = film.subtitle_cues(lines, settings["narrator"], chars)
        made = await film.burn_subtitles(video, cues, target, style)
        return dict(made, cue_list=[list(c[:3]) for c in cues])
    if op == "film":
        clips = [await offload(item, i) for i in settings["clips"]]
        made = await film.join_on_master(clips, await offload(item, settings["audio"], "sound"), target)
        at, parts = 0, []   # the pictures are copied as they are: each part starts where the frames before it end
        for n, clip in enumerate(clips, start=1):
            frames = await film.frames_of(clip)
            parts.append({"n": n, "start": round(at / media.FPS, 3), "end": round((at + frames) / media.FPS, 3), "frames": frames})
            at += frames
        return dict(made, measured=await media.measure(target), parts=parts)
    if op == "speech":
        source = await offload(item, settings["audio"], "sound")
        if settings.get("lines"):
            found = await film.speech_spans(source, settings["lines"])
        else:
            found = {"runs": await film.speech_runs(source, settings["windows"])}
        film.write_json(found, target)
        return {"seconds": 0, "width": 0, "height": 0, "spans": len(found) if settings.get("lines") else None,
                "found": found if settings.get("save_to") else None}
    if op == "reframe":
        return await reframe.crop(await offload(item, settings["video"]), settings["shape"], target, settings["x"], settings["y"])
    if op == "html":
        return await _html(settings, item, target, node_path, tmp_dir)
    if op == "ffmpeg":
        return await _ffmpeg(settings, item, target, tmp_dir)
    if op == "logo":
        made = await logo.prepare(await offload(item, settings["logo"], (settings["kind"],)), settings["kind"], target, node_path, tmp_dir)
        files = made.pop("files")
        each = [{"_kind": "image"}] + ([{"_kind": "text", "_name": "Logo, SVG cleaned"}] if len(files) > 1 else [])
        return dict(made, seconds=0, files=files, each=each)
    more = {"shots": _shots, "keyframes": _keyframes, "board": _board, "beats": _beats, "beat_cut": _beat_cut,
            "multicam": _multicam, "gif": _gif, "composite": _composite, "audio_check": _audio_check}.get(op)
    if more:
        return await more(settings, item, target)
    raise media.MediaError("There is no film operation named '{}'.".format(op))


# ---------------------------------------------------------------- finding and cutting without a model (detect.py, montage.py)

def _sized_list(values, most=200):
    """A list kept short enough for the tool's answer; the whole is in the result's file."""
    return values[:most] + (["… {} more in the file".format(len(values) - most)] if len(values) > most else [])


async def _shots(settings, item, target):
    found = await detect.shots(await offload(item, settings["video"]), settings["threshold"], settings["min_shot"])
    film.write_json(found, target)
    spans = {str(s["n"]): {"start": s["start"], "end": s["end"]} for s in found["shots"]}
    return {"seconds": 0, "width": 0, "height": 0, "length": found["seconds"], "count": len(found["shots"]),
            "cuts": _sized_list(found["cuts"]), "found": spans if settings.get("save_to") else None}


async def _keyframes(settings, item, target):
    video = await offload(item, settings["video"])
    width, height, length, fps = await montage._picture(video)
    marks = montage.keyframe_times(length, fps, settings["from"], settings.get("to"), settings.get("count"), settings.get("every"),
                                   settings.get("times"), settings.get("shots"), settings["pick"])
    captions = settings.get("labels") or []
    if settings.get("save_to") and not captions:   # one kept for recall is captioned with its shot and time
        captions = ["{}{:.1f} s".format("Shot {} · ".format(extra["shot"]) if extra.get("shot") is not None else "", at)
                    for at, extra in marks]
    made = await montage.keyframes(video, marks, target, captions=captions)
    files, each = [], []
    for k, (path, facts, captioned) in enumerate(made, start=1):
        number = facts.get("shot", k)
        slot = "{}/{}/{}".format(settings["save_to"], number, settings["key"]) if settings.get("save_to") else None
        files.append(path)
        each.append({"at": facts["at"], **({"shot": facts["shot"]} if "shot" in facts else {}), "_name": "Keyframe {:.2f} s".format(facts["at"]),
                     **({"_keep_at": slot, "_keep": {"time": facts["at"], "shot": number, "source": settings["video"]}} if slot else {})})
        if captioned:
            files.append(captioned)
            each.append({"at": facts["at"], "captioned": True, "_name": "Keyframe {:.2f} s, captioned".format(facts["at"]),
                         **({"_keep_at": slot + "_captioned", "_keep": {"time": facts["at"], "shot": number}} if slot else {})})
    first = await media.probe(files[0])
    return {"seconds": 0, "width": first["width"], "height": first["height"], "keyframes": len(made), "files": files, "each": each}


async def _board(settings, item, target):
    stills = []
    for still in settings["stills"]:
        if "video" in still:
            stills.append((await offload(item, still["video"]), still["at"]))
        else:
            stills.append((await offload(item, still["image"], "image"), None))
    made = await montage.board(stills, target, settings["panels"], settings["numbered"])
    boards = made.pop("boards")
    each = [{"stills": b["stills"], "grid": "{}x{}".format(b["across"], b["down"]), "_name": "Board {}–{}".format(*b["stills"]),
             **({"_keep_at": settings["save_to"] if k == 0 else "{}_{}".format(settings["save_to"], k + 1)} if settings.get("save_to") else {})}
            for k, b in enumerate(boards)]
    labels = settings.get("labels") or []
    return dict(made, files=[b["file"] for b in boards], each=each, boards=len(boards),
                **({"labels": {str(i + 1): l for i, l in enumerate(labels) if l}} if labels else {}))


async def _beats(settings, item, target):
    found = await detect.beats(await offload(item, settings["audio"], "sound"), settings["from"], settings.get("to"))
    film.write_json(found, target)
    return {"seconds": 0, "width": 0, "height": 0, "tempo": found["tempo"], "confidence": found["confidence"],
            "beats": _sized_list(found["beats"], 300), "bars": _sized_list(found["bars"], 100), "onsets": len(found["onsets"]),
            "found": found if settings.get("save_to") else None}


async def _beat_cut(settings, item, target):
    music = await offload(item, settings["audio"], "sound")
    beats = settings.get("beats")
    if not beats:
        beats = (await detect.beats(music))["beats"]
    points = detect.cut_points(sorted(beats), len(settings["clips"]), settings["every"], settings["first"])
    made = await montage.beat_cut([await offload(item, i) for i in settings["clips"]], points, music, target, settings.get("size"))
    return dict(made, measured=await media.measure(target))


async def _multicam(settings, item, target):
    return await montage.multicam(await offload(item, settings["video"]), settings["cuts"], target, settings.get("cameras"))


async def _gif(settings, item, target):
    return await montage.gif(await offload(item, settings["video"]), target, settings["fps"], settings["width"], settings["loop"],
                             settings["from"], settings.get("to"))


async def _composite(settings, item, target):
    overlay = await offload(item, settings["overlay"], settings["overlay_kind"])
    made = await montage.composite(await offload(item, settings["video"]), overlay, target, settings["at"], settings["x"], settings["y"], settings["scale"])
    return dict(made, measured=await media.measure(target))


async def _html(settings, item, target, node_path, tmp_dir):
    """A page the agent wrote whole, drawn by HyperFrames (motion.render_page): a video, a see-through WebM, a GIF or a
    still of its last moment, filed as its type."""
    files = {m["name"]: await offload(item, m["item"], ANY) for m in settings.get("media") or []}
    if settings.get("project_dir"):   # a project written file by file (pages.py): a video and its review sheets, or stills
        return await motion.render_project(settings["project_dir"], target, settings["fps"], settings["format"], files,
                                           settings.get("frames"), settings.get("review", True), node_path, tmp_dir)
    made = await motion.render_page(settings["html"], settings["width"], settings["height"], settings["duration"], target,
                                    settings["fps"], settings["format"], files, node_path, tmp_dir)
    file = made.pop("file", None) or target
    return dict(made, files=[file], each=[{"_kind": "image" if settings["format"] in ("gif", "png") else "video"}])


async def _ffmpeg(settings, item, target, tmp_dir):
    """An ffmpeg command written whole (ffjob.py), checked when it was queued and again here. Each output is filed as
    its type, under its own name when there are several; a command with none (a measurement) files what ffmpeg said."""
    argv, sidecars, timeout = ffjob.check(settings["argv"], settings["inputs"], settings.get("sidecars") or [],
                                          settings["outputs"], settings.get("timeout"))
    names = [o["name"] for o in settings["outputs"]]
    made = await ffjob.run(argv, {i["name"]: await offload(item, i["item"], ANY) for i in settings["inputs"]}, sidecars, names, target, timeout, tmp_dir)
    each = []
    for path, name in zip(made["files"], names or ["log.txt"]):
        kind = ffjob.kind_of(name)
        found = await media.probe(path) if kind != "text" else {"seconds": 0.0, "width": 0, "height": 0}
        each.append({"_kind": kind, "output": name, "duration": round(found["seconds"], 1), "width": found["width"],
                     "height": found["height"], **({"_name": "{} · {}".format(settings["workflow_title"], name)} if len(names) > 1 else {})})
    each[0]["log"] = made["log"]   # once: what ffmpeg said (a measurement is read from it)
    return {"seconds": each[0]["duration"], "width": each[0]["width"], "height": each[0]["height"], "files": made["files"], "each": each}


async def _audio_check(settings, item, target):
    found = await media.audio_check(await offload(item, settings["audio"], "sound"))
    film.write_json(found, target)
    return {"seconds": 0, "width": 0, "height": 0, "length": found["seconds"],
            **{k: v for k, v in found.items() if k != "seconds"}}
