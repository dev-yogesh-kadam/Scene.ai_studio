"""Each tool says plainly what is missing when its program or model is not there (ffmpeg, Node.js, HyperFrames, the
embedding API), and a program that hangs on a file is stopped: a job fails with a reason, never waits for good."""

import asyncio
import builtins
import sys

import httpx
import pytest

from scene import detect, film, media, montage, motion, reframe, semantic, transcript


@pytest.fixture
def no_ffmpeg(monkeypatch):
    """A machine without ffmpeg: imageio-ffmpeg not installed and none on the PATH."""
    real = builtins.__import__

    def without(name, *args, **kwargs):
        if name == "imageio_ffmpeg":
            raise ImportError(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without)
    monkeypatch.setattr(media.shutil, "which", lambda name: None)


def test_without_ffmpeg_every_tool_says_it_is_not_installed(no_ffmpeg, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00" * 64)
    for made in (lambda: detect.beats(clip), lambda: detect.shots(clip), lambda: reframe.crop(clip, "portrait", tmp_path / "o.mp4"),
                 lambda: film.speech_runs(clip, [(0, 1)]), lambda: montage.gif(clip, tmp_path / "o.gif"),
                 lambda: film.trim(clip, 24, tmp_path / "t.mp4")):
        with pytest.raises(media.MediaError, match="ffmpeg is not installed"):
            asyncio.run(made())


def test_without_node_or_hyperframes_a_motion_render_says_what_to_install(monkeypatch, tmp_path):
    monkeypatch.setattr(motion, "node_path", lambda configured="": None)
    assert motion.status() == {"ready": False, "detail": "Node.js 22 or newer is not installed on the machine that runs Scene.ai."}
    with pytest.raises(motion.MotionError, match="Node.js 22"):
        asyncio.run(motion.render_page("<html></html>", 320, 180, 1, tmp_path / "o.mp4"))
    monkeypatch.setattr(motion, "node_path", lambda configured="": sys.executable)
    monkeypatch.setattr(motion, "CLI", tmp_path / "missing" / "hyperframes.mjs")
    assert "npm install" in motion.status()["detail"]
    with pytest.raises(motion.MotionError, match="HyperFrames is not installed"):
        asyncio.run(motion.render_project(tmp_path, tmp_path / "o.mp4"))
    assert not list(tmp_path.glob("o*"))


def test_a_transcript_that_is_not_one_is_refused_with_a_reason():
    for text, words in (("", "empty"), ("{not json", "not valid JSON"), ('{"lines": 3}', "segments")):
        with pytest.raises(transcript.TranscriptError, match=words):
            transcript.parse(text)


def test_the_embedding_api_unreachable_is_a_search_error_not_a_crash(monkeypatch):
    def unreachable(*args, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(semantic.httpx, "post", unreachable)   # nothing is sent anywhere
    for provider in ("voyage", "azure_openai"):
        with pytest.raises(semantic.SemanticError, match="could not be reached"):
            semantic.Embedder(provider, "k", "https://example.invalid").embed(["a red car"], query=True)
    monkeypatch.setattr(semantic.httpx, "post", lambda *a, **k: httpx.Response(200, text="<html>a login page</html>"))
    with pytest.raises(semantic.SemanticError, match="not a list of vectors"):
        semantic.Embedder("voyage", "k").embed(["a red car"])
    with pytest.raises(semantic.SemanticError, match="voyage, azure_openai or fake"):
        semantic.Embedder("openai")


@pytest.mark.parametrize("module", [detect, film])
def test_ffmpeg_hanging_on_a_sound_is_stopped(module, monkeypatch, tmp_path):
    real = asyncio.create_subprocess_exec

    async def hangs(program, *args, **options):   # an ffmpeg that never finishes reading
        return await real(sys.executable, "-c", "import time; time.sleep(60)", **options)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", hangs)
    monkeypatch.setattr(module, "READ_LIMIT", 1)
    read = module._bands(tmp_path / "song.mp3") if module is detect else module._envelope(tmp_path / "talk.wav")
    with pytest.raises(media.MediaError, match="stopped responding"):
        asyncio.run(read)
