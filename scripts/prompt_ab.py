"""Old prompts against new: the same shots, prompted by the agent's model with the instructions it had before the
model guides (prompters/) and with the ones it has now, rendered on the render PC with the same seed, size and length.

    .venv/Scripts/python.exe scripts/prompt_ab.py [out folder] [--only=case,case] [--prompts-only] [--judge]

The old instructions are the agent's own text with the guide changes taken back out (OLD below), so nothing else
differs. Writes <out>/<case>/old.* and new.*, prompts.json, and report.html to compare them side by side. Free of
credits: it talks to ComfyUI directly, not through the studio's queue (the studio need not be running).

--judge: once both are rendered, each result gets the studio's own review against what the user asked (not against
either prompt, so neither is favoured), and a stronger model compares the two blind, in a random order.

--image-models: every picture model instead (IMAGE_MODELS), on the picture cases and a poster with words in it, old and
new on each, one seed per case on every model; with --judge, old against new per model, and the models of each case
ranked blind. Writes <out>/report.html (default prompt-ab-models/)."""

import asyncio
import json
import random
import re
import sys
import time
import uuid
import zlib
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from scene import agent, camera, catalog, claude, review  # noqa: E402
from scene.comfy import client, workflows  # noqa: E402

MODEL = "sonnet"   # the studio's first Claude model (claude_models in config.json)
JUDGE = "opus"     # the blind comparison: the strongest model offered
COMPARE = """You judge two results made for the same request at Scene.ai, an AI image and video studio, the way a film
director picks between takes. You are shown the request, then the pictures of result A and of result B (a picture is
itself; a clip is frames in order). They were made from different prompts with the same model and seed; you are not
told which is which. Score each from 1 to 5 on: "asked" (it shows what the request asked for: the subject, the action,
the place), "craft" (framing, light, composition, a look a viewer would call cinematic), "clean" (no broken hands or
faces, no melting, no garbled text, nothing cut off), and for a clip "motion" (natural movement, no jumps or morphing;
3 for a picture). Then say which is better overall ("A", "B" or "same") and why, in one or two plain sentences."""
REVIEW_SHAPE = {"type": "object", "required": ["checks", "problem", "fix"], "properties": {   # as Agent.review asks
    "checks": {"type": "array", "items": {"type": "object", "required": ["check", "level", "note"], "properties": {
        "check": {"type": "string", "enum": ["who", "what", "clean", "coherence", "continuity"]},
        "level": {"type": "string", "enum": ["fine", "minor", "major"]}, "note": {"type": "string"}}}},
    "problem": {"type": "string"}, "fix": {"type": "object", "required": ["prompt", "start_from_previous", "why"], "properties": {
        "prompt": {"type": "string"}, "start_from_previous": {"type": "boolean"}, "why": {"type": "string"}}}}}
COMPARE_SHAPE = {"type": "object", "required": ["A", "B", "better", "why"], "properties": {
    **{side: {"type": "object", "required": ["asked", "craft", "clean", "motion"], "properties": {
        k: {"type": "integer", "minimum": 1, "maximum": 5} for k in ("asked", "craft", "clean", "motion")}} for side in "AB"},
    "better": {"type": "string", "enum": ["A", "B", "same"]}, "why": {"type": "string"}}}

# (case, workflow, what the user asks, fixed settings both versions get)
CASES = [
    ("portrait", "image/image_t2i_flux2_klein_9b", "An old fisherman mending his net on a wooden pier at dawn, for a poster.",
     {"orientation": "portrait"}),
    ("product", "image/image_t2i_qwen_image_21", "A product photo of a glass perfume bottle on wet black stone with orange petals, for an Instagram post.",
     {"orientation": "square"}),
    ("market", "image/image_t2i_flux2_klein_9b", "A rainy night market in Mumbai, wide and cinematic, for a YouTube thumbnail.",
     {"orientation": "landscape"}),
    ("corridor", "video/h3_all_in_one", "A young woman in a green saree walks down a sunlit corridor of an old haveli and glances back over her shoulder.",
     {"orientation": "landscape", "resolution": 480, "duration": 6}),
    ("chai", "video/h3_all_in_one", "A chai seller at a roadside stall hands a cup to a customer and says \"Garam hai, dhyan se.\"",
     {"orientation": "landscape", "resolution": 480, "duration": 6}),
    ("football", "video/h3_all_in_one", "A boy kicks a football against a wall in a narrow lane; it bounces back and he traps it under his foot.",
     {"orientation": "landscape", "resolution": 480, "duration": 6}),
    ("beach-dog", "video/video_ltx2_5_t2v", "A wet golden retriever shakes off water on a beach at sunset.",
     {"orientation": "landscape", "duration": 5}),
]

