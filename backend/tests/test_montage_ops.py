"""The finding and cutting ops done without a model (detect.py, montage.py), on real ffmpeg with made-up clips and
sounds, and as film ops queued through POST /api/edit/film: checked before anything is queued, their files filed, and
what save_to asks kept in the run."""

import asyncio
import json

from scene import detect, media, montage, runs
from test_api import register
from test_film_api import item, made


def run(coro):
    return asyncio.run(coro)


def colours(path, parts, size="160x90"):
    """A clip of plain colours one after another: parts is [(colour, seconds)]; each change is a hard cut."""
    graph, labels = [], ""
    for i, (colour, seconds) in enumerate(parts):
        graph.append("color=c={}:s={}:r=24:d={}[c{}]".format(colour, size, seconds, i))
        labels += "[c{}]".format(i)
    graph.append("{}concat=n={}:v=1:a=0,format=yuv420p[v]".format(labels, len(parts)))
    run(media._ffmpeg("-loglevel", "error", "-filter_complex", ";".join(graph), "-map", "[v]", "-c:v", "libx264", path))
    return path


def clicks(path, bpm=120, seconds=12):
    """A click on every beat, so the tempo is known."""
    beat = 60.0 / bpm
    expr = "if(lt(mod(t,{b}),0.02),sin(2*PI*1000*t),0)".format(b=beat)
    run(media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "aevalsrc='{}':s=22050:d={}".format(expr, seconds), path))
    return path


def size_of(path):
    return run(media.probe(path))["width"], run(media.probe(path))["height"]


# ---------------------------------------------------------------- the work itself

def test_shots_finds_each_hard_cut_and_the_spans_between(tmp_path):
    clip = colours(tmp_path / "three.mp4", [("red", 1.5), ("blue", 1.0), ("green", 2.0)])
    found = run(detect.shots(clip))
    assert len(found["shots"]) == 3
    assert [round(c, 1) for c in found["cuts"]] == [1.5, 2.5]
    assert found["shots"][0]["start"] == 0 and abs(found["shots"][-1]["end"] - 4.5) < 0.1
    assert len(run(detect.shots(colours(tmp_path / "one.mp4", [("red", 2.0)])))["shots"]) == 1


def test_keyframe_times_one_way_at_a_time():
    spread = [t for t, _ in montage.keyframe_times(10, 24, count=3)]
    assert spread[0] == 0.0 and abs(spread[-1] - (10 - 1 / 24)) < 1e-3 and len(spread) == 3   # first to last frame
    assert [t for t, _ in montage.keyframe_times(10, 24, every=4)] == [0.0, 4.0, 8.0]
    assert [t for t, _ in montage.keyframe_times(10, 24, times=[2, 12])] == [2.0]   # past the end: dropped
    middle = montage.keyframe_times(10, 24, shots=[{"n": 7, "start": 2, "end": 4}], pick="middle")
    assert middle == [(3.0, {"shot": 7})]
    last = montage.keyframe_times(10, 24, shots=[[0, 2]], pick="last")
    assert abs(last[0][0] - (2 - 1 / 24)) < 1e-3 and last[0][1] == {"shot": 1}   # times are kept to the millisecond


def test_keyframes_keep_a_clean_frame_and_a_captioned_copy_with_the_label_below(tmp_path):
    clip = colours(tmp_path / "c.mp4", [("red", 1.0), ("blue", 1.0)], size="320x180")
    made_ = run(montage.keyframes(clip, [(0.5, {"shot": 1}), (1.5, {"shot": 2})], tmp_path / "k.jpg",
                                  captions=["Maya, kitchen, wide", "Ravi, door"]))
    assert len(made_) == 2
    (clean, facts, captioned), _ = made_
    assert facts == {"at": 0.5, "shot": 1}
    w, h = size_of(clean)
    cw, ch = size_of(captioned)
    assert (w, h) == (320, 180) and cw == w and ch > h   # the strip is added below; the picture itself is untouched


