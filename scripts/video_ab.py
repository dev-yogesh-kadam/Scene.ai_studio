"""The video models and their settings, and old prompts against the model guides, on the render PC.

    .venv/Scripts/python.exe scripts/video_ab.py [out folder] [--only=group,group] [--prompts-only] [--no-judge]

Groups (RUNS below):
  settings   H3 All In One at quality low, medium and high at 480p, and high at 720p, on three shots of the first A/B
  oldnew     old prompts against the guides on two more H3 shots, and on a Wan restyle
  modes      a shot that starts on a picture: H3 first-frame mode, H3 reference mode, H3 Chunk's anchor
  talking    Talking Head on H3 and on Wan S2V, and on H3 with the voice taken out of its street noise first
  restyle    the same clip and style frame on LTX-2.3 IC-LoRA, Wan 2.2 Fun Control and Wan VACE

Every variant of a group gets the same seed. Prompts are written by the agent's model (prompt_ab.write_prompt) with the
old or the new instructions; a group's variants share one prompt, so only the setting or the model differs. Each group
is ranked blind by Opus from frames (it cannot hear: lips are judged by eye), old/new pairs compared blind. Pictures,
the voice and the source clip come from the earlier runs in C:/Scene/prompt-ab. Writes <out>/report.html."""

import asyncio
import json
import random
import subprocess
import sys
import zlib
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import prompt_ab as ab  # noqa: E402
from scene import catalog, claude, media, review  # noqa: E402
from scene.comfy import client, workflows  # noqa: E402

AB = Path("C:/Scene/prompt-ab")
PICTURES = {"perfume": AB / "models/product@flux2_dev/new.png", "market": AB / "models/market@flux2_dev/new.png",
            "fisherman": AB / "models/portrait@flux2_dev/new.png"}
SOURCE_CLIP = AB / "corridor/new.mp4"     # the restyle source: the corridor walk of the second round
VOICE_CLIP = AB / "chai/old.mp4"          # its sound: the chai seller's line over street noise
EARLIER = {c: next(r for r in json.loads((AB / "prompts.json").read_text(encoding="utf-8")) if r["case"] == c) for c in ("corridor", "chai", "football")}
H3 = "video/h3_all_in_one"
WATERCOLOR = "Restyle @1 as a hand-painted watercolour illustration: the same woman, the same walk and glance, the same corridor."

