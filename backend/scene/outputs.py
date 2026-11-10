"""Where finished images, videos and sounds are kept: one folder per user, named after the user's email, and in it one
folder per project, with one per module inside it:

    <outputs>/ada@example.com/Pocket Film (6)/Main canvas/      the project's own canvas
    <outputs>/ada@example.com/Pocket Film (6)/Episode 1 (9)/    a module of it
    <outputs>/ada@example.com/No project/                       work in no project

A folder is named after its project and its number, so two projects of the same name stay apart; it follows the project
when it is renamed, and goes with it when it is deleted. An item's `filename` is its path inside the user's folder.
"""

import glob
import re
import shutil
import time
from pathlib import Path

from .db import as_everyone

NO_PROJECT = "No project"
MAIN_CANVAS = "Main canvas"   # the folder of a project's own canvas, beside its modules' folders
POSTER_OF = re.compile(r"(\.\d+)?\.jpg|\.webp")   # what follows a file's name in its posters' names (media.py)


def folder_name(email):
    """An email as a folder name every system accepts: ada@example.com stays as it is."""
    return re.sub(r"[^\w.@+-]+", "_", email).strip("._ ") or "user"


def safe(name):
    """A name made safe as a folder name on any system (at most 60 characters); empty when nothing is left."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name or "")).strip(" .")[:60].strip(" .")


def canvas_folder(name):
    """The folder of a project's own canvas, by the name it was given ("Main canvas" when it has none)."""
    return safe(name) or MAIN_CANVAS


def label(row):
    """A project's folder name: its name, made safe for any system, and its number."""
    name = safe(row["name"]) or "Untitled"
    return "{} ({})".format(name, row["id"])


