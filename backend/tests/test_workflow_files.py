"""Every workflow the studio offers, as it is in workflows/{image,video,audio,upscaler}: its files read, what its presets file
(<name>.studio.json) names is in the workflow, its seeds are written into real inputs, it has a price, its id is its file
name, and it builds a job for every choice its presets offer. Read without ComfyUI: the files alone, and the node
definitions a real server gave (tests/fixtures/node_definitions.json) for the required settings of the nodes listed there.

A new workflow dropped into the folder is checked by these tests with no change to them."""

import asyncio
import itertools
import json
from pathlib import Path

import pytest

from conftest import ROOT
from scene import catalog, credits, prompters
from scene.api import studio
from scene.comfy import workflows

FOLDER = ROOT / "workflows"
NODES = json.loads((Path(__file__).parent / "fixtures" / "node_definitions.json").read_text(encoding="utf-8"))
SECONDS_KINDS = [k for k in catalog.FOLDERS if k not in credits.PER_JOB]
# Billed the assumed 5 seconds (credits.ASSUMED_SECONDS) whatever they make, until the studio can price them by what they
# are given or by a length in frames: a voice split and the transcripts are as long as the sound they are given, the Wan
# restyles' length is a number of frames. Listed so that a new workflow that is billed 5 s by mistake is caught.
BILLED_FIVE_SECONDS = {"audio/audio_separate_voice", "audio/audio_transcribe", "audio/audio_transcribe_video",
                       "video/video_v2v_wan22_fun_control", "video/video_v2v_wan_vace"}


def _files():
    return sorted(p for kind in catalog.FOLDERS for p in (FOLDER / kind).glob("*.json"))


def _ids():
    return ["{}/{}".format(p.parent.name, p.stem) for p in _files() if not p.name.endswith((".studio.json", ".ui.json"))]


def _load(workflow_id, info=NODES):
    return workflows.load_workflow(FOLDER / (workflow_id + ".json"), info, workflow_id)


def test_every_file_is_json_and_comes_in_its_set():
    names = {p.name for p in _files()}
    assert len(names) == len(_files()) > 0
    for path in _files():
        json.loads(path.read_text(encoding="utf-8"))   # raises on a broken file
        if path.name.endswith(".studio.json"):
            assert path.name[: -len(".studio.json")] + ".json" in names, "{}: a presets file with no workflow".format(path.name)
        elif path.name.endswith(".ui.json"):
            assert path.name[: -len(".ui.json")] + ".json" in names, "{}: a ComfyUI save with no workflow".format(path.name)
        else:
            assert path.stem + ".studio.json" in names, "{}: a workflow with no presets file".format(path.name)


def test_the_catalog_finds_every_workflow_under_its_file_name():
    found = catalog.Catalog(FOLDER, comfy=None).files()
    assert sorted(found) == _ids()
    for workflow_id, path in found.items():
        kind, name = workflow_id.split("/", 1)
        assert (path.parent.name, path.stem) == (kind, name)
        assert _load(workflow_id)["id"] == workflow_id


def test_the_folders_hold_what_the_readme_says():
    """workflows/README.md counts each folder's workflows."""
    readme = (FOLDER / "README.md").read_text(encoding="utf-8")
    for kind in catalog.FOLDERS:
        count = len([i for i in _ids() if i.startswith(kind + "/")])
        assert any(line.split()[:2] == [kind + "/", str(count)] for line in readme.splitlines()), (kind, count)


@pytest.mark.parametrize("workflow_id", _ids())
def test_it_is_read_from_its_file_alone(workflow_id):
    """Every workflow can be read with ComfyUI off and no node definitions saved."""
    wf = _load(workflow_id, None)
    assert not wf["approximate"] and wf["nodes"]
    assert workflows.describe(wf)["title"]