# group, case, variant, workflow, how the prompt is made, settings: options / values / resolution / orientation / refs
RUNS = [
    *[("settings", case, "{}_{}".format(q, res), H3, ("earlier", case), {"options": {"quality": q}, "resolution": res, "duration": 6})
      for case in ("corridor", "chai", "football") for q, res in (("low", 480), ("medium", 480), ("high", 480), ("high", 720))],
    *[("oldnew", case, version, H3, ("agent", version, idea, []), {"resolution": 480, "orientation": shape})
      for case, idea, shape in (("product-turn", "A glass perfume bottle on wet black stone slowly turns while orange petals drift past it, for a YouTube ad.", "landscape"),
                                ("crane-reveal", "A slow crane up over a misty tea plantation at sunrise that reveals the whole valley, for the opening of a travel film.", "landscape"))
      for version in ("old", "new")],
    *[("oldnew", "wan-restyle", version, "video/video_v2v_wan_vace", ("agent", version, WATERCOLOR, ["clip", "style"]), {"refs": {"299:file": "clip", "73:image": "style"}})
      for version in ("old", "new")],
    ("modes", "perfume", "h3_first_frame", H3, ("agent", "new", "Animate @1 exactly as it is: the petals drift and the camera slowly circles the bottle.", ["perfume"]),
     {"options": {"engine": "first_frame"}, "refs": {"209:image": "perfume"}, "resolution": 480}),
    ("modes", "perfume", "h3_reference", H3, ("agent", "new", "A new shot of the perfume of @1: it stands on wet black stone, orange petals drift past, the camera slowly circles it.", ["perfume"]),
     {"options": {"engine": "reference"}, "refs": {"206:image": "perfume"}, "resolution": 480}),
    ("modes", "market", "h3_first_frame", H3, ("agent", "new", "Animate @1: rain keeps falling, people walk through the market, the camera slowly pushes in.", ["market"]),
     {"options": {"engine": "first_frame"}, "refs": {"209:image": "market"}, "resolution": 480}),
    ("modes", "market", "h3_reference", H3, ("agent", "new", "Use @1 as the background reference (the place), not as the first frame: a new shot of that rainy night market where rain keeps falling, people walk through it and the camera slowly pushes in.", ["market"]),
     {"options": {"engine": "reference"}, "refs": {"205:image": "market"}, "resolution": 480}),
    ("modes", "market", "h3_chunk_anchor", "video/h3_chunk", ("agent", "new", "The rainy night market of @1: rain keeps falling, people walk through it, the camera slowly pushes in.", ["market"]),
     {"refs": {"205:image": "market"}}),
    *[("talking", "fisherman", variant, "video/talking_head_narration", ("agent", "new", "@1 says the words of @2 warmly, straight to camera, with small natural nods.", ["fisherman", "voice"]),
       {"options": {"engine": engine}, "refs": {"2:image": "fisherman", "3:audio": voice}, "duration": 6})
      for variant, engine, voice in (("h3", "h3", "voice"), ("wan_s2v", "wan", "voice"), ("h3_clean_voice", "h3", "voice_clean"))],
    *[("restyle", "watercolour", variant, wid, ("agent", "new", WATERCOLOR, ["clip", "style"]), {"refs": refs})
      for variant, wid, refs in (("ltx23_iclora", "video/video_v2v_ltx23_iclora", {"199:file": "clip", "200:image": "style"}),
                                 ("wan22_fun_control", "video/video_v2v_wan22_fun_control", {"158:file": "clip", "145:image": "style"}),
                                 ("wan_vace", "video/video_v2v_wan_vace", {"299:file": "clip", "73:image": "style"}))],
]
ATTACHED = {   # what the agent is told of each input, as an attached item
    "perfume": {"kind": "image", "name": "perfume picture", "shows": "A clear glass perfume bottle on a slab of wet black stone with orange petals, warm glow behind it, square."},
    "market": {"kind": "image", "name": "market picture", "shows": "A rainy night market street in Mumbai, stalls, umbrellas, neon, wet road, landscape."},
    "fisherman": {"kind": "image", "name": "fisherman portrait", "shows": "An old fisherman with a white beard on a pier at dawn, portrait."},
    "voice": {"kind": "audio", "name": "voice line", "seconds": 6.0},
    "clip": {"kind": "video", "name": "corridor walk", "seconds": 6.0, "shows": "A young woman in a green saree walks down a sunlit haveli corridor and glances back."},
    "style": {"kind": "image", "name": "watercolour style frame", "shows": "The first frame of the corridor walk as a watercolour illustration."},
}
RANK = """You judge video clips made for the same request at Scene.ai, an AI video studio, by different models or
settings, with the same seed where they could. You are not told which is which. Each clip is shown as frames in order.
Score each from 1 to 5 on: "asked" (it shows what the request asked for), "craft" (framing, light, a look a client
would pay for), "clean" (no broken hands or faces, no melting, nothing garbled), "motion" (natural movement, the same
face and clothes through the clip, no jumps or morphing). You cannot hear the sound: judge speech only by the mouth.
Then rank them all, best first, and say in two plain sentences what puts the first ahead and pulls the last down."""
RANK_SHAPE = {"type": "object", "required": ["scores", "ranking", "why"], "properties": {
    "scores": {"type": "array", "items": {"type": "object", "required": ["clip", "asked", "craft", "clean", "motion"], "properties": {
        "clip": {"type": "integer"}, **{k: {"type": "integer", "minimum": 1, "maximum": 5} for k in ("asked", "craft", "clean", "motion")}}}},
    "ranking": {"type": "array", "items": {"type": "integer"}}, "why": {"type": "string"}}}
