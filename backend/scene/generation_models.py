"""The generation server's models: Seedance, Kling, Wan, MiniMax, Gemini Omni, Grok, Happy Horse (video) and Nano
Banana, GPT Image, Seedream, Grok (pictures).

ComfyUI's are workflows; the generation server's are models, and the studio keeps the two apart wherever it offers
them. Inside, every model of a kind runs through one workflow, `video/generation_video` or `image/generation_image`
(workflows.describe gives them "source": "generation"), whose Model setting (the option `model`) is the model. Its
Resolution, Shape and Sound options come once per group of models that share a list ("when": {"model": [...]}), so a
setting is found by its label and the model chosen (`option_for`), never by its id alone.

What each model takes comes from two places:
- the workflow's presets file, always there: each model's name and hint, the resolutions, shapes and sound shown for
  it, the frames it takes (refs_when);
- the generation server's list (GET <server>/generation/models), read from the server whose Workflows claim the
  workflow (balancer.py), kept FRESH seconds and the last good answer after that: each model's lengths, reference
  counts, frames, sound and prices. It is a help: when it can't be read, the presets file alone still works and the
  generation server refuses, saying why, what a model can't take.
"""

import asyncio
import json
import re
import time

import httpx

from .comfy import workflows

MODEL = "model"        # the option that picks the model
FRESH = 600            # seconds the server's list is used before it is read again
RETRY = 60             # seconds before asking again a server whose list could not be read
KINDS = ("video", "image")


def is_generation(schema):
    return (schema or {}).get("source") == "generation"


def model_option(schema):
    """The Model option of a generation workflow, or None."""
    if not is_generation(schema):
        return None
    return next((o for o in schema.get("options") or [] if o["id"] == MODEL), None)


def has_models(schema):
    """Whether a generation workflow offers models (video, pictures). One without a Model setting (a voiceover, music,
    a sound effect, lip sync, upscale) is one model on its own: offered and run like a workflow, from the same server."""
    return model_option(schema) is not None


def only_models(schema, models):
    """The schema with its Model setting kept to these models (a chat pinned to them), in the workflow's order; the
    first of them its default when the workflow's own is not among them. Unchanged when none of them is one of its
    models. A copy: the catalog's schema is left as it is."""
    option = model_option(schema)
    if option is None:
        return schema
    kept = [c for c in option["choices"] if c["id"] in set(models)]
    if not kept:
        return schema
    ids = [c["id"] for c in kept]
    narrowed = dict(option, choices=kept, default=option["default"] if option["default"] in ids else ids[0])
    schema = dict(schema, options=[narrowed if o is option else o for o in schema["options"]])
    if isinstance(schema.get("models"), list):
        schema["models"] = [m for m in schema["models"] if m.get("model") in ids]
    return schema


def model_of(schema, options):
    """The model chosen in these options (a job's settings["options"]), or the workflow's default; None for a
    workflow without one."""
    option = model_option(schema)
    if option is None:
        return None
    chosen = (options or {}).get(MODEL)
    return chosen if chosen in {c["id"] for c in option["choices"]} else option.get("default")


def _models_of(option):
    """The models an option is shown for (its "when" on the model), or None when it is shown for every model."""
    when = option.get("when")
    for one in (when if isinstance(when, list) else [when] if when else []):
        if isinstance(one, dict) and MODEL in one:
            value = one[MODEL]
            return set(value if isinstance(value, list) else [value])
    return None


def option_for(schema, label, model):
    """The option of this label ("resolution", "Shape") or id shown for this model, or None."""
    wanted = str(label or "").strip().lower()
    if wanted == MODEL:
        return model_option(schema)
    for option in schema.get("options") or []:
        if option["id"] == MODEL or wanted not in (option["id"].lower(), option["label"].strip().lower()):
            continue
        models = _models_of(option)
        if models is None or model in models:
            return option
    return None


def settings_of(schema, model):
    """{label lower case: option} of the settings shown for one model, Model left out."""
    found = {}
    for option in schema.get("options") or []:
        if option["id"] == MODEL:
            continue
        models = _models_of(option)
        if models is None or model in models:
            found.setdefault(option["label"].strip().lower(), option)
    return found