class Outputs:
    def __init__(self, root, db):
        self.root = Path(root)
        self.db = db
        self.names = {}   # user id -> folder name; an email never changes, so this is filled once per user
        self.storage = None   # where the files are kept for good (storage.py; main.py sets it): None or local, nothing to do

    # ------------------------------------------------------------ where the files are kept for good (storage.py)

    def _stored(self, path):
        """(the storage, kind, key) of a media file, or None while the media are kept only here."""
        if self.storage is None or self.storage.name == "local":
            return None
        from .storage import kind_and_key   # an output, a poster, or a showcase file media.remove_result deletes
        return (self.storage, *kind_and_key(self.storage, path))

    def keep(self, path):
        """A file just made in the outputs' folder (a result, a poster) is kept where the media are kept for good."""
        stored = self._stored(path)
        if stored:
            stored[0].keep(stored[1], stored[2])

    def fetch(self, path):
        """A file of the outputs, here: downloaded into its folder first when the media are kept elsewhere."""
        stored = self._stored(path)
        return stored[0].local(stored[1], stored[2]) if stored else Path(path)

    def forget(self, path):
        """A file deleted from the outputs' folder is deleted where the media are kept for good too, with its posters
        there (this folder may have had no copy of them for media.remove_result to name)."""
        stored = self._stored(path)
        if stored:
            stored[0].delete(stored[1], stored[2])
            if stored[1] == "outputs":
                for name in self._posters_kept(Path(path)):
                    stored[0].delete("posters", name)

    def _posters_kept(self, path):
        """The keys of a file's poster, keyframes and WebP copy where the media are kept."""
        store, posters, poster = self._stored(path.parent / ".posters" / path.name)
        return [found for found, _, _ in store.list(posters, poster.rsplit("/", 1)[0])
                if POSTER_OF.fullmatch(found.rsplit("/", 1)[1][len(path.name):]) and found.rsplit("/", 1)[1].startswith(path.name)]

    def _taken(self, path):
        """Whether a file is at `path`: here, or (kept elsewhere) there, where this folder may hold no copy of it."""
        if path.exists():
            return True
        stored = self._stored(path)
        return bool(stored) and stored[0].exists(stored[1], stored[2])

    def _carry(self, old, new):
        """Kept elsewhere: a file moved here from `old` to `new` is moved there too, with its poster, keyframes and the
        poster's WebP copy (.posters/<name>.jpg, <name>.<tenth>.jpg, <name>.webp)."""
        stored = self._stored(old)
        if not stored:
            return
        store, kind, key = stored
        store.move(kind, key, self._stored(new)[2])
        for found in self._posters_kept(old):
            rest = found.rsplit("/", 1)[1][len(old.name):]
            store.move("posters", found, self._stored(new.parent / ".posters" / (new.name + rest))[2])

    def _carry_folder(self, before, after):
        """Kept elsewhere: everything under the folder `before` (outputs and posters alike) is moved under `after`."""
        stored = self._stored(before / "_")
        if not stored:
            return
        store, old = stored[0], stored[2].rsplit("/", 1)[0]
        new = self._stored(after / "_")[2].rsplit("/", 1)[0]
        for kind in ("outputs", "posters"):
            for found, _, _ in store.list(kind, old):
                store.move(kind, found, new + found[len(old):])

    def folder(self, user_id):
        """The folder of one user's finished work. It is not created here."""
        if user_id not in self.names:
            with as_everyone():   # the folder of whoever made it, also when another person in a shared project asks
                user = self.db.one("SELECT email FROM users WHERE id = ?", (user_id,))
            if user is None:
                return self.root / str(user_id)
            self.names[user_id] = folder_name(user["email"])
        return self.root / self.names[user_id]

    def relative(self, project_id):
        """Where the work of a project goes inside its user's folder: "<project> (n)/Main canvas" for its own canvas,
        "<project> (n)/<module> (m)" for a module, "No project" for none."""
        with as_everyone():   # a shared project is its owner's row; a member files their work in it too
            row = self.db.one("SELECT id, parent_id, canvas_name FROM projects WHERE id = ?", (project_id,)) if project_id else None
        if row is None:
            return Path(NO_PROJECT)
        return self.folder_of(project_id) if row["parent_id"] else self.folder_of(project_id) / canvas_folder(row["canvas_name"])

    def folder_of(self, project_id):
        """The folder of a project (holding its Main canvas and its modules' folders), or of a module (inside its
        project's): what is renamed with it and deleted with it."""
        with as_everyone():
            row = self.db.one("SELECT id, name, parent_id FROM projects WHERE id = ?", (project_id,)) if project_id else None
        if row is None:
            return Path(NO_PROJECT)
        if row["parent_id"]:
            with as_everyone():
                parent = self.db.one("SELECT id, name FROM projects WHERE id = ?", (row["parent_id"],))
            return Path(label(parent)) / label(row) if parent else Path(label(row))
        return Path(label(row))

    def settle(self, user_id, project_id, path):
        """Put a file of a user's work into the folder of its project, if it is not there, and return its path inside
        the user's folder ("Pocket Film (6)/shot.png"), which is what an item records as its filename."""
        home = self.folder(user_id)
        target_dir = home / self.relative(project_id)
        path = Path(path)
        if path.parent.resolve() != target_dir.resolve():
            target_dir.mkdir(parents=True, exist_ok=True)
            target = _free(target_dir / path.name, self._taken)
            _moved(path.replace, target)
            _move_posters(path, target)
            path = target
        return path.relative_to(home).as_posix()

    def refile(self, user_id, item_id, project_id):
        """Move an item's file into the folder of `project_id` (an item moved to another project) and record it."""
        row = self.db.one("SELECT filename FROM generations WHERE id = ?", (item_id,))
        if row is None:
            return
        home = self.folder(user_id)
        path = home / row["filename"]
        if not path.is_file() and self._taken(path):
            self.fetch(path)   # kept elsewhere, with no copy here: brought here, to be moved like any file
        if path.is_file():
            filed = self.settle(user_id, project_id, path)
            if home / filed != path:
                self._carry(path, home / filed)
            self.db.run("UPDATE generations SET filename = ? WHERE id = ?", (filed, item_id))

    def rename(self, user_id, before, after):
        """A project or module was renamed: its folder (`before`, a path inside the user's folder) becomes `after`, and
        its items' recorded paths with it."""
        if before == after:
            return
        home = self.folder(user_id)
        if (home / before).is_dir():
            (home / after).parent.mkdir(parents=True, exist_ok=True)
            if (home / after).exists():   # a folder of that name is there already: what is in the old one joins it
                for path in (home / before).rglob("*"):
                    if path.is_file():
                        dest = home / after / path.relative_to(home / before)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        _moved(path.replace, dest)
                shutil.rmtree(home / before, ignore_errors=True)
            else:
                _moved((home / before).rename, home / after)
        self._carry_folder(home / before, home / after)
        old, new = before.as_posix() + "/", after.as_posix() + "/"
        for row in self.db.all("SELECT id, filename FROM generations WHERE user_id = ?", (user_id,)):
            if row["filename"].startswith(old):
                self.db.run("UPDATE generations SET filename = ? WHERE id = ?", (new + row["filename"][len(old):], row["id"]))

    def remove_folder(self, user_id, relative):
        """Delete what is left of a project's or module's folder (it goes with the project or module)."""
        target = self.folder(user_id) / relative
        if not relative.parts or relative.parts[0] == NO_PROJECT:
            return
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        stored = self._stored(target / "_")
        if stored:   # and there, where this folder may have had no copy of some of it
            folder = stored[2].rsplit("/", 1)[0]
            for kind in ("outputs", "posters"):
                for found, _, _ in stored[0].list(kind, folder):
                    stored[0].delete(kind, found)



def _free(path, taken=Path.exists):
    """`path`, or the same name with a number when a file is there already (`taken`: here, or where it is kept)."""
    if not taken(path):
        return path
    for n in range(2, 10000):
        candidate = path.with_name("{}_{}{}".format(path.stem, n, path.suffix))
        if not taken(candidate):
            return candidate
    return path


def _move_posters(old, new):
    """A file's poster, keyframes and the poster's WebP copy (.posters/<name>.jpg, <name>.<tenth>.jpg, <name>.webp)
    follow it."""
    posters = old.parent / ".posters"
    if not posters.is_dir():
        return
    for made in [*posters.glob(glob.escape(old.name) + "*.jpg"), *posters.glob(glob.escape(old.name) + "*.webp")]:
        dest = new.parent / ".posters" / (new.name + made.name[len(old.name):])
        dest.parent.mkdir(exist_ok=True)
        _moved(made.replace, dest)


def _moved(move, target, tries=20):
    """Move a file or folder. On Windows a file another program has open (ffmpeg making its poster from it, a moment after
    it was made) can't be moved: it is tried again, for up to two seconds, before giving up."""
    for attempt in range(tries):
        try:
            return move(target)
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.1)
