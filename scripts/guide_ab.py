"""Today's prompt changes (4 November) on the render PC: each case's prompt is written by the agent's model twice, with
this morning's words ("before") and today's ("after"), rendered with one seed, and ranked blind by Opus from frames.
The dialogue clips are transcribed to check the words H3 speaks; the one-man clips are asked how many people they show.

Cases: talking (P7: Talking Head had no guide), dialogue (P3: one way to write speech), one-man (P2: two pictures of one
person). Resumable: what is done is kept in OUT/runs.json."""

import asyncio
import contextlib
import json
import sys
import wave
from pathlib import Path

ROOT = Path(r"C:\Scene\Scene.ai")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import prompt_ab as ab  # noqa: E402
import video_ab as vab  # noqa: E402
from scene import agent, camera, catalog, claude, prompters  # noqa: E402
from scene.comfy import client, workflows  # noqa: E402

OUT = Path("C:/Scene/prompt-ab/guides-2026-11-04")
FISHERMAN = Path("C:/Scene/prompt-ab/models/portrait@flux2_dev/new.png")
VOICE = Path("C:/Scene/prompt-ab/video/inputs/voice_clean.wav")
LINES = ("Garam hai, dhyan se.", "Shukriya, bhaiya.")
SEED = 4112026

# Today's words -> this morning's, so "before" is the agent as it was.
SYSTEM_BACK = [
    ("if it matters.\n  Inside a skill's run, complete means all its plan decided and nothing it did not: no person, prop, light, move or\n"
     "  line the plan has no word for (its prompter writes only from its inputs). Outside a run, fill in what the user left\n"
     "  open. A workflow with a \"prompt_guide\"",
     "if it matters.\n  A workflow with a \"prompt_guide\""),
    ("When\n  someone speaks, write their exact words in quotation marks, as the user gave them, tied to who says them (Maya says:\n"
     "  \"We are late.\"), where the workflow's guide puts the sound (a guide whose voice file carries the words, as Talking\n"
     "  Head's, leaves them out), and give the shot the time they need.",
     "When\n  someone speaks, write their exact words in the prompt in quotation marks after \"Audio:\", as the user gave them, and\n"
     "  give the shot the time they need."),
]
GUIDE_BACK = [
    ("a voice \"the voice of the main character only\"; a motion video \"camera movement and pacing only\", never its people,\n"
     "place or look. Two pictures of one person (H3 All in One's \"same person, other angle\", a sheet and a close face) are\n"
     "one line: \"both pictures show the main character, one person\"; one person's pictures never make two people. A frame\n"
     "taken from a clip is never a person's reference: their identity comes from their sheet or portrait. Never name a\n"
     "reference the step does not fill.",
     "a voice \"the voice of the main character only\". Never name a reference the step does not fill."),
    ("nobody else's lips move\". The track is used as recorded, word for word (\"Use the voice track exactly as recorded.\"\n"
     "  in LOCKS), and no voice sample goes beside it: the recording's voice is the voice.",
     "nobody else's lips move\"."),
]
HINT_BACK = ("For speech write who says what, in quotes, in the beat it is said: the old man says: \"Sign here.\" With a VOICE TRACK",
             "For speech put the words in quotes after \"Audio:\", tied to the speaker. With a VOICE TRACK")

ATTACHED = {
    "fisherman": {"kind": "image", "name": "fisherman portrait", "shows": "An old fisherman with a white beard on a pier at dawn, portrait."},
    "fisherman_side": {"kind": "image", "name": "fisherman side view",
                       "shows": "The same old fisherman with a white beard, seen from his left side, on the pier at dawn."},
    "voice": {"kind": "audio", "name": "chai seller's line", "transcript": "Garam hai, dhyan se."},
}
H3 = "video/h3_all_in_one"
CASES = [   # case, workflow, the user's message, attached, refs {slot or role: input}, options, seconds
    ("talking", "video/talking_head_narration", "@1 says the words of @2 warmly, straight to camera, with small natural nods.",
     ["fisherman", "voice"], {"2:image": "fisherman", "3:audio": "voice"}, {"engine": "h3"}, None),
    ("dialogue", H3, "A chai seller at a roadside stall hands a cup of chai to a young woman and says \"Garam hai, dhyan se.\" "
                     "She smiles and says \"Shukriya, bhaiya.\" For a reel.", [], {}, {"quality": "medium"}, 7),
    ("one-man", H3, "The old fisherman of @1 and @2 (the same man, from the side) mends a fishing net on the pier at dawn, then "
                    "looks up at the sea.", ["fisherman", "fisherman_side"], {"character 1": "fisherman", "same person": "fisherman_side"},
     {"engine": "reference", "quality": "medium"}, 6),
]
PEOPLE = """You look at frames of one video clip, in order. Say how many different people appear in it, and whether one
and the same man is shown throughout (the same face, beard and clothes), in one short sentence of what you see."""
PEOPLE_SHAPE = {"type": "object", "required": ["people", "same_man_throughout", "seen"], "properties": {
    "people": {"type": "integer"}, "same_man_throughout": {"type": "boolean"}, "seen": {"type": "string"}}}