# The agent's instructions before the model guides: (what it says now, what it said then).
OLD = [
    ("""- Write each "prompt" as a concrete, complete shot: subject, action, setting, camera, light, and sound if it matters.
  A workflow with a "prompt_guide" is written in that guide's structure and at its length (see "Prompt guides"): a
  full prompt in the model's own structure gives a far better result than a sentence or two, so never cut one short.
  A workflow's "prompt_tips" add to its guide: follow both in every prompt for it.""",
     """- Write each "prompt" as a concrete shot: subject, action, setting, camera, light, and sound if it matters. One to three
  sentences. A workflow's "prompt_tips" say how its model wants prompts written: follow them in every prompt for it."""),
    ("""They are turned into words in the prompt for you; a guide that times the shot
  beat by beat still says the camera in its beats (words already in the prompt are not added twice). Open""",
     """They are turned into words in the prompt for you, so do not repeat them there. Open"""),
    ("""defaults; the prompts are cut short here to show the shape: write yours in full, as the workflow's prompt guide says):""",
     """defaults):"""),
    ("""- Never use "generate" to edit a video the user already has, or to show readable words in a video (a picture may have
  a few, see "What the studio does").""",
     """- Never use "generate" to edit a video the user already has, or to show readable words."""),
    ("""- Pictures from words, in the image workflows listed, with a few readable words in them when asked (a sign, a title,
  a label, a poster's lines): each word written out in quotation marks in the prompt, with where it sits and its
  lettering ("a wooden sign that reads "CHAI 10" in large red painted letters"). Short lines only; a paragraph of
  text, or words in a video, go on screen with "motion" instead.""",
     """- Pictures from words, in the image workflows listed."""),
    ("""  readable words inside a generated video. When asked for one, say plainly it is not here yet and offer the nearest
  thing the studio does (words on screen with "motion" instead of text in a video; a new picture from words instead
  of an edit).""",
     """  readable words inside a generated picture. When asked for one, say plainly it
  is not here yet and offer the nearest thing the studio does (words on screen with "motion" instead of text in a
  picture; a new picture from words instead of an edit)."""),
]
OLD_GUIDE_END = "nothing in this shot. This structure wins over any other advice on how to lay out a prompt."
OLD_TIP_CHARS = 220


def old_system():
    text = agent.system()
    for now, then in OLD:
        assert now in text, "the agent's text changed: update OLD in this script"
        text = text.replace(now, then)
    return text


def old_guide():
    new = agent.STRUCTURE_GUIDE
    start = new.index("nothing in this shot.")
    end = new.index("<<<")
    return (new[:start] + OLD_GUIDE_END + "\n" + new[end:]).format(structure=agent.PROMPT_STRUCTURE)


def old_offer(offer):
    offer = {k: v for k, v in offer.items() if k != "prompt_guide"}
    if offer.get("prompt_tips"):
        offer["prompt_tips"] = [t[:OLD_TIP_CHARS] for t in offer["prompt_tips"]]
    return offer


async def write_prompt(service, version, wid, schema, idea):
    """The step the agent's model plans for one idea, with the old or the new instructions."""
    offer = agent.offer(schema)
    if version == "old":
        system, guide, offer = old_system(), old_guide(), old_offer(offer)
    else:
        system, guide = agent.system(), agent.STRUCTURE_GUIDE.format(structure=agent.PROMPT_STRUCTURE)
    message = agent.question(idea, [offer], [], wid, guides=guide)
    text, _, _ = await claude.ask(service, MODEL, [{"role": "system", "content": system}, {"role": "user", "content": message}],
                                  agent.reply_format([wid]))
    answer = json.loads(text)
    step = next((s for s in answer["steps"] if s.get("tool") == "generate"), None)
    if step is None:   # it planned no picture (the old agent said a picture could not have words): that is a result too
        raise NoStep("the agent planned nothing: " + " ".join(str(answer.get("reply") or "").split())[:300])
    return dict(step, prompt=camera.apply(step.get("prompt"), camera.clean(step), wid.split("/", 1)[0]))


