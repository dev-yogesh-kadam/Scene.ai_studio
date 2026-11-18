"""The providers' models offered in the studio, while the router is on (registry.ROUTER "on").

Each model a key unlocks (provider_models) is offered as a workflow of its capability's folder, `<folder>/@<model id>`
(video/@seedance_2_5, audio/@speech), made from its `input_schema` and `limits` in the shape a workflow file has, so
everything that offers, prices, checks and queues a workflow (the pickers, Create, the agent's catalog, estimates,
credits) works on it unchanged:

- one node, PROVIDER_NODE ("ProviderJob"), whose inputs are the model's inputs by the provider's own names;
- the prompt (or a speech's text), the length and every other free value as a primitive node linked into it (the
  prompt is titled "Prompt", the length "Duration (seconds)", which gives them their roles);
- every choice (an enum, a yes/no) as an option of the presets, with a rule per choice that writes it into the node;
- every file input (marked "x-file", v1.file_fields) as a reference slot: a first or last frame as its own slot, a
  list of reference pictures as the presets' list of references, other lists as numbered slots.

The queue sends such a job through the provider (jobs.py, _run_provider): the graph is built as any workflow's
(workflows.build_prompt), and the provider node's inputs are its `input`, files uploaded first (POST /v1/files).
A model offered by several providers is one workflow: the router picks the provider and key for each job. A model with
a prompt, a length and a first frame makes long videos of several clips (jobs._run_provider_chain), each starting on
the last frame of the one before."""

import copy
import json
import time

from ..db import as_everyone, offload
from . import registry
from .base import CAPABILITY_FOLDERS
from .v1 import file_fields

PROVIDER_NODE = "100"
PROVIDER_CLASS = "ProviderJob"
MARK = "@"            # a provider model's workflow id is <folder>/@<model id>
FRESH = 5             # seconds the models and the switch are kept between reads
LIST_MOST = 9         # reference slots of a list whose length the model does not say
LABELS = {"first_frame": "First frame", "last_frame": "Last frame", "reference_video": "Reference video",
          "video": "Video", "audio": "Voice track", "voice_id": "Voice id", "language_code": "Language",
          "style_instructions": "Style instructions", "aspect_ratio": "Shape", "sound": "Sound", "factor": "Scale",
          "resolution": "Resolution", "duration": "Duration (seconds)", "prompt": "Prompt", "text": "Prompt"}
LIMIT_LISTS = {"resolution": "resolutions", "aspect_ratio": "aspect_ratios"}
LIMIT_COUNTS = {"reference_images": "max_reference_images", "reference_audios": "max_reference_audios"}


def workflow_id(capability, model_id):
    folder = CAPABILITY_FOLDERS.get(capability)
    return "{}/{}{}".format(folder, MARK, model_id) if folder else None


def is_provider_id(workflow_id_):
    return str(workflow_id_ or "").rsplit("/", 1)[-1].startswith(MARK)


def model_id_of(workflow_id_):
    """The provider's model id of a provider workflow ("video/@seedance_2_5" -> "seedance_2_5"), else None."""
    name = str(workflow_id_ or "").rsplit("/", 1)[-1]
    return name[len(MARK):] if name.startswith(MARK) else None


def _label(name, spec):
    return str(spec.get("title") or LABELS.get(name) or name.replace("_", " ").capitalize())[:60]


