"""P5 on the render PC (4 November): v2's character sheet prompt with its "No ..." words, as written, against the same
prompt without them, on FLUX.2 dev (two seeds); and on Qwen Image the words in the prompt against the same words in
its negative prompt. Each pair is judged blind by Opus. Resumable: OUT/runs.json."""

import asyncio
import base64
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Scene\Scene.ai")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import prompt_ab as ab  # noqa: E402
from scene import agent, catalog, claude, media  # noqa: E402
from scene.comfy import client, workflows  # noqa: E402

OUT = Path("C:/Scene/prompt-ab/sheet-no-words-2026-11-04")
LOOK = ("Meera, a woman of about thirty, slim, with warm brown skin, a long black braid over her right shoulder, a small "
        "gold nose ring, a mustard-yellow cotton kurta with a white dupatta, silver bangles on her left wrist and brown "
        "leather kolhapuri sandals")
LAYOUT = ("three panels side by side: full body front framed from the chin down, head out of frame · full body back, same "
          "framing · head-and-shoulders close-up, front, eyes to camera. The close-up is the only face on the sheet")
WITH = (   # v2's character sheet prompt, filled, every word as written
    "Character reference sheet, 16:9, one seamless mid-grey studio backdrop: {layout}.\n"
    "{look}. Same face, same outfit, same proportions in every view. Hair neatly styled, no frizzy flyaway strands.\n"
    "Lighting: a large soft key from front-left at head height, a soft fill from the right one stop under, a gentle top light "
    "separating the subject from the backdrop; soft shallow shadows, no blown highlights.\n"
    "Visible pores and fine skin texture, no airbrushing; individual hair strands; real fabric weave, seams and wear; hide, "
    "scale, metal and stone with real surface detail; natural single-exposure contrast, not HDR.\n"
    "No plastic waxy skin, no CGI sheen, no text, labels, arrows or panel borders, no extra views, no people beyond the views named."
).format(layout=LAYOUT, look=LOOK)
NO_WORDS = [", no frizzy flyaway strands", ", no blown highlights", ", no airbrushing", ", not HDR",
            "\nNo plastic waxy skin, no CGI sheen, no text, labels, arrows or panel borders, no extra views, no people beyond the views named."]
WITHOUT = WITH
for words in NO_WORDS:
    assert words in WITHOUT
    WITHOUT = WITHOUT.replace(words, "")
NEGATIVE = ("frizzy flyaway strands, blown highlights, airbrushing, HDR, plastic waxy skin, CGI sheen, text, labels, arrows, "
            "panel borders, extra views, people beyond the views named")
RUNS = [   # name, workflow, seed, variants: {variant: (prompt, negative or None)}
    ("flux2-seed1", "image/image_t2i_flux2_dev", 11, {"with": (WITH, None), "without": (WITHOUT, None)}),
    ("flux2-seed2", "image/image_t2i_flux2_dev", 22, {"with": (WITH, None), "without": (WITHOUT, None)}),
    ("qwen", "image/image_t2i_qwen_image_21", 11, {"in-prompt": (WITH, None), "in-negative": (WITHOUT, NEGATIVE)}),
]
JUDGE = """You judge character reference sheets made for an AI film studio from the same request. You are not told how
each was made. The request asked for: {layout}; of {look}; on one seamless mid-grey studio backdrop; real skin and fabric
texture, nothing plastic, waxy or CGI-looking; no text, labels, arrows or panel borders; no extra views and no other people.
Score each picture from 1 to 5 on: "layout" (exactly the three views asked, framed as asked), "realism" (real skin, hair and
fabric, no plastic or CGI sheen, no airbrushing), "clean" (no text, labels, arrows, borders, extra views or people),
"match" (the look asked, the same in every view). Then say which is better as a reference for every later shot of
this character, and why, in two plain sentences."""
SHAPE = {"type": "object", "required": ["scores", "better", "why"], "properties": {
    "scores": {"type": "array", "items": {"type": "object", "required": ["picture", "layout", "realism", "clean", "match"], "properties": {
        "picture": {"type": "integer"}, **{k: {"type": "integer", "minimum": 1, "maximum": 5} for k in ("layout", "realism", "clean", "match")}}}},
    "better": {"type": "integer"}, "why": {"type": "string"}}}