def test_a_board_is_laid_out_so_video_models_take_it():
    assert montage.board_layout(6, 16 / 9) == (2, 3)
    assert montage.board_layout(6, 9 / 16) == (3, 2)
    for panels in montage.BOARD_PANELS:
        for ratio in (16 / 9, 9 / 16, 1.0):
            plan = montage.board_plan(panels, panels, ratio)
            for _, _, across, down in plan:
                assert montage.BOARD_RATIO[0] <= across * ratio / down <= montage.BOARD_RATIO[1], (panels, ratio)


def test_a_board_of_six_wide_stills_is_numbered_and_within_shape(tmp_path):
    clip = colours(tmp_path / "c.mp4", [(c, 0.5) for c in ("red", "blue", "green", "white", "yellow", "purple")], size="320x180")
    made_ = run(montage.board([(clip, 0.25 + 0.5 * i) for i in range(6)], tmp_path / "b.png", 6, True))
    board = made_["boards"][0]
    assert (board["across"], board["down"]) == (2, 3) and board["stills"] == [1, 6]
    w, h = size_of(board["file"])
    assert 0.4 <= w / h <= 2.5


def test_beats_find_the_tempo_of_a_click_track_and_cut_points_follow_them(tmp_path):
    found = run(detect.beats(clicks(tmp_path / "clicks.wav", bpm=120)))
    assert abs(found["tempo"] - 120) < 4
    assert len(found["beats"]) >= 18
    points = detect.cut_points(found["beats"], 3, every=2)
    assert len(points) == 4 and points == found["beats"][0:8:2][:4]


def test_gif_and_multicam_keep_their_promises(tmp_path):
    clip = colours(tmp_path / "c.mp4", [("red", 1.0), ("blue", 1.0)], size="320x180")
    gif = run(montage.gif(clip, tmp_path / "loop.gif", fps=10, width=160))
    assert gif["width"] == 160
    cut = run(montage.multicam(clip, [{"at": 1.0, "camera": "close"}], tmp_path / "mc.mp4"))
    assert (cut["width"], cut["height"]) == (320, 180)   # a punch-in never changes the shape


# ---------------------------------------------------------------- queued as film ops

def test_the_new_film_ops_run_and_keep_what_save_to_asks_in_the_run(client):
    me = register(client)
    db = client.app.state.db
    clip = item(client, me, "Clip", "video", "clip.mp4", ["-f", "lavfi", "-i", "color=c=red:s=320x180:r=24:d=1", "-f", "lavfi",
                                                          "-i", "color=c=blue:s=320x180:r=24:d=1", "-filter_complex",
                                                          "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-pix_fmt", "yuv420p"])
    song = item(client, me, "Song", "audio", "song.wav", ["-f", "lavfi", "-i",
                "aevalsrc='if(lt(mod(t,0.5),0.02),sin(2*PI*1000*t),0)':s=22050:d=8"])
    post = lambda **body: client.post("/api/edit/film", json=body)

    shots = made(client, post(op="shots", video=clip, save_to="/scene1/shots", run="s2v-1"), run="s2v-1")[0]
    assert shots["kind"] == "text" and shots["context"]["count"] == 2
    assert runs.read(db, me["id"], "s2v-1", "/scene1/shots/2")["value"]["start"] > 0.9

    frames = made(client, post(op="keyframes", video=clip, shots=[[0, 1], [1, 2]], pick="middle",
                               save_to="/continuity/recall/keyframes", run="s2v-1"), run="s2v-1")
    assert len(frames) == 4   # a clean frame and a captioned copy of each shot
    assert {f["name"] for f in frames} >= {"Keyframe 0.50 s", "Keyframe 1.50 s, captioned"}
    kept = runs.read(db, me["id"], "s2v-1", "/continuity/recall/keyframes/2/keyframe")["value"]
    assert kept["shot"] == 2 and kept["url"].startswith("$state:/assets/") and kept["item"] in [f["id"] for f in frames]
    assert runs.read(db, me["id"], "s2v-1", "/continuity/recall/keyframes/1/keyframe_captioned")["value"]["item"]

    board = made(client, post(op="board", stills=[{"video": clip, "at": t} for t in (0.2, 0.6, 1.2, 1.8)], panels=4,
                              save_to="/continuity/board/scene1", run="s2v-1"), run="s2v-1")[0]
    assert board["kind"] == "image" and runs.read(db, me["id"], "s2v-1", "/continuity/board/scene1")["value"]["item"] == board["id"]

    beats = made(client, post(op="beats", audio=song))[0]
    assert abs(beats["context"]["tempo"] - 120) < 4
    assert made(client, post(op="gif", video=clip, width=160))[0]["kind"] == "image"
    assert made(client, post(op="multicam", video=clip, cuts=[{"at": 1.0, "camera": "close", "push": 0.2}]))[0]["kind"] == "video"
    checked = made(client, post(op="audio_check", audio=song))[0]
    assert checked["kind"] == "text" and abs(checked["context"]["length"] - 8) < 0.1
    padded = made(client, post(op="slice", audio=song, f_in=0, f_out=24, pad=2))[0]
    assert padded["context"]["duration"] == 2.0
    cut = made(client, post(op="beat_cut", clips=[clip, clip], audio=song, every=2))[0]
    assert cut["kind"] == "video" and abs(cut["context"]["duration"] - 2.0) < 0.2   # two clips, two beats of 0.5 s each
    logo = item(client, me, "Logo", "image", "logo.png", ["-f", "lavfi", "-i", "color=c=white@0.5:s=64x64,format=rgba", "-frames:v", "1"])
    laid = made(client, post(op="composite", video=clip, overlay=logo, at=0.5, x=0.8, y=0.2, scale=0.25))[0]
    assert laid["kind"] == "video" and laid["context"]["width"] == 320
    styled = made(client, post(op="subtitles", video=clip, lines=[{"start": 0, "end": 2, "text": "Run", "speaker": "maya"}],
                               style={"font": "Poppins", "size": 60, "place": "top", "box": "#000000"}))[0]
    assert styled["kind"] == "video"