def _choice_id(value):
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def build(model):
    """The workflow (catalog.load's shape: {"id", "nodes", "info", "profile", "approximate"}) of one provider model, a
    provider_models row with its JSON read. None for a capability the studio does not offer as a workflow."""
    wid = workflow_id(model["capability"], model["model_id"])
    if wid is None:
        return None
    schema = model.get("input_schema") or {}
    limits = model.get("limits") or {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    order = [n for n in schema.get(registry.ORDER) or [] if n in properties]   # the provider's order (jsonb keeps none)
    properties = {n: properties[n] for n in order + [n for n in properties if n not in order]}
    required = set(schema.get("required") or [])
    files = file_fields(schema)
    nodes = {PROVIDER_NODE: {"class_type": PROVIDER_CLASS, "inputs": {}, "_meta": {"title": model.get("name") or model["model_id"]}}}
    sink = nodes[PROVIDER_NODE]["inputs"]
    profile = {"title": model.get("name") or model["model_id"], "description": model.get("best_for") or "",
               "pick_when": model.get("best_for") or "", "labels": {}, "defaults": {}, "options": [], "rules": [],
               "optional_refs": [], "required_refs": [], "hints": [],
               "provider": {"model": model["model_id"], "capability": model["capability"], "limits": limits,
                            "pricing": model.get("pricing") or {}, "typical_seconds": model.get("typical_seconds"),
                            "can_cancel": bool(model.get("can_cancel")), "files": {k: list(v) for k, v in files.items()}}}
    number = [1]

    def node(class_type, inputs, title):
        number[0] += 1
        nid = str(number[0])
        nodes[nid] = {"class_type": class_type, "inputs": inputs, "_meta": {"title": title}}
        return nid

    dynamic_done = False
    for name, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        label = _label(name, spec)
        if name in files:
            kind, many, most = files[name]
            if not many:
                nid = node("ProviderOptional" + kind.capitalize(), {kind: "none"}, label)
                sink[name] = [nid, 0]
                (profile["required_refs"] if name in required else profile["optional_refs"]).append("{}:{}".format(nid, kind))
                continue
            most = most or limits.get(LIMIT_COUNTS.get(name, ""), None) or LIST_MOST
            most = most if isinstance(most, int) and not isinstance(most, bool) else LIST_MOST
            if kind == "image" and not dynamic_done:   # the list of reference pictures: the presets' list of references
                dynamic_done = True
                profile["refs"] = {"mode": "dynamic", "max": most, "min": 1 if name in required else 0,
                                   "node_class": "LoadImage", "node_input": "image", "node_id": "ref_{n}",
                                   "label": "REFERENCE {n}", "target_node": PROVIDER_NODE,
                                   "target_input": name + "#{n}", "first_index": 1, "prompt_tag": "image {n}"}
                continue
            for n in range(1, most + 1):
                nid = node("ProviderOptional" + kind.capitalize(), {kind: "none"}, "{} {}".format(label.rstrip("s"), n))
                sink["{}#{}".format(name, n)] = [nid, 0]
                profile["optional_refs"].append("{}:{}".format(nid, kind))
            continue
        kind = spec.get("type")
        enum = spec.get("enum") if isinstance(spec.get("enum"), list) else None
        if enum is None and name in LIMIT_LISTS and isinstance(limits.get(LIMIT_LISTS[name]), list):
            enum = list(limits[LIMIT_LISTS[name]])
        if kind == "boolean" or enum:
            values = [True, False] if kind == "boolean" and not enum else enum
            default = spec.get("default", values[0] if kind != "boolean" else False)
            choices = [{"id": _choice_id(v), "label": ("On" if v else "Off") if isinstance(v, bool) else str(v)} for v in values]
            profile["options"].append({"id": name, "label": label, "default": _choice_id(default), "choices": choices})
            for v in values:
                profile["rules"].append({"when": {name: _choice_id(v)}, "set": {"{}.{}".format(PROVIDER_NODE, name): v}})
            continue
        if kind in ("integer", "number"):
            title = "Duration (seconds)" if name in ("duration", "seconds") else label
            seconds = limits.get("seconds") if isinstance(limits.get("seconds"), dict) else {}
            default = spec.get("default", seconds.get("min") if name in ("duration", "seconds") else spec.get("minimum", 0))
            if kind == "integer":
                default = int(default or 0)
                nid = node("PrimitiveInt", {"value": default}, title)
            else:
                default = float(default or 0)
                nid = node("PrimitiveFloat", {"value": default}, title)
            low, high = spec.get("minimum", seconds.get("min") if name == "duration" else None), \
                spec.get("maximum", seconds.get("max") if name == "duration" else None)
            if low is not None and high is not None:
                profile["labels"]["{}:value".format(nid)] = "{} ({:g} to {:g})".format(title, low, high)
            sink[name] = [nid, 0]
            if name in ("duration", "seconds"):
                profile["pricing"] = {"seconds": "{}:value".format(nid)}
            continue
        # free words: the prompt (or the words a voice speaks) is the prompt; any other words a setting of their own
        if name in ("prompt", "text") and "Prompt" not in [n["_meta"]["title"] for n in nodes.values()]:
            nid = node("PrimitiveStringMultiline", {"value": str(spec.get("default") or "")}, "Prompt")
            if name == "text":
                profile["labels"]["{}:value".format(nid)] = "The words to speak"
            if name not in required:
                profile["prompt_optional"] = True
        else:
            nid = node("PrimitiveStringMultiline" if spec.get("maxLength", 0) and spec["maxLength"] > 200 else "PrimitiveString",
                       {"value": str(spec.get("default") or "")}, label)
        sink[name] = [nid, 0]
    if "Prompt" not in [n["_meta"]["title"] for n in nodes.values()]:
        profile["prompt_optional"] = True
    said = price_words(model.get("pricing") or {})
    if said:
        profile["hints"].append("The provider's price: " + said + ".")
    return {"id": wid, "nodes": nodes, "info": {}, "profile": profile, "approximate": False}


def price_words(pricing):
    """The provider's price list in a few words ("6 credits a second at 480p, 10 at 720p"), or ""."""
    credits = pricing.get("credits")
    unit = {"second": "a second", "job": "a job", "image": "a picture"}.get(str(pricing.get("unit") or ""), "")
    if isinstance(credits, dict) and credits:
        parts = ["{:g} credits {} at {}".format(v, unit, k) if i == 0 else "{:g} at {}".format(v, k)
                 for i, (k, v) in enumerate(credits.items()) if isinstance(v, (int, float))]
        words = ", ".join(parts)
    elif isinstance(credits, (int, float)):
        words = "{:g} credits {}".format(credits, unit).strip()
    else:
        return "priced by the provider's quote" if pricing else ""
    extra = pricing.get("credits_with_sound")
    if isinstance(extra, dict) and extra:
        words += "; with sound " + ", ".join("{:g} at {}".format(v, k) for k, v in extra.items() if isinstance(v, (int, float)))
    elif isinstance(extra, (int, float)):
        words += "; {:g} with sound".format(extra)
    return words


def provider_input(wf, graph):
    """A built graph's provider node inputs as the model's `input`: links read through to their values, a list's
    numbered slots gathered in order, an empty file slot ("none") left out. Files are still the studio's names
    ({"file": name}) for the caller to upload."""
    files = (wf["profile"].get("provider") or {}).get("files") or {}
    found, lists = {}, {}
    for name, value in (graph.get(PROVIDER_NODE) or {}).get("inputs", {}).items():
        if isinstance(value, list) and len(value) == 2 and str(value[0]) in graph:
            source = graph[str(value[0])]["inputs"]
            value = source.get("value", next((source[k] for k in ("image", "audio", "video") if k in source), None))
        base, _, n = name.partition("#")
        if base in files:
            if value in (None, "", "none"):
                continue
            value = {"file": str(value), "kind": files[base][0]}
        if n:
            lists.setdefault(base, []).append((int(n), value))
        else:
            found[name] = value
    for base, items in lists.items():
        found[base] = [v for _, v in sorted(items, key=lambda item: item[0])]
    return found


def limits_problem(wf, schema, settings):
    """What a provider's model can't take of this job, in words, or "": its lengths (limits.seconds) and how many
    reference pictures and sounds it takes. The provider checks the rest itself and says why."""
    provider = wf["profile"].get("provider") or {}
    limits = provider.get("limits") or {}
    name = wf["profile"].get("title") or provider.get("model")
    seconds = limits.get("seconds") if isinstance(limits.get("seconds"), dict) else {}
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    if "duration" in roles and seconds:
        from ..comfy import workflows as studio_workflows
        asked = studio_workflows.context(schema, settings).get("duration")
        low, high = seconds.get("min"), seconds.get("max")
        if asked is not None and ((low is not None and asked < low) or (high is not None and asked > high)):
            return "{} makes clips of {:g} to {:g} seconds; this one asks for {:g}.".format(name, low or 0, high or asked, asked)
    refs = settings.get("refs") or {}
    kinds = {r["id"]: r["kind"] for r in schema["refs"]}
    for kind, limit in (("image", "max_reference_images"), ("audio", "max_reference_audios")):
        most = limits.get(limit)
        listed = [slot for slot, given in refs.items() if given and kinds.get(slot) == kind
                  and slot not in (schema["slots"].get("first_frame"), schema["slots"].get("last_frame"))]
        if isinstance(most, int) and not isinstance(most, bool) and len(listed) > most:
            what = "reference pictures" if kind == "image" else "reference sounds"
            return "{} takes {} {}; this job gives {}.".format(name, "no" if not most else "at most {}".format(most), what, len(listed))
    frames = limits.get("frames")
    if isinstance(frames, list):
        for frame in ("first", "last"):
            slot = schema["slots"].get(frame + "_frame")
            if slot and refs.get(slot) and frame not in frames:
                return "{} can't take a {} frame.".format(name, frame)
    return ""


class ProviderWorkflows:
    """The providers' models as workflows, read from the registry at most every FRESH seconds; none while the router
    is not "on". Its sync accessors read what was last read; refresh() (async) reads again when due."""

    def __init__(self, db):
        self.db = db
        self.read_at = 0.0
        self.mode = "off"
        self.found = {}   # workflow id -> wf

    def _read(self):
        mode = registry.router_mode(self.db)
        if mode != "on":
            return mode, {}
        with as_everyone():
            rows = self.db.all(
                "SELECT m.* FROM provider_models m JOIN provider_keys k ON k.id = m.key_id JOIN providers p ON p.id = m.provider_id "
                "WHERE p.active = 1 AND k.active = 1 AND k.status <> 'invalid' AND p.kind IN ('scene_provider_v1', 'local_tools') "
                "ORDER BY p.priority, p.id, k.priority, k.id")
        found = {}
        for row in rows:
            for field in ("input_schema", "limits", "pricing"):
                row[field] = registry._json(row[field]) or {}
            wid = workflow_id(row["capability"], row["model_id"])
            if wid and wid not in found:   # the first provider's description of a model offered by several
                wf = build(row)
                if wf is not None:
                    found[wid] = wf
        return mode, found

    async def refresh(self, force=False):
        if not force and time.time() - self.read_at < FRESH:
            return
        try:
            self.mode, self.found = await offload(self._read)
        except Exception as error:   # the registry's tables missing (a database behind 0015): none offered
            print("The providers' models could not be read: {}".format(error))
            self.mode, self.found = "off", {}
        self.read_at = time.time()

    def active(self):
        return self.mode == "on"

    def workflows(self):
        return self.found

    def get(self, wid):
        wf = self.found.get(wid)
        return copy.deepcopy(wf) if wf is not None else None


def describe_pricing(wf):
    """The provider's price of a provider workflow, as JSON text for the console, or ""."""
    pricing = (wf["profile"].get("provider") or {}).get("pricing")
    return json.dumps(pricing) if pricing else ""