def swap(text, pairs):
    for now, then in pairs:
        assert now in text, "today's text is not where this script expects it: " + now[:60]
        text = text.replace(now, then)
    return text


def deep_swap(value, pair):
    if isinstance(value, str):
        return value.replace(*pair)
    if isinstance(value, list):
        return [deep_swap(v, pair) for v in value]
    if isinstance(value, dict):
        return {k: deep_swap(v, pair) for k, v in value.items()}
    return value


@contextlib.contextmanager
def before_guides():
    """The prompt guides as they were this morning: no Talking Head guide, the H3 guide without today's lines."""
    real = prompters.load

    def load(folder=prompters.FOLDER):
        return [dict(g, text=swap(g["text"], GUIDE_BACK)) if g["id"] == "minimax-h3" else g for g in real(folder) if g["id"] != "talking-head"]
    prompters.load = load
    try:
        yield
    finally:
        prompters.load = real


async def write(service, version, wid, schema, idea, given):
    selection = [dict(ATTACHED[g], tag="@{}".format(n), id=900 + n) for n, g in enumerate(given, start=1)]
    guide = agent.STRUCTURE_GUIDE.format(structure=agent.PROMPT_STRUCTURE)
    with before_guides() if version == "before" else contextlib.nullcontext():
        offer = agent.offer(schema)
        system = agent.system()
        if version == "before":
            offer, system = deep_swap(offer, HINT_BACK), swap(system, SYSTEM_BACK)
        message = agent.question(idea, [offer], selection, wid, guides=guide)
    text, _, _ = await claude.ask(service, ab.MODEL, [{"role": "system", "content": system}, {"role": "user", "content": message}],
                                  agent.reply_format([wid]))
    answer = json.loads(text)
    step = next((s for s in answer["steps"] if s.get("tool") == "generate"), None)
    if step is None:
        raise ab.NoStep("the agent planned nothing: " + " ".join(str(answer.get("reply") or "").split())[:300])
    return camera.apply(step.get("prompt"), camera.clean(step), "video")


async def free(comfy):
    """Wait until ComfyUI runs and holds nothing (another job, the studio's users), at most 15 minutes."""
    for _ in range(45):
        state = await comfy.queue_state()
        if not state["running"] and not state["pending"]:
            return
        print("ComfyUI is busy ({} running, {} waiting): waiting".format(state["running"], state["pending"]), flush=True)
        await asyncio.sleep(20)
    raise SystemExit("ComfyUI stayed busy for 15 minutes: stopped without queueing")


async def transcribe(comfy, shelf, clip):
    wav = clip.with_suffix(".wav")
    vab.ffmpeg("-i", clip, "-vn", "-ac", "1", "-ar", "16000", wav)
    name = await comfy.upload("scene_ab_" + wav.name, wav.read_bytes(), "audio/wav")
    wf = await shelf.load("audio/audio_transcribe")
    slot = next(r["id"] for r in workflows.describe(wf)["refs"] if r["kind"] == "audio")
    graph, _ = workflows.build_prompt(wf, {"values": {}, "options": {}, "refs": {slot: {"comfy_name": name}}, "name": "ab transcribe"})
    await free(comfy)
    entry = await vab.run_graph(comfy, graph)
    texts = []
    for node in (entry.get("outputs") or {}).values():
        for items in node.values():
            for item in items if isinstance(items, list) else []:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict) and str(item.get("filename", "")).lower().endswith((".txt", ".json", ".srt", ".vtt")):
                    response = await comfy.view(item["filename"], item.get("subfolder", ""))
                    try:
                        response.raise_for_status()
                        texts.append((await response.aread()).decode("utf-8", "replace"))
                    finally:
                        await response.aclose()
    return "\n".join(texts)[:3000]


