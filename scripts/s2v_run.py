"""A real script-to-video run in a throwaway studio: its own PostgreSQL database (scripts/testdb.py, beside
SCENE_TEST_DATABASE_URL's, kept in state.json for the next run) and storage (nothing of the live studio's),
real Claude, and the render PC's ComfyUI. It does what the agent panel does under "Allow all" (agent.js): sends the
message, answers each question as a click would, queues the plan's steps (their references, a shot that starts on an
earlier one, the cut), waits for them, has each picture and clip checked, and tells the agent what they made in the
panel's own "Continue the run" words. Every turn goes to C:/Scene/workbench/prompt-ab/s2v-run/log.md; its state.json lets it go on after a stop.

    python scripts/s2v_run.py"""

import json
import os
import sys
import time
from pathlib import Path

HERE = Path("C:/Scene/workbench/prompt-ab/s2v-run")   # the throwaway studio, outside the repo
HERE.mkdir(exist_ok=True)
ROOT = Path(r"C:\Scene\Scene.ai")
sys.path.insert(0, str(ROOT / "backend"))
KEY = HERE / "secret.txt"   # the throwaway studio's own vault key: never secret.key in the project
if not KEY.is_file():
    from cryptography.fernet import Fernet
    KEY.write_text(Fernet.generate_key().decode("ascii"), encoding="ascii")
os.environ["SCENE_SECRET_KEY"] = KEY.read_text(encoding="ascii").strip()

from fastapi.testclient import TestClient  # noqa: E402
from scene.config import Settings  # noqa: E402
from scene.main import create_app  # noqa: E402

IDEA = ("Make a 20-second reel from this idea: at dawn in a narrow Mumbai lane, an old chai seller lights his stove and "
        "hands the first cup of the day to a tired young nurse coming off her night shift. She warms her hands on it, "
        "smiles and says \"Aaj ki pehli chai.\" He nods and says \"Hamesha ki tarah.\"")
RUN, TAB, MODEL = "s2v-real", "Agent 1", "claude/sonnet"
ME = {"name": "Run Test", "email": "run@example.com", "password": "a long test password"}
MAX_TURNS = 45
SAVED_ONLY = 3   # turns in a row that only save their work and go on by themselves (agent.js)
PREFER = [   # words of a question -> the option to pick, by its words, in order
    (("is this a film", "film or", "a film?"), ("film", "yes")),
    (("starting from", "start from", "what are you starting"), ("idea",)),
    (("shape", "aspect", "orientation", "where will", "format"), ("9:16", "reel", "portrait", "vertical")),
    (("quality", "resolution"), ("480", "draft", "fast", "preview")),
    (("continuity",), ("board",)),
    (("style", "look"), ("realistic", "live action", "live-action", "cinematic", "photo")),
    (("length", "how long", "runtime", "duration"), ("20", "15", "short")),
    (("music",), ("yes", "music")),
]
LOG = HERE / "log.md"


def log(text):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text[:400], flush=True)


def pick(question, options, default=None):
    said = question.lower()
    for words, wanted in PREFER:
        if any(w in said for w in words):
            for want in wanted:
                for option in options:
                    if want in option.lower():
                        return option
    return default if default in options else options[0]