class NoStep(Exception):
    pass


def settings_of(schema, steps, version, fixed, seed):
    """The job settings of one version: the new step's settings for both (quality, shape, length, seed), so the prompt
    is the only thing that differs."""
    base = steps.get("new") or steps["old"]
    settings, _ = agent.settings_for(schema, dict(base, **{k: v for k, v in fixed.items() if k != "duration"},
                                                         duration=fixed.get("duration", base.get("duration"))), [], None)
    prompt_id = next(c["id"] for c in schema["controls"] if c["role"] == "prompt")
    settings["values"][prompt_id] = steps[version]["prompt"][:4000]
    settings.update(seed_mode="fixed", seed=seed)
    return settings


async def render(comfy, wf, settings, target_stem):
    graph, ctx = workflows.build_prompt(wf, settings)
    prompt_id = await comfy.queue(graph, uuid.uuid4().hex)
    started = time.time()
    while True:
        await asyncio.sleep(3)
        found = await comfy.history(prompt_id)
        status = (found or {}).get("status", {})
        if status.get("status_str") == "error":
            raise client.ComfyError(json.dumps(status.get("messages"))[:600])
        if status.get("completed"):
            break
    saved = []
    for node_output in (found.get("outputs") or {}).values():
        for items in node_output.values():
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict) and item.get("type") == "output" and item.get("filename"):
                    suffix = Path(item["filename"]).suffix.lower()
                    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov"):
                        saved.append((item, suffix))
    if not saved:
        raise client.ComfyError("the run saved no picture or video")
    item, suffix = saved[-1]
    target = target_stem.with_suffix(suffix)
    response = await comfy.view(item["filename"], item.get("subfolder", ""))
    try:
        response.raise_for_status()
        target.write_bytes(await response.aread())
    finally:
        await response.aclose()
    return target.name, round(time.time() - started)


def words(text):
    return len(re.findall(r"\S+", text or ""))


async def judge(service, out, r, reviews=True):
    """The studio's review of each result against what the user asked, and the blind comparison of the two."""
    kind = r["workflow"].split("/", 1)[0]
    frames = {}
    for v in ("old", "new"):
        frames[v] = await review.result_frames(out / r["case"] / r[v]["file"], kind)
        if reviews and not r[v].get("review"):
            named = "\n".join("Picture {}: {}".format(n, label) for n, (label, _) in enumerate(frames[v], start=1))
            text, _, _ = await claude.ask(service, MODEL, [{"role": "system", "content": agent.REVIEW}, {"role": "user", "content":
                "The {} was made for this request:\n{}\n\nThe pictures, in order:\n{}\n\nReview it.".format(
                    "clip" if kind == "video" else "picture", r["idea"], named)}], REVIEW_SHAPE, images=[b for _, b in frames[v]])
            r[v]["review"] = review.verdict_from(json.loads(text))
    if not r.get("compare"):
        order = random.sample(["old", "new"], 2)   # which version is A
        labels = ["A: " + label for label, _ in frames[order[0]]] + ["B: " + label for label, _ in frames[order[1]]]
        named = "\n".join("Picture {}: {}".format(n, label) for n, label in enumerate(labels, start=1))
        text, _, _ = await claude.ask(service, JUDGE, [{"role": "system", "content": COMPARE}, {"role": "user", "content":
            "The request:\n{}\n\nThe pictures, in order:\n{}\n\nJudge them.".format(r["idea"], named)}], COMPARE_SHAPE,
            images=[b for _, b in frames[order[0]]] + [b for _, b in frames[order[1]]])
        said = json.loads(text)
        r["compare"] = {"old": said[{order[0]: "A", order[1]: "B"}["old"]], "new": said[{order[0]: "A", order[1]: "B"}["new"]],
                        "better": {"A": order[0], "B": order[1], "same": "same"}[said["better"]], "why": said["why"], "a_was": order[0]}