FRAMES = 4   # frames of each clip the ranking is shown (several clips go in one look)


def ffmpeg(*args):
    subprocess.run([media.ffmpeg_path(), "-loglevel", "error", "-y", *map(str, args)], check=True)


async def inputs(out, comfy, shelf, service):
    """The files the runs use, each put on the render PC once: {"name": {"path", "comfy_name"}}."""
    prep = out / "inputs"
    prep.mkdir(parents=True, exist_ok=True)
    files = {name: path for name, path in PICTURES.items()}
    files["clip"] = SOURCE_CLIP
    voice = prep / "voice.wav"
    if not voice.is_file():
        ffmpeg("-i", VOICE_CLIP, "-vn", "-ac", "1", "-ar", "44100", voice)
    files["voice"] = voice
    uploaded = {}
    for name, path in files.items():
        uploaded[name] = await comfy.upload("scene_ab_" + path.name if name not in ("voice", "clip") else "scene_ab_{}{}".format(name, path.suffix),
                                            path.read_bytes(), None)
    # The voice alone: the separation workflow, as a job with "clean_voice" runs it.
    clean = prep / "voice_clean.wav"
    if not clean.is_file():
        wf = await shelf.load("audio/audio_separate_voice")
        slot = next(r["id"] for r in workflows.describe(wf)["refs"] if r["kind"] == "audio")
        graph, _ = workflows.build_prompt(wf, {"values": {}, "options": {}, "refs": {slot: {"comfy_name": uploaded["voice"]}}, "name": "ab voice"})
        entry = await run_graph(comfy, graph)
        from scene import jobs   # the stems told apart as a job tells them: by the title of the node that saved each
        outputs = list(jobs._outputs(entry))
        voice_out = next(item for (item, kind, _), label in zip(outputs, jobs._output_labels(wf, outputs)) if "VOICE" in str(label or "").upper())
        await save(comfy, voice_out, clean)
    uploaded["voice_clean"] = await comfy.upload("scene_ab_voice_clean.wav", clean.read_bytes(), "audio/wav")
    # The style frame: the source clip's first frame made a watercolour by FLUX.2 dev, with the frame as its reference.
    style = prep / "style.png"
    if not style.is_file():
        first = prep / "first_frame.png"
        ffmpeg("-i", SOURCE_CLIP, "-frames:v", "1", first)
        name = await comfy.upload("scene_ab_first_frame.png", first.read_bytes(), "image/png")
        wf = await shelf.load("image/image_t2i_flux2_dev")
        schema = workflows.describe(wf)
        prompt_id = next(c["id"] for c in schema["controls"] if c["role"] == "prompt")
        settings = {"values": {prompt_id: "The woman, the corridor and the framing of image 1, painted as a hand-painted watercolour "
                               "illustration: soft washes of green and ochre, visible paper texture, loose ink lines; the same pose, "
                               "the same composition, the same light."}, "options": {}, "refs": {"ref_1": {"comfy_name": name}},
                    "seed_mode": "fixed", "seed": 7, "name": "ab style"}
        ab.agent.shape_like(schema, settings, (16, 9))
        await ab.render(comfy, wf, settings, prep / "style")
    uploaded["style"] = await comfy.upload("scene_ab_style.png", style.read_bytes(), "image/png")
    return uploaded


async def run_graph(comfy, graph):
    import uuid
    prompt_id = await comfy.queue(graph, uuid.uuid4().hex)
    while True:
        await asyncio.sleep(3)
        found = await comfy.history(prompt_id)
        status = (found or {}).get("status", {})
        if status.get("status_str") == "error":
            raise client.ComfyError(json.dumps(status.get("messages"))[:600])
        if status.get("completed"):
            return found


async def save(comfy, item, target):
    response = await comfy.view(item["filename"], item.get("subfolder", ""))
    try:
        response.raise_for_status()
        target.write_bytes(await response.aread())
    finally:
        await response.aclose()


