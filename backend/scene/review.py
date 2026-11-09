"""Review: the agent looks at what it made and says whether it is what was asked for.

A finished picture or clip is checked by the agent's model against its prompt, the reference pictures it was made
with (a character, a place) and, for a shot that continues another, the last frame of that shot. Five checks, as a
director would make them:

    who          the right people, compared with their reference pictures
    what         the action, the place and the framing the prompt asked for
    clean        no broken hands or faces, no garbled text or watermarks, nothing cut off at the edge
    coherence    the face, the props and the light stay the same through the clip; movement is believable
    continuity   the outfit, the props and the time of day match the shot before; the cut from it is smooth

Each check is "fine", "minor" or "major"; a result passes unless one is major. A failed result comes with a fix: a
corrected prompt, and whether the retake should start on the last frame of the shot before. The verdict is kept with
the item (generations.review), shown under the step, in Shared memory, and to the agent when it plans again.

A sound the agent made (music, a voice track) has no picture: it is measured instead (review_sound), its length against
what was asked, its loudness and its silences, and kept the same way.
"""

import base64
import json
import tempfile
import time
from pathlib import Path

from . import media

CHECKS = ("who", "what", "clean", "coherence", "continuity")
LEVELS = ("fine", "minor", "major")
MAX_REFERENCES = 3      # reference pictures shown beside the result
FRAME_WIDTH = 768       # the frames of a clip the model looks at
CLIP_FRAMES = 8         # frames spread over a clip, start to end
EDGE = 0.3              # seconds kept clear of a clip's first and last frame
STRIP_WIDTH = 512       # the three neighbouring frames where the picture changes most
SHARPEST = 0.08         # a change smaller than this is ordinary movement: no strip


class ReviewError(Exception):
    pass


def _b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


async def _still(path):
    """A small JPEG of a picture, or of a video's first moments, base64."""
    return _b64(await media.poster(path))


async def result_frames(path, kind):
    """What the model looks at of a result: [(label, base64 JPEG)]. A picture is itself; a clip is CLIP_FRAMES frames
    spread from start to end, then, where the picture changes most from one frame to the next (a cut, a jump, a face
    or a hand that melts), that frame with the ones just before and after it: a fault between the spread frames would
    be missed otherwise."""
    if kind == "image":
        return [("the result", await _still(path))]
    length = (await media.probe(path))["seconds"]
    if length <= 0:
        raise ReviewError("That video can't be read.")
    edge = min(EDGE, length / 4)
    step = (length - 2 * edge) / (CLIP_FRAMES - 1)
    moments = sorted({round(edge + n * step, 2) for n in range(CLIP_FRAMES)})
    frames = []
    with tempfile.TemporaryDirectory() as folder:
        for number, moment in enumerate(moments):
            found = await media.frame_at(path, moment, Path(folder) / "f{}.jpg".format(number), FRAME_WIDTH)
            if found:
                frames.append(("the result at {:.1f} s".format(moment), _b64(found)))
        if not frames:
            raise ReviewError("No frame could be taken from that video.")
        sharpest = max(((t, s) for t, s in await media.changes(path) if 0 < t < length), key=lambda c: c[1], default=None)
        if sharpest and sharpest[1] >= SHARPEST:
            at = sharpest[0]
            for number, (moment, said) in enumerate(((at - 1 / media.FPS, "just before"), (at, "at"), (at + 1 / media.FPS, "just after"))):
                found = await media.frame_at(path, moment, Path(folder) / "s{}.jpg".format(number), STRIP_WIDTH)
                if found:
                    frames.append(("{} the sharpest change, {:.2f} s".format(said, moment), _b64(found)))
    return frames


async def last_frame(path, kind):
    """The last frame of a shot (a picture is its own), base64, for the continuity check."""
    if kind == "image":
        return await _still(path)
    with tempfile.TemporaryDirectory() as folder:
        found = await media.last_frame(path, Path(folder) / "last.jpg")
        return _b64(found) if Path(found).is_file() else None