def _frames(schema, model):
    """The frames (first, last) a model takes, from the slots its presets file shows for it."""
    found = []
    for name, slot in (("first", (schema.get("slots") or {}).get("first_frame")), ("last", (schema.get("slots") or {}).get("last_frame"))):
        ref = next((r for r in schema["refs"] if r["id"] == slot), None) if slot else None
        if ref is None:
            continue
        models = _models_of({"when": ref.get("when")}) if ref.get("when") else None
        if models is None or model in models:
            found.append(name)
    return found


def catalog(schema, live=None):
    """Every model of a generation workflow, in its order: [{"model" (the Model choice), "name", "about", "resolutions",
    "shapes", "sound", "frames", and from the server's list when there is one: "seconds" {"min", "max"},
    "references" (most reference or source pictures), "best_for", "prices" {resolution: credits a second or a
    picture}}]. [] for any other workflow."""
    option = model_option(schema)
    if option is None:
        return []
    live = live or {}
    found = []
    for choice in option["choices"]:
        model = choice["id"]
        shown = settings_of(schema, model)
        entry = {"model": model, "name": choice.get("label") or model, "about": str(choice.get("hint") or ""),
                 "resolutions": [c["id"] for c in (shown.get("resolution") or {}).get("choices", [])],
                 "shapes": [c.get("label") or c["id"] for c in (shown.get("shape") or {}).get("choices", [])],
                 "sound": "choice" if "sound" in shown else "fixed",
                 "frames": _frames(schema, model)}
        known = live.get(model)
        if known:
            if isinstance(known.get("seconds"), dict):
                entry["seconds"] = {k: known["seconds"][k] for k in ("min", "max") if isinstance(known["seconds"].get(k), (int, float))}
            references = known.get("max_reference_images", known.get("max_source_images"))
            if isinstance(references, int):
                entry["references"] = references
            if isinstance(known.get("frames"), list):
                entry["frames"] = [f for f in known["frames"] if f in ("first", "last")]
            if known.get("sound") in ("always", "never", "choice"):
                entry["sound"] = known["sound"]
            if known.get("best_for"):
                entry["best_for"] = str(known["best_for"])
            prices = {}
            for res in known.get("resolutions") or []:
                if not isinstance(res, dict) or not res.get("id"):
                    continue
                per = res.get("credits_per_second") if isinstance(res.get("credits_per_second"), dict) else None
                price = res.get("credits_per_image") if per is None else (per.get("with_sound") or per.get("silent"))
                if isinstance(price, (int, float)):
                    prices[str(res["id"])] = price
            if prices:
                entry["prices"] = prices
        found.append(entry)
    return found


def find(schema, live, model):
    return next((m for m in catalog(schema, live) if m["model"] == model), None)


def _reference_count(schema, settings):
    """The reference (or source) pictures a job gives: its filled slots of the list of references."""
    listed = {r["id"] for r in schema["refs"] if r.get("order")}
    return len([slot for slot, given in (settings.get("refs") or {}).items() if slot in listed and given])


# Only these models take a first or last frame together with reference pictures, sound or a clip; every other one
# takes one or the other (the generation server's own check, server/src/core/models.ts, which the list does not say).
FRAMES_WITH_REFERENCES = ("seedance",)


def frame_slots(schema):
    """The first and last frame slots of a generation workflow."""
    return {s for s in ((schema.get("slots") or {}).get("first_frame"), (schema.get("slots") or {}).get("last_frame")) if s}


def clashes(schema, options, used):
    """Whether a job of this model fills a frame slot and a reference slot together (`used`: the slots it fills),
    which only Seedance takes."""
    model = model_of(schema, options)
    if model is None or str(model).startswith(FRAMES_WITH_REFERENCES):
        return False
    used = set(used or ())
    return bool(used & frame_slots(schema)) and bool(used & reference_slots(schema))


def clash_note(schema, options):
    """What is said when a shot of such a model drops the frame it would start on and keeps its references."""
    return ("{} can't start on a frame and take reference pictures together (only Seedance can): this shot starts "
            "fresh from its references, not on the frame before.").format(label_of(schema, options) or "This model")


