"""A result's poster is made once, and a page never reads half of one.

Under load the canvas loading a just-made item got a 500 from /api/library/<id>/poster: the studio makes the poster as
the result is filed (media.make_poster_soon) while the canvas asks for it, and up to three ffmpegs wrote the same file
at once; a reader in between got an empty or half-written JPEG (and on Windows a file being sent can't be deleted)."""

import asyncio
import threading

from scene import media
from test_api import register


async def _picture(folder, name="kite.png"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    await media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1600x1600", "-frames:v", "1", path)
    return path


def test_a_poster_asked_for_by_many_at_once_is_made_once_and_read_whole(tmp_path, monkeypatch):
    made = []
    real = media._make_poster

    async def counted(video, target):
        made.append(target)
        return await real(video, target)
    monkeypatch.setattr(media, "_make_poster", counted)

    async def scene():
        picture = await _picture(tmp_path)
        target = media.poster_path(picture)
        seen, stop = [], threading.Event()

        def reader():   # what a browser would be sent, read the whole time the poster is being made
            while not stop.is_set():
                try:
                    data = target.read_bytes()
                except (FileNotFoundError, PermissionError):
                    continue
                if not data.endswith(b"\xff\xd9"):
                    seen.append(len(data))
        watching = threading.Thread(target=reader)
        watching.start()
        try:
            async def asks(after):
                await asyncio.sleep(after)
                return await media.poster(picture)
            given = await asyncio.gather(media.make_poster_soon(picture), *[asks(n * 0.02) for n in range(8)])
        finally:
            stop.set()
            watching.join()
        return target, given[1:], seen

    target, given, seen = asyncio.run(scene())
    assert made == [target]   # once, not once per request (it was six times for eight requests)
    assert given == [target] * 8 and target.read_bytes()[:2] == b"\xff\xd8"
    assert seen == []         # never an empty or half-written picture
    assert not media._partial(target).exists() and not any(media._making.values())


def test_a_poster_older_than_its_video_is_made_again_beside_it(tmp_path):
    import os

    async def scene():
        picture = await _picture(tmp_path)
        first = await media.poster(picture)
        before = first.read_bytes()
        os.utime(first, (picture.stat().st_mtime - 5,) * 2)   # the file changed after its poster was made
        again = await media.poster(picture)
        return first, again, before
    first, again, before = asyncio.run(scene())
    assert again == first and again.read_bytes()[:2] == b"\xff\xd8" and media.fresh(again, tmp_path / "kite.png")
    assert not media._partial(again).exists()


def test_a_poster_that_cant_be_put_in_place_yet_is_a_503_to_ask_again(client, monkeypatch):
    me = register(client)
    folder = client.app.state.outputs.folder(me["id"])
    asyncio.run(_picture(folder))
    item = client.app.state.db.run(
        "INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
        "VALUES (?, 'upload/file', 'image', 'kite', 'kite.png', '{}', '{}', 1)", (me["id"],))

    async def busy(video):
        raise PermissionError("[WinError 32] being sent")
    monkeypatch.setattr(media, "poster", busy)
    response = client.get("/api/library/%d/poster" % item)
    assert response.status_code == 503 and response.headers["retry-after"] == "1"
    monkeypatch.undo()
    assert client.get("/api/library/%d/poster" % item).content[:2] == b"\xff\xd8"


def test_a_frame_is_written_whole_and_put_in_place(tmp_path):
    async def scene():
        folder = tmp_path / "v"
        folder.mkdir()
        clip = folder / "clip.mp4"
        await media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color=red:s=64x64:r=24:d=1", "-pix_fmt", "yuv420p", clip)
        target = folder / "clip.mp4.5.jpg"
        return target, await media.frame_at(clip, 0.5, target), await media.frame_at(clip, 30, folder / "late.jpg")
    target, made, late = asyncio.run(scene())
    assert made == target and target.read_bytes()[:2] == b"\xff\xd8" and not media._partial(target).exists()
    assert late is None and not (tmp_path / "v" / "late.partial.jpg").exists()
