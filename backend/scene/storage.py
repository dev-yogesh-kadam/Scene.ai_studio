"""Where the studio's media are kept: the library's finished pictures, videos and sounds (outputs), their thumbnails
(posters), NeuralCore's files (kit), the work picked for the Home page (showcase) and the files jobs use as inputs
(references). They are folders on this machine (LocalStorage, `storage_backend` "local", the only one); the interface
is there so the tests can keep them in memory instead (FakeStorage).

Keys are paths inside a kind's folder, written with "/" ("ada@example.com/Film (3)/shot_1.mp4").
"""

import shutil
from pathlib import Path, PurePosixPath

# references: the files a job uses as inputs (references.keep_reference), kept here and sent to the provider that
# makes the job when it starts, so an upload never depends on a provider answering.
KINDS = ("outputs", "posters", "kit", "showcase", "references")


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
        """The local path of kind/key, for the studio's own tools (ffmpeg, Pillow) and to serve it."""
        raise NotImplementedError

    def ready(self):
        """Whether the media can be kept now (GET /readyz): the folders can be written."""
        raise NotImplementedError

    def response(self, kind, key, download=None, headers=None):
        """What a route answers with to give kind/key to a browser: the file itself (with byte ranges, for video)."""
        from fastapi import HTTPException
        from starlette.responses import FileResponse
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
    """The storage `storage_backend` names: "local", these folders (`roots`: the folder of each kind). Any other value
    is a setting left over from an older studio, and stops it at start-up."""
    backend = (settings.storage_backend or "local").lower()
    if backend == "local":
        return LocalStorage(roots)
    raise StorageError("storage_backend is {!r}: only 'local' is supported.".format(settings.storage_backend))