@pytest.mark.parametrize("workflow_id", _ids())
def test_what_its_presets_file_names_is_in_the_workflow(workflow_id):
    wf = _load(workflow_id)
    nodes, profile = wf["nodes"], wf["profile"]
    schema = workflows.describe(wf)
    refs, controls = {r["id"] for r in schema["refs"]}, {c["id"] for c in schema["controls"]}
    problems = []

    def node_of(key):   # "105", "105:prompt" or "105:104:prompt" (a node in a subgraph)
        key = str(key)
        return key if key in nodes else key.rsplit(":", 1)[0] if ":" in key and key.rsplit(":", 1)[0] in nodes else None

    def has_input(nid, name):
        return str(nid) in nodes and name in nodes[str(nid)]["inputs"]

    assert profile.get("title") and profile.get("description"), "a title and a description"
    problems += ["hide: no node {}".format(h) for h in profile.get("hide", []) if node_of(h) is None]
    problems += ["labels: nothing named {}".format(k) for k in profile.get("labels", {}) if k not in refs and node_of(k) is None]
    problems += ["defaults: no field {}".format(k) for k in profile.get("defaults", {}) if k not in controls and k not in refs]
    for key in ("optional_refs", "required_refs"):
        problems += ["{}: no reference box {}".format(key, r) for r in profile.get(key, []) if r not in refs]
    for group in profile.get("refs_when", []):
        problems += ["refs_when: no reference box {}".format(r) for r in group.get("refs", []) if r not in refs]
        problems += ["refs_when: no option {}".format(k) for k in group.get("when", {}) if k not in {o["id"] for o in schema["options"]}]
    problems += ["extra_refs: no node {}".format(e["node"]) for e in profile.get("extra_refs", []) if str(e["node"]) not in nodes]
    problems += ["slots: no reference box {}".format(r) for r in profile.get("slots", {}).values() if r not in refs]
    problems += ["controls: no input {}.{}".format(c["node"], c["input"]) for c in profile.get("controls", [])
                 if not has_input(c["node"], c["input"])]
    added = set()
    options = {o["id"]: {c["id"] for c in o["choices"]} for o in schema["options"]}
    for rule in profile.get("rules", []):
        for key, value in rule.get("when", {}).items():
            chosen = set(value) if isinstance(value, list) else {value}
            if key in options and not chosen <= options[key]:
                problems.append("rules: when {} = {}, which is not a choice".format(key, sorted(chosen - options[key])))
        added |= set(rule.get("add", {}))
        for key in rule.get("set", {}):
            nid = key.split(".", 1)[0]
            if nid not in nodes and nid not in added:
                problems.append("rules: sets {}, no such node".format(key))
    if profile.get("output_name"):
        nid, name = profile["output_name"].split(".", 1)
        if not has_input(nid, name):
            problems.append("output_name: no input {}".format(profile["output_name"]))
    if isinstance(profile.get("refs"), dict) and str(profile["refs"].get("target_node")) not in nodes:
        problems.append("refs: no target node {}".format(profile["refs"].get("target_node")))
    if profile.get("caption"):
        nid, name = profile["caption"]["template"].split(":", 1)
        if not has_input(nid, name):
            problems.append("caption: no input {}".format(profile["caption"]["template"]))
    for old in profile.get("replaces", []):
        kind, _, name = str(old).partition("/")
        if kind not in catalog.FOLDERS or not name or old in _ids():
            problems.append("replaces: {} is not a workflow that has gone".format(old))
    assert not problems, problems


@pytest.mark.parametrize("workflow_id", _ids())
def test_its_seed_targets_are_inputs_and_get_the_jobs_seed(workflow_id):
    wf = _load(workflow_id)
    spec = wf["profile"].get("seed")
    listed = [(str(n), i) for n, i in (spec.get("targets") or [])] if isinstance(spec, dict) else []
    for nid, name in listed:   # seed_targets() leaves out a target that is not there: the file must not name one
        assert nid in wf["nodes"] and name in wf["nodes"][nid]["inputs"], "seed target {}.{} is not in the workflow".format(nid, name)
    targets = workflows.seed_targets(wf)
    assert set(listed) <= set(targets)
    schema = workflows.describe(wf)
    if not schema["seeded"]:
        return
    graph, ctx = workflows.build_prompt(wf, _settings(schema, {o["id"]: o["default"] for o in schema["options"]}, seed=12345))
    assert ctx["seed"] == 12345
    for nid, name in targets:
        if nid in graph:
            assert graph[nid]["inputs"][name] == 12345, (nid, name)


