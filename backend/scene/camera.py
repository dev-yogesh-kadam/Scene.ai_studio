"""Camera language as fields: a shot has a size, an angle and a move, and they are turned into prompt words here.

The video models read a camera from words in the prompt, not from settings, so the agent decides the fields and this
table says them the way the models understand. A shot with no camera fields (the model left them empty) is untouched.
"""

import re

SIZES = {
    "ECU": ("extreme close-up", r"extreme close[- ]?up"),
    "CU": ("close-up shot", r"close[- ]?up"),
    "MCU": ("medium close-up", r"medium close[- ]?up"),
    "MS": ("medium shot", r"medium shot|mid[- ]?shot"),
    "WS": ("wide shot", r"wide shot|wide angle|establishing"),
    "EWS": ("extreme wide shot", r"extreme wide|aerial|drone"),
}
ANGLES = {
    "eye": ("eye-level angle", r"eye[- ]level"),
    "low": ("low angle looking up", r"low[- ]angle|from below"),
    "high": ("high angle looking down", r"high[- ]angle|from above"),
    "top": ("top-down view from directly above", r"top[- ]down|overhead|bird'?s[- ]eye"),
    "OTS": ("over-the-shoulder shot", r"over[- ]the[- ]shoulder"),
}
MOVES = {
    "static": ("static camera, locked off", r"static|locked[- ]off|still camera"),
    "push in": ("slow push in", r"push(es|ing)? in|dolly in|zoom(s|ing)? in"),
    "pull back": ("slow pull back", r"pull(s|ing)? back|dolly out|zoom(s|ing)? out"),
    "pan": ("smooth pan", r"\bpan(s|ning)?\b"),
    "track": ("tracking shot following the subject", r"track(s|ing)?\b|follow(s|ing)?"),
    "crane": ("crane move rising", r"crane|jib"),
    "handheld": ("handheld camera", r"handheld|hand[- ]held"),
    "orbit": ("camera orbits around the subject", r"orbit"),
}
FIELDS = {"shot_size": SIZES, "angle": ANGLES, "move": MOVES}
# A frame that is the same for a whole picture has no move.
STILL_FIELDS = ("shot_size", "angle")


def choices(field):
    """The values the model may give a field, with "" for 'not decided'."""
    return ["", *FIELDS[field]]


def clean(step):
    """The camera fields of a step as kept: each is a known value or ""; end_state is a short phrase."""
    out = {}
    for field, table in FIELDS.items():
        value = step.get(field) if isinstance(step, dict) else ""
        out[field] = value if value in table else ""
    end = " ".join(str(step.get("end_state") or "").split())[:160] if isinstance(step, dict) else ""
    out["end_state"] = end
    return out


def words(camera, kind="video"):
    """The prompt words for the camera fields, as a list of phrases (empty when none is set)."""
    return [FIELDS[f][camera[f]][0] for f in (FIELDS if kind == "video" else STILL_FIELDS) if camera.get(f)]


# A prompt laid out in labelled parts (the studio's structure, or a model's guide, prompters/) says the camera and the
# end in its own parts: the words go there, or nowhere when its timed beats already carry the camera.
CAMERA_LINE = re.compile(r"(?im)^(CAMERA:[^\n]*)$")
BEATS = re.compile(r"(?m)^SHOTS\s*$")
END_PART = re.compile(r"(?m)^END STATE:?\s*$")


def apply(prompt, camera, kind="video"):
    """The prompt with the camera said in it. A phrase the prompt already has (in any of its spellings) is not added again.
    In a prompt with a CAMERA: line the missing words go on that line; one with timed SHOTS beats (H3's guide) says its
    camera beat by beat and gets none. The end state is added as the last sentence unless the prompt already has it or
    an END STATE part."""
    prompt = (prompt or "").strip()
    if not prompt:
        return prompt
    missing = []
    for field in FIELDS if kind == "video" else STILL_FIELDS:
        value = camera.get(field)
        if value and not re.search(FIELDS[field][value][1], prompt, re.IGNORECASE):
            missing.append(FIELDS[field][value][0])
    out = prompt
    line = CAMERA_LINE.search(out)
    if missing and line:
        out = out[:line.end()].rstrip(" .") + "; " + ", ".join(missing) + "." + out[line.end():]
    elif missing and not BEATS.search(out):
        out = out.rstrip(" .") + ". Camera: " + ", ".join(missing) + "."
    end = camera.get("end_state")
    if end and kind == "video" and end.lower().rstrip(". ") not in prompt.lower() and not END_PART.search(prompt):
        out += "\nAt the end: " + end.rstrip(". ") + "." if "\n" in out else " At the end: " + end.rstrip(". ") + "."
    return out
