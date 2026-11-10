"""The film ops written whole: an ffmpeg command (ffjob.py) and an HTML page (motion.render_page). What they may reach is
checked before anything runs, they run on real ffmpeg (and HyperFrames, where it is installed), and each output is
filed as what it is."""

import asyncio
import json

import pytest

from scene import ffjob, motion
from test_agent_shots import hosted
from test_api import register
from test_film_api import item, made


def run(coro):
    return asyncio.run(coro)


CLIP = {"name": "a.mp4", "item": 1}
OUT = [{"name": "o.mp4"}]


def refused(argv, words, inputs=(CLIP,), sidecars=None, outputs=OUT):
    with pytest.raises(ffjob.JobError) as caught:
        ffjob.check(argv, list(inputs), sidecars, outputs)
    assert words in str(caught.value), str(caught.value)


# ---------------------------------------------------------------- what an ffmpeg command may reach

def test_a_command_reaches_nothing_outside_its_folder():
    refused(["-f", "gdigrab", "-i", "desktop", "o.mp4"], "no devices")
    refused(["-f", "lavfi", "-i", "ddagrab=0", "o.mp4"], "ddagrab")
    refused(["-f", "lavfi", "-i", "gfxcapture", "o.mp4"], "gfxcapture")
    refused(["-i", "a.mp4", "-vf", "zmq,scale=2:2", "o.mp4"], "zmq")
    refused(["-i", "a.mp4", "-vf", "movie=a.mp4,scale=2:2", "o.mp4"], "movie")
    refused(["-i", "http://example.com/a.mp4", "o.mp4"], "URL or protocol")
    refused(["-i", "concat:a.mp4|a.mp4", "o.mp4"], "URL or protocol")
    refused(["-i", "a.mp4", "-vf", "subtitles=C\\:/Scene/x.srt", "o.mp4"], "outside the folder")   # escaped as a filter reads it
    refused(["-i", "a.mp4", "-vf", "drawtext=textfile='\\Scene\\secret.key'", "o.mp4"], "outside the folder")
    refused(["-i", "/etc/passwd", "o.mp4"], "outside the folder")
    refused(["-i", "\\\\server\\share\\a.mp4", "o.mp4"], "outside the folder")
    refused(["-i", "../a.mp4", "o.mp4"], "up out of the folder")
    refused(["-i", "a.mp4", "-protocol_whitelist", "file,http", "o.mp4"], "the job sets it")
    refused(["-i", "a.mp4", "o.mp4", "&&", "del", "x"], "no shell")
    refused(["-i", "a.mp4", "-i", "b.mp4", "o.mp4"], "b.mp4 is not one of")
    refused(["-i", "a.mp4", "x.mp4"], "the output o.mp4 is not written")
    refused(["-f", "concat", "-safe", "0", "-i", "l.txt", "o.mp4"], "-safe 0", sidecars=[{"name": "l.txt", "content": "file 'a.mp4'"}])
    refused(["-f", "concat", "-i", "l.txt", "o.mp4"], "outside the folder", sidecars=[{"name": "l.txt", "content": "file 'C:/x/y.mp4'"}])
    refused(["-i", "a.mp4", "-vf", "sendcmd=f=s.srt,drawtext=text=x", "o.mp4"], "read as subtitles only",
            sidecars=[{"name": "s.srt", "content": "0 drawtext reinit text=x;"}])
    refused(["-i", "a.mp4", "-filter_complex_script", "g.ass", "o.mp4"], "a .txt sidecar", sidecars=[{"name": "g.ass", "content": "null"}])
    with pytest.raises(ffjob.JobError, match="bare file name"):
        ffjob.check(["-i", "a.mp4", "o.mp4"], [{"name": "x/a.mp4", "item": 1}], None, OUT)
    with pytest.raises(ffjob.JobError, match="name of its own"):
        ffjob.check(["-i", "a.mp4", "a.mp4"], [CLIP], None, [{"name": "a.mp4"}])
    with pytest.raises(ffjob.JobError, match="timeout"):
        ffjob.check(["-i", "a.mp4", "o.mp4"], [CLIP], None, OUT, timeout=5000)