def report(out, results):
    rows = []
    for r in results:
        cells = []
        for v in ("old", "new"):
            got = r.get(v) or {}
            media = got.get("file")
            shown = ("<video src='{0}/{1}' controls loop muted playsinline></video>" if media and media.endswith((".mp4", ".webm", ".mov"))
                     else "<img src='{0}/{1}' loading='lazy'>" if media else "<div class='none'>{2}</div>").format(
                escape(r["case"]), escape(media or ""), escape(got.get("error") or "not rendered"))
            scores = (r.get("compare") or {}).get(v)
            judged = "<p class='verdict'>{}{}</p>".format(
                escape(review.summary(got["review"])) if got.get("review") else "",
                " · asked {asked}, craft {craft}, clean {clean}, motion {motion}".format(**scores) if scores else "")
            cells.append("<td>{}{}<p class='meta'>{} words · {}</p><pre>{}</pre></td>".format(
                shown, judged, words(got.get("prompt")), "{} s".format(got["seconds"]) if got.get("seconds") else "", escape(got.get("prompt") or "")))
        compare = r.get("compare")
        said = "<p class='win'>Blind pick: <b>{}</b> — {}</p>".format(
            {"old": "old", "new": "new", "same": "same"}[compare["better"]], escape(compare["why"])) if compare else ""
        rows.append("<tr><th colspan='2'>{} <span>{} · seed {}</span><p>{}</p>{}</th></tr><tr>{}</tr>".format(
            escape(r["case"]), escape(r["workflow"]), r["seed"], escape(r["idea"]), said, "".join(cells)))
    (out / "report.html").write_text("""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prompt A/B</title><style>
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd;--code:#f5f5f3}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--muted:#999;--line:#333;--code:#1e1e1e}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:16px}
table{width:100%;border-collapse:collapse;table-layout:fixed}td,th{vertical-align:top;padding:12px;border-bottom:1px solid var(--line)}
th{text-align:left;font-size:18px;padding-top:28px}th span{font-weight:400;color:var(--muted);font-size:13px;margin-left:8px}
th p{font-weight:400;font-size:14px;margin:4px 0 0}img,video{width:100%;border-radius:6px;background:#000}
pre{white-space:pre-wrap;background:var(--code);padding:10px;border-radius:6px;font-size:12.5px;max-height:320px;overflow:auto}
.meta{color:var(--muted);font-size:13px;margin:6px 0}.verdict{font-size:13px;margin:6px 0}.win{font-size:14px;font-weight:400}.head td{font-weight:600;border:0;padding-bottom:0}.none{padding:40px;color:var(--muted)}
@media (max-width:700px){td{display:block;width:auto}}
</style><h1>Prompt A/B: old instructions vs model guides</h1><table><tr class="head"><td>Old (one to three sentences)</td><td>New (model guide)</td></tr>
""" + "\n".join(rows) + "</table>", encoding="utf-8")


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--only=")), None)
    prompts_only = "--prompts-only" in sys.argv
    out = Path(args[0] if args else ROOT / "prompt-ab")
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    service = claude.service(config.get("claude_models") or MODEL)
    if not service:
        sys.exit("Claude Code is not on this machine: the agent's model can't write the prompts.")
    comfy = client.Comfy(lambda: config["comfy_url"])
    shelf = catalog.Catalog(ROOT / "workflows", comfy)
    kept = out / "prompts.json"
    results = json.loads(kept.read_text(encoding="utf-8")) if kept.is_file() else []
    done = {r["case"]: r for r in results}
    for case, wid, idea, fixed in CASES:
        if only and case not in only:
            continue
        wf = await shelf.load(wid)
        schema = workflows.describe(wf)
        r = done.get(case) or {"case": case, "workflow": wid, "idea": idea, "seed": workflows.new_seed()}
        (out / case).mkdir(exist_ok=True)
        for version in ("old", "new"):
            if not (r.get(version) or {}).get("prompt"):
                print("{} {}: writing the prompt".format(case, version), flush=True)
                step = await write_prompt(service, version, wid, schema, idea)
                r[version] = {"prompt": step["prompt"], "step": step}
        for version in ("old", "new"):
            got = r[version]
            if not prompts_only and not got.get("file"):
                print("{} {}: rendering ({} words)".format(case, version, words(got["prompt"])), flush=True)
                try:
                    settings = settings_of(schema, {v: r[v]["step"] | {"prompt": r[v]["prompt"]} for v in ("old", "new")}, version, fixed, r["seed"])
                    got["file"], got["seconds"] = await render(comfy, wf, settings, out / case / version)
                    got.pop("error", None)
                except Exception as e:   # one failed render is reported, the others go on
                    got["error"] = str(e)[:500]
                    print("  failed: " + got["error"], flush=True)
            done[case] = r
            kept.write_text(json.dumps(list(done.values()), indent=1, ensure_ascii=False), encoding="utf-8")
            report(out, list(done.values()))
        if "--judge" in sys.argv and all((r.get(v) or {}).get("file") for v in ("old", "new")):
            print("{}: judging".format(case), flush=True)
            await judge(service, out, r)
            kept.write_text(json.dumps(list(done.values()), indent=1, ensure_ascii=False), encoding="utf-8")
            report(out, list(done.values()))
    picks = [r["compare"]["better"] for r in done.values() if r.get("compare")]
    if picks:
        print("Blind picks: new {}, old {}, same {}".format(picks.count("new"), picks.count("old"), picks.count("same")))
    print("Report: " + str(out / "report.html"))