def test_the_new_film_ops_are_checked_before_anything_is_queued(client):
    me = register(client)
    clip = item(client, me, "Clip", "video", "clip.mp4", ["-f", "lavfi", "-i", "color=c=red:s=64x64:r=24:d=1", "-pix_fmt", "yuv420p"])
    still = item(client, me, "Still", "image", "still.png", ["-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1"])
    post = lambda **body: client.post("/api/edit/film", json=body)
    jobs_before = len(client.app.state.db.all("SELECT id FROM jobs"))

    def refused(body, words, status=400):
        response = post(**body)
        assert response.status_code == status, response.text
        assert words in response.json()["detail"], response.json()["detail"]

    refused({"op": "keyframes", "video": clip}, "one way")
    refused({"op": "keyframes", "video": clip, "count": 2, "every": 1}, "one way")
    refused({"op": "keyframes", "video": clip, "count": 2, "pick": "best"}, "pick is first, middle or last")
    refused({"op": "keyframes", "video": clip, "count": 99}, "count")
    refused({"op": "board", "stills": [{"image": still}], "panels": 5}, "panels is one of")
    refused({"op": "board", "stills": []}, "the stills")
    refused({"op": "multicam", "video": clip, "cuts": [{"at": 0.5, "camera": "drone"}]}, "a camera of")
    refused({"op": "shots", "video": clip, "threshold": 2}, "threshold")
    refused({"op": "shots", "video": clip, "save_to": "/x"}, "name the run")
    refused({"op": "gif", "video": clip, "save_to": "/x", "run": "r1"}, "save_to keeps")
    refused({"op": "slice", "audio": clip, "f_in": 0, "f_out": 24, "pad": 99}, "pad")
    refused({"op": "subtitles", "video": clip, "lines": [{"start": 0, "end": 1, "text": "Hi"}], "style": {"font": "Nope Sans"}}, "not on this machine")
    refused({"op": "composite", "video": clip, "overlay": 999999}, "not in your library", status=404)
    assert len(client.app.state.db.all("SELECT id FROM jobs")) == jobs_before   # nothing was queued