def test_a_command_a_page_could_have_planted_reaches_nothing_either():
    # what text from outside (a fetched page, a file) might talk the model into writing: still refused, every one
    refused(["-i", "http://example.com/a.mp4", "o.mp4"], "URL or protocol")
    refused(["-i", "C:\\Scene\\Data\\secrets\\scene_app.txt", "o.mp4"], "outside the folder")
    refused(["-i", "C:/Scene/x.mp4", "o.mp4"], "outside the folder")
    refused(["-i", "/etc/passwd", "o.mp4"], "outside the folder")
    refused(["-f", "lavfi", "-i", "movie=C\\:/Scene/x.mp4", "o.mp4"], "movie")
    refused(["-f", "lavfi", "-i", "movie=C\\:/Scene/x.mp4", "o.mp4"], "outside the folder")
    refused(["-f", "lavfi", "-i", "amovie=/etc/passwd", "o.mp4"], "outside the folder")
    refused(["-f", "concat", "-i", "l.txt", "o.mp4"], "outside the folder", sidecars=[{"name": "l.txt", "content": "file '/etc/passwd'"}])
    for name in ("C:/x/l.txt", "/etc/l.txt", "..\\l.txt"):   # a sidecar named by a path, not a bare name
        with pytest.raises(ffjob.JobError, match="bare file name"):
            ffjob.check(["-i", "a.mp4", "o.mp4"], [CLIP], [{"name": name, "content": "x"}], OUT)


def test_a_path_relative_to_another_drive_is_refused_too():
    # E:SceneBackups/x is E:\SceneBackups\x when the job's folder is on C: (a drive's own folder, no slash after it)
    refused(["-f", "data", "-i", "E:SceneBackups/scene.dump", "-map", "0", "-c", "copy", "-f", "data", "o.txt"],
            "outside the folder", outputs=[{"name": "o.txt"}])
    refused(["-i", "D:secret", "o.mp4"], "outside the folder")
    refused(["-i", "a.mp4", "-vstats_file", "C:Users/LUFI/x", "o.mp4"], "outside the folder")
    refused(["-i", "a.mp4", "-passlogfile", "E:x", "o.mp4"], "outside the folder")
    refused(["-i", "a.mp4", "-vf", "subtitles=E\\:SceneBackups/x", "o.mp4"], "outside the folder")
    refused(["-i", "a.mp4", "-vf", "drawtext=textfile=C\\:Scene/Data/secrets/x", "o.mp4"], "outside the folder")
    refused(["-i", "a.mp4", "-vf", "drawtext=textfile='E:x'", "o.mp4"], "outside the folder")
    refused(["-i", "a.mp4", "-filter_complex_script", "g.txt", "o.mp4"], "outside the folder",
            sidecars=[{"name": "g.txt", "content": "movie='E:x' [m]; [0][m] overlay"}])
    # ...while a filter's own w:h, stream options and a caption's "B\: go" are not paths
    for argv in (["-i", "a.mp4", "-vf", "crop=w:h:0:0,pad=w:h,scale=w=1280:h=720", "-c:v", "libx264", "-b:a", "128k", "o.mp4"],
                 ["-i", "a.mp4", "-vf", "drawtext=fontfile=Anton-Regular.ttf:text='Plan B\\: go':x=w-tw", "o.mp4"],
                 ["-i", "a.mp4", "-map", "0:v", "-metadata:s:a:0", "language=eng", "o.mp4"]):
        ffjob.check(argv, [CLIP], None, OUT)


