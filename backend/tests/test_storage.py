"""Where the media are kept (storage.py): this machine's folders, or Azure Blob Storage with the folders as its cache.
The fast tests use the in-memory fake; the Azure tests run against Azurite (Microsoft's emulator) when it can be found
(SCENE_TEST_AZURITE: a running one's connection string, or SCENE_AZURITE_BIN: its azurite-blob program, or azurite-blob
on the PATH; npm install -g azurite) and are skipped, saying so, when it can't."""

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from scene import media, storage
from scene.storage import AzureBlobStorage, FakeStorage, LocalStorage, StorageError

AZURITE_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="   # its public dev key


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
    assert storage.kind_and_key(store, tmp_path / "outputs" / "ada" / ".posters" / "a.mp4.jpg") == ("posters", "ada/.posters/a.mp4.jpg")
    assert storage.kind_and_key(store, tmp_path / "assets" / "3" / "x.png") == ("kit", "3/x.png")


@pytest.fixture
def kept_elsewhere(client):
    """The app with its media kept in the fake (as they would be in Azure Blob Storage)."""
    state = client.app.state
    fake = FakeStorage(state.storage.roots)
    state.storage = state.outputs.storage = storage.ACTIVE = fake
    yield fake
    storage.ACTIVE = None


def test_with_the_media_elsewhere_results_are_kept_there_and_served_from_there(client, kept_elsewhere):
    from test_api import register
    from conftest import a_job
    me = register(client)
    state = client.app.state
    folder = state.outputs.folder(me["id"])
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "made.png"
    target.write_bytes(b"\x89PNG made")
    a_job(state.db, "jkept", me["id"])
    job = {"user_id": me["id"], "id": "jkept", "project_id": None, "workflow": "image/x", "name": "Made", "summary": "",
           "settings": {}, "started": time.time()}
    state.jobs._record(job, "text", target, {})
    row = state.db.one("SELECT id, filename FROM generations WHERE job_id = 'jkept'")
    key = "{}/{}".format(folder.name, row["filename"])
    assert kept_elsewhere.read_bytes("outputs", key) == b"\x89PNG made"           # kept where the media are kept
    answer = client.get("/api/library/{}/file".format(row["id"]), follow_redirects=False)
    assert answer.status_code == 307 and answer.headers["location"].startswith("https://fake.blob/outputs/")
    (folder / row["filename"]).unlink()                                         # this machine's copy is only a cache
    assert state.outputs.fetch(folder / row["filename"]).read_bytes() == b"\x89PNG made"
    assert client.delete("/api/library/{}".format(row["id"])).status_code == 200
    assert not kept_elsewhere.exists("outputs", key)                             # deleted there too


def test_with_the_media_elsewhere_neuralcore_files_are_kept_there(client, kept_elsewhere):
    from scene import kit
    from test_api import register
    me = register(client)
    state = client.app.state
    project = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    folder = state.assets_dir / str(me["id"])
    entry = kit.add(state.db, folder, me["id"], project, b"\x89PNG meera", "meera.png", "image", "Meera", tag="character")
    stored = state.db.one("SELECT filename FROM assets WHERE id = ?", (entry,))["filename"]
    assert kept_elsewhere.read_bytes("kit", "{}/{}".format(me["id"], stored)) == b"\x89PNG meera"
    answer = client.get("/api/kit/{}/file".format(entry), follow_redirects=False)
    assert answer.status_code == 307 and "/kit/" in answer.headers["location"]


