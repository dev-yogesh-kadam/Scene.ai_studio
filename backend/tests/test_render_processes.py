"""The programs the studio starts for a render or an edit (HyperFrames with its Chrome and ffmpeg; ffmpeg alone) are
stopped whole when their time is up or their job is cancelled, and what a failed render leaves is taken away: its
temporary folder, Chrome's profile, a half-written video."""

import asyncio
import sys
import time
from pathlib import Path

import pytest

from scene import ffjob, motion

# A stand-in for HyperFrames: it starts a program of its own (as HyperFrames starts Chrome), which beats on a file
# every 0.1 s, says where its TEMP is, and waits.
PARENT = r"""
import os, subprocess, sys, time
open(sys.argv[2], "w").write(os.environ.get("TEMP", ""))
subprocess.Popen([sys.executable, "-c", "import time, sys\nwhile True:\n    open(sys.argv[1], 'w').write(str(time.time()))\n    time.sleep(0.1)", sys.argv[1]])
time.sleep(120)
"""


def beating(heart, seconds=1.0):
    """Whether the started program still beats on its file."""
    before = heart.read_text() if heart.exists() else ""
    time.sleep(seconds)
    return heart.exists() and heart.read_text() != before


def wait_for_file(path, seconds=15):
    end = time.time() + seconds
    while time.time() < end and not (path.exists() and path.read_text()):
        time.sleep(0.1)
    assert path.exists(), "the stand-in never started"


def test_a_render_out_of_time_is_stopped_with_everything_it_started(tmp_path):
    script, heart, said = tmp_path / "parent.py", tmp_path / "heart.txt", tmp_path / "temp.txt"
    script.write_text(PARENT, encoding="utf-8")
    scratch = tmp_path / "render"

    async def go():
        task = asyncio.ensure_future(motion._run([sys.executable, str(script), str(heart), str(said)], tmp_path, timeout=6,
                                                 scratch=scratch))
        while not heart.exists():
            await asyncio.sleep(0.1)
        with pytest.raises(motion.MotionError, match="took longer"):
            await task

    asyncio.run(go())
    assert not beating(heart), "the program the render started is still running"
    assert said.read_text() == str(scratch / "temp")   # Chrome's profile and the like go into the render's own folder


def test_a_cancelled_ffmpeg_job_ends_its_program_and_leaves_no_folder(tmp_path, monkeypatch):
    script, heart, said = tmp_path / "parent.py", tmp_path / "heart.txt", tmp_path / "temp.txt"
    script.write_text(PARENT, encoding="utf-8")
    work = tmp_path / "work"
    # ffmpeg itself starts nothing, so a program that does stands in for it: whatever runs is ended whole
    real = asyncio.create_subprocess_exec

    async def started(program, *args, **options):
        if program == "taskkill":   # stop()'s own
            return await real(program, *args, **options)
        assert options["env"].get("TEMP") and "SCENE_TEST_DATABASE_URL" not in options["env"]   # the studio's variables stay
        return await real(sys.executable, str(script), str(heart), str(said), **options)

    monkeypatch.setattr(ffjob, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", started)

    async def go():
        task = asyncio.ensure_future(ffjob.run(["x"], {}, {}, ["o.mp4"], tmp_path / "out" / "job.txt", 60, work_dir=work))
        while not heart.exists():
            await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert not beating(heart)
    assert list(work.iterdir()) == []                   # the job's folder is gone
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


def test_stop_is_safe_on_a_program_that_has_ended():
    async def go():
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass", **ffjob.own_group())
        await process.wait()
        await ffjob.stop(process)
        return process.returncode

    assert asyncio.run(go()) == 0


@pytest.mark.parametrize("still", [None, 0.5])
def test_a_failed_render_leaves_no_half_written_file_and_no_temporary_folder(tmp_path, monkeypatch, still):
    work, target = tmp_path / "work", tmp_path / "out" / "card.mp4"

    async def failing(command, folder, check=True, timeout=0, scratch=None):
        (Path(scratch) / "temp" / "puppeteer_profile").mkdir(parents=True)   # what Chrome leaves while it runs
        if "render" in command:
            target.write_bytes(b"half a video")             # HyperFrames writes the video where it is asked to
        raise motion.MotionError("HyperFrames could not render this: Chrome crashed")

    monkeypatch.setattr(motion, "_run", failing)
    monkeypatch.setattr(motion, "FONT", tmp_path / "font.woff2")
    (tmp_path / "font.woff2").write_bytes(b"font")
    monkeypatch.setattr(motion, "GSAP_DIST", tmp_path)
    (tmp_path / "gsap.min.js").write_text("", encoding="utf-8")
    with pytest.raises(motion.MotionError, match="Chrome crashed"):
        asyncio.run(motion._produce(lambda project: (project / "index.html").write_text("<html></html>", encoding="utf-8"),
                                    {}, target, 30, "Card", "", work, still=still))
    assert not target.exists() and not target.with_suffix(".png").exists()
    assert list(work.iterdir()) == []


def test_a_failed_project_render_takes_back_the_files_it_had_written(tmp_path, monkeypatch):
    source, work, target = tmp_path / "launch", tmp_path / "work", tmp_path / "out" / "launch.mp4"
    source.mkdir()
    (source / "index.html").write_text('<div data-composition-id="main" data-width="320" data-height="180" data-duration="1">'
                                       "</div>", encoding="utf-8")

    async def checked(project, node):
        return []

    async def failing(command, folder, check=True, timeout=0, scratch=None):
        if "render" in command:
            target.write_bytes(b"half a video")
            raise motion.MotionError("The render took longer than 40 minutes and was stopped.")
        return ""

    monkeypatch.setattr(motion, "status", lambda node="": {"ready": True, "detail": ""})
    monkeypatch.setattr(motion, "_check", checked)
    monkeypatch.setattr(motion, "_run", failing)
    with pytest.raises(motion.MotionError, match="took longer"):
        asyncio.run(motion.render_project(source, target, work_dir=work))
    assert not target.exists() and list(work.iterdir()) == []