async def main():
    swap(agent.system(), SYSTEM_BACK)   # every "before" swap finds its text, before anything is rendered
    with before_guides():
        prompters.load()
    sidecar = (ROOT / "workflows/video/h3_all_in_one.studio.json").read_text(encoding="utf-8").replace('\\"', '"')
    assert HINT_BACK[0] in sidecar, "H3 All in One's speech hint changed"
    if "--check" in sys.argv:
        print("swaps ok")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    service = claude.service(config.get("claude_models") or ab.MODEL)
    comfy = client.Comfy(lambda: config["comfy_url"])
    shelf = catalog.Catalog(ROOT / "workflows", comfy)
    kept = OUT / "runs.json"
    state = json.loads(kept.read_text(encoding="utf-8")) if kept.is_file() else {}

    def store():
        kept.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")

    await free(comfy)
    uploaded = {"fisherman": await comfy.upload("scene_ab_fisherman.png", FISHERMAN.read_bytes(), "image/png"),
                "voice": await comfy.upload("scene_ab_voice_clean.wav", VOICE.read_bytes(), "audio/wav")}
    side = OUT / "fisherman_side.png"
    if not side.is_file():   # the second picture of the same man, made from the first on FLUX.2 dev
        wf = await shelf.load("image/image_t2i_flux2_dev")
        schema = workflows.describe(wf)
        prompt_id = next(c["id"] for c in schema["controls"] if c["role"] == "prompt")
        settings = {"values": {prompt_id: "The old fisherman of image 1, the same face, white beard, age and clothes, seen in left "
                               "profile, standing on the same wooden pier at dawn, soft light from the sea, the same photographic "
                               "look as image 1."}, "options": {}, "refs": {"ref_1": {"comfy_name": uploaded["fisherman"]}},
                    "seed_mode": "fixed", "seed": 7, "name": "ab side view"}
        ab.agent.shape_like(schema, settings, (2, 3))
        await free(comfy)
        await ab.render(comfy, wf, settings, OUT / "fisherman_side")
    uploaded["fisherman_side"] = await comfy.upload("scene_ab_fisherman_side.png", side.read_bytes(), "image/png")
    with wave.open(str(VOICE)) as w:
        voice_seconds = round(w.getnframes() / w.getframerate(), 1)
    ATTACHED["voice"]["seconds"] = voice_seconds

    for case, wid, idea, given, refs, options, seconds in CASES:
        wf = await shelf.load(wid)
        schema = workflows.describe(wf)
        slots = {}
        for want, source in refs.items():
            slot = want if ":" in want else next((r["id"] for r in schema["refs"] if want in r["label"].lower()), None)
            if slot is None:
                raise SystemExit("{}: no slot labelled {!r}; its slots: {}".format(wid, want, [(r["id"], r["label"]) for r in schema["refs"]]))
            slots[slot] = source
        done = state.setdefault(case, {"idea": idea, "workflow": wid, "runs": {}})
        for version in ("before", "after"):
            run = done["runs"].setdefault(version, {})
            if not run.get("prompt"):
                run["prompt"] = await write(service, version, wid, schema, idea, given)
                store()
                print("{} / {}: prompt written ({} words)".format(case, version, len(run["prompt"].split())), flush=True)
            if not run.get("file"):
                spec = {"options": options, "refs": slots, "resolution": 480, "duration": seconds or voice_seconds}
                settings = vab.settings_for(schema, run["prompt"], spec, SEED, uploaded, "ab {} {}".format(case, version))
                await free(comfy)
                name, took = await ab.render(comfy, wf, settings, OUT / "{}_{}".format(case, version))
                run.update(file=name, seconds=took)
                store()
                print("{} / {}: rendered in {} s".format(case, version, took), flush=True)
            if case == "dialogue" and "heard" not in run:
                run["heard"] = await transcribe(comfy, shelf, OUT / run["file"])
                store()
            if case == "one-man" and "people" not in run:
                shots = await vab.frames_of(OUT / run["file"])
                text, _, _ = await claude.ask(service, ab.JUDGE, [{"role": "system", "content": PEOPLE}, {"role": "user", "content":
                                              "The frames of the clip, in order. How many people are in it?"}], PEOPLE_SHAPE, images=shots)
                run["people"] = json.loads(text)
                store()
        if "rank" not in done:
            ranked = [dict(r, variant=v, idea=idea) for v, r in done["runs"].items()]
            done["rank"] = await vab.rank(service, OUT, "guides", case, ranked)
            store()
            print("{}: ranked {}".format(case, done["rank"]["order"]), flush=True)
    print("done:", kept)


asyncio.run(main())
