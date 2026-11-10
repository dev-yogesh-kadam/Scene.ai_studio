"""Where the studio's media are kept: the library's finished pictures, videos and sounds (outputs), their thumbnails
(posters), NeuralCore's files (kit) and the work picked for the Home page (showcase). One interface, two places:

- LocalStorage (`storage_backend` "local", the default): folders on this machine, as they always were.
- AzureBlobStorage ("azure"): Azure Blob Storage, one container with a prefix per kind ("outputs/<user>/<file>"). The
  same local folders become its cache (a container's disk): a file is downloaded there once when the studio's own tools
  (ffmpeg, Pillow) need it, and a browser is sent a link signed for a few minutes (SAS) instead of having Python stream
  the file.

Keys are paths inside a kind's folder, written with "/" ("ada@example.com/Film (3)/shot_1.mp4"). A file the studio makes
is made in the local folder first (ffmpeg writes files) and then kept (`keep`); what it reads it gets with `local`.

Why one container with prefixes, not one per kind: every kind is private and served the same way, so one container
gives one place for lifecycle rules (they filter by prefix), soft delete and versioning, one origin for a CDN, one
role assignment for the app's managed identity, and one thing for move_media.py to copy. Separate containers would
only pay off for different access levels, which nothing here needs.
"""

import mimetypes
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

KINDS = ("outputs", "posters", "kit", "showcase")


class StorageError(ValueError):
    pass


def clean_key(key):
    """A key as kept: "/"-separated, no "..", no leading "/" (a key never leaves its kind's folder)."""
    parts = PurePosixPath(str(key).replace("\\", "/")).parts
    if not parts or any(p in ("..", "") for p in parts) or parts[0] == "/":
        raise StorageError("Not a key of the studio's storage: {!r}".format(key))
    return "/".join(parts)


class Storage:
    """What every kind of storage does. `kind` is one of KINDS; `key` a path inside it."""

    name = ""

    def save(self, kind, key, source):
        """Keep `source` (bytes, or the path of a local file) as kind/key, replacing what was there."""
        raise NotImplementedError

    def keep(self, kind, key):
        """The local file kind/key was just made (by ffmpeg, a render): keep it where it belongs."""
        raise NotImplementedError

    def open(self, kind, key):
        """A binary file object to read kind/key from (close it after)."""
        raise NotImplementedError

    def read_bytes(self, kind, key):
        with self.open(kind, key) as f:
            return f.read()

    def url(self, kind, key, seconds=900, download=None):
        """A link a browser may fetch kind/key from for `seconds`, or None when the studio serves it itself."""
        return None

    def delete(self, kind, key):
        raise NotImplementedError

    def move(self, kind, key, new_key):
        """kind/key becomes kind/new_key (an item moved to another project, a project renamed), replacing what was
        there."""
        self.save(kind, new_key, self.local(kind, key))
        self.delete(kind, key)

    def exists(self, kind, key):
        raise NotImplementedError

    def size(self, kind, key):
        raise NotImplementedError

    def list(self, kind, prefix=""):
        """The keys of a kind under `prefix` (a folder), with their sizes and MD5 when the store knows it:
        [(key, size, md5)]."""
        raise NotImplementedError

    def local(self, kind, key):
        """A local path of kind/key for the studio's own tools (ffmpeg, Pillow): the file itself, or a cached copy."""
        raise NotImplementedError

    def ready(self):
        """Whether the media can be kept now (GET /readyz): the folders can be written, or the container answers."""
        raise NotImplementedError

    def response(self, kind, key, download=None, headers=None):
        """What a route answers with to give kind/key to a browser: the file itself (with byte ranges, for video), or a
        redirect to a signed link."""
        from fastapi import HTTPException
        from starlette.responses import FileResponse, RedirectResponse
        link = self.url(kind, key, download=download)
        if link:
            return RedirectResponse(link, status_code=307, headers=headers)
        path = self.local(kind, key)
        if not path.is_file():
            raise HTTPException(404, "That file is gone.")
        return FileResponse(path, filename=download, headers=headers)