def test_ordinary_commands_pass_the_check():
    ok = lambda argv, sidecars=None, outputs=OUT: ffjob.check(argv, [CLIP], sidecars, outputs)
    argv, _, timeout = ok(["ffmpeg", "-i", "a.mp4", "-vf", "drawtext=fontfile=Anton-Regular.ttf:text='Scene 4\\: Rooftop':"
                           "x=(w-tw)/2:y=h-th-40:enable='between(t,2,6)'", "-r", "30000/1001", "o.mp4"])
    assert argv[0] == "-i" and timeout == 300   # a leading "ffmpeg" is dropped
    ok(["-i", "a.mp4", "-vf", "scale=iw/2:-2,setpts=PTS/2,crop=ih*9/16:ih:(iw-ih*9/16)*0.5:0", "o.mp4"])
    ok(["-i", "a.mp4", "-c:v", "libx264", "-map", "0:v", "-map", "0:a?", "o.mp4"])
    ok(["-i", "a.mp4", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "o.mp4"])
    ok(["-i", "a.mp4", "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-"], outputs=[])
    caps = "Dialogue: 0,0:00:00.20,0:00:01.40,Cap,,0,0,0,,{\\an2}WAIT... the data: {\\c&H0000D7FF&}the movie, then\\Nयह"
    ok(["-i", "a.mp4", "-vf", "ass=caps.ass:fontsdir=.", "o.mp4"], sidecars=[{"name": "caps.ass", "content": caps}])
    ok(["-f", "concat", "-i", "list.txt", "-c", "copy", "o.mp4"],
       sidecars=[{"name": "list.txt", "content": "ffconcat version 1.0\nfile 'a.mp4'\nfile 'a.mp4'\n"}])
    assert ffjob._whitelisted(["-f", "lavfi", "-i", "x", "-i", "a.mp4"]).count("-protocol_whitelist") == 2


def job(argv, files, outputs, target, sidecars=None):
    """Check a command and run it: files {name: path}, outputs [name]."""
    argv, texts, timeout = ffjob.check(argv, [{"name": n, "item": 1} for n in files], sidecars, [{"name": n} for n in outputs])
    return run(ffjob.run(argv, files, texts, outputs, target, timeout))


def test_a_command_runs_in_its_own_folder_and_keeps_only_what_it_declared(tmp_path):
    clip = tmp_path / "clip.mp4"
    job(["-f", "lavfi", "-i", "color=c=red:s=160x90:r=24:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2", "-pix_fmt", "yuv420p",
         "-shortest", "c.mp4"], {}, ["c.mp4"], tmp_path / "make.txt")
    (tmp_path / "make_c.mp4").rename(clip)
    argv, sidecars, timeout = ffjob.check(["-ss", "0.5", "-i", "a.mp4", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                           "cut.mp4", "-map", "0:a", "-vn", "sound.wav"],
                                          [CLIP], None, [{"name": "cut.mp4"}, {"name": "sound.wav"}])
    done = run(ffjob.run(argv, {"a.mp4": clip}, sidecars, ["cut.mp4", "sound.wav"], tmp_path / "job.txt", timeout))
    assert [p.name for p in done["files"]] == ["job_cut.mp4", "job_sound.wav"] and all(p.is_file() for p in done["files"])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clip.mp4", "job_cut.mp4", "job_sound.wav"]   # nothing else left
    measured = job(["-i", "a.mp4", "-af", "ebur128=framelog=quiet", "-f", "null", "-"], {"a.mp4": clip}, [], tmp_path / "loud.txt")
    assert "LUFS" in measured["log"] and "LUFS" in (tmp_path / "loud.txt").read_text(encoding="utf-8")
    with pytest.raises(ffjob.JobError, match="stopped with an error"):
        job(["-i", "a.mp4", "-vf", "nosuchfilter", "o.mp4"], {"a.mp4": clip}, ["o.mp4"], tmp_path / "bad.txt")
    assert not list(tmp_path.glob("bad*"))


