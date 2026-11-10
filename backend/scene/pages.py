"""The agent's motion projects: HyperFrames projects it writes file by file (index.html, compositions/<scene>.html,
styles, scripts, an SVG it drew), kept per module, rendered by the render_html tool (motion.render_project).

A project lives in <storage>/motion/<whose>/<module>/<project>/. Only text files are written here; pictures, clips,
sounds and fonts come in at render time from the library (the op's "media") and from the studio's own (GSAP, Three.js,
Lottie, the sound effects). A path never leaves its project: no "..", no drive, no root.
"""

import re
import shutil
from pathlib import Path

FILE_MOST = 300_000          # characters of one file
FILES_MOST = 80              # files in one project
PROJECTS_MOST = 40           # projects in one module
TYPES = {".html", ".css", ".js", ".mjs", ".json", ".svg", ".txt", ".md"}
PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DEPTH = 4                    # folders under a project, at most


class PageError(ValueError):
    pass


def root(storage, user_id, module):
    """Where a module's motion projects are kept."""
    return Path(storage) / "motion" / str(int(user_id)) / str(int(module))


def split(path):
    """(project, the file's path inside it) of "launch/compositions/hook.html". Raises PageError when it is not a
    path this store keeps: each part a plain name, nothing up or out of the project."""
    parts = [p for p in str(path or "").replace("\\", "/").strip().strip("/").split("/") if p]
    if not parts:
        raise PageError("Name a project, or a file in one: launch/index.html.")
    for part in parts:
        if not PART.match(part) or part.startswith(".") or ".." in part:
            raise PageError("\"{}\" can't be part of a path: letters, digits, dots, dashes and underscores, as launch/compositions/hook.html.".format(part[:60]))
    if len(parts) > DEPTH + 2:
        raise PageError("That path is too deep: keep files at most {} folders into the project.".format(DEPTH))
    return parts[0], "/".join(parts[1:])


def write(base, path, text):
    """Write one text file of a project. Returns {"project", "path", "characters", "files"}."""
    project, inner = split(path)
    if not inner:
        raise PageError("Give the file's path inside the project: {}/index.html.".format(project))
    if Path(inner).suffix.lower() not in TYPES:
        raise PageError("Only text files are written here ({}). Pictures, clips, sounds and fonts come in as the "
                        "render's media.".format(", ".join(sorted(TYPES))))
    if not isinstance(text, str) or len(text) > FILE_MOST:
        raise PageError("A file is text of at most {:,} characters.".format(FILE_MOST))
    base = Path(base)
    folder = base / project
    if not folder.is_dir() and base.is_dir() and len([p for p in base.iterdir() if p.is_dir()]) >= PROJECTS_MOST:
        raise PageError("This module has {} motion projects already: write into one of them.".format(PROJECTS_MOST))
    target = folder / inner
    if not target.is_file() and folder.is_dir() and len(files(base, project)) >= FILES_MOST:
        raise PageError("A project holds at most {} files.".format(FILES_MOST))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    return {"project": project, "path": inner, "characters": len(text), "files": len(files(base, project))}


def files(base, project):
    """The files of a project: [path inside it], in order."""
    folder = Path(base) / project
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else []


def read(base, path):
    """A file's text, or for a project alone the list of its files: ("file", text) or ("project", [{"path", "characters"}])."""
    project, inner = split(path)
    folder = Path(base) / project
    if not folder.is_dir():
        raise PageError("There is no motion project \"{}\" in this module.".format(project))
    if not inner:
        return "project", [{"path": p, "characters": (folder / p).stat().st_size} for p in files(base, project)]
    target = folder / inner
    if not target.is_file():
        raise PageError("{} has no file {}.".format(project, inner))
    return "file", target.read_text(encoding="utf-8", errors="replace")


def remove(base, path):
    """Remove one file of a project, or the whole project."""
    project, inner = split(path)
    target = Path(base) / project / inner if inner else Path(base) / project
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    else:
        raise PageError("There is nothing at {}.".format(path))


def projects(base):
    """The module's motion projects, by name."""
    base = Path(base)
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