async def write(service, version, wid, schema, idea, given):
    """The prompt of one run: the agent's model told of the inputs as attached items."""
    selection = [dict(ATTACHED[g], tag="@{}".format(n), id=900 + n) for n, g in enumerate(given, start=1)]
    offer = ab.agent.offer(schema)
    if version == "old":
        system, guide, offer = ab.old_system(), ab.old_guide(), ab.old_offer(offer)
    else:
        system, guide = ab.agent.system(), ab.agent.STRUCTURE_GUIDE.format(structure=ab.agent.PROMPT_STRUCTURE)
    message = ab.agent.question(idea, [offer], selection, wid, guides=guide)
    text, _, _ = await claude.ask(service, ab.MODEL, [{"role": "system", "content": system}, {"role": "user", "content": message}],
                                  ab.agent.reply_format([wid]))
    answer = json.loads(text)
    step = next((s for s in answer["steps"] if s.get("tool") == "generate"), None)
    if step is None:
        raise ab.NoStep("the agent planned nothing: " + " ".join(str(answer.get("reply") or "").split())[:300])
    return ab.camera.apply(step.get("prompt"), ab.camera.clean(step), "video")


def settings_for(schema, prompt, spec, seed, uploaded, name):
    """Job settings from the workflow's defaults and the run's own: only what the run names differs from the defaults."""
    values = {c["id"]: c["default"] for c in schema["controls"]}
    roles = {c["role"]: c for c in schema["controls"] if c["role"]}
    if "prompt" in roles:
        values[roles["prompt"]["id"]] = prompt[:ab.agent.PROMPT_CHARS]
    if "duration" in roles and spec.get("duration"):
        values[roles["duration"]["id"]] = spec["duration"]
    if "resolution" in roles and spec.get("resolution"):
        values[roles["resolution"]["id"]] = spec["resolution"]
    options = {o["id"]: o["default"] for o in schema["options"]}
    options.update(spec.get("options") or {})
    settings = {"workflow": schema["id"], "name": name, "values": values, "options": options, "clips": 1, "seed_mode": "fixed", "seed": seed,
                "refs": {slot: {"comfy_name": uploaded[source], "name": source} for slot, source in (spec.get("refs") or {}).items()}}
    if schema.get("size"):
        settings.update(resolution=spec.get("resolution") or schema["size"]["resolution"], orientation=spec.get("orientation") or schema["size"]["orientation"])
    elif spec.get("orientation"):
        ab.agent.shape_like(schema, settings, {"landscape": (16, 9), "portrait": (9, 16), "square": (1, 1)}[spec["orientation"]])
    return settings


