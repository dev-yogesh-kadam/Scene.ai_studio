"""Motion projects the agent writes file by file (pages.py), what they may reach, drawn by HyperFrames with its whole
check and its review sheets (motion.render_project), and a brand's logo made ready for them from any file (logo.py)."""

import asyncio
import json
import shutil

import pytest
from PIL import Image, ImageDraw

from scene import logo, motion, pages

ready = motion.status()["ready"]
needs_hyperframes = pytest.mark.skipif(not ready, reason="HyperFrames is not installed here")


def run(coro):
    return asyncio.run(coro)


INDEX = """<!doctype html>
<html><head><meta charset="UTF-8"><script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>html,body{margin:0;width:640px;height:360px;overflow:hidden;background:#0b0d1a}</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="2" data-width="640" data-height="360">
  <div id="bg" class="clip" data-start="0" data-duration="2" style="position:absolute;inset:0;background:#202a8f"></div>
  <div id="one" data-composition-id="one" data-composition-src="compositions/one.html" data-start="0" data-duration="2"
       data-track-index="1" data-width="640" data-height="360"></div>
  <audio id="sfx-pop" class="clip" src="assets/sfx/pop.mp3" data-start="0.5" data-duration="0.3" data-volume="0.8"></audio>
</div>
<script>window.__timelines = window.__timelines || {}; window.__timelines["main"] = gsap.timeline({ paused: true });</script>
</body></html>"""
SCENE = """<template>
  <style>#root{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}
  #one-t{font-family:"Montserrat";font-weight:800;font-size:64px;color:#fff}</style>
  <div id="root" data-composition-id="one" data-width="640" data-height="360">
    <div id="one-t" class="clip" data-start="0" data-duration="2">Hello__MORE__</div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo("#one-t", { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, ease: "expo.out" }, 0);
    window.__timelines["one"] = tl;
  </script>
</template>"""


def project(base, more=""):
    pages.write(base, "demo/index.html", INDEX)
    pages.write(base, "demo/compositions/one.html", SCENE.replace("__MORE__", more))
    return base / "demo"


# ---------------------------------------------------------------- the files

def test_a_project_keeps_text_files_inside_itself(tmp_path):
    done = pages.write(tmp_path, "launch/compositions/hook.html", "<template></template>")
    assert done == {"project": "launch", "path": "compositions/hook.html", "characters": 21, "files": 1}
    assert pages.read(tmp_path, "launch") == ("project", [{"path": "compositions/hook.html", "characters": 21}])
    assert pages.read(tmp_path, "launch/compositions/hook.html") == ("file", "<template></template>")
    for path, words in (("../x/index.html", "can't be part of a path"), ("launch/../../x.html", "can't be part of a path"),
                        ("C:/x/index.html", "can't be part of a path"), ("launch/logo.png", "Only text files"),
                        ("launch", "Give the file's path"), ("a/b/c/d/e/f/g.html", "too deep")):
        with pytest.raises(pages.PageError, match=words):
            pages.write(tmp_path, path, "x")
    with pytest.raises(pages.PageError, match="at most"):
        pages.write(tmp_path, "launch/big.html", "x" * (pages.FILE_MOST + 1))
    pages.remove(tmp_path, "launch")
    assert pages.projects(tmp_path) == []


def test_a_staged_project_reaches_nothing_off_its_folder(tmp_path):
    def staged(more):
        folder = project(tmp_path / more.__hash__().__str__(), more)
        copy = tmp_path / "stage"
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(folder, copy)
        motion._stage(copy, {})
        return copy

    copy = staged("")
    assert motion.check_project(copy) == (640, 360, 2.0)
    assert 'src="lib/gsap/gsap.min.js"' in (copy / "index.html").read_text() and (copy / "assets" / "sfx" / "pop.mp3").is_file()
    for more, words in (('<img src="../../secret.png">', "off the project's folder"),
                        ('<img src="https://example.com/x.png">', "is on the web"),
                        ('<img src="assets/nope.png">', "is not in the project"),
                        ('<script type="module">import x from "https://evil.example/x.js";</script>', "an import of"),
                        ("<script>fetch('http://localhost:8000/api/me')</script>", "fetch()"),
                        ('<iframe src="x.html"></iframe>', "<iframe> element")):
        with pytest.raises(motion.MotionError, match=words):
            motion.check_project(staged(more))
    # Three.js comes from here, by its name or its CDN link
    copy = staged('<script type="module">import * as THREE from "three"; import { RoundedBoxGeometry } from '
                  '"three/addons/geometries/RoundedBoxGeometry.js";</script>')
    assert motion.check_project(copy)[0] == 640
    assert '"three": "./lib/three/build/three.module.js"' in (copy / "index.html").read_text()
    assert (copy / "lib" / "three" / "build" / "three.module.js").is_file()


