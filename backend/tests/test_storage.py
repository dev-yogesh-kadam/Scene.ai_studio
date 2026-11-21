"""Where the media are kept (storage.py): this machine's folders (LocalStorage), and the in-memory fake the tests can
use in their place (FakeStorage). Both keep the same promises; local folders are the only storage the studio opens."""

import json
import time
from types import SimpleNamespace

import pytest

from scene import media
from scene.config import load_settings
from scene.storage import FakeStorage, LocalStorage, StorageError, open_storage


def roots(tmp_path):
    out = tmp_path / "outputs"
    return {"outputs": out, "posters": out, "kit": tmp_path / "assets", "showcase": tmp_path / "showcase"}


@pytest.mark.parametrize("make", [LocalStorage, FakeStorage])
def test_what_every_storage_does(tmp_path, make):
    store = make(roots(tmp_path))
    store.save("outputs", "ada/Film (1)/shot 1.mp4", b"0123456789")
    assert store.exists("outputs", "ada/Film (1)/shot 1.mp4") and store.size("outputs", "ada/Film (1)/shot 1.mp4") == 10
    assert store.read_bytes("outputs", "ada/Film (1)/shot 1.mp4") == b"0123456789"
    assert [k for k, _, _ in store.list("outputs", "ada")] == ["ada/Film (1)/shot 1.mp4"]
    assert store.local("outputs", "ada/Film (1)/shot 1.mp4").read_bytes() == b"0123456789"
    source = tmp_path / "made.png"
    source.write_bytes(b"png")
    store.save("kit", "1/made.png", source)
    assert store.read_bytes("kit", "1/made.png") == b"png" and not store.exists("outputs", "1/made.png")
    store.delete("outputs", "ada/Film (1)/shot 1.mp4")
    assert not store.exists("outputs", "ada/Film (1)/shot 1.mp4")
    store.delete("outputs", "ada/Film (1)/shot 1.mp4")   # deleting what is gone is no error
    for bad in ("../secret.key", "/etc/passwd", "a/../../b", ""):
        with pytest.raises(StorageError):
            store.save("outputs", bad, b"x")


def test_a_poster_is_a_kind_of_its_own_inside_the_outputs(tmp_path):
    store = LocalStorage(roots(tmp_path))
    store.save("outputs", "ada/a.mp4", b"v")
    store.save("posters", "ada/.posters/a.mp4.jpg", b"p")
    assert [k for k, _, _ in store.list("outputs")] == ["ada/a.mp4"]
    assert [k for k, _, _ in store.list("posters")] == ["ada/.posters/a.mp4.jpg"]


def test_only_local_storage_is_opened(tmp_path):
    assert isinstance(open_storage(SimpleNamespace(storage_backend="local"), roots(tmp_path)), LocalStorage)
    assert isinstance(open_storage(SimpleNamespace(storage_backend=""), roots(tmp_path)), LocalStorage)
    with pytest.raises(StorageError, match="only 'local' is supported"):   # a stale setting stops the studio at start
        open_storage(SimpleNamespace(storage_backend="azure"), roots(tmp_path))


def test_a_retired_azure_setting_is_ignored_with_a_warning(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"azure_storage_container": "scene"}), encoding="utf-8")
    monkeypatch.setenv("SCENE_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("SCENE_AZURE_STORAGE_ACCOUNT_URL", "https://example.invalid")
    settings = load_settings(config)
    told = [w for w in settings.warnings if "no longer read" in w]
    assert len(told) == 2 and not hasattr(settings, "azure_storage_container")


def test_a_new_results_poster_has_a_webp_copy_for_browsers_that_take_it(client):
    from PIL import Image
    from conftest import a_job
    from test_api import register
    me = register(client)
    state = client.app.state
    folder = state.outputs.folder(me["id"])
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "made.png"
    Image.new("RGB", (640, 360), "teal").save(target)
    a_job(state.db, "jwebp", me["id"])
    state.jobs._record({"user_id": me["id"], "id": "jwebp", "project_id": None, "workflow": "image/x", "name": "Made",
                        "summary": "", "settings": {}, "started": time.time()}, "image", target, {})
    row = state.db.one("SELECT id, filename FROM generations WHERE job_id = 'jwebp'")
    webp = media.webp_of(media.poster_path(folder / row["filename"]))
    until = time.time() + 10
    while not webp.is_file():
        assert time.time() < until, "no WebP copy was made"
        time.sleep(0.05)
    taken = client.get("/api/library/{}/poster".format(row["id"]), headers={"Accept": "image/avif,image/webp,*/*"})
    assert taken.status_code == 200 and taken.headers["content-type"] == "image/webp" and taken.headers["vary"] == "Accept"
    plain = client.get("/api/library/{}/poster".format(row["id"]), headers={"Accept": "image/jpeg,*/*"})
    assert plain.status_code == 200 and plain.headers["content-type"] == "image/jpeg"
    assert len(taken.content) < len(plain.content)