class LocalStorage(Storage):
    """Folders on this machine: {kind: folder}. Posters live inside the outputs' folders (".posters/"), so their kind
    has the same folder as the outputs."""

    name = "local"

    def __init__(self, roots):
        self.roots = {k: Path(v) for k, v in roots.items()}

    def path(self, kind, key):
        root = self.roots[kind]
        path = (root / clean_key(key)).resolve()
        if root.resolve() not in path.parents and path != root.resolve():
            raise StorageError("Not inside {}: {!r}".format(kind, key))
        return path

    def save(self, kind, key, source):
        target = self.path(kind, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".partial")
        if isinstance(source, (bytes, bytearray)):
            partial.write_bytes(source)
        elif Path(source).resolve() != target:
            shutil.copyfile(source, partial)
        else:
            return
        partial.replace(target)

    def keep(self, kind, key):
        return None   # it is already where it belongs

    def open(self, kind, key):
        return open(self.path(kind, key), "rb")

    def delete(self, kind, key):
        self.path(kind, key).unlink(missing_ok=True)

    def move(self, kind, key, new_key):
        target = self.path(kind, new_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.path(kind, key).replace(target)

    def exists(self, kind, key):
        return self.path(kind, key).is_file()

    def size(self, kind, key):
        return self.path(kind, key).stat().st_size

    def list(self, kind, prefix=""):
        root = self.roots[kind].resolve()
        start = root / clean_key(prefix) if prefix else root
        if not start.exists():
            return []
        found = []
        for path in start.rglob("*"):
            if path.is_file() and not path.name.endswith(".partial"):
                key = path.relative_to(root).as_posix()
                if (kind == "posters") == (".posters" in key.split("/")):   # posters are their own kind, inside outputs
                    found.append((key, path.stat().st_size, None))
        return sorted(found)

    def local(self, kind, key):
        return self.path(kind, key)

    def ready(self):
        root = self.roots["outputs"]
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".ready"
        probe.write_bytes(b"")
        probe.unlink()
        return True


class AzureBlobStorage(Storage):
    """Azure Blob Storage: one container, a prefix per kind. Signed in with a connection string (an account key, or
    Azurite's for tests), or, on Azure, with the app's managed identity (DefaultAzureCredential and `account_url`):
    then no key is stored anywhere and links are signed with a user delegation key."""

    name = "azure"

    def __init__(self, container, roots, connection_string="", account_url="", sas_minutes=15):
        from azure.storage.blob import BlobServiceClient
        if connection_string:
            self.service = BlobServiceClient.from_connection_string(connection_string)
            self.credential = None
        elif account_url:
            from azure.identity import DefaultAzureCredential
            self.credential = DefaultAzureCredential()
            self.service = BlobServiceClient(account_url, credential=self.credential)
        else:
            raise StorageError("Azure storage needs azure_storage_connection_string or azure_storage_account_url.")
        self.container = self.service.get_container_client(container)
        if not self.container.exists():
            self.container.create_container()
        self.roots = {k: Path(v) for k, v in roots.items()}   # the local folders, its cache
        self.sas_minutes = sas_minutes
        self.delegation = None   # (key, until): a user delegation key signs links when there is no account key

    def blob(self, kind, key):
        if kind not in KINDS:
            raise StorageError("No such kind of storage: {}".format(kind))
        return self.container.get_blob_client("{}/{}".format(kind, clean_key(key)))

    def save(self, kind, key, source):
        """Upload it, with its MD5 (Azure keeps one by itself only for a small upload): every copy can be checked."""
        import hashlib
        from azure.storage.blob import ContentSettings
        data = bytes(source) if isinstance(source, (bytes, bytearray)) else None
        digest = hashlib.md5(data).digest() if data is not None else bytes.fromhex(md5_of(source))
        settings = ContentSettings(content_type=mimetypes.guess_type(key)[0] or "application/octet-stream", content_md5=digest)
        if data is not None:
            self.blob(kind, key).upload_blob(data, overwrite=True, content_settings=settings)
        else:
            with open(source, "rb") as f:
                self.blob(kind, key).upload_blob(f, overwrite=True, content_settings=settings, max_concurrency=4)

    def keep(self, kind, key):
        self.save(kind, key, self.cached(kind, key))

    def open(self, kind, key):
        return open(self.local(kind, key), "rb")

    def url(self, kind, key, seconds=None, download=None):
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas
        blob = self.blob(kind, key)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=seconds or self.sas_minutes * 60)
        signing = {}
        if self.credential is None:   # an account key, from the connection string
            signing["account_key"] = self.service.credential.account_key
        else:
            signing["user_delegation_key"] = self._delegation_key()
        sas = generate_blob_sas(account_name=self.service.account_name, container_name=self.container.container_name,
                                blob_name=blob.blob_name, permission=BlobSasPermissions(read=True), expiry=expiry,
                                content_disposition='attachment; filename="{}"'.format(download) if download else None,
                                **signing)
        return blob.url + "?" + sas

    def _delegation_key(self):
        now = datetime.now(timezone.utc)
        if self.delegation is None or self.delegation[1] - now < timedelta(minutes=30):
            until = now + timedelta(hours=6)
            self.delegation = (self.service.get_user_delegation_key(now - timedelta(minutes=5), until), until)
        return self.delegation[0]

    def delete(self, kind, key):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            self.blob(kind, key).delete_blob()
        except ResourceNotFoundError:
            pass
        self.cached(kind, key).unlink(missing_ok=True)

    def move(self, kind, key, new_key):
        """Copied inside the account by Azure itself (nothing passes through the studio; the copy keeps the MD5 and the
        content type), then the old blob goes. Its source is a signed link, so it works signed in either way. A cached
        copy is the caller's: Outputs moves the local file itself."""
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
        target = self.blob(kind, new_key)
        try:
            target.start_copy_from_url(self.url(kind, key, seconds=3600))
        except HttpResponseError as error:   # no such blob, most often
            raise StorageError("Copying {}/{} to {} was refused: {}".format(kind, key, new_key, error.reason or error)) from error
        for _ in range(1200):   # a copy inside one account is done at once, or in seconds for a big video
            copy = target.get_blob_properties().copy
            if copy.status != "pending":
                break
            time.sleep(0.25)
        if copy.status != "success":
            raise StorageError("Copying {}/{} to {} ended as {}: {}".format(kind, key, new_key, copy.status, copy.status_description))
        try:
            self.blob(kind, key).delete_blob()
        except ResourceNotFoundError:
            pass

    def exists(self, kind, key):
        return self.blob(kind, key).exists()

    def size(self, kind, key):
        return self.blob(kind, key).get_blob_properties().size

    def list(self, kind, prefix=""):
        start = "{}/{}".format(kind, clean_key(prefix) if prefix else "").rstrip("/") + "/"
        return sorted((b.name[len(kind) + 1:], b.size, (bytes(b.content_settings.content_md5).hex()
                                                        if b.content_settings and b.content_settings.content_md5 else None))
                      for b in self.container.list_blobs(name_starts_with=start))

    def cached(self, kind, key):
        return self.roots[kind] / clean_key(key)

    def ready(self):
        return self.container.exists()

    def local(self, kind, key):
        """The cached copy, downloaded the first time (to a .partial file, so a copy cut short is never used)."""
        path = self.cached(kind, key)
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(path.name + ".partial")
            with open(partial, "wb") as f:
                self.blob(kind, key).download_blob().readinto(f)
            partial.replace(path)
        return path