def verdict_from(answer):
    """The model's answer as a verdict we keep: {"passed", "problem", "checks", "fix", "at"}. Unknown checks and levels
    are dropped; a result passes unless a check is major."""
    checks = []
    for check in answer.get("checks") if isinstance(answer.get("checks"), list) else []:
        if isinstance(check, dict) and check.get("check") in CHECKS and check.get("level") in LEVELS:
            checks.append({"check": check["check"], "level": check["level"], "note": " ".join(str(check.get("note") or "").split())[:240]})
    passed = not any(c["level"] == "major" for c in checks)
    fix = answer.get("fix") if isinstance(answer.get("fix"), dict) else {}
    problem = " ".join(str(answer.get("problem") or "").split())[:300]
    if not passed and not problem:
        problem = next(c["note"] for c in checks if c["level"] == "major") or "It is not what was asked for."
    return {"passed": passed, "problem": "" if passed else problem, "checks": checks, "at": time.time(),
            "fix": {} if passed else {"prompt": " ".join(str(fix.get("prompt") or "").split())[:2000],
                                      "start_from_previous": fix.get("start_from_previous") is True,
                                      "why": " ".join(str(fix.get("why") or "").split())[:240]}}


# What a reference kept for reuse must be, by the type it is kept as (memory.KEEP_AS's tags), checked with its review:
# a blurred, dark or cluttered sheet carries its flaws into every shot made from it.
SHEET = ("This picture is kept as a reference for reuse: every later shot takes {what} from it. Check it as a reference "
         "too, under \"clean\": it must be sharp and evenly lit, {how}, with no words, logos or watermarks that were not "
         "asked for. {major} is major.")
SHEET_CHECKS = {
    "character": SHEET.format(what="this character's face, body and clothes", how="on a plain, clean background, only who "
                              "it is of (several views of them are fine), with at least one view of the whole figure, head to toe",
                              major="Blur, a busy background, someone who should not be there, or no view of the whole figure"),
    "outfit": SHEET.format(what="these clothes", how="on a plain, clean background, the whole outfit in view",
                           major="Blur, a busy background, or part of the outfit cut off"),
    "prop": SHEET.format(what="this object", how="on a plain, clean background, the one object only, the whole of it in frame",
                         major="Blur, a busy background, a second object, or the object cut off"),
    "background": SHEET.format(what="this place's layout and light", how="the whole place readable from a clear viewpoint, "
                               "with no people in it unless they were asked for", major="Blur, people who were not asked for, "
                               "or a view so close the place cannot be read"),
}


def summary(verdict):
    """One line of a verdict, for Shared memory and the agent's book."""
    if not verdict:
        return ""
    if verdict.get("passed"):
        minor = [c["note"] for c in verdict.get("checks", []) if c["level"] == "minor" and c["note"]]
        return "Passed the review" + (" (minor: {})".format("; ".join(minor)[:160]) if minor else "")
    return "Failed the review: " + verdict.get("problem", "")


def load(row):
    """The verdict kept with a library item, or None."""
    try:
        found = json.loads(row.get("review") or "null")
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


