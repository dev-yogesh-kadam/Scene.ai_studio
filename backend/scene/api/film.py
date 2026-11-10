"""The frame-exact work of a film made on its audio, queued as edits: free, made on this machine (see film.py).

POST /api/edit/film takes {"op", "name"?, "project_id"?, "run"?, ...the op's own fields}; every item it names must be
one of the user's library items of the right kind, and every number is checked here, before anything is queued.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import core, detect, edits, ffjob, film, montage, motion, pages, reframe, runs, sharing, storage
from ..media import FPS, MediaError
from .deps import costly, current_user
from .workspace import _project_id
from ..db import offload

router = APIRouter(prefix="/api", tags=["film"])

RUN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")   # the run a working file belongs to
MAX_FRAMES = FPS * 3 * 3600                       # three hours: the longest master a slice or a trim may reach
MAX_CLIP_FRAMES = FPS * 60                        # one trimmed clip or one timing track: a minute at most
SIZES = range(64, 2161)
MAX_PAD_SECONDS = 30                              # a slice padded with silence to this at most
MONTAGE_OPS = ("shots", "keyframes", "board", "beats", "beat_cut", "multicam", "gif", "composite", "audio_check")
KEPT_OPS = ("shots", "keyframes", "board", "beats")   # the ones whose findings or files can be kept in a run (save_to)
PICKS = ("first", "middle", "last")
MAX_STILLS = 64                                   # the stills one board op lays out (on as many boards as they need)


def _number(value, low, high, what, whole=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (whole and value != int(value)) or not low <= value <= high:
        raise HTTPException(400, "{} must be a {} from {} to {}.".format(what, "whole number" if whole else "number", low, high))
    return int(value) if whole else float(value)


def _list(value, most, what):
    if not isinstance(value, list) or not 1 <= len(value) <= most:
        raise HTTPException(400, "Give {} as a list of 1 to {}.".format(what, most))
    return value


def _span(value, what):
    if not isinstance(value, list) or len(value) != 2:
        raise HTTPException(400, "{} must be [start, end] in seconds.".format(what))
    s, e = (_number(v, 0, MAX_FRAMES / FPS, what) for v in value)
    if e < s:
        raise HTTPException(400, "{} ends before it starts.".format(what))
    return [s, e]


def _text(value, most):
    return " ".join(str(value or "").split())[:most]


@router.post("/edit/film", dependencies=[costly("render")])
async def film_edit(body: dict, request: Request, user: dict = Depends(current_user)):
    """Queue one film operation. Costs no credits: it needs no GPU. Returns {"job", "name"}."""
    return await offload(queue, request, user, body)


def queue(request, user, body):
    """Check one film operation and queue it (the endpoint above, and the agent's "film" tool). Raises HTTPException
    with the reason when anything in it is wrong; nothing is queued then."""
    state = request.app.state
    op = body.get("op")
    if op not in edits.FILM:
        raise HTTPException(400, "The operation must be one of: {}.".format(", ".join(edits.FILM)))
    workflow, title, _, _ = edits.FILM[op]
    folder = state.outputs.folder(user["id"])

    def own(item_id, kinds, what):
        """The id of one of the user's items of one of these kinds, whose file is there."""
        if isinstance(item_id, bool) or not isinstance(item_id, int):
            raise HTTPException(400, "Name {} by its library id.".format(what))
        row = state.db.one("SELECT * FROM generations WHERE id = ? AND user_id = ? AND kind IN ({})".format(", ".join("?" * len(kinds))),
                           (item_id, user["id"], *kinds))
        if row is None or not storage.here(folder / row["filename"]).is_file():
            raise HTTPException(404, "{} is not in your library.".format(what[0].upper() + what[1:]))
        return row["id"]

    def kind_of(item_id):
        """The library kind of one of the user's items, already checked by own()."""
        return state.db.one("SELECT kind FROM generations WHERE id = ? AND user_id = ?", (item_id, user["id"]))["kind"]

    def size():
        given = body.get("size", list(film.SQUARE))
        if not isinstance(given, list) or len(given) != 2:
            raise HTTPException(400, "size must be [width, height].")
        w, h = (_number(v, SIZES.start, SIZES.stop - 1, "The frame size", whole=True) for v in given)
        return [w // 2 * 2, h // 2 * 2]

    settings, facts = {"workflow_title": title}, ""
    if op == "reference":
        settings["image"] = own(body.get("image"), ("image",), "the picture")
        facts = "longer side {} px".format(film.REF_SIDE)
    elif op == "slice":
        f_in = _number(body.get("f_in"), 0, MAX_FRAMES - 1, "f_in", whole=True)
        f_out = _number(body.get("f_out"), f_in + 1, MAX_FRAMES, "f_out", whole=True)
        settings.update(audio=own(body.get("audio"), ("audio", "video"), "the master audio"), f_in=f_in, f_out=f_out,
                        pad=_number(body.get("pad", 0), 0, MAX_PAD_SECONDS, "pad"))
        facts = "frames {}–{} · {:.2f} s".format(f_in, f_out, (f_out - f_in) / FPS) + (
            " · padded to {:g} s".format(settings["pad"]) if settings["pad"] > (f_out - f_in) / FPS else "")
    elif op == "track":
        frames = [_number(n, 1, MAX_CLIP_FRAMES, "Each block's frames", whole=True) for n in _list(body.get("frames"), 60, "the blocks' frames")]
        if sum(frames) > MAX_CLIP_FRAMES:
            raise HTTPException(400, "A timing track lasts a minute at most.")
        settings["frames"] = frames
        facts = "{} blocks · {} frames".format(len(frames), max(sum(frames), film.MIN_FRAMES))
    elif op in ("trim", "retime"):
        settings.update(video=own(body.get("video"), ("video",), "the clip"),
                        frames=_number(body.get("frames"), 1, MAX_CLIP_FRAMES, "frames", whole=True), size=size())
        if op == "trim":
            settings.update(stretch=_number(body.get("stretch", 1), 0.5, 2.0, "stretch"),
                            max_pad=_number(body.get("max_pad", film.MAX_PAD), 0, FPS, "max_pad", whole=True))
        else:
            settings["lines"] = [{"master": _span(l.get("master"), "A line's master span"), "clip": _span(l.get("clip"), "A line's clip span")}
                                 for l in _list(body.get("lines"), 40, "the lines spoken on screen") if isinstance(l, dict)]
        facts = "{} frames".format(settings["frames"])
    elif op == "proof":
        marks = [{"at": _number(m.get("at"), 0, MAX_FRAMES / FPS, "A mark's time"), "label": _text(m.get("label"), 40)}
                 for m in _list(body.get("marks"), 1200, "the frames to show") if isinstance(m, dict)]
        settings.update(video=own(body.get("video"), ("video",), "the film"), marks=marks)
        facts = "{} frames · {} sheet{}".format(len(marks), -(-len(marks) // film.SHEET_MAX), "" if len(marks) <= film.SHEET_MAX else "s")
    if op == "subtitles":
        lines = []
        for l in _list(body.get("lines"), 5000, "the transcript's lines"):
            if isinstance(l, dict):
                start, end = _span([l.get("start"), l.get("end")], "A line's start and end")
                lines.append({"start": start, "end": end, "text": _text(l.get("text"), 500), "speaker": _text(l.get("speaker"), 60),
                              "lead": l.get("lead") is True})
        settings.update(video=own(body.get("video"), ("video",), "the film"), lines=lines,
                        narrator=_text(body.get("narrator"), 60) or "narrator")
        if body.get("style") is not None:
            if not isinstance(body["style"], dict):
                raise HTTPException(400, "style is the subtitles' look: {\"font\", \"size\", \"colour\", ...}.")
            try:
                film.subtitle_style(body["style"])
            except MediaError as error:
                raise HTTPException(400, str(error))
            settings["style"] = body["style"]
        if body.get("words_from") is not None:   # a transcription with its words' times, for karaoke
            settings["words_from"] = own(body.get("words_from"), ("text",), "the transcription with the words' times")
        facts = "{} lines".format(len(lines)) + (" · styled" if settings.get("style") else "")
    elif op == "film":
        clips = [own(c, ("video",), "a trimmed clip") for c in _list(body.get("clips"), 1000, "the trimmed clips")]
        settings.update(clips=clips, audio=own(body.get("audio"), ("audio", "video"), "the master audio"))
        facts = "{} clips on the master".format(len(clips))
    elif op == "speech":
        settings["audio"] = own(body.get("audio"), ("audio", "video"), "the sound")
        if body.get("lines") is not None:
            settings["lines"] = []
            narrator = _text(body.get("narrator"), 60)   # the transcript's label for the narrator, when it is not "narrator"
            for l in _list(body.get("lines"), 10000, "the transcript's lines"):
                if isinstance(l, dict):
                    start, end = _span([l.get("start"), l.get("end")], "A line's start and end")
                    speaker = _text(l.get("speaker"), 60) or "narrator"
                    settings["lines"].append({"n": _number(l.get("n"), 0, 10 ** 6, "A line's number", whole=True), "start": start,
                                              "end": end, "speaker": "narrator" if narrator and speaker == narrator else speaker})
            facts = "{} lines".format(len(settings["lines"]))
            if body.get("save_to"):
                if not body.get("run") and not body.get("state_run"):
                    raise HTTPException(400, "save_to keeps the spans in a run: name the run.")
                try:
                    settings["save_to"] = runs.clean_path(body["save_to"])
                except runs.RunError as error:
                    raise HTTPException(400, str(error))
                if body.get("state_run"):   # an episode's shared state (core.py): only for someone who may write there
                    settings["state_user"], settings["state_run"] = _episode(request, user, body["state_run"])
        else:
            settings["windows"] = [_span(w, "A window") for w in _list(body.get("windows"), 400, "the windows to scan")]
            facts = "{} windows".format(len(settings["windows"]))
    elif op in ("reframe", "outpaint_prep", "outpaint_join"):
        shape = body.get("shape")
        if shape not in reframe.SHAPES:
            raise HTTPException(400, "shape must be one of: {}.".format(", ".join(reframe.SHAPES)))
        settings.update(video=own(body.get("video"), ("video",), "the video"), shape=shape)
        if op == "reframe":
            settings.update(x=_number(body.get("x", 0.5), 0, 1, "x"), y=_number(body.get("y", 0.5), 0, 1, "y"))
            facts = "cropped to {}".format(shape)
        elif op == "outpaint_join":
            settings["parts"] = [own(p, ("video",), "a filled-in part") for p in _list(body.get("parts"), 400, "the filled-in parts")]
            facts = "{} parts · {}".format(len(settings["parts"]), shape)
        else:
            facts = "{} · parts of {} frames at {} fps".format(shape, reframe.PART_FRAMES, reframe.GEN_FPS)
    elif op == "logo":
        settings["logo"] = own(body.get("logo"), ("image", "text"), "the logo")
        settings["kind"] = kind_of(settings["logo"])
        facts = "cut out, its colours read"
    elif op in ("html", "ffmpeg"):
        facts = _project(request, user, body, settings, own) if op == "html" and body.get("project") else _written(op, body, settings, own)
    elif op in MONTAGE_OPS:
        facts = _montage(op, body, settings, own, size, kind_of)
        if body.get("save_to"):
            if op not in KEPT_OPS:
                raise HTTPException(400, "save_to keeps what {} finds or makes in the run; it is for {} only.".format(op, ", ".join(KEPT_OPS)))
            if not body.get("run"):
                raise HTTPException(400, "save_to keeps the result in a run: name the run.")
            try:
                settings["save_to"] = runs.clean_path(body["save_to"])
            except runs.RunError as error:
                raise HTTPException(400, str(error))
    run = str(body.get("run") or "")
    if run and not RUN.match(run):
        raise HTTPException(400, "A run is named with lower-case letters, digits and dashes.")
    settings["run"] = run
    project_id = _project_id(request, user, body.get("project_id")) or None
    name = _text(body.get("name"), 80) or title
    job_id = state.jobs.add(user["id"], name, workflow, settings, facts, None, 0, project_id)
    return {"job": job_id, "name": name}


def _media(body, own):
    """The library items a page or a project plays, by the names it gives them: [{"name", "item"}]."""
    given = body.get("media") or []
    if not isinstance(given, list) or len(given) > motion.MEDIA_MOST * 3:
        raise HTTPException(400, "media is a list of at most {} {{\"name\", \"item\"}}.".format(motion.MEDIA_MOST * 3))
    out = []
    for entry in given:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not motion.MEDIA_NAME.match(name):
            raise HTTPException(400, "Each media file needs a bare name like bg.mp4 (letters, digits, - and _, then its type).")
        out.append({"name": name, "item": own(entry.get("item"), edits.ANY, "the media file {}".format(name))})
    return out


def _project(request, user, body, settings, own):
    """Check a motion project the agent wrote file by file (pages.py) into `settings`: that it is there with its
    index.html, how it is to be made (fps, format, stills at "frames", review sheets) and the media it plays. What its
    files may reach is checked when it is staged for the render. Returns the facts shown with the job."""
    try:
        name, inner = pages.split(body.get("project"))
    except pages.PageError as error:
        raise HTTPException(400, str(error))
    module = _project_id(request, user, body.get("project_id")) or 0
    folder = pages.root(request.app.state.assets_dir.parent, user["id"], module) / name
    if inner or not (folder / "index.html").is_file():
        raise HTTPException(400, "There is no motion project \"{}\" with an index.html in this module: write it with page_build first.".format(name))
    fps = _number(body.get("fps", 30), min(motion.PAGE_FPS), max(motion.PAGE_FPS), "fps", whole=True)
    fmt = body.get("format", "mp4")
    if fps not in motion.PAGE_FPS or fmt not in ("mp4", "webm", "gif"):
        raise HTTPException(400, "fps is one of {} and format one of mp4, webm, gif (stills: \"frames\").".format(", ".join(map(str, motion.PAGE_FPS))))
    frames = body.get("frames") or []
    if not isinstance(frames, list) or len(frames) > motion.STILLS_MOST:
        raise HTTPException(400, "frames is a list of at most {} times in seconds.".format(motion.STILLS_MOST))
    frames = [_number(t, 0, 180, "a frame's time") for t in frames]
    settings.update(project_dir=str(folder), project=name, fps=fps, format=fmt, frames=frames, review=body.get("review", True) is not False,
                    media=_media(body, own))
    return "{} · {}".format(name, "stills at {}".format(", ".join("{:g} s".format(t) for t in frames)) if frames else "{} fps {}".format(fps, fmt))


def _written(op, body, settings, own):
    """Check a page (html) or an ffmpeg command (ffmpeg) written whole into `settings`, as far as it can be before it
    runs: everything the page or the command names, and what it may reach. Returns the facts shown with the job."""
    named = lambda entry, what: own(entry.get("item") if isinstance(entry, dict) else None, edits.ANY, what)
    if op == "html":
        width = _number(body.get("width", 1080), *motion.PAGE_SIDE, "width", whole=True)
        height = _number(body.get("height", 1920), *motion.PAGE_SIDE, "height", whole=True)
        seconds = _number(body.get("duration"), *motion.PAGE_SECONDS, "duration")
        fps = _number(body.get("fps", 30), min(motion.PAGE_FPS), max(motion.PAGE_FPS), "fps", whole=True)
        fmt = body.get("format", "mp4")
        if fps not in motion.PAGE_FPS or fmt not in motion.PAGE_FORMATS:
            raise HTTPException(400, "fps is one of {} and format one of {}.".format(", ".join(map(str, motion.PAGE_FPS)), ", ".join(motion.PAGE_FORMATS)))
        if fmt in ("mp4", "webm") and (width % 2 or height % 2):
            raise HTTPException(400, "A video's width and height are even numbers.")
        given = body.get("media") or []
        if not isinstance(given, list) or len(given) > motion.MEDIA_MOST:
            raise HTTPException(400, "media is a list of at most {} {{\"name\", \"item\"}}.".format(motion.MEDIA_MOST))
        media_list = []
        for entry in given:
            name = entry.get("name") if isinstance(entry, dict) else None
            if not isinstance(name, str) or not motion.MEDIA_NAME.match(name):
                raise HTTPException(400, "Each media file needs a bare name like bg.mp4 (letters, digits, - and _, then its type).")
            media_list.append({"name": name, "item": named(entry, "the media file {}".format(name))})
        page = body.get("html")
        try:
            motion.check_page(page, width, height, seconds, {m["name"] for m in media_list})
            if fmt != "png":
                motion.page_budget(page, width, height, seconds, fps)
        except motion.MotionError as error:
            raise HTTPException(400, str(error))
        settings.update(html=page, width=width, height=height, duration=seconds, fps=fps, format=fmt, media=media_list)
        return "{}x{} · {:g} s · {}".format(width, height, seconds, fmt)
    try:
        ffjob.check(body.get("argv"), body.get("inputs") or [], body.get("sidecars") or [], body.get("outputs") or [], body.get("timeout"))
    except ffjob.JobError as error:
        raise HTTPException(400, str(error))
    settings.update(argv=[str(a) for a in body["argv"]], sidecars=body.get("sidecars") or [], outputs=body.get("outputs") or [],
                    inputs=[{"name": i["name"], "item": named(i, "the input {}".format(i["name"]))} for i in body.get("inputs") or []],
                    timeout=body.get("timeout") or 300, reason=_text(body.get("reason"), 200))
    outputs = [o["name"] for o in settings["outputs"]]
    return "{} → {}".format(", ".join(i["name"] for i in settings["inputs"]) or "nothing", ", ".join(outputs) or "a measurement")


def _stretch(body, settings):
    """The stretch of a clip or song worked on: "from" (default its start) and "to" (default its end)."""
    settings["from"] = _number(body.get("from", 0), 0, MAX_FRAMES / FPS, "from")
    if body.get("to") is not None:
        settings["to"] = _number(body.get("to"), settings["from"], MAX_FRAMES / FPS, "to")
        if settings["to"] <= settings["from"]:
            raise HTTPException(400, "to must come after from.")


def _montage(op, body, settings, own, size, kind_of):
    """Check the fields of a finding or cutting op done without a model (detect.py, montage.py) into `settings`.
    Returns the facts shown with the job."""
    if op == "shots":
        settings.update(video=own(body.get("video"), ("video",), "the clip"),
                        threshold=_number(body.get("threshold", detect.CUT), 0.05, 0.95, "threshold"),
                        min_shot=_number(body.get("min_shot", detect.MIN_SHOT), 0.05, 10, "min_shot"))
        return "cuts over {:g}".format(settings["threshold"])
    if op == "keyframes":
        settings["video"] = own(body.get("video"), ("video",), "the clip")
        _stretch(body, settings)
        ways = [w for w in ("count", "every", "times", "shots") if body.get(w) is not None]
        if len(ways) != 1:
            raise HTTPException(400, "Ask for keyframes one way: \"count\", \"every\", \"times\" or \"shots\".")
        way = ways[0]
        if way == "count":
            settings["count"] = _number(body["count"], 1, montage.KEYFRAMES_MOST, "count", whole=True)
        elif way == "every":
            settings["every"] = _number(body["every"], 0.1, 600, "every")
        elif way == "times":
            settings["times"] = [_number(t, 0, MAX_FRAMES / FPS, "A keyframe's time") for t in _list(body["times"], montage.KEYFRAMES_MOST, "the times")]
        else:
            shots = []
            for n, shot in enumerate(_list(body["shots"], montage.KEYFRAMES_MOST, "the shots"), start=1):
                if isinstance(shot, dict):
                    start, end = _span([shot.get("start"), shot.get("end")], "A shot's start and end")
                    shots.append({"n": _number(shot.get("n", n), 0, 10 ** 6, "A shot's number", whole=True), "start": start, "end": end})
                else:
                    start, end = _span(shot, "A shot")
                    shots.append({"n": n, "start": start, "end": end})
            settings["shots"] = shots
        settings["pick"] = body.get("pick", "middle")
        if settings["pick"] not in PICKS:
            raise HTTPException(400, "pick is first, middle or last: which frame of each shot.")
        if body.get("labels") is not None:
            settings["labels"] = [_text(l, 80) for l in _list(body["labels"], montage.KEYFRAMES_MOST, "the labels")]
        key = str(body.get("key") or "keyframe")
        if not re.fullmatch(r"[a-z0-9_]{1,32}", key):
            raise HTTPException(400, "key is a short lower-case name, the last part of each keyframe's path.")
        settings["key"] = key
        return "{} {}".format(way, len(settings[way]) if isinstance(settings[way], list) else "{:g}".format(settings[way]))
    if op == "board":
        stills = []
        for still in _list(body.get("stills"), MAX_STILLS, "the stills"):
            if not isinstance(still, dict):
                raise HTTPException(400, "Each still is {\"video\", \"at\"} or {\"image\"}.")
            if still.get("video") is not None:
                stills.append({"video": own(still["video"], ("video",), "a still's clip"),
                               "at": _number(still.get("at"), 0, MAX_FRAMES / FPS, "A still's time")})
            else:
                stills.append({"image": own(still.get("image"), ("image",), "a still's picture")})
        panels = body.get("panels", 6)
        if panels not in montage.BOARD_PANELS:
            raise HTTPException(400, "panels is one of {}.".format(", ".join(str(n) for n in montage.BOARD_PANELS)))
        settings.update(stills=stills, panels=panels, numbered=body.get("numbered", True) is not False)
        if body.get("labels") is not None:
            settings["labels"] = [_text(l, 80) for l in _list(body["labels"], MAX_STILLS, "the labels")]
        return "{} stills · up to {} a board".format(len(stills), panels)
    if op == "beats":
        settings["audio"] = own(body.get("audio"), ("audio", "video"), "the music")
        _stretch(body, settings)
        return "tempo and beats"
    if op == "beat_cut":
        clips = [own(c, ("video",), "a clip") for c in _list(body.get("clips"), 200, "the clips")]
        settings.update(clips=clips, audio=own(body.get("audio"), ("audio", "video"), "the music"),
                        every=_number(body.get("every", 1), 1, 32, "every", whole=True),
                        first=_number(body.get("first", 0), 0, 10000, "first", whole=True))
        if body.get("beats") is not None:
            settings["beats"] = sorted(_number(b, 0, MAX_FRAMES / FPS, "A beat's time") for b in _list(body["beats"], 20000, "the beats"))
        if body.get("size") is not None:
            settings["size"] = size()
        return "{} clips, a cut every {} beat{}".format(len(clips), settings["every"], "" if settings["every"] == 1 else "s")
    if op == "multicam":
        settings["video"] = own(body.get("video"), ("video",), "the clip")
        cameras = {}
        for name, camera in (body.get("cameras") or {}).items() if isinstance(body.get("cameras"), dict) else []:
            if not re.fullmatch(r"[a-z0-9_-]{1,24}", str(name)) or not isinstance(camera, dict):
                raise HTTPException(400, "Each camera is a short name with {\"zoom\", \"x\", \"y\"}.")
            cameras[name] = {"zoom": _number(camera.get("zoom", 1), 1, montage.MAX_ZOOM, "A camera's zoom"),
                             "x": _number(camera.get("x", 0.5), 0, 1, "A camera's x"), "y": _number(camera.get("y", 0.5), 0, 1, "A camera's y")}
        known = set(montage.CAMERAS) | set(cameras)
        cuts = []
        for cut in _list(body.get("cuts"), 400, "the cuts"):
            if not isinstance(cut, dict) or cut.get("camera") not in known:
                raise HTTPException(400, "Each cut is {\"at\", \"camera\"} with a camera of: " + ", ".join(sorted(known)) + ".")
            cuts.append({"at": _number(cut.get("at"), 0, MAX_FRAMES / FPS, "A cut's time"), "camera": cut["camera"],
                         **({"push": _number(cut["push"], 0, montage.MAX_PUSH, "push")} if cut.get("push") is not None else {})})
        settings["cuts"] = cuts
        if cameras:
            settings["cameras"] = cameras
        return "{} cuts".format(len(cuts))
    if op == "gif":
        settings.update(video=own(body.get("video"), ("video",), "the clip"),
                        fps=_number(body.get("fps", 12), 1, 30, "fps", whole=True),
                        width=_number(body.get("width", 480), 64, 1080, "width", whole=True),
                        loop=_number(body.get("loop", 0), 0, 100, "loop", whole=True))
        _stretch(body, settings)
        return "{} px at {} fps".format(settings["width"], settings["fps"])
    if op == "composite":
        overlay = own(body.get("overlay"), ("video", "image"), "the overlay")
        settings.update(video=own(body.get("video"), ("video",), "the video"), overlay=overlay, overlay_kind=kind_of(overlay),
                        at=_number(body.get("at", 0), 0, MAX_FRAMES / FPS, "at"),
                        x=_number(body.get("x", 0.5), 0, 1, "x"), y=_number(body.get("y", 0.5), 0, 1, "y"),
                        scale=_number(body.get("scale", 1), 0.05, 1, "scale"))
        return "from {:g} s".format(settings["at"])
    settings["audio"] = own(body.get("audio"), ("audio", "video"), "the sound")   # audio_check
    return "length, loudness and silences"


def _episode(request, user, state_run):
    """(whose rows, the run) of an episode's state the speech spans go to, when this user may write there."""
    found = re.fullmatch(r"ep-(\d{1,12})", str(state_run or ""))
    role, _, top = sharing.role_in(request.app.state.db, user["id"], int(found.group(1))) if found else (None, None, None)
    if role not in core.WRITE_ROLES:
        raise HTTPException(403, "The spans can't be kept in that episode's state.")
    return top["user_id"], found.group(0)