def jpeg(path):
    """The picture as a 1280-pixel-wide JPEG, base64: big enough to judge skin and fabric texture."""
    target = path.with_name(path.stem + "_judge.jpg")
    subprocess.run([media.ffmpeg_path(), "-loglevel", "error", "-y", "-i", str(path), "-vf", "scale=1280:-2", "-q:v", "3", str(target)],
                   check=True)
    return base64.b64encode(target.read_bytes()).decode("ascii")


async def free(comfy):
    for _ in range(45):
        state = await comfy.queue_state()
        if not state["running"] and not state["pending"]:
            return
        print("ComfyUI is busy ({} running, {} waiting): waiting".format(state["running"], state["pending"]), flush=True)
        await asyncio.sleep(20)
    raise SystemExit("ComfyUI stayed busy for 15 minutes: stopped without queueing")


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    service = claude.service(config.get("claude_models") or ab.MODEL)
    comfy = client.Comfy(lambda: config["comfy_url"])
    shelf = catalog.Catalog(ROOT / "workflows", comfy)
    kept = OUT / "runs.json"
    state = json.loads(kept.read_text(encoding="utf-8")) if kept.is_file() else {}

    def store():
        kept.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    for name, wid, seed, variants in RUNS:
        wf = await shelf.load(wid)
        schema = workflows.describe(wf)
        prompt_id = next(c["id"] for c in schema["controls"] if c["role"] == "prompt")
        negative_id = next((c["id"] for c in schema["controls"] if "negative" in str(c.get("label") or c["id"]).lower()), None)
        done = state.setdefault(name, {"workflow": wid, "seed": seed, "runs": {}})
        for variant, (prompt, negative) in variants.items():
            run = done["runs"].setdefault(variant, {"prompt": prompt, "negative": negative})
            if run.get("file"):
                continue
            values = {prompt_id: prompt}
            if negative is not None:
                if negative_id is None:
                    raise SystemExit("{} has no negative prompt control: {}".format(wid, [(c["id"], c.get("label")) for c in schema["controls"]]))
                values[negative_id] = negative
            settings = {"values": values, "options": {}, "refs": {}, "seed_mode": "fixed", "seed": seed, "name": "ab sheet " + variant}
            agent.shape_like(schema, settings, (16, 9))
            await free(comfy)
            file, took = await ab.render(comfy, wf, settings, OUT / "{}_{}".format(name, variant))
            run.update(file=file, seconds=took)
            store()
            print("{} / {}: rendered in {} s".format(name, variant, took), flush=True)
        if "judged" not in done:
            order = list(done["runs"])
            random.shuffle(order)
            pictures = [jpeg(OUT / done["runs"][v]["file"]) for v in order]
            text, _, _ = await claude.ask(service, ab.JUDGE, [{"role": "system", "content": JUDGE.format(layout=LAYOUT, look=LOOK)},
                                                              {"role": "user", "content": "Picture 1 and Picture 2. Judge both."}],
                                          SHAPE, images=pictures)
            said = json.loads(text)
            variant_of = {n: v for n, v in enumerate(order, start=1)}
            done["judged"] = {"better": variant_of.get(said["better"]), "why": said["why"],
                              "scores": {variant_of[s["picture"]]: {k: s[k] for k in ("layout", "realism", "clean", "match")}
                                         for s in said["scores"] if s["picture"] in variant_of}}
            store()
            print("{}: better = {} ({})".format(name, done["judged"]["better"], said["why"]), flush=True)
    print("done:", kept)


asyncio.run(main())