class FakeStorage(Storage):
    """In memory, for tests: what the interface promises, nothing else."""

    name = "fake"

    def __init__(self, roots):
        self.files = {}
        self.roots = {k: Path(v) for k, v in roots.items()}

    def save(self, kind, key, source):
        self.files[(kind, clean_key(key))] = bytes(source) if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()

    def keep(self, kind, key):
        self.save(kind, key, self.roots[kind] / clean_key(key))

    def open(self, kind, key):
        import io
        return io.BytesIO(self.files[(kind, clean_key(key))])

    def url(self, kind, key, seconds=900, download=None):
        return "https://fake.blob/{}/{}?expires={}".format(kind, clean_key(key), int(time.time() + seconds))

    def delete(self, kind, key):
        self.files.pop((kind, clean_key(key)), None)

    def move(self, kind, key, new_key):
        self.files[(kind, clean_key(new_key))] = self.files.pop((kind, clean_key(key)))

    def exists(self, kind, key):
        return (kind, clean_key(key)) in self.files

    def size(self, kind, key):
        return len(self.files[(kind, clean_key(key))])

    def list(self, kind, prefix=""):
        import hashlib
        start = clean_key(prefix) + "/" if prefix else ""
        return sorted((k, len(v), hashlib.md5(v).hexdigest()) for (kd, k), v in self.files.items()
                      if kd == kind and k.startswith(start))

    def ready(self):
        return True

    def local(self, kind, key):
        path = self.roots[kind] / clean_key(key)
        if not path.is_file() and (kind, clean_key(key)) in self.files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.files[(kind, clean_key(key))])
        return path