@needs_hyperframes
def test_a_project_is_checked_drawn_reviewed_and_levelled(tmp_path):
    folder = project(tmp_path)
    made = run(motion.render_project(folder, tmp_path / "out" / "film.mp4", fps=30))
    kinds = [e["_kind"] for e in made["each"]]
    assert kinds[0] == "video" and "image" in kinds   # the film, then its review sheets
    assert made["width"] == 640 and abs(made["seconds"] - 2.0) < 0.1
    assert any(n.startswith("index.html") for n in made.get("notes", []))   # HyperFrames' warnings come back
    stills = run(motion.render_project(folder, tmp_path / "out" / "look.mp4", frames=[0.5, 1.5]))
    assert [p.name for p in stills["files"]] == ["look_at0.5s.png", "look_at1.5s.png"]
    broken = project(tmp_path / "broken")
    (broken / "index.html").write_text(INDEX.replace('<audio id="sfx-pop" ', "<audio "), encoding="utf-8")   # an <audio> needs an id
    with pytest.raises(motion.MotionError, match="check found"):
        run(motion.render_project(broken, tmp_path / "out" / "broken.mp4"))


# ---------------------------------------------------------------- the logo

def test_a_logo_on_a_flat_ground_is_cut_out_with_its_colours(tmp_path):
    im = Image.new("RGB", (900, 500), "white")
    draw = ImageDraw.Draw(im)
    draw.ellipse((60, 100, 360, 400), fill="#e8402a")
    draw.rectangle((420, 200, 860, 300), fill="#1b1b1b")
    im.save(tmp_path / "logo.jpg", quality=90)
    made = run(logo.prepare(tmp_path / "logo.jpg", "image", tmp_path / "cut.png"))
    cut = Image.open(tmp_path / "cut.png")
    assert made["ground"] == "#ffffff" and cut.mode == "RGBA" and cut.getpixel((0, 0))[3] == 0
    rgb = [tuple(int(p["hex"][i:i + 2], 16) for i in (1, 3, 5)) for p in made["palette"][:2]]
    assert any(r > 200 and g < 90 for r, g, b in rgb) and any(sum(c) < 150 for c in rgb)   # the red and the near-black
    assert made["wants"] == "light"
    photo = Image.linear_gradient("L").resize((400, 300)).convert("RGB")   # no flat ground: kept whole
    photo.save(tmp_path / "photo.png")
    assert run(logo.prepare(tmp_path / "photo.png", "image", tmp_path / "photo_cut.png"))["ground"] == "kept"


def test_an_svg_keeps_its_shapes_and_loses_what_runs():
    svg = ('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100" onload="alert(1)">'
           '<script>alert(2)</script><circle cx="50" cy="50" r="40" fill="#2a6cf0"/><foreignObject><div>x</div></foreignObject>'
           '<a href="javascript:alert(3)"><rect x="100" y="30" width="90" height="40" fill="#22d3a6"/></a></svg>')
    cleaned = logo.clean_svg(svg)
    assert "script" not in cleaned and "onload" not in cleaned and "foreignObject" not in cleaned and "javascript" not in cleaned
    assert '<rect x="100" y="30" width="90" height="40"' in cleaned and cleaned.startswith("<svg")
    with pytest.raises(logo.LogoError):
        logo.clean_svg("just words")


@needs_hyperframes
def test_an_svg_logo_is_drawn_whole(tmp_path):
    (tmp_path / "logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><circle cx="50" cy="50" r="40" '
                                       'fill="#2a6cf0"/><rect x="100" y="30" width="90" height="40" fill="#22d3a6"/></svg>')
    made = run(logo.prepare(tmp_path / "logo.svg", "text", tmp_path / "mark.png"))
    assert made["svg"] and made["shapes"] == 2 and made["ground"] == "transparent"
    colours = {p["hex"][:3] for p in made["palette"]}
    assert {"#28", "#20"} <= colours or len(made["palette"]) >= 2   # both shapes drawn, each with its own colour
    assert (tmp_path / "mark.svg").is_file()


# ---------------------------------------------------------------- through the agent (these need the test database)

