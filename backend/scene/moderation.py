"""What is made in the studio, looked at by its moderators.

A list of words the studio does not want in prompts (setting `moderation_words`) and what is done about them (setting
`moderation_mode`): "off"; "flag", which marks an item made from such a prompt for review; or "refuse", which also
refuses the job before it is made (jobs.JobManager.add), gives its credits back, and writes the refusal down. The
console's Moderation section shows what was made lately, flagged first, and each item gets a verdict: fine, or
removed from its owner's library. Verdicts and refusals are kept in the `moderation` table.
"""

import json
import re
import time

MODES = ("off", "flag", "refuse")


def settings(db):
    try:
        words = json.loads(db.setting("moderation_words", "") or "[]")
    except ValueError:
        words = []
    mode = db.setting("moderation_mode", "off")
    return {"words": [str(w) for w in words if str(w).strip()], "mode": mode if mode in MODES else "off"}


def save(db, words, mode):
    clean = sorted({" ".join(str(w).lower().split())[:60] for w in words if str(w).strip()})[:500]
    db.set_setting("moderation_words", json.dumps(clean))
    db.set_setting("moderation_mode", mode if mode in MODES else "off")
    return settings(db)


def matches(text, words):
    """The listed words (or phrases) in `text`, as whole words, any case."""
    low = str(text or "").lower()
    return [w for w in words if re.search(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", low)]


def prompt_of(settings_json):
    """The words a job or an item was made from: its prompt and the text values typed into it, then the words it
    draws on its result (drawn_words): the same list is looked for in all of them, from the studio, the agent's tools
    and the phone."""
    try:
        found = json.loads(settings_json) if isinstance(settings_json, str) else (settings_json or {})
    except ValueError:
        return ""
    if not isinstance(found, dict):
        return ""
    values = found.get("values") if isinstance(found.get("values"), dict) else {}
    parts = [found.get("prompt")] + [v for v in values.values() if isinstance(v, str)] + drawn_words(found)
    return " · ".join(dict.fromkeys(" ".join(str(p).split()) for p in parts if p and str(p).strip()))


DRAWN_MOST = 20_000   # characters of drawn words looked at, of one job


def drawn_words(settings):
    """The words a job puts on its result besides its prompt: the scenes and cards of motion graphics and the final cut,
    the lines of subtitles, the text of a page drawn by HyperFrames (its tags taken out), and an ffmpeg command's words
    and text files (drawtext, subtitles). Without these, words the studio refuses in a prompt could be drawn on a video
    by the agent's film tools."""
    found = []

    def text(value):
        if isinstance(value, str) and value.strip():
            found.append(value)

    for scene in settings.get("scenes") if isinstance(settings.get("scenes"), list) else []:
        if isinstance(scene, dict):
            text(scene.get("heading"))
            text(scene.get("text"))
    for card in (settings.get("title"), settings.get("end")):
        if isinstance(card, dict):
            text(card.get("heading"))
            text(card.get("text"))
    for line in settings.get("lines") if isinstance(settings.get("lines"), list) else []:
        if isinstance(line, dict):
            text(line.get("text"))
    if isinstance(settings.get("html"), str):
        text(re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|<[^>]+>", " ", settings["html"], flags=re.IGNORECASE | re.DOTALL))
    if isinstance(settings.get("argv"), list):
        text(" ".join(str(word) for word in settings["argv"] if isinstance(word, (str, int, float))))
    for sidecar in settings.get("sidecars") if isinstance(settings.get("sidecars"), list) else []:
        if isinstance(sidecar, dict):
            text(sidecar.get("content"))
    joined, total = [], 0
    for part in found:
        if total >= DRAWN_MOST:
            break
        joined.append(part[:DRAWN_MOST - total])
        total += len(joined[-1])
    return joined


def step_settings(step):
    """The settings of one step of an agent's plan as the job it queues will have them (plans.PlanRunner._queue)."""
    if not isinstance(step, dict):
        return {}
    for kind in ("motion", "sound", "edit", "assemble"):
        if isinstance(step.get(kind), dict):
            return step[kind]
    return step.get("settings") if isinstance(step.get("settings"), dict) else {}


def plan_refusal(db, steps):
    """[(step name, words)] of a plan's steps the studio would refuse (moderation_mode "refuse"), found before the plan
    is priced and approved, so the user is told at once instead of the plan failing at that step. Nothing is written:
    the refusal is written down when a job is refused (refusal)."""
    found = settings(db)
    if found["mode"] != "refuse" or not found["words"]:
        return []
    hits = []
    for i, step in enumerate(steps if isinstance(steps, list) else []):
        hit = matches(prompt_of(step_settings(step)), found["words"])
        if hit:
            hits.append((str(step.get("name") or "Step {}".format(i + 1))[:80], hit))
    return hits


def plan_problem(db, steps):
    """plan_refusal in words for the user, or None."""
    hits = plan_refusal(db, steps)
    if not hits:
        return None
    return "This plan can't be made here: {}. Change those words and try again.".format(
        "; ".join("“{}” ({})".format(name, ", ".join(words)) for name, words in hits[:5]))


def refusal(db, user_id, job_settings):
    """The words that refuse this job, when the studio refuses such prompts; written down. None when it may run."""
    found = settings(db)
    if found["mode"] != "refuse" or not found["words"]:
        return None
    prompt = prompt_of(job_settings)
    hit = matches(prompt, found["words"])
    if not hit:
        return None
    db.run("INSERT INTO moderation (kind, generation_id, user_id, verdict, words, prompt, by_name, created) "
           "VALUES ('refused', NULL, ?, 'refused', ?, ?, '', ?)", (user_id, ", ".join(hit), prompt[:1000], time.time()))
    return hit