def problem(schema, settings, live):
    """Why the chosen model can't take this job, in words, or "". A first or last frame with references is refused
    for every model but Seedance; the rest is only what the server's list says: with no list nothing more is refused
    here (the generation server refuses it, saying why)."""
    model = model_of(schema, settings.get("options"))
    if clashes(schema, settings.get("options"), (settings.get("refs") or {}).keys()):
        return ("{} can't combine a first or last frame with reference images or audio (only Seedance can): "
                "leave out the frame or the references.").format(label_of(schema, settings.get("options")) or model)
    if model is None or not live or model not in live:
        return ""
    entry = find(schema, live, model)
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    seconds = entry.get("seconds") or {}
    if "duration" in roles and seconds:
        asked = workflows.context(schema, settings).get("duration")
        low, high = seconds.get("min"), seconds.get("max")
        if asked is not None and ((low is not None and asked < low) or (high is not None and asked > high)):
            return "{} makes clips of {:g} to {:g} seconds; this one asks for {:g}.".format(entry["name"], low or 0, high or 0, asked)
    if "references" in entry:
        given = _reference_count(schema, settings)
        if given > entry["references"]:
            return ("{} takes no reference pictures; this job gives {}.".format(entry["name"], given) if not entry["references"] else
                    "{} takes at most {} reference pictures; this job gives {}.".format(entry["name"], entry["references"], given))
    slots = schema.get("slots") or {}
    for name, slot in (("first", slots.get("first_frame")), ("last", slots.get("last_frame"))):
        if slot and (settings.get("refs") or {}).get(slot) and name not in entry["frames"]:
            return "{} can't take a {} frame.".format(entry["name"], name)
    return ""


def bound_seconds(schema, live, model, seconds):
    """`seconds` kept within the model's lengths, when the server's list says them."""
    entry = find(schema, live, model) if live else None
    span = (entry or {}).get("seconds") or {}
    if span.get("min") is not None:
        seconds = max(span["min"], seconds)
    if span.get("max") is not None:
        seconds = min(span["max"], seconds)
    return seconds


def label_of(schema, options):
    """The chosen model's name ("Seedance 2.5"), or ""."""
    option, model = model_option(schema), model_of(schema, options)
    if option is None:
        return ""
    return next((c.get("label") or c["id"] for c in option["choices"] if c["id"] == model), model or "")


def title_of(schema, options):
    """How a job's maker is named wherever it is shown: a ComfyUI workflow by its title, a generation server model
    by its own name, with where it is made ("Seedance 2.5 (generation server)"), never as a workflow."""
    label = label_of(schema, options)
    return "{} (generation server)".format(label) if label else schema["title"]


# ---------------------------------------------------------------- what the provider refuses that its list doesn't say

# Models that render only some of their resolutions when they are given reference pictures, sound or a clip; the
# server's list names every resolution a model has, not this. MiniMax H3 Max refused 480p with references ("with
# reference images or audio renders at 1080p, 768p only"). More are learned from the provider's own refusals
# (learn_refusal) and kept in the settings table under REFERENCE_RULES, so the next job is fitted before it is sent.
WITH_REFERENCES = {"minimax_h3_max": ["768p", "1080p"]}
REFERENCE_RULES = "generation_reference_resolutions"
_REFUSED = re.compile(r"bad_resolution_with_references\b.*?renders at (.+?) only", re.I | re.S)
_K_HEIGHT = {"1k": 1080, "2k": 1440, "4k": 2160}


def height(resolution):
    """A resolution's height, to order them: "768p" 768, "2k" 1440; 0 for what is not one."""
    name = str(resolution or "").strip().lower()
    if name in _K_HEIGHT:
        return _K_HEIGHT[name]
    found = re.fullmatch(r"(\d+)(p|k)", name)
    if not found:
        return 0
    return int(found.group(1)) * (540 if found.group(2) == "k" else 1)


def _learned(db):
    try:
        found = json.loads(db.setting(REFERENCE_RULES, "{}") or "{}")
    except (ValueError, TypeError):
        return {}
    return {k: v for k, v in found.items() if isinstance(v, list)} if isinstance(found, dict) else {}


def reference_rules(db=None):
    """{model: the resolutions it renders with references}: the known ones and those learned (db: the studio's)."""
    rules = dict(WITH_REFERENCES)
    if db is not None:
        rules.update(_learned(db))
    return rules