def test_the_agent_writes_a_project_and_draws_it(client, monkeypatch):
    from test_agent_shots import hosted
    from test_api import register
    register(client)
    module = client.post("/api/projects", json={"name": "Brand"}).json()["id"]
    calls = [{"tool": "page_write", "path": "demo/index.html", "value": INDEX},
             {"tool": "page_write", "path": "demo/compositions/one.html", "value": SCENE.replace("__MORE__", "")},
             {"tool": "page_read", "path": "demo"},
             {"tool": "page_read", "path": "@hyperframes/hyperframes/references/motion.md"},
             {"tool": "page_write", "path": "../escape/index.html", "value": "x"}]
    if ready:
        calls.append({"tool": "film", "op": "html", "settings": json.dumps({"project": "demo", "frames": [1.0]})})
    seen = hosted(monkeypatch, client, *calls, {"tool": "finish", "reply": "Done.", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "a motion graphics test", "project_id": module})
    told = [m["content"] for m in seen[-1] if m["role"] == "user" and m["content"].startswith("Result of page_")]
    assert '"files": 2' in told[1] and '"compositions/one.html"' in told[2]
    assert "Motion" in told[3] or "motion" in told[3]   # HyperFrames' own guide, read as it is
    assert told[4].startswith("Result of page_write:\nNot written")
    if ready:
        drawn = next(m["content"] for m in seen[-1] if m["role"] == "user" and m["content"].startswith("Result of film"))
        assert '"kind": "image"' in drawn and "Style frame" in drawn


def test_the_page_writer_builds_a_project_outside_the_conversation(client, monkeypatch):
    from test_agent_shots import hosted
    from test_api import register
    register(client)
    module = client.post("/api/projects", json={"name": "Brand"}).json()["id"]
    asked = []

    async def fake_build(guides, message, model=None):
        asked.append((guides, message))
        return {"files": [{"path": "index.html", "text": INDEX}, {"path": "compositions/one.html", "text": SCENE.replace("__MORE__", "")},
                          {"path": "../out.html", "text": "x"}],
                "remove": ["old.md"], "notes": "Two files; expects assets/sfx/pop.mp3.", "model": "claude/sonnet",
                "tokens": {"prompt": 9000, "cached": 7000, "written": 0, "answer": 3000}}
    monkeypatch.setattr(client.app.state.agent, "build_pages", fake_build)
    seen = hosted(monkeypatch, client,
                  {"tool": "page_write", "path": "demo/old.md", "value": "old"},
                  {"tool": "page_write", "path": "demo/spec.md", "value": "Navy ground, white type."},
                  {"tool": "page_build", "path": "demo", "text": "One scene of 2 s: Hello in white.",
                   "query": "@hyperframes/hyperframes/references/types/vertical.md, @hyperframes/nope.md"},
                  {"tool": "finish", "reply": "Done.", "steps": []})
    plan = client.post("/api/agent/plan", json={"instruction": "a motion graphics test", "project_id": module}).json()
    guides, message = asked[0]
    assert "data-composition-id" in guides and "Motion" in guides   # the contract and HyperFrames' guides, every time
    assert "Navy ground" in message and "One scene of 2 s" in message and "types/vertical.md" in message
    told = next(m["content"] for m in seen[-1] if m["role"] == "user" and m["content"].startswith("Result of page_build"))
    result = json.loads(told.split("\n", 1)[1])
    assert [w["path"] for w in result["wrote"]] == ["index.html", "compositions/one.html"] and result["removed"] == ["old.md"]
    assert result["check"].startswith("passed: 640x360, 2 s (") and len(result["not_written"]) == 1
    assert result["guides_not_found"] == ["@hyperframes/nope.md"] and "<template>" not in told   # the pages stay out
    assert plan["tokens"]["answer"] >= 3000   # the writer's tokens are the turn's, and charged


def test_a_quick_check_stages_the_project_and_names_the_media_it_needs(tmp_path):
    (tmp_path / "demo" / "compositions").mkdir(parents=True)
    (tmp_path / "demo" / "index.html").write_text(INDEX.replace('<div id="bg"', '<img src="assets/logo.png" alt=""><div id="bg"'), encoding="utf-8")
    (tmp_path / "demo" / "compositions" / "one.html").write_text(SCENE.replace("__MORE__", ""), encoding="utf-8")
    assert motion.quick_check(tmp_path / "demo") == (640, 360, 2.0, ["logo.png"])   # the CDN and the sound effects are here
    assert not (tmp_path / "demo" / "assets").exists()   # the project itself is left as written
    (tmp_path / "demo" / "index.html").write_text(INDEX.replace("compositions/one.html", "../one.html"), encoding="utf-8")
    with pytest.raises(motion.MotionError):
        motion.quick_check(tmp_path / "demo")