# ---------------------------------------------------------------- every picture model, old and new (--image-models)

IMAGE_MODELS = ["image/image_t2i_flux2_dev", "image/image_t2i_flux2_klein_9b", "image/image_t2i_flux3_klein",
                "image/image_t2i_hunyuan_image_21", "image/image_t2i_krea2_turbo", "image/image_t2i_qwen_image_21"]
IMAGE_CASES = [(case, idea, fixed) for case, wid, idea, fixed in CASES if wid.startswith("image/")] + [
    ("poster", 'A film poster for "MONSOON NIGHTS": a woman in a yellow raincoat on a wet Mumbai street at night, the title '
               'at the top and "IN CINEMAS SOON" at the bottom, for an Instagram story.', {"orientation": "portrait"})]
RANK = """You judge pictures made for the same request at Scene.ai, an AI image studio, by different image models with
the same seed. You are not told which model made which. Score each picture from 1 to 5 on: "asked" (it shows what the
request asked for), "craft" (composition, light, a look a client would pay for), "clean" (no broken hands or faces, no
melted objects, nothing cut off) and "text" (when the request asks for words: every word spelled exactly and readable;
5 when it asks for none and no garbled letters show, lower for garbled signs). Then rank them all, best first, and say
in two plain sentences what puts the first ahead and what pulls the last down."""
RANK_SHAPE = {"type": "object", "required": ["scores", "ranking", "why"], "properties": {
    "scores": {"type": "array", "items": {"type": "object", "required": ["picture", "asked", "craft", "clean", "text"], "properties": {
        "picture": {"type": "integer"}, **{k: {"type": "integer", "minimum": 1, "maximum": 5} for k in ("asked", "craft", "clean", "text")}}}},
    "ranking": {"type": "array", "items": {"type": "integer"}}, "why": {"type": "string"}}}


def short(wid):
    return wid.split("_t2i_", 1)[1]


def thumb(path):
    """A small JPEG beside a picture, for the report (the PNGs are several MB each)."""
    import subprocess
    from scene import media
    small = path.with_name(path.stem + "_small.jpg")
    if not small.is_file():
        subprocess.run([media.ffmpeg_path(), "-loglevel", "error", "-y", "-i", str(path), "-vf", "scale=960:-2", "-q:v", "3", str(small)], check=True)
    return small.name