def open_storage(settings, roots):
    """The storage `storage_backend` names. `roots`: the local folders of each kind (LocalStorage's, and Azure's cache)."""
    backend = (settings.storage_backend or "local").lower()
    if backend == "local":
        return LocalStorage(roots)
    if backend == "azure":
        return AzureBlobStorage(settings.azure_storage_container, roots,
                                connection_string=settings.azure_storage_connection_string,
                                account_url=settings.azure_storage_account_url, sas_minutes=settings.storage_sas_minutes)
    raise StorageError("storage_backend is {!r}: it is 'local' or 'azure'.".format(settings.storage_backend))


def key_of(root, path):
    """The key of a local path inside a kind's folder."""
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def kind_of(key):
    return "posters" if ".posters" in key.split("/") else "outputs"


def md5_of(path):
    import hashlib
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


os.environ.setdefault("AZURE_LOG_LEVEL", "warning")


def _elsewhere(state):
    store = getattr(state, "storage", None)
    return store if store is not None and store.name != "local" else None


def kind_and_key(store, path, kind=None):
    """(kind, key) of a local media path: by the folder it is in (outputs, kit, showcase); a ".posters" folder's file is
    a poster."""
    path = Path(path).resolve()
    for name in ([kind] if kind else ("outputs", "kit", "showcase")):
        root = store.roots[name].resolve()
        if root in path.parents:
            key = path.relative_to(root).as_posix()
            return ("posters" if ".posters" in key.split("/") and name in ("outputs", "posters") else name), key
    raise StorageError("Not a media file of the studio: {}".format(path))


def signed(state, kind, path, download=None, headers=None):
    """A route's answer for a media file kept elsewhere (Azure): a redirect to a link signed for a few minutes, which
    the browser fetches straight from Blob Storage (byte ranges and all). None while the media are kept here: the
    route answers with the file itself, as it always did. `kind` None: found from the path's folder."""
    store = _elsewhere(state)
    if store is None:
        return None
    from starlette.responses import RedirectResponse
    kind, key = kind_and_key(store, path, None if kind in (None, "outputs", "posters") else kind)
    return RedirectResponse(store.url(kind, key, download=download), status_code=307, headers=headers)


def fetch_path(state, path):
    """A media file here, downloaded into its folder first when the media are kept elsewhere. Sync: offload it."""
    store = _elsewhere(state)
    return store.local(*kind_and_key(store, path)) if store else Path(path)


def keep_path(state, path):
    """A media file just made here (a poster, a NeuralCore file, a showcase item) kept where the media are kept for
    good. Sync: offload it. Nothing to do while they are kept here."""
    store = _elsewhere(state)
    if store:
        store.keep(*kind_and_key(store, path))


ACTIVE = None   # the app's storage (main.py sets it), for code with no app state at hand (kit.py, showcase.py, memory.py)


def keep_file(path):
    """keep_path for code with no app state at hand: a NeuralCore or showcase file just written here."""
    if ACTIVE is not None and ACTIVE.name != "local":
        ACTIVE.keep(*kind_and_key(ACTIVE, path))


def kept(state, path):
    """Whether a media file is kept where the media are kept for good (asked of the store, not of this folder). Sync."""
    store = _elsewhere(state)
    return Path(path).is_file() if store is None else store.exists(*kind_and_key(store, path))


def here(path):
    """A media file's local path for the studio's own tools, downloaded first when the media are kept elsewhere and this
    folder (their cache) has no copy; the path as it is, missing, when the file is nowhere, so `is_file()` still says
    so. Sync: offload it."""
    path = Path(path)
    if path.is_file() or ACTIVE is None or ACTIVE.name == "local":
        return path
    try:
        kind, key = kind_and_key(ACTIVE, path)
    except StorageError:
        return path
    return ACTIVE.local(kind, key) if ACTIVE.exists(kind, key) else path


def forget_file(path):
    """A media file deleted here is deleted where the media are kept for good too."""
    if ACTIVE is not None and ACTIVE.name != "local":
        ACTIVE.delete(*kind_and_key(ACTIVE, path))