def test_with_the_media_elsewhere_uploads_renames_moves_and_deletes_follow_there(client, kept_elsewhere):
    """Each step with this machine's copies gone first: they are only a cache, and a new container starts with none."""
    import io
    from PIL import Image
    from test_api import register
    me = register(client)
    state, db = client.app.state, client.app.state.db
    home = state.outputs.folder(me["id"])
    picture = io.BytesIO()
    Image.new("RGB", (64, 36), "teal").save(picture, "PNG")
    png = picture.getvalue()
    film = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    other = client.post("/api/projects", json={"name": "Other"}).json()["id"]
    item = client.post("/api/library/upload", files={"file": ("shot.png", png, "image/png")}, data={"project_id": str(film)}).json()
    filename = lambda: db.one("SELECT filename FROM generations WHERE id = ?", (item["id"],))["filename"]
    blobs = lambda kind: sorted(k for (kd, k) in kept_elsewhere.files if kd == kind)
    assert blobs("outputs") == ["{}/{}".format(home.name, filename())]           # an upload is kept there
    assert client.get("/api/library/{}/poster".format(item["id"]), follow_redirects=False).status_code == 307
    assert len(blobs("posters")) == 1                                            # its poster too, made once

    shutil.rmtree(home)
    client.put("/api/projects/{}".format(film), json={"name": "Pocket"})         # renamed: there too
    assert filename().startswith("Pocket ({})/".format(film)) and blobs("outputs") == ["{}/{}".format(home.name, filename())]
    assert blobs("posters")[0].startswith("{}/Pocket ({})/".format(home.name, film))

    shutil.rmtree(home, ignore_errors=True)
    client.put("/api/library/{}".format(item["id"]), json={"project_id": other})  # moved to another project: there too
    assert filename().startswith("Other ({})/".format(other)) and blobs("outputs") == ["{}/{}".format(home.name, filename())]
    assert [k.split("/")[1] for k in blobs("posters")] == ["Other ({})".format(other)]

    shutil.rmtree(home)
    assert storage.here(home / filename()).read_bytes() == png                   # the studio's own tools get it back here
    assert storage.here(home / "not there.png") == home / "not there.png"         # and a file that is nowhere stays missing
    shutil.rmtree(home)
    assert client.get("/api/library/{}/poster".format(item["id"]), follow_redirects=False).status_code == 307
    assert not (home / filename()).exists()                                      # a kept poster is signed, not made again

    assert client.delete("/api/library/{}".format(item["id"])).status_code == 200
    assert blobs("outputs") == [] and blobs("posters") == []                     # deleted there, posters and all

    kept = client.post("/api/library/upload", files={"file": ("kept.png", png, "image/png")}, data={"project_id": str(film)}).json()
    client.get("/api/library/{}/poster".format(kept["id"]))
    shutil.rmtree(home)
    client.delete("/api/projects/{}".format(film))                               # a project deleted: its folder there goes
    assert not [k for k in blobs("outputs") + blobs("posters") if "/Pocket ({})/".format(film) in k]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def azurite(tmp_path_factory):
    """A connection string to Azurite's blob service: a running one (SCENE_TEST_AZURITE), or one started here."""
    if os.environ.get("SCENE_TEST_AZURITE"):
        yield os.environ["SCENE_TEST_AZURITE"]
        return
    program = os.environ.get("SCENE_AZURITE_BIN") or shutil.which("azurite-blob")
    if not program:
        pytest.skip("Azurite is not installed (npm install -g azurite, or set SCENE_AZURITE_BIN or SCENE_TEST_AZURITE): "
                    "the Azure Blob Storage tests did not run")
    port = _free_port()
    place = tmp_path_factory.mktemp("azurite")
    process = subprocess.Popen([program, "--blobHost", "127.0.0.1", "--blobPort", str(port), "--location", str(place),
                                "--silent", "--skipApiVersionCheck", "--loose"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               shell=program.lower().endswith(".cmd"))
    url = "http://127.0.0.1:{}/devstoreaccount1".format(port)
    for _ in range(100):
        try:
            httpx.get(url, timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey={};BlobEndpoint={};".format(AZURITE_KEY, url)
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()


def test_azure_blob_storage_keeps_serves_with_ranges_and_lists_md5s(azurite, tmp_path):
    store = AzureBlobStorage("scene-test-{}".format(int(time.time() * 1000)), roots(tmp_path), connection_string=azurite)
    video = b"".join(bytes([n % 256]) * 1000 for n in range(100))
    store.save("outputs", "ada/Film (1)/shot 1.mp4", video)
    assert store.exists("outputs", "ada/Film (1)/shot 1.mp4") and store.size("outputs", "ada/Film (1)/shot 1.mp4") == len(video)
    link = store.url("outputs", "ada/Film (1)/shot 1.mp4", seconds=60)
    assert httpx.get(link).content == video                                       # the signed link opens it
    part = httpx.get(link, headers={"Range": "bytes=1000-1999"})
    assert part.status_code == 206 and part.content == video[1000:2000]           # a video player's byte range
    assert httpx.get(link.split("?")[0]).status_code in (401, 403, 404)           # without the signature: no
    listed = store.list("outputs", "ada")
    import hashlib
    assert listed == [("ada/Film (1)/shot 1.mp4", len(video), hashlib.md5(video).hexdigest())]
    path = store.local("outputs", "ada/Film (1)/shot 1.mp4")                       # downloaded once into the cache
    assert path == tmp_path / "outputs" / "ada" / "Film (1)" / "shot 1.mp4" and path.read_bytes() == video
    made = tmp_path / "outputs" / "ada" / ".posters" / "shot 1.mp4.jpg"
    made.parent.mkdir(parents=True)
    made.write_bytes(b"jpg")
    store.keep("posters", "ada/.posters/shot 1.mp4.jpg")                          # made here, kept there
    assert store.read_bytes("posters", "ada/.posters/shot 1.mp4.jpg") == b"jpg"
    store.delete("outputs", "ada/Film (1)/shot 1.mp4")
    assert not store.exists("outputs", "ada/Film (1)/shot 1.mp4") and not path.exists()
    download = store.url("posters", "ada/.posters/shot 1.mp4.jpg", download="poster.jpg")
    assert "poster.jpg" in httpx.get(download).headers.get("content-disposition", "")


def test_azure_blob_storage_moves_a_file_inside_the_container_with_its_md5(azurite, tmp_path):
    import hashlib
    store = AzureBlobStorage("scene-test-{}".format(int(time.time() * 1000)), roots(tmp_path), connection_string=azurite)
    store.save("outputs", "ada/Film (1)/shot 1.mp4", b"a video")
    store.move("outputs", "ada/Film (1)/shot 1.mp4", "ada/Pocket (1)/shot 1.mp4")
    assert store.list("outputs", "ada") == [("ada/Pocket (1)/shot 1.mp4", 7, hashlib.md5(b"a video").hexdigest())]
    assert httpx.get(store.url("outputs", "ada/Pocket (1)/shot 1.mp4")).content == b"a video"
    with pytest.raises(StorageError):   # what is not there is not copied
        store.move("outputs", "ada/Film (1)/gone.mp4", "ada/Pocket (1)/gone.mp4")


def test_remove_result_forgets_the_copies_elsewhere(tmp_path):
    fake = FakeStorage(roots(tmp_path))
    outputs_root = tmp_path / "outputs"
    target = outputs_root / "ada" / "a.mp4"
    poster = outputs_root / "ada" / ".posters" / "a.mp4.jpg"
    for path in (target, poster):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    fake.keep("outputs", "ada/a.mp4")
    fake.keep("posters", "ada/.posters/a.mp4.jpg")
    told = []
    media.on_removed, before = lambda p: (told.append(Path(p).name), fake.delete(*storage.kind_and_key(fake, p))), media.on_removed
    try:
        media.remove_result(target)
    finally:
        media.on_removed = before
    assert sorted(told) == ["a.mp4", "a.mp4.jpg"] and fake.files == {}


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