def main():
    state = json.loads((HERE / "state.json").read_text(encoding="utf-8")) if (HERE / "state.json").is_file() else {}

    def store():
        (HERE / "state.json").write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if not state.get("database"):   # a throwaway database of its own, kept for the runs after a stop
        import subprocess
        state["database"] = subprocess.run([sys.executable, str(ROOT / "scripts" / "testdb.py"), "create"],
                                           capture_output=True, text=True, check=True).stdout.strip()
        store()
    settings = Settings(database_url=state["database"], comfy_url=config["comfy_url"], storage_dir=str(HERE / "storage"),
                        claude_home=str(HERE / "claude-home"), signup_credits=1_000_000, first_account_local=False,
                        workflows_dir=str(ROOT / "workflows"))
    with TestClient(create_app(settings)) as c:
        if not state.get("project"):
            c.post("/api/auth/register", json=ME)
            state["project"] = c.post("/api/projects", json={"name": "Chai at dawn"}).json()["id"]
            state.update(history=[], turn=0, text=IDEA, saved_in_row=0)
            store()
        else:
            c.post("/api/auth/login", json={"email": ME["email"], "password": ME["password"]})
        project = state["project"]

        def jobs():
            got = c.get("/api/jobs").json()
            return {j["id"]: j for j in (got.get("jobs") if isinstance(got, dict) else got)}

        def item_of(job_id):
            for where in ({"project": project}, {"project": project, "run": RUN}):   # a run's working files are listed apart
                items = c.get("/api/library", params=where).json()["items"]
                found = next((i for i in items if i.get("job_id") == job_id), None)
                if found:
                    return found
            return None

        def wait(job_id, name):
            started = time.time()
            while True:
                job = jobs().get(job_id)
                status = (job or {}).get("status")
                if status in ("failed", "cancelled"):
                    return None, (job or {}).get("error") or status
                if status == "done" or job is None:
                    made = item_of(job_id)
                    if made:
                        return made, None
                    if job is None:
                        return None, "no result in the library"
                if time.time() - started > 3600:
                    return None, "still not made after an hour"
                time.sleep(5)

        def reference(item_id, kind=None):
            ref = c.post("/api/library/{}/reference".format(item_id), params={"kind": kind} if kind else None).json()
            return {"comfy_name": ref["comfy_name"], "name": ref["name"]}

        def run_steps(steps):
            """Queue and wait for every step, in order, as approve() does; then each picture and clip is checked."""
            made = {}
            for n, step in enumerate(steps):
                try:
                    if step.get("assemble"):
                        cut, clips, last = step["assemble"], list(step["assemble"].get("clips") or []), None
                        for index in cut.get("steps") or []:
                            shot = steps[index]
                            if index not in made or not made[index].get("item"):
                                continue
                            fade = bool(last and shot.get("place") and last.get("place") and shot["place"] != last["place"])
                            clips.append({"id": made[index]["item"]["id"], "start": 0, "end": 0, "fade": fade})
                            last = shot
                        music = made.get(cut["music_step"], {}).get("item", {}).get("id") if cut.get("music_step") is not None else cut.get("music")
                        job = c.post("/api/edit/assemble", json={"name": cut.get("name"), "clips": clips, "music": music, "title": cut.get("title"),
                                                                 "end": cut.get("end"), "look": cut.get("look"), "shape": cut.get("shape"),
                                                                 "project_id": project}).json()["job"]
                    elif step.get("motion") or step.get("sound") or step.get("edit"):
                        path, body = (("/api/motion/render", step["motion"]) if step.get("motion") else ("/api/edit/sound", step["sound"])
                                      if step.get("sound") else ("/api/timeline/export", {"name": step["name"], "clips": step["edit"]["clips"],
                                                                                         "parent": step["edit"]["clips"][0]["id"]}))
                        job = c.post(path, json=dict(body, project_id=project)).json()["job"]
                    else:
                        uses = step.get("uses") or []
                        job_settings = dict(step["settings"], refs={}, parent=step["start"]["id"] if step.get("start") else uses[0]["id"] if uses else None)
                        for use in uses:
                            job_settings["refs"][use["slot"]] = ({"asset_id": use["asset"], "name": use["name"]} if use.get("asset")
                                                                 else reference(use["id"], use["kind"]))
                        if step.get("start"):
                            job_settings["refs"][step["start"]["slot"]] = reference(step["start"]["id"])
                        if step.get("after"):
                            earlier = made.get(step["after"]["step"], {}).get("item")
                            if not earlier:
                                raise RuntimeError("the step this one starts on was not made")
                            job_settings["refs"][step["after"]["slot"]] = reference(earlier["id"])
                            job_settings["parent"] = earlier["id"]
                        answer = c.post("/api/jobs", files={"settings": (None, json.dumps(job_settings))})
                        if answer.status_code >= 400:
                            raise RuntimeError(answer.text[:300])
                        job = answer.json()["id"]
                    log("  - queued “{}” (job {})".format(step["name"], job))
                    item, error = wait(job, step["name"])
                    made[n] = {"item": item, "error": error}
                    if item and step.get("settings") and step.get("kind") in ("image", "video"):
                        before = steps[step["after"]["step"]] if step.get("after") else steps[step["follows"]] if step.get("follows") is not None else None
                        previous = made.get(steps.index(before), {}).get("item", {}).get("id") if before else None
                        uses = [{"asset": u["asset"]} if u.get("asset") else {"id": u["id"]} for u in step.get("uses") or []]
                        found = c.post("/api/agent/review", json={"item": item["id"], "prompt": step.get("prompt"), "uses": uses,
                                                                  "previous": previous, "retake": False}).json()
                        made[n]["review"] = (found or {}).get("verdict") or {}
                    log("  - “{}”: {}{}".format(step["name"], "item {}".format(item["id"]) if item else "not made: " + str(error),
                                               "" if not made[n].get("review") else " · check: " + ("passed" if made[n]["review"].get("passed")
                                                                                                   else str(made[n]["review"].get("problem")))))
                except Exception as error:   # the panel stops at the first refusal
                    made[n] = {"item": None, "error": str(error)}
                    log("  - “{}” was not made: {}".format(step["name"], error))
                    break
            lines = []
            for n, step in enumerate(steps):
                got = made.get(n)
                if not got:
                    lines.append("- “{}”: skipped".format(step["name"]))
                elif got["item"]:
                    i = got["item"]
                    size = ", {}×{}".format(i["width"], i["height"]) if i.get("width") else ""
                    seconds = ", {} s".format(i["duration"]) if i.get("duration") else ""
                    review = got.get("review") or {}
                    check = " — its check: {}".format(review.get("problem")) if review and not review.get("passed") else ""
                    lines.append("- “{}”: item {} ({}{}{}){}".format(step["name"], i["id"], step.get("kind") or i.get("kind"), size, seconds, check))
                else:
                    lines.append("- “{}”: not made — {}".format(step["name"], got["error"]))
            return lines, any(s.get("assemble") for s in steps) and all(m.get("item") for m in made.values())

        while state["turn"] < MAX_TURNS:
            state["turn"] += 1
            text = state["text"]
            log("\n## Turn {}\n\n**Sent:** {}".format(state["turn"], text[:1500]))
            started = time.time()
            plan = c.post("/api/agent/plan", json={"instruction": text, "project_id": project, "selection": [], "model": MODEL,
                                                    "run": RUN, "tab": TAB, "history": state["history"]}).json()
            if "reply" not in plan:
                log("**Error:** " + json.dumps(plan)[:1500])
                break
            notes = [e.get("text") for e in plan.get("activity") or [] if e.get("text")]
            log("**Took:** {} s\n\n**Activity:** {}\n\n**Reply:** {}".format(round(time.time() - started), " | ".join(notes)[:3000],
                                                                         (plan.get("reply") or "")[:3000]))
            steps = plan.get("steps") or []
            for s in steps:
                log("  - step “{}” · {} · {}".format(s.get("name"), s.get("workflow") or s.get("kind"), " ".join(str(s.get("prompt") or "").split())[:500]))
            state["history"].append({"instruction": text, "reply": plan.get("reply") or "",
                                     "steps": [{"name": s.get("name"), "uses": [u.get("name") for u in s.get("uses") or []]} for s in steps]})
            store()
            if plan.get("questions"):
                picks = [pick(q["text"], q["options"], q.get("default")) for q in plan["questions"]]
                state["text"] = "My answers:\n" + "\n".join("{}. {} — {}".format(i, q["text"], p) for i, (q, p) in enumerate(zip(plan["questions"], picks), 1))
                state["saved_in_row"] = 0
            elif plan.get("question"):
                q = plan["question"]
                state["text"] = pick(q["text"], q["options"])
                log("**Answered:** " + state["text"])
                state["saved_in_row"] = 0
            elif steps:
                lines, finished = run_steps(steps)
                if finished:
                    log("\n**The film is made.**")
                    store()
                    break
                state["text"] = ("Continue the run. The steps you planned have come to an end:\n" + "\n".join(lines) + "\n"
                                 "Write what they made to the run's state, then go on from its status.")
                state["saved_in_row"] = 0
            elif plan.get("continues") and state["saved_in_row"] < SAVED_ONLY:
                state["saved_in_row"] += 1
                state["text"] = "Continue the run: you saved your work and planned nothing to make. Go on from the run's status."
            else:
                log("\n**The run stopped:** no question, no steps, and it does not go on by itself.")
                store()
                break
            store()
    log("\nDone after {} turns.".format(state["turn"]))


main()