async def review_item(state, user_id, item, prompt, references=(), previous=None, model=None):
    """Review one library item. item: its generations row. prompt: what it was asked to show (its own prompt when
    empty). references: [(label, path)] of the reference pictures it was made with. previous: (path, kind) of the
    shot it continues, or None. model: the one that reviews; the agent's usual one when not given. Keeps the verdict
    with the item and returns it."""
    path = state.outputs.folder(user_id) / item["filename"]
    if item["kind"] not in ("image", "video"):
        raise ReviewError("Only pictures and videos can be reviewed.")
    if not path.is_file():
        raise ReviewError("The file of {} is missing from storage.".format(item["name"]))
    try:
        made_with = json.loads(item["settings"] or "{}")
    except ValueError:
        made_with = {}
    if not prompt:
        prompt = str(made_with.get("prompt") or "")
    focus = " ".join(str(made_with.get("check") or "").split())[:400] if isinstance(made_with, dict) else ""
    if focus:   # what the plan asked to check closely in this shot, besides the usual checks
        prompt = "{}\n\nCheck closely, besides the usual checks: {}".format(prompt, focus)
    kept = (made_with.get("keep") or {}).get("tag") if isinstance(made_with, dict) and isinstance(made_with.get("keep"), dict) else None
    if kept in SHEET_CHECKS:   # a reference kept for reuse: every later shot that uses it inherits its flaws
        prompt = "{}\n\n{}".format(prompt, SHEET_CHECKS[kept])
    pictures = []
    for label, ref in list(references)[:MAX_REFERENCES]:
        if Path(ref).is_file():
            try:
                pictures.append(("reference: " + label, await _still(ref)))
            except media.MediaError:
                continue
    if previous and Path(previous[0]).is_file():
        try:
            before = await last_frame(*previous)
            if before:
                pictures.append(("the last frame of the shot before", before))
        except media.MediaError:
            pass
    try:
        pictures += await result_frames(path, item["kind"])
    except media.MediaError as error:
        raise ReviewError(str(error))
    answer = await state.agent.review([p for _, p in pictures], [label for label, _ in pictures], prompt, item["kind"], **({"model": model} if model else {}))
    verdict = verdict_from(answer)
    state.db.run("UPDATE generations SET review = ? WHERE id = ? AND user_id = ?", (json.dumps(verdict), item["id"], user_id))
    return verdict


# ---------------------------------------------------------------- sound: music and audio results

LENGTH_SLACK = 0.15   # a sound this much shorter or longer than asked (and at least 2 s off) is noted


def sound_verdict(measured, asked=None):
    """A verdict for a sound, kept as review_item keeps one: {"passed", "problem", "checks", "fix", "at", "sound"}.
    measured: what media.audio_check found (its "problems" in plain words). asked: the seconds the step asked for, or
    None. A silent sound, or one less than half as long as asked, fails; the rest of its problems are minor."""
    seconds, checks = measured.get("seconds") or 0, []
    if asked and seconds:
        off = abs(seconds - asked) > max(2.0, LENGTH_SLACK * asked)
        checks.append({"check": "length", "level": ("major" if seconds < asked / 2 else "minor") if off else "fine",
                       "note": "{:.0f} s long, {:.0f} s was asked".format(seconds, asked) if off else "{:.0f} s, as asked".format(seconds)})
    for problem in measured.get("problems") or []:
        checks.append({"check": "sound", "level": "major" if "silent" in problem else "minor", "note": problem})
    if not measured.get("problems"):
        checks.append({"check": "sound", "level": "fine", "note": "{} LUFS, no holes".format(
            "{:.0f}".format(measured["loudness"]) if isinstance(measured.get("loudness"), (int, float)) else "?")})
    passed = not any(c["level"] == "major" for c in checks)
    problem = "" if passed else "The sound is not usable: {}.".format(next(c["note"] for c in checks if c["level"] == "major"))
    return {"passed": passed, "problem": problem, "checks": checks, "fix": {}, "at": time.time(),
            "sound": {k: measured.get(k) for k in ("seconds", "loudness", "true_peak", "silent_share", "clipping")}}


async def review_sound(state, user_id, item, asked=None):
    """Check a sound the agent made (music, a voice track): its length against what was asked, its loudness and its
    silences, measured with ffmpeg (media.audio_check, the film tool's audio_check), not by a model: nothing is
    charged. Keeps the verdict with the item."""
    path = state.outputs.folder(user_id) / item["filename"]
    if item["kind"] != "audio":
        raise ReviewError("Only sounds are checked this way.")
    if not path.is_file():
        raise ReviewError("The file of {} is missing from storage.".format(item["name"]))
    try:
        verdict = sound_verdict(await media.audio_check(path), asked)
    except media.MediaError as error:
        raise ReviewError(str(error))
    state.db.run("UPDATE generations SET review = ? WHERE id = ? AND user_id = ?", (json.dumps(verdict), item["id"], user_id))
    return verdict
