"""A video in another shape (reframe.py): cropped, or extended with the new space filled in by Wan VACE, prepared and
joined on this machine around the render."""

import asyncio

from scene import reframe
from scene.film import frames_of
from scene.media import probe
from test_api import register
from test_film_api import item, made


def test_the_parts_wan_fills_in_are_its_lengths_and_cover_the_video():
    assert reframe.parts(81) == [(0, 81, 81)]
    assert reframe.parts(112) == [(0, 81, 81), (81, 31, 33)]           # 31 frames sent as 33 (4n+1), the last one held
    assert sum(f for _, f, _ in reframe.parts(500)) == 500 and all((s - 1) % 4 == 0 for _, _, s in reframe.parts(500))
    assert reframe.box(1280, 720, (480, 832)) == (0, 280, 480, 270)   # 16:9 fits the width of 9:16, centred
    assert reframe.box(720, 1280, (832, 480)) == (280, 0, 270, 480)


def test_a_video_is_cropped_and_extended_to_a_new_shape(client):
    me = register(client)
    clip = item(client, me, "Clip", "video", "wide.mp4", ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=2", "-f", "lavfi", "-i",
                                                          "sine=f=440:d=2", "-shortest", "-pix_fmt", "yuv420p"])
    post = lambda **body: client.post("/api/edit/film", json=body)
    cropped = made(client, post(op="reframe", video=clip, shape="portrait", x=0.2))[0]
    assert (cropped["context"]["width"], cropped["context"]["height"]) == (1080, 1920)

    prepared = made(client, post(op="outpaint_prep", video=clip, shape="square"))
    assert len(prepared) == 2                                           # one part (2 s) and its mask
    assert prepared[0]["context"]["box"] == [0, 140, 640, 360] and prepared[0]["context"]["parts"] == [{"frames": 32, "sent": 33}]
    folder = client.app.state.outputs.folder(me["id"])
    part, mask = (folder / p["filename"] for p in prepared)
    assert asyncio.run(frames_of(part)) == asyncio.run(frames_of(mask)) == 33
    # the render server would fill the part in; the part itself stands in for what it makes
    joined = made(client, post(op="outpaint_join", video=clip, parts=[prepared[0]["id"]], shape="square"))[0]
    found = asyncio.run(probe(folder / joined["filename"]))
    assert (found["width"], found["height"], found["audio"]) == (1080, 1080, True)
    assert asyncio.run(frames_of(folder / joined["filename"])) == 48   # as long as the video, to the frame

    assert post(op="reframe", video=clip, shape="16:10").status_code == 400
    assert post(op="outpaint_join", video=clip, parts=[], shape="square").status_code == 400


def test_the_outpaint_workflow_takes_the_part_and_its_mask(client):
    register(client)
    form = client.get("/api/workflows/video/video_outpaint_wan_vace").json()
    text = str(form)
    assert "299:file" in text and "303:file" in text and "Change shape" in form["title"]
