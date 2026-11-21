"""A video in another shape (reframe.py): cropped on this machine, free and quick.

(Extending a video into a new shape, the new space filled in, is a provider's video model that edits a clip, as the
capabilities say (test_providers.py). The parts and masks once made here for ComfyUI's Wan VACE went with ComfyUI.)"""

import asyncio

from scene import reframe
from scene.media import probe
from test_api import register
from test_film_api import item, made


def test_a_picture_is_fitted_inside_a_shape_centred():
    assert reframe.box(1280, 720, (480, 832)) == (0, 280, 480, 270)   # 16:9 fits the width of 9:16, centred
    assert reframe.box(720, 1280, (832, 480)) == (280, 0, 270, 480)
    assert reframe.shape_of("square") == ((1080, 1080), (640, 640))


def test_a_video_is_cropped_to_a_new_shape(client):
    me = register(client)
    clip = item(client, me, "Clip", "video", "wide.mp4", ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=2", "-f", "lavfi", "-i",
                                                          "sine=f=440:d=2", "-shortest", "-pix_fmt", "yuv420p"])
    post = lambda **body: client.post("/api/edit/film", json=body)
    cropped = made(client, post(op="reframe", video=clip, shape="portrait", x=0.2))[0]
    assert (cropped["context"]["width"], cropped["context"]["height"]) == (1080, 1920)
    found = asyncio.run(probe(client.app.state.outputs.folder(me["id"]) / cropped["filename"]))
    assert (found["width"], found["height"], found["audio"]) == (1080, 1920, True)   # with the video's sound
    assert post(op="reframe", video=clip, shape="16:10").status_code == 400


def test_the_comfyui_outpaint_ops_are_gone(client):
    me = register(client)
    clip = item(client, me, "Clip", "video", "wide.mp4", ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=1", "-pix_fmt", "yuv420p"])
    for op in ("outpaint_prep", "outpaint_join"):
        assert client.post("/api/edit/film", json={"op": op, "video": clip, "shape": "square"}).status_code == 400, op