def learn_refusal(db, model, error):
    """The provider refused a job of `model` saying which resolutions it renders with references: kept, so the next
    job is fitted before it goes. Returns those resolutions, or None for any other error."""
    found = _REFUSED.search(str(error or ""))
    sizes = sorted({s.lower() for s in re.findall(r"\b\d+(?:p|k)\b", found.group(1), re.I)}, key=height) if found else []
    if not model or not sizes:
        return None
    learned = _learned(db)
    if learned.get(model) != sizes:
        learned[model] = sizes
        db.set_setting(REFERENCE_RULES, json.dumps(learned))
    return sizes


def reference_slots(schema):
    """The slots of a generation workflow that are references (pictures, sound, a clip): all but the first and the
    last frame."""
    frames = {(schema.get("slots") or {}).get("first_frame"), (schema.get("slots") or {}).get("last_frame")}
    return {r["id"] for r in schema["refs"] if r["id"] not in frames}


def fit_references(schema, settings, used, rules):
    """A job of a model that renders only some resolutions with references, given references (`used`: the slots it
    fills), is made at the nearest of those: the lowest one at or above what was asked, else the highest. Written
    into settings["options"]; returns the note that says so, or ""."""
    model = model_of(schema, settings.get("options"))
    allowed = [r.lower() for r in rules.get(model) or []]
    if not allowed or not set(used or ()) & reference_slots(schema):
        return ""
    option = option_for(schema, "resolution", model)
    if option is None:
        return ""
    options = settings.setdefault("options", {})
    asked = str(options.get(option["id"], option["default"]))
    if asked.lower() in allowed:
        return ""
    choices = sorted((c for c in option["choices"] if c["id"].lower() in allowed), key=lambda c: height(c["id"]))
    if not choices:
        return ""
    chosen = next((c for c in choices if height(c["id"]) >= height(asked)), choices[-1])
    options[option["id"]] = chosen["id"]
    return "{} renders at {} only when it is given references: made at {}, not {}.".format(
        label_of(schema, options) or model, " or ".join(c.get("label") or c["id"] for c in choices),
        chosen.get("label") or chosen["id"], asked)


class ModelList:
    """The generation server's list of models, read from the server whose Workflows claim each generation workflow.
    Never fails: it gives the last good answer, or None."""

    def __init__(self, pool):
        self.pool = pool
        self.kept = {}      # url -> (the answer, when it was read)
        self.tried = {}     # url -> when it last failed
        self.lock = asyncio.Lock()

    def _url(self, workflow_id):
        if self.pool is None:
            return None
        try:
            servers, _ = self.pool.route(workflow_id)
        except Exception:   # a pool of a test, or none: no list
            return None
        claimed = [s for s in servers if s.get("patterns")]
        return claimed[0]["url"] if claimed else None

    async def answer(self, workflow_id):
        """The server's whole answer for the server that makes this workflow, or None."""
        url = self._url(workflow_id)
        if url is None:
            return None
        kept, when = self.kept.get(url, (None, 0))
        now = time.time()
        if now - when < FRESH or now - self.tried.get(url, 0) < RETRY:
            return kept
        async with self.lock:
            kept, when = self.kept.get(url, (None, 0))
            if time.time() - when < FRESH:
                return kept
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(5, connect=3)) as http:
                    r = await http.get(url + "/generation/models")
                    r.raise_for_status()
                    body = r.json()
                if not isinstance(body, dict) or not any(isinstance(body.get(k), dict) for k in KINDS):
                    raise ValueError("not a list of models")
                self.kept[url] = (body, time.time())
                return body
            except (httpx.HTTPError, ValueError):
                self.tried[url] = time.time()
                return kept

    async def live(self, workflow_id):
        """{model choice: the server's entry} for one generation workflow, or None when the list can't be read (or the
        server has no account signed in, "ready" false)."""
        body = await self.answer(workflow_id)
        if not body or body.get("ready") is False:
            return None
        section = next((body[k] for k in KINDS if isinstance(body.get(k), dict) and body[k].get("workflow") == workflow_id), None)
        if section is None:
            return None
        found = {}
        for model in section.get("models") or []:
            if isinstance(model, dict):
                choice = model.get("choice") or re.sub(r"[^A-Za-z0-9_]", "_", str(model.get("id") or ""))
                if choice:
                    found[choice] = model
        return found or None