async def models_mode(out, service, comfy, shelf):
    out.mkdir(parents=True, exist_ok=True)
    kept = out / "prompts.json"
    done = {r["case"]: r for r in (json.loads(kept.read_text(encoding="utf-8")) if kept.is_file() else [])}
    ranks = done.pop("_ranks", {}).get("ranks", {}) if "_ranks" in done else {}

    def save():
        kept.write_text(json.dumps([*done.values(), {"case": "_ranks", "ranks": ranks}], indent=1, ensure_ascii=False), encoding="utf-8")
        models_report(out, done, ranks)
    loaded = {}
    for wid in IMAGE_MODELS:
        wf = await shelf.load(wid)
        loaded[wid] = (wf, workflows.describe(wf))
    for case, idea, fixed in IMAGE_CASES:
        for wid in IMAGE_MODELS:
            key = "{}@{}".format(case, short(wid))
            done.setdefault(key, {"case": key, "base": case, "workflow": wid, "idea": idea, "fixed": fixed,
                                  "seed": zlib.crc32(case.encode()) % workflows.SEED_RANGE})   # one seed per case, every model

    async def prompt_for(r, version):
        try:
            step = await write_prompt(service, version, r["workflow"], loaded[r["workflow"]][1], r["idea"])
            r[version] = {"prompt": step["prompt"], "step": step}
        except NoStep as e:
            r[version] = {"prompt": "", "error": str(e)}
        except Exception as e:
            r[version] = {"prompt": "", "error": "writing the prompt failed: " + str(e)[:300]}
    todo = [prompt_for(r, v) for r in done.values() for v in ("old", "new") if not (r.get(v) or {}).get("prompt") and not (r.get(v) or {}).get("error")]
    print("writing {} prompts".format(len(todo)), flush=True)
    await asyncio.gather(*todo)
    save()
    if "--prompts-only" in sys.argv:
        return
    for wid in IMAGE_MODELS:   # grouped by model, so the render PC loads each model once
        wf, schema = loaded[wid]
        for r in [r for r in done.values() if r["workflow"] == wid]:
            steps = {v: dict(r[v]["step"], prompt=r[v]["prompt"]) for v in ("old", "new") if (r.get(v) or {}).get("prompt")}
            for version in steps:
                got = r[version]
                if got.get("file"):
                    continue
                print("{} {}: rendering ({} words)".format(r["case"], version, words(got["prompt"])), flush=True)
                (out / r["case"]).mkdir(exist_ok=True)
                try:
                    got["file"], got["seconds"] = await render(comfy, wf, settings_of(schema, steps, version, r["fixed"], r["seed"]), out / r["case"] / version)
                    got["thumb"] = thumb(out / r["case"] / got["file"])
                    got.pop("error", None)
                except Exception as e:
                    got["error"] = str(e)[:500]
                    print("  failed: " + got["error"], flush=True)
                save()
    if "--judge" not in sys.argv:
        return

    async def pair(r):
        if r.get("compare") or not all((r.get(v) or {}).get("file") for v in ("old", "new")):
            return
        try:
            await judge(service, out, r, reviews=False)
        except Exception as e:
            print("  {} not judged: {}".format(r["case"], str(e)[:200]), flush=True)
    print("judging old against new", flush=True)
    await asyncio.gather(*(pair(r) for r in done.values()))
    save()
    for case, idea, _ in IMAGE_CASES:
        if case in ranks:
            continue
        made = [r for r in done.values() if r["base"] == case and (r.get("new") or {}).get("file")]
        random.shuffle(made)
        pictures = [await review._still(out / r["case"] / r["new"]["file"]) for r in made]
        named = "\n".join("Picture {}".format(n) for n in range(1, len(made) + 1))
        text, _, _ = await claude.ask(service, JUDGE, [{"role": "system", "content": RANK}, {"role": "user", "content":
            "The request:\n{}\n\nThe pictures, in order:\n{}\n\nJudge them.".format(idea, named)}], RANK_SHAPE, images=pictures)
        said = json.loads(text)
        model_of = {n: short(r["workflow"]) for n, r in enumerate(made, start=1)}
        ranks[case] = {"order": [model_of[n] for n in said["ranking"] if n in model_of], "why": said["why"],
                       "scores": {model_of[s["picture"]]: {k: s[k] for k in ("asked", "craft", "clean", "text")} for s in said["scores"] if s["picture"] in model_of}}
        print("{}: {}".format(case, " > ".join(ranks[case]["order"])), flush=True)
        save()


