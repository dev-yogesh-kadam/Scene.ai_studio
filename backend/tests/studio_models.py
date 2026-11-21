"""The models every test studio is given (conftest.client): a Scene provider played by fake_v1.FakeV1 (no port is
opened), with models shaped like Studio_automation's, so a test makes videos, pictures and sounds the way the studio
does now, with no ComfyUI. Each is offered as a workflow "<folder>/@<id>" (providers/workflows.py):

    video/@seedance_2_5     a video: prompt, 4-30 s, 480p/720p/1080p, shape, sound, first and last frame, up to 9
                            reference pictures, a reference video it edits. Chains long videos (a first frame).
    video/@kling_4_0        a video with no references: prompt, 3-15 s, 720p/1080p, shape, a first frame.
    image/@nano_banana_pro  a picture: prompt, 1K/2K/4K, shape, up to 6 reference pictures.
    image/@seedream_5       a picture from words alone: prompt, 2K/4K, shape.
    audio/@speech           a voiceover: the words, a voice id.
    audio/@music            music: a description, lyrics, 10-120 s.
    audio/@sound_effect     a sound effect: a description, 1-22 s.
    video/@lip_sync         a clip's lips to a voice track: a video and an audio file (its "Voice track").
    upscaler/@upscale_video a video made larger: the video, a factor.
    image/@upscale_image    a picture made larger: the picture, a factor.

`install(app_state)` adds the provider and its key to the registry with these models and points the router at the
fake; it returns the FakeV1, whose `calls` say what was asked and whose `jobs` what it made."""

from fake_v1 import FakeV1
from scene.providers import registry
from scene.providers.v1 import V1

KEY = "sa_live_tests0001"
BASE = "http://fake-v1"


def _file(kind, **extra):
    return dict({"type": "string", "x-file": kind}, **extra)


def _files(kind, most):
    return {"type": "array", "maxItems": most, "items": {"type": "string", "x-file": kind}}


def _video(model_id, name, seconds, resolutions, shapes, refs=0, reference_video=False, last_frame=True, best_for=""):
    properties = {"prompt": {"type": "string"},
                  "duration": {"type": "integer", "minimum": seconds[0], "maximum": seconds[1], "default": min(5, seconds[1])},
                  "resolution": {"type": "string", "enum": list(resolutions), "default": resolutions[0]},
                  "aspect_ratio": {"type": "string", "enum": list(shapes), "default": shapes[0]},
                  "sound": {"type": "boolean", "default": False},
                  "first_frame": _file("image")}
    if last_frame:
        properties["last_frame"] = _file("image")
    if refs:
        properties["reference_images"] = _files("image", refs)
    if reference_video:
        properties["reference_video"] = _file("video", description="A clip to continue or edit (cite as @Video1).")
    return {"id": model_id, "name": name, "capability": "text_to_video", "best_for": best_for,
            "input_schema": {"type": "object", "required": ["prompt"], "properties": properties},
            "limits": {"seconds": {"min": seconds[0], "max": seconds[1]}, "resolutions": list(resolutions),
                       "aspect_ratios": list(shapes), "max_reference_images": refs, "frames": ["first", "last"] if last_frame else ["first"],
                       "sound": "choice", "reference_video": reference_video, "reference_video_edits": reference_video},
            "pricing": {"unit": "second", "by": "resolution", "credits": {r: 10 * (n + 1) for n, r in enumerate(resolutions)}},
            "typical_seconds": 120, "can_cancel": False}


def _image(model_id, name, resolutions, refs=0, best_for=""):
    properties = {"prompt": {"type": "string"},
                  "resolution": {"type": "string", "enum": list(resolutions), "default": resolutions[0]},
                  "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9", "9:16"], "default": "1:1"}}
    if refs:
        properties["reference_images"] = _files("image", refs)
    return {"id": model_id, "name": name, "capability": "image", "best_for": best_for,
            "input_schema": {"type": "object", "required": ["prompt"], "properties": properties},
            "limits": {"resolutions": list(resolutions), "aspect_ratios": ["1:1", "16:9", "9:16"], "max_reference_images": refs},
            "pricing": {"unit": "image", "by": "resolution", "credits": {r: 5 * (n + 1) for n, r in enumerate(resolutions)}},
            "typical_seconds": 30, "can_cancel": False}