def test_an_ffmpeg_op_files_each_output_as_what_it_is(client):
    me = register(client)
    clip = item(client, me, "Clip", "video", "clip.mp4", ["-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=2", "-f", "lavfi",
                                                          "-i", "sine=f=330:d=2", "-pix_fmt", "yuv420p", "-shortest"])
    post = lambda **body: client.post("/api/edit/film", json=body)
    found = made(client, post(op="ffmpeg", argv=["-i", "a.mp4", "-vf", "hflip", "-pix_fmt", "yuv420p", "flip.mp4", "-map", "0:a",
                                                 "-vn", "sound.wav", "-frames:v", "1", "still.png"],
                              inputs=[{"name": "a.mp4", "item": clip}], outputs=[{"name": "flip.mp4"}, {"name": "sound.wav"},
                                                                                 {"name": "still.png"}], reason="test"))
    kinds = {f["context"]["output"]: f["kind"] for f in found}
    assert kinds == {"flip.mp4": "video", "sound.wav": "audio", "still.png": "image"}
    assert next(f for f in found if f["kind"] == "video")["context"]["width"] == 160
    measured = made(client, post(op="ffmpeg", argv=["-i", "a.mp4", "-af", "volumedetect", "-f", "null", "-"],
                                 inputs=[{"name": "a.mp4", "item": clip}], outputs=[]))[0]
    assert measured["kind"] == "text" and "mean_volume" in measured["context"]["log"]

    jobs_before = len(client.app.state.db.all("SELECT id FROM jobs"))
    for body, words in ((dict(argv=["-i", "C:/Windows/win.ini", "o.mp4"], inputs=[], outputs=OUT), "outside the folder"),
                        (dict(argv=["-i", "a.mp4", "o.mp4"], inputs=[{"name": "a.mp4", "item": 999999}], outputs=OUT), "not in your library")):
        response = post(op="ffmpeg", **body)
        assert response.status_code in (400, 404) and words in response.json()["detail"], response.text
    assert len(client.app.state.db.all("SELECT id FROM jobs")) == jobs_before   # nothing was queued


# ---------------------------------------------------------------- what a page may reach

PAGE = """<!doctype html><html><head>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/SplitText.min.js"></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&display=block">
<style>html,body{margin:0;width:320px;height:180px;overflow:hidden;background:#111}
#t{font-family:"Inter";color:#fff;font-size:40px}</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="1" data-width="320" data-height="180">
<div id="t" class="clip" data-start="0" data-duration="1">Case file: 1427 — wait...</div>__MORE__</div>
<script>const tl = gsap.timeline({paused: true}); tl.from("#t", {opacity: 0, duration: 0.3}, 0); tl.set({}, {}, 1);
window.__timelines = window.__timelines || {}; window.__timelines["main"] = tl;</script></body></html>"""


def test_a_page_loads_gsap_from_here_and_reaches_nothing_else():
    page = motion.check_page(PAGE.replace("__MORE__", '<img src="logo.png">'), 320, 180, 1, {"logo.png"})
    assert 'src="gsap.min.js"' in page and 'src="SplitText.min.js"' in page and "jsdelivr" not in page

    def no(more, words, width=320, seconds=1, names=()):
        with pytest.raises(motion.MotionError) as caught:
            motion.check_page(PAGE.replace("__MORE__", more), width, 180, seconds, set(names))
        assert words in str(caught.value), str(caught.value)

    no("", 'data-width must be "640"', width=640)
    no("", 'data-duration must be "2"', seconds=2)
    no('<img src="https://example.com/x.png">', "is on the web")
    no('<img src="bg.png">', "bg.png is not one of the media given")
    no('<img src="../../secret.key">', "off the page's folder")
    no('<img src="file:///C:/x.png">', "off the page's folder")
    no('<iframe src="logo.png"></iframe>', "<iframe> element", names=["logo.png"])
    no("<script>fetch('http://localhost:8000/api/me')</script>", "fetch()")
    no("<script src='https://cdn.jsdelivr.net/npm/gsap@3/dist/NoSuchPlugin.min.js'></script>", "not one of GSAP's files")
    with pytest.raises(motion.MotionError, match="no timeline"):
        motion.check_page(PAGE.replace('window.__timelines["main"] = tl;', ""), 320, 180, 1)
    with pytest.raises(motion.MotionError, match="too much for one render"):
        motion.page_budget(PAGE, 3840, 2160, 90, 60)