async def frames_of(path):
    got = await review.result_frames(path, "video")
    spread = [b for label, b in got if label.startswith("the result at")] or [b for _, b in got]
    step = max(1, len(spread) // FRAMES)
    return spread[::step][:FRAMES]


async def rank(service, out, group, case, runs):
    made = [r for r in runs if r.get("file")]
    if len(made) < 2:
        return None
    random.shuffle(made)
    pictures, named = [], []
    for n, r in enumerate(made, start=1):
        shots = await frames_of(out / r["file"])
        pictures += shots
        named += ["Clip {} frame {}".format(n, k) for k in range(1, len(shots) + 1)]
    idea = made[0]["idea"]
    text, _, _ = await claude.ask(service, ab.JUDGE, [{"role": "system", "content": RANK}, {"role": "user", "content":
        "The request:\n{}\n\nThe pictures, in order:\n{}\n\nJudge the {} clips.".format(idea, "\n".join("Picture {}: {}".format(i, l) for i, l in enumerate(named, start=1)), len(made))}],
        RANK_SHAPE, images=pictures)
    said = json.loads(text)
    variant_of = {n: r["variant"] for n, r in enumerate(made, start=1)}
    return {"order": [variant_of[n] for n in said["ranking"] if n in variant_of], "why": said["why"],
            "scores": {variant_of[s["clip"]]: {k: s[k] for k in ("asked", "craft", "clean", "motion")} for s in said["scores"] if s["clip"] in variant_of}}


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--only=")), None)
    out = Path(args[0] if args else AB / "video")
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    service = claude.service(config.get("claude_models") or ab.MODEL)
    comfy = client.Comfy(lambda: config["comfy_url"])
    shelf = catalog.Catalog(ROOT / "workflows", comfy)
    kept = out / "runs.json"
    state = json.loads(kept.read_text(encoding="utf-8")) if kept.is_file() else {"runs": {}, "ranks": {}, "pairs": {}}

    def store():
        kept.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
        report(out, state)
    runs = [dict(zip(("group", "case", "variant", "workflow", "how", "spec"), run)) for run in RUNS if not only or run[0] in only]
    schemas = {}
    for r in runs:
        if r["workflow"] not in schemas:
            schemas[r["workflow"]] = (await shelf.load(r["workflow"]),)
            schemas[r["workflow"]] += (workflows.describe(schemas[r["workflow"]][0]),)
    # Prompts: one per (group, case, version), shared by the case's variants where only a setting differs; where the
    # mode or the model differs (modes, restyle), each variant's own, as the studio would write it for that workflow.
    prompts = {}
    for r in runs:
        how = r["how"]
        key = "{}/{}/{}".format(r["group"], r["case"], how[1] if how[0] == "agent" else "earlier") + (
            "/" + r["variant"] if r["group"] in ("modes", "restyle") else "")
        if how[0] == "earlier":
            prompts[key] = EARLIER[how[1]]["new"]["prompt"]
            r["idea"] = EARLIER[how[1]]["idea"]
        else:
            r["idea"] = how[2]
            if key not in prompts:
                prompts[key] = None
        r["prompt_key"] = key
    async def one(key, r):
        saved = state["runs"].get("prompt:" + key)
        if saved:
            prompts[key] = saved
            return
        how = r["how"]
        try:
            prompts[key] = await write(service, how[1], r["workflow"], schemas[r["workflow"]][1], how[2], how[3])
        except Exception as e:
            prompts[key] = ""
            print("  no prompt for {}: {}".format(key, str(e)[:200]), flush=True)
        state["runs"]["prompt:" + key] = prompts[key]
    firsts = {}
    for r in runs:
        firsts.setdefault(r["prompt_key"], r)
    await asyncio.gather(*(one(k, r) for k, r in firsts.items() if prompts[k] is None))
    store()
    if "--prompts-only" in sys.argv:
        return
    uploaded = await inputs(out, comfy, shelf, service)
    for wid in dict.fromkeys(r["workflow"] for r in runs):   # grouped by workflow: each model is loaded once
        wf, schema = schemas[wid]
        for r in [r for r in runs if r["workflow"] == wid]:
            rid = "{}/{}/{}".format(r["group"], r["case"], r["variant"])
            got = state["runs"].setdefault(rid, {})
            got.update(group=r["group"], case=r["case"], variant=r["variant"], workflow=wid, idea=r["idea"], prompt=prompts[r["prompt_key"]])
            if got.get("file") or not got["prompt"]:
                continue
            seed = zlib.crc32("{}/{}".format(r["group"], r["case"]).encode()) % workflows.SEED_RANGE
            print("{}: rendering".format(rid), flush=True)
            (out / r["group"] / r["case"]).mkdir(parents=True, exist_ok=True)
            try:
                settings = settings_for(schema, got["prompt"], r["spec"], seed, uploaded, rid.replace("/", "_"))
                name, got["seconds"] = await ab.render(comfy, wf, settings, out / r["group"] / r["case"] / r["variant"])
                got["file"] = "{}/{}/{}".format(r["group"], r["case"], name)
                got.pop("error", None)
            except Exception as e:
                got["error"] = str(e)[:500]
                print("  failed: " + got["error"], flush=True)
            store()
    if "--no-judge" in sys.argv:
        return
    cases = dict.fromkeys((r["group"], r["case"]) for r in runs)
    for group, case in cases:
        key = "{}/{}".format(group, case)
        mine = [v for v in state["runs"].values() if isinstance(v, dict) and v.get("group") == group and v.get("case") == case]
        if group == "oldnew":
            if not state["pairs"].get(key) and all(any(v["variant"] == ver and v.get("file") for v in mine) for ver in ("old", "new")):
                pair = {"case": case, "workflow": mine[0]["workflow"], "idea": mine[0]["idea"],
                        **{v["variant"]: {"file": Path(v["file"]).name} for v in mine}}
                try:
                    await ab.judge(service, out / group, pair, reviews=False)   # reads <out>/oldnew/<case>/<old|new>.mp4
                    state["pairs"][key] = pair["compare"]
                except Exception as e:
                    print("  {} not judged: {}".format(key, str(e)[:200]), flush=True)
        elif key not in state["ranks"]:
            try:
                state["ranks"][key] = await rank(service, out, group, case, mine)
            except Exception as e:
                print("  {} not ranked: {}".format(key, str(e)[:200]), flush=True)
        if state["ranks"].get(key):
            print("{}: {}".format(key, " > ".join(state["ranks"][key]["order"])), flush=True)
        if state["pairs"].get(key):
            print("{}: {} wins".format(key, state["pairs"][key]["better"]), flush=True)
        store()
    print("Report: " + str(out / "report.html"))


def report(out, state):
    groups = {}
    for v in state["runs"].values():
        if isinstance(v, dict) and v.get("group"):
            groups.setdefault(v["group"], {}).setdefault(v["case"], []).append(v)
    parts = []
    for group, cases in groups.items():
        parts.append("<h2>{}</h2>".format(escape(group)))
        for case, runs in cases.items():
            key = "{}/{}".format(group, case)
            rank_, pair = state["ranks"].get(key), state["pairs"].get(key)
            order = (rank_ or {}).get("order") or [r["variant"] for r in runs]
            runs = sorted(runs, key=lambda r: order.index(r["variant"]) if r["variant"] in order else 99)
            said = "<p class='win'>Blind ranking: <b>{}</b> — {}</p>".format(escape(" > ".join(rank_["order"])), escape(rank_["why"])) if rank_ else ""
            if pair:
                said = "<p class='win'>Blind pick: <b>{}</b> — {}</p>".format(escape(pair["better"]), escape(pair["why"]))
            cells = []
            for r in runs:
                scores = ((rank_ or {}).get("scores") or {}).get(r["variant"]) or (pair or {}).get(r["variant"])
                media_ = "<video src='{}' controls loop playsinline preload='metadata'></video>".format(escape(r["file"])) if r.get("file") \
                    else "<div class='none'>{}</div>".format(escape(r.get("error") or "not rendered"))
                cells.append("<div class='cell'><b>{}</b>{}<p class='meta'>{}{}</p><details><summary>prompt ({} words)</summary><pre>{}</pre></details></div>".format(
                    escape(r["variant"]), media_, " · ".join("{} {}".format(k, s) for k, s in (scores or {}).items()),
                    " · {} s to render".format(r["seconds"]) if r.get("seconds") else "", len((r.get("prompt") or "").split()), escape(r.get("prompt") or "")))
            parts.append("<h3>{}</h3><p>{}</p>{}<div class='grid'>{}</div>".format(escape(case), escape(runs[0].get("idea") or ""), said, "".join(cells)))
    (out / "report.html").write_text("""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video models</title><style>
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd;--code:#f5f5f3}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--muted:#999;--line:#333;--code:#1e1e1e}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:16px;max-width:1600px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;margin-bottom:28px}
video{width:100%;border-radius:6px;background:#000}pre{white-space:pre-wrap;background:var(--code);padding:10px;border-radius:6px;font-size:12px}
.meta{color:var(--muted);font-size:13px;margin:6px 0}.none{padding:40px;color:var(--muted)}.win{font-size:14px}h2{border-top:1px solid var(--line);padding-top:16px}
</style><h1>Video models, settings and prompts</h1><p>Same seed for every variant of a case. Ranked blind by Opus from frames; it cannot hear, so lips are judged by eye.</p>
""" + "\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