def _tool(model_id, name, capability, properties, required, pricing=None, best_for=""):
    return {"id": model_id, "name": name, "capability": capability, "best_for": best_for,
            "input_schema": {"type": "object", "required": list(required), "properties": properties},
            "limits": {}, "pricing": pricing or {"unit": "job", "by": None, "credits": None}, "typical_seconds": 30,
            "can_cancel": False}


def _clips(model, most, each, together):
    """A model's limits on its reference videos, as Studio_automation says them (Seedance 2.5: 10 of 1.8-30 s, 30.2 s in all)."""
    model["limits"].update(max_reference_videos=most, reference_clips={"max_clips": most, "seconds_each": list(each),
                                                                         "seconds_together": together})
    return model


MODELS = [
    _clips(_video("seedance_2_5", "Seedance 2.5", (4, 30), ("480p", "720p", "1080p"), ("16:9", "9:16", "1:1"), refs=9,
                  reference_video=True, best_for="The default for every video: cinematic multi-shot scenes, many references."),
           10, (1.8, 30), 30.2),
    _video("kling_4_0", "Kling 4.0", (3, 15), ("720p", "1080p"), ("16:9", "9:16"), last_frame=False,
           best_for="Clips from words or a first frame."),
    _image("nano_banana_pro", "Nano Banana Pro", ("1K", "2K", "4K"), refs=6, best_for="Pictures that keep a character."),
    _image("seedream_5", "Seedream 5", ("2K", "4K"), best_for="Pictures from words alone."),
    _tool("speech", "Voiceover", "speech", {"text": {"type": "string"}, "voice_id": {"type": "string", "default": ""}}, ["text"]),
    _tool("music", "Music", "music", {"prompt": {"type": "string"}, "lyrics": {"type": "string", "default": ""},
                                      "duration": {"type": "integer", "minimum": 10, "maximum": 120, "default": 30}}, ["prompt"],
          pricing={"unit": "second", "by": None, "credits": 2}),
    _tool("sound_effect", "Sound effect", "sound_effect", {"prompt": {"type": "string"},
                                                           "duration": {"type": "integer", "minimum": 1, "maximum": 22, "default": 5}}, ["prompt"]),
    _tool("lip_sync", "Lip sync", "lip_sync", {"video": _file("video"), "audio": _file("audio")}, ["video", "audio"]),
    _tool("upscale_video", "Upscale", "upscale_video", {"video": _file("video"), "factor": {"type": "number", "enum": [2, 4], "default": 2}},
          ["video"]),
    _tool("upscale_image", "Image upscale", "upscale_image", {"image": _file("image"), "factor": {"type": "number", "enum": [2, 4], "default": 2}},
          ["image"]),
]
# What each model's output is, for the fake's answers (fake_v1.KINDS by capability).
OUTPUT_KINDS = {"text_to_video": ("video", "video/mp4", ".mp4"), "lip_sync": ("video", "video/mp4", ".mp4"),
                "upscale_video": ("video", "video/mp4", ".mp4"), "image": ("image", "image/png", ".png"),
                "upscale_image": ("image", "image/png", ".png"), "speech": ("audio", "audio/mpeg", ".mp3"),
                "music": ("audio", "audio/mpeg", ".mp3"), "sound_effect": ("audio", "audio/mpeg", ".mp3")}


def install(state, models=None):
    """Give the test studio its provider: a "Test provider" with one live key and `models` (MODELS), the router pointed
    at the fake. Returns the FakeV1."""
    import fake_v1
    fake_v1.KINDS.update(OUTPUT_KINDS)
    fake = FakeV1(models=list(models or MODELS), live=(KEY,))
    db = state.db
    provider_id = registry.add_provider(db, "scene_provider_v1", "Test provider", BASE)
    key_id = registry.add_key(db, provider_id, KEY, "tests", status="ok",
                              info={"key": {"mode": "live", "max_concurrent": 4}})
    registry.save_models(db, provider_id, key_id, fake.models)
    state.router.adapters[provider_id] = V1(BASE, http=fake.client())
    state.router.forget()
    if state.catalog.providers is not None:
        state.catalog.providers.read_at = 0.0   # read again on the next look
    return fake