def models_report(out, done, ranks):
    models = [short(w) for w in IMAGE_MODELS]
    rows = []
    tally = {m: {"new": 0, "old": 0, "same": 0, "points": 0, "cases": 0} for m in models}
    for r in done.values():
        c = r.get("compare")
        if c:
            tally[short(r["workflow"])][c["better"]] += 1
    for case, _ in [(c, i) for c, i, _ in IMAGE_CASES]:
        for place, m in enumerate((ranks.get(case) or {}).get("order", [])):
            tally[m]["points"] += len(models) - place
            tally[m]["cases"] += 1
    head = "".join("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
        m, t["new"], t["old"], t["same"], "{:.1f}".format(len(models) + 1 - t["points"] / t["cases"]) if t["cases"] else "")
        for m, t in sorted(tally.items(), key=lambda kv: -kv[1]["points"]))
    for case, idea, _ in IMAGE_CASES:
        rank = ranks.get(case) or {}
        order = rank.get("order") or models
        rows.append("<h2>{}</h2><p>{}</p>{}".format(escape(case), escape(idea),
                    "<p class='win'>Blind ranking: <b>{}</b> — {}</p>".format(escape(" > ".join(rank["order"])), escape(rank["why"])) if rank else ""))
        rows.append("<table><tr class='head'><td>Model</td><td>Old prompt</td><td>New prompt (model guide)</td></tr>")
        for m in order:
            r = done.get("{}@{}".format(case, m)) or {}
            cells = []
            for v in ("old", "new"):
                got = r.get(v) or {}
                shown = "<a href='{0}/{1}'><img src='{0}/{2}' loading='lazy'></a>".format(escape(r["case"]), escape(got["file"]), escape(got.get("thumb") or got["file"])) \
                    if got.get("file") else "<div class='none'>{}</div>".format(escape(got.get("error") or "not rendered"))
                scores = (r.get("compare") or {}).get(v)
                cells.append("<td>{}<p class='meta'>{}{} words · {}</p><details><summary>prompt</summary><pre>{}</pre></details></td>".format(
                    shown, "asked {asked}, craft {craft}, clean {clean} · ".format(**scores) if scores else "", words(got.get("prompt")),
                    "{} s".format(got["seconds"]) if got.get("seconds") else "", escape(got.get("prompt") or "")))
            c = r.get("compare")
            rank_scores = (rank.get("scores") or {}).get(m)
            rows.append("<tr><th>{}{}{}</th>{}</tr>".format(escape(m),
                        "<p class='meta'>ranked {}: asked {asked}, craft {craft}, clean {clean}, text {text}</p>".format(order.index(m) + 1, **rank_scores) if rank_scores else "",
                        "<p class='meta'>old vs new: <b>{}</b><br>{}</p>".format(c["better"], escape(c["why"])) if c else "", "".join(cells)))
        rows.append("</table>")
    (out / "report.html").write_text("""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Picture models</title><style>
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#ddd;--code:#f5f5f3}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--muted:#999;--line:#333;--code:#1e1e1e}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:16px;max-width:1500px}
table{width:100%;border-collapse:collapse;table-layout:fixed;margin-bottom:24px}td,th{vertical-align:top;padding:10px;border-bottom:1px solid var(--line);text-align:left}
th{width:220px;font-size:16px}img{width:100%;border-radius:6px}pre{white-space:pre-wrap;background:var(--code);padding:10px;border-radius:6px;font-size:12.5px}
.meta{color:var(--muted);font-size:13px;margin:6px 0;font-weight:400}.head td{font-weight:600}.none{padding:40px;color:var(--muted)}.win{font-size:14px}
.sum td{text-align:right}.sum td:first-child{text-align:left}
@media (max-width:800px){td,th{display:block;width:auto}}
</style><h1>Picture models: old prompts vs model guides</h1>
<p>Same seed per case on every model; the prompt is the only thing that differs between old and new. Judged blind by Opus.</p>
<table class="sum"><tr class="head"><td>Model</td><td>New won</td><td>Old won</td><td>Same</td><td>Average place (1 is best)</td></tr>""" + head + "</table>"
        + "\n".join(rows), encoding="utf-8")


if __name__ == "__main__":
    if "--image-models" in sys.argv:
        async def go():
            config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
            comfy = client.Comfy(lambda: config["comfy_url"])
            out = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), str(ROOT / "prompt-ab-models")))
            await models_mode(out, claude.service(config.get("claude_models") or MODEL), comfy, catalog.Catalog(ROOT / "workflows", comfy))
            print("Report: " + str(out / "report.html"))
        asyncio.run(go())
    else:
        asyncio.run(main())