def test_an_html_op_is_checked_before_it_is_queued(client):
    me = register(client)
    still = item(client, me, "Still", "image", "still.png", ["-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1"])
    post = lambda **body: client.post("/api/edit/film", json=body)
    jobs_before = len(client.app.state.db.all("SELECT id FROM jobs"))
    for body, words in ((dict(html=PAGE.replace("__MORE__", ""), width=320, height=180, duration=2), "data-duration"),
                        (dict(html=PAGE.replace("__MORE__", '<img src="x.png">'), width=320, height=180, duration=1,
                              media=[{"name": "y.png", "item": still}]), "x.png is not one of"),
                        (dict(html=PAGE, width=321, height=180, duration=1), "even"),
                        (dict(html=PAGE, width=320, height=180, duration=1, format="avi"), "format one of"),
                        (dict(html=PAGE, width=320, height=180, duration=1, media=[{"name": "../x.png", "item": still}]), "bare name")):
        response = post(op="html", **body)
        assert response.status_code == 400 and words in response.json()["detail"], response.text
    assert len(client.app.state.db.all("SELECT id FROM jobs")) == jobs_before


@pytest.mark.skipif(not motion.status()["ready"], reason="HyperFrames is not installed here")
def test_an_html_op_draws_the_page_and_files_a_still_as_a_picture(client):
    me = register(client)
    logo = item(client, me, "Logo", "image", "logo.png", ["-f", "lavfi", "-i", "color=c=orange:s=64x64", "-frames:v", "1"])
    page = PAGE.replace("__MORE__", '<img src="logo.png" style="position:absolute;right:10px;top:10px">')
    found = made(client, client.post("/api/edit/film", json={"op": "html", "html": page, "width": 320, "height": 180,
                                                             "duration": 1, "format": "png", "media": [{"name": "logo.png", "item": logo}]}))[0]
    assert found["kind"] == "image" and (found["context"]["width"], found["context"]["height"]) == (320, 180)


def test_the_agent_writes_a_command_and_a_page_with_its_film_tool(client, monkeypatch):
    me = register(client)
    clip = item(client, me, "Clip", "video", "clip.mp4", ["-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=2", "-pix_fmt", "yuv420p"])
    client.app.state.db.run("UPDATE generations SET about = 'A blue frame.' WHERE id = ?", (clip,))   # NeuralCore needn't look at it
    command = json.dumps({"argv": ["-i", "a.mp4", "-vf", "drawtext=fontfile=Anton-Regular.ttf:text='Take 3\\: go':fontsize=20",
                                   "-pix_fmt", "yuv420p", "slate.mp4"],
                          "inputs": [{"name": "a.mp4", "item": clip}], "outputs": [{"name": "slate.mp4"}], "reason": "a slate"})
    calls = [{"tool": "film", "op": "ffmpeg", "settings": command}]
    if motion.status()["ready"]:   # the page comes in "value", as it is, beside its settings
        calls.append({"tool": "film", "op": "html", "settings": json.dumps({"width": 320, "height": 180, "duration": 1, "format": "png"}),
                      "value": PAGE.replace("__MORE__", "")})
    seen = hosted(monkeypatch, client, *calls, {"tool": "finish", "reply": "Done.", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "slate it"})
    told = [m["content"] for m in seen[-1] if m["role"] == "user" and m["content"].startswith("Result of film")]
    assert len(told) == len(calls) and '"output": "slate.mp4"' in told[0] and '"kind": "video"' in told[0]
    assert all('"kind": "image"' in t for t in told[1:])