@pytest.mark.parametrize("workflow_id", _ids())
def test_it_has_a_price(workflow_id):
    """A rate for its kind (credits.RATES; an admin may give one workflow its own in the console), and, priced by the
    second, a length to bill: a duration, a fixed length, a field that sets it, or the video it is given."""
    kind = credits.kind_of(workflow_id)
    assert kind in credits.RATES
    if kind not in SECONDS_KINDS:
        return
    wf = _load(workflow_id)
    schema = workflows.describe(wf)
    pricing = wf["profile"].get("pricing") or {}
    assert set(pricing) <= {"seconds", "fixed_seconds", "source"}, sorted(pricing)
    if "seconds" in pricing:
        assert pricing["seconds"] in {c["id"] for c in schema["controls"]}, "pricing.seconds names no field"
    if "source" in pricing:
        assert pricing["source"] == "video"
    settings = _settings(schema, {o["id"]: o["default"] for o in schema["options"]})
    seconds = asyncio.run(studio.billed_seconds(None, wf, schema, settings))
    if seconds is None and studio.by_source(wf):
        seconds = asyncio.run(studio.billed_seconds(None, wf, schema, dict(settings, source_seconds=7.0)))
    if workflow_id in BILLED_FIVE_SECONDS:
        assert seconds is None, "{} has a length to bill now: take it off BILLED_FIVE_SECONDS".format(workflow_id)
    else:
        assert seconds and seconds > 0, "{} would be billed the assumed {} s".format(workflow_id, credits.ASSUMED_SECONDS)


@pytest.mark.parametrize("workflow_id", _ids())
def test_it_builds_a_job_for_every_choice(workflow_id):
    """Every combination of its presets' choices gives a graph with a node that saves the result, and each node that
    the node definitions list gets the settings they say it needs (as video_minimax_h3_i2v's save node once did not)."""
    wf = _load(workflow_id)
    schema = workflows.describe(wf)
    output = (wf["profile"].get("output_name") or "").split(".", 1)[0]
    choices = [[c["id"] for c in o["choices"]] for o in schema["options"]]
    for combo in itertools.product(*choices):
        chosen = {o["id"]: c for o, c in zip(schema["options"], combo)}
        graph, _ = workflows.build_prompt(wf, _settings(schema, chosen))
        assert any("Save" in n["class_type"] or nid == output for nid, n in graph.items()), (chosen, "no node saves the result")
        if output:
            assert graph[output]["inputs"][wf["profile"]["output_name"].split(".", 1)[1]] == "{}/job".format(workflow_id.split("/")[0])
        for nid, node in graph.items():
            for name in _required_settings(node["class_type"]):
                assert name in node["inputs"], (chosen, "node {} ({}) has no {}".format(nid, node["class_type"], name))


@pytest.mark.parametrize("workflow_id", [i for i in _ids() if i.split("/")[0] in ("image", "video")])
def test_a_picture_or_video_workflow_with_a_prompt_has_a_prompt_guide(workflow_id):
    schema = workflows.describe(_load(workflow_id))
    if any(c["role"] == "prompt" for c in schema["controls"]):
        assert prompters.for_workflow(workflow_id), "no guide in scene/prompters/ matches {}".format(workflow_id)


def test_titles_are_told_apart_within_a_kind():
    seen = {}
    for workflow_id in _ids():
        key = (workflow_id.split("/")[0], workflows.describe(_load(workflow_id))["title"])
        assert key not in seen, (workflow_id, seen.get(key))
        seen[key] = workflow_id


def _settings(schema, options, seed=None):
    settings = {"values": {c["id"]: "A cat on a wall." for c in schema["controls"] if c["role"] == "prompt"},
                "options": options, "name": "job", "clips": 1,
                "refs": {r["id"]: {"comfy_name": "scene_x.png"} for r in schema["refs"] if r.get("required")}}
    if seed is not None:
        settings.update(seed_mode="fixed", seed=seed)
    return settings


def _required_settings(class_type):
    """The settings (not the links) the node definitions say a node needs."""
    info = NODES.get(class_type) or {}
    needed = []
    for name, entry in ((info.get("input") or {}).get("required") or {}).items():
        kind, opts = entry[0], entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
        if (isinstance(kind, list) or kind in workflows.WIDGET_TYPES or kind == workflows.DYNAMIC_COMBO) and not opts.get("forceInput"):
            needed.append(name)
    return needed
