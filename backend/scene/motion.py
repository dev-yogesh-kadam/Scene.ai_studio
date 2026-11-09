"""Motion graphics: titles and overlays made from HTML templates and rendered to video by HyperFrames.

HyperFrames (https://github.com/heygen-com/hyperframes) is a Node.js program that plays an HTML page in headless
Chrome frame by frame and encodes the frames with ffmpeg. It is installed into motion/ with `npm install`.
Each folder in motion/templates is one template: index.html (the composition) and template.json (its form).
"""

import asyncio
import json
import os
import platform
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import media, sequence
from .config import ROOT

MOTION_DIR = ROOT / "motion"
TEMPLATES_DIR = MOTION_DIR / "templates"
CLI = MOTION_DIR / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
FONT = ROOT / "frontend" / "assets" / "fonts" / "Archivo-latin.woff2"
SHAPES = {"landscape": (1920, 1080), "portrait": (1080, 1920), "square": (1080, 1080)}
CARD_FPS = 30
RENDER_TIMEOUT = 900            # seconds
MAX_SOURCE_SECONDS = 120        # a longer video is better titled on the timeline
_one_at_a_time = asyncio.Lock()   # every render starts its own Chrome


class MotionError(Exception):
    pass


def node_path(configured=""):
    """The Node.js program: the configured one, the one on the PATH, or where its installer puts it."""
    places = [configured, shutil.which("node"), r"C:\Program Files\nodejs\node.exe", "/usr/local/bin/node", "/opt/homebrew/bin/node"]
    return next((str(p) for p in places if p and Path(p).is_file()), None)


def _ffprobe():
    system = {"Windows": "win32", "Darwin": "darwin"}.get(platform.system(), "linux")
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") and system == "darwin" else "x64"
    path = MOTION_DIR / "node_modules" / "ffprobe-static" / "bin" / system / arch / ("ffprobe.exe" if system == "win32" else "ffprobe")
    return path if path.is_file() else None


def status(configured_node=""):
    """Whether motion graphics can be rendered here, and if not, what is missing."""
    if not node_path(configured_node):
        return {"ready": False, "detail": "Node.js 22 or newer is not installed on the machine that runs Scene.ai."}
    if not CLI.is_file() or not _ffprobe():
        return {"ready": False, "detail": "HyperFrames is not installed. Run `npm install` in the motion folder."}
    return {"ready": True, "detail": ""}


def templates():
    """Every template, as the web page needs it: {"id", "title", "description", "needs", "fields"}."""
    found = []
    # Templates that stand on their own come first, then the ones laid over a video.
    folders = sorted(TEMPLATES_DIR.iterdir(), key=lambda f: (f.name != "title_card", f.name)) if TEMPLATES_DIR.is_dir() else []
    for folder in folders:
        try:
            form = json.loads((folder / "template.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (folder / "index.html").is_file():
            found.append({"id": folder.name, "title": form.get("title", folder.name), "description": form.get("description", ""),
                          "needs": form.get("needs"), "fields": form.get("fields", [])})
    return found


def clean(template, values):
    """The values of a template's form, checked against its fields. Raises MotionError with what is wrong."""
    out = {}
    for field in template["fields"]:
        value = (values or {}).get(field["id"], field.get("default", ""))
        if field["type"] == "choice":
            match = next((c for c in field["choices"] if str(c) == str(value)), None)
            if match is None:
                raise MotionError("'{}' is not a choice for {}.".format(value, field["label"]))
            out[field["id"]] = match
        else:
            text = " ".join(str(value or "").split())[:field.get("max", 200)]
            if field.get("required") and not text:
                raise MotionError("Fill in \"{}\".".format(field["label"]))
            out[field["id"]] = text
    return out


async def render(template_id, values, target, source=None, node="", work_dir=None, alpha=False):
    """Render one template to the video file `target`. source: the video a template is laid over.
    alpha (or the template's "background" set to "clear"): only the words, on nothing, as a see-through WebM at the
    video's size and length, for laying over it (or another) later; see _produce.

    Returns {"seconds", "width", "height"} of the result, and "file" when it was written elsewhere than `target`."""
    template = next((t for t in templates() if t["id"] == template_id), None)
    if template is None:
        raise MotionError("There is no motion template called {}.".format(template_id))
    ready = status(node)
    if not ready["ready"]:
        raise MotionError(ready["detail"])
    values = clean(template, values)
    alpha = alpha or values.pop("background", "video") == "clear"

    sound = "muted"
    if template["needs"] == "video":
        if source is None:
            raise MotionError("Select a video on the canvas first: {} is laid over a video.".format(template["title"].lower()))
        found = await media.probe(source)
        if not found["seconds"] or not found["width"]:
            raise MotionError("That video can't be read.")
        if found["seconds"] > MAX_SOURCE_SECONDS:
            raise MotionError("The video is longer than {} s. Trim it first.".format(MAX_SOURCE_SECONDS))
        width, height, seconds, fps = found["width"] // 2 * 2, found["height"] // 2 * 2, round(found["seconds"], 3), media.FPS
        sound = 'data-has-audio="true"' if found["audio"] and not alpha else "muted"
    else:
        width, height = SHAPES[values.pop("shape", "landscape")]
        seconds, fps = float(values.pop("seconds", 5)), CARD_FPS

    def fill(project):
        shutil.copytree(TEMPLATES_DIR / template_id, project, dirs_exist_ok=True)
        page = (project / "index.html").read_text(encoding="utf-8")
        for mark, value in (("__WIDTH__", width), ("__HEIGHT__", height), ("__DURATION__", seconds), ("__SOUND__", sound)):
            page = page.replace(mark, str(value))
        if alpha:   # the words alone: no video under them, nothing behind the page
            page = re.sub(r'<video id="clip"[^>]*>\s*</video>', "", page)
            page = page.replace("</head>", "<style>html, body { background: transparent !important; }</style>\n  </head>", 1)
        (project / "index.html").write_text(page, encoding="utf-8")
        if source is not None and not alpha:
            shutil.copy(source, project / "clip.mp4")

    return await _produce(fill, values, target, fps, template["title"], node, work_dir, alpha)


async def render_sequence(scenes, look, shape, target, node="", work_dir=None, alpha=False):
    """Render a video made of scenes of words (see sequence.py) to the video file `target`. alpha: see-through (the
    "clear" look's words on nothing), see _produce.

    Returns {"seconds", "width", "height"} of the result, and "file" when it was written elsewhere than `target`."""
    ready = status(node)
    if not ready["ready"]:
        raise MotionError(ready["detail"])
    width, height = SHAPES.get(shape, SHAPES["landscape"])
    page, _ = sequence.page(scenes, look, width, height, alpha)
    return await _produce(lambda project: (project / "index.html").write_text(page, encoding="utf-8"), {}, target, CARD_FPS,
                          "Sequence", node, work_dir, alpha)


async def _produce(fill, values, target, fps, name, node, work_dir, alpha=False, fmt="mp4", still=None, lint=False):
    """Build a HyperFrames project in a temporary folder (fill(project) writes its index.html) and render it.
    alpha: rendered see-through, as a WebM (VP9 with alpha: it plays see-through in a browser, and ffmpeg keeps the
    alpha when it decodes it with libvpx, see montage.composite) next to `target`, with the type .webm.
    fmt: "mp4", "webm" (see-through) or "gif"; the file made takes its type. still: a time in seconds: one PNG of that
    moment instead of a video. lint: check the page with HyperFrames first and refuse it with what it found wrong.

    Returns {"seconds", "width", "height"}, "file" when it was written elsewhere than `target`, and "notes": what the
    check found worth knowing that did not stop the render."""
    fmt = "webm" if alpha else fmt
    asked = Path(target)
    target = asked.with_suffix(".png" if still is not None else PAGE_FORMATS[fmt])
    target.parent.mkdir(parents=True, exist_ok=True)
    if work_dir:
        Path(work_dir).mkdir(parents=True, exist_ok=True)
    notes = []
    async with _one_at_a_time:
        with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
            project = Path(tmp) / "motion"
            project.mkdir()
            fill(project)
            (project / "meta.json").write_text(json.dumps({"id": "motion", "name": name}), encoding="utf-8")
            (project / "variables.json").write_text(json.dumps(values), encoding="utf-8")
            if not (project / "gsap.min.js").is_file():
                shutil.copy(GSAP_DIST / "gsap.min.js", project / "gsap.min.js")
            shutil.copy(FONT, project / "Archivo.woff2")
            if lint:
                notes = await _lint(project, node)
            if still is not None:
                shots = Path(tmp) / "still"
                await _run([node_path(node), str(CLI), "snapshot", str(project), "--at", "{:.3f}".format(still), "--no-end",
                            "--output", str(shots)], project)
                found = sorted(shots.glob("*.png"))
                if found:
                    shutil.move(str(found[0]), str(target))
            else:
                await _run([node_path(node), str(CLI), "render", str(project), "--output", str(target), "--fps", str(fps),
                            *(["--format", fmt] if fmt != "mp4" else []), *(["--gif-loop", "0"] if fmt == "gif" else []),
                            "--variables-file", str(project / "variables.json"), "--quiet"], project)
    if not target.is_file() or not target.stat().st_size:
        raise MotionError("HyperFrames finished without making a {}.".format("picture" if still is not None else "video"))
    made = await media.probe(target)
    return {"seconds": 0.0 if still is not None else made["seconds"], "width": made["width"], "height": made["height"],
            **({"file": target} if target != asked else {}), **({"alpha": True} if fmt == "webm" else {}),
            **({"notes": notes} if notes else {})}


# Findings of HyperFrames' check that say nothing about the picture: ids for its own editor, and the like.
QUIET_FINDINGS = {"studio_missing_editable_id", "nested_structure_needs_subcomposition"}


async def _lint(project, node):
    """HyperFrames' check of a page: raises MotionError with its errors, so the page can be fixed; returns its warnings."""
    output = await _run([node_path(node), str(CLI), "lint", str(project), "--json"], project, check=False)
    try:
        found = json.loads(output[output.index("{"):output.rindex("}") + 1])
    except ValueError:
        return []   # a check that could not be read is no reason to refuse the render
    said = lambda f: "{}{}".format(f.get("message", ""), " ({})".format(f["fixHint"]) if f.get("fixHint") else "")[:400]
    errors = [said(f) for f in found.get("findings", []) if f.get("severity") == "error"]
    if errors:
        raise MotionError("HyperFrames' check found {} problem{} in the page: {}".format(
            len(errors), "" if len(errors) == 1 else "s", " · ".join(errors[:8])))
    return [said(f) for f in found.get("findings", []) if f.get("severity") == "warning" and f.get("code") not in QUIET_FINDINGS][:8]


async def _run(command, folder, check=True):
    """Run HyperFrames and return what it said. check: a failure raises MotionError with its last words."""
    env = dict(os.environ, HYPERFRAMES_FFMPEG_PATH=media.ffmpeg_path(), HYPERFRAMES_FFPROBE_PATH=str(_ffprobe()),
               # Nothing is sent anywhere and nothing is installed while rendering. The one thing looked up is a Google
               # Font a page names, fetched once and kept in FONT_CACHE.
               HYPERFRAMES_NO_TELEMETRY="1", DO_NOT_TRACK="1", HYPERFRAMES_NO_UPDATE_CHECK="1", HYPERFRAMES_NO_FEEDBACK="1",
               HYPERFRAMES_SKIP_SKILLS="1", HYPERFRAMES_NO_AUTO_INSTALL="1", HYPERFRAMES_FONT_CACHE_DIR=str(FONT_CACHE))
    flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}   # no console window on Windows
    process = await asyncio.create_subprocess_exec(*command, cwd=str(folder), env=env, stdin=asyncio.subprocess.DEVNULL,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **flags)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), RENDER_TIMEOUT)
    except asyncio.CancelledError:   # the job this was for was cancelled
        process.kill()
        raise
    except asyncio.TimeoutError:
        process.kill()
        raise MotionError("The render took longer than {} minutes and was stopped.".format(RENDER_TIMEOUT // 60))
    text = output.decode("utf-8", "replace")
    if check and process.returncode:
        lines = [line for line in text.splitlines() if line.strip()]
        raise MotionError("HyperFrames could not render this: {}".format(" ".join(lines[-3:])[-400:] or "no message"))
    return text


# ---------------------------------------------------------------- pages written whole (the agent's own compositions)

PAGE_MOST = 256_000                 # characters of one page
PAGE_SECONDS = (0.1, 90.0)
PAGE_FPS = (24, 25, 30, 50, 60)
PAGE_SIDE = (16, 3840)              # pixels, either side
PIXELS_MOST = 2_600_000_000         # frames x width x height in one render (about 41 s at 1080x1920 and 30 fps)...
VIDEO_SHARE = 3                     # ...and a third of that when the page plays a video: each of its frames is decoded too
PAGE_FORMATS = {"mp4": ".mp4", "webm": ".webm", "gif": ".gif", "png": ".png"}
MEDIA_MOST = 10
GSAP_DIST = MOTION_DIR / "node_modules" / "gsap" / "dist"
FONT_CACHE = MOTION_DIR / ".fonts"  # the Google Fonts pages have named, fetched by HyperFrames the first time and kept
FONT_SITES = ("fonts.googleapis.com", "fonts.gstatic.com")   # the only sites a page may name: the fonts it is set in
MEDIA_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,60}\.[A-Za-z0-9]{2,5}$")
# GSAP and its plugins, as a page names them on a CDN: loaded from the copy installed here instead.
GSAP_LINK = re.compile(r"^(?:https?:)?//(?:cdn\.jsdelivr\.net/npm|unpkg\.com|cdnjs\.cloudflare\.com/ajax/libs)/gsap(?:@[\w.-]+)?/"
                       r"(?:[\w.-]+/)?(?:dist/)?(\w+?)(?:\.min)?\.js$", re.IGNORECASE)
SCRIPT_SRC = re.compile(r"""<script\b[^>]*?\bsrc\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
LINKS = re.compile(r"""\b(?:src|href|poster|srcset|data|action|background|xlink:href)\s*=\s*(["'])(.*?)\1|"""
                   r"""url\(\s*(["']?)(.*?)\3\s*\)|@import\s+(["'])(.*?)\5""", re.IGNORECASE | re.DOTALL)
# What a page may not have: a frame of another page, a way to reach the web from its script, a path off its folder.
BARRED = [(re.compile(r"<\s*(iframe|frame|object|embed|base|portal)\b", re.IGNORECASE), "a <{}> element"),
          (re.compile(r"<meta\b[^>]*http-equiv", re.IGNORECASE), "a <meta http-equiv>"),
          (re.compile(r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|Worker|SharedWorker|"
                      r"RTCPeerConnection)\("), "{}() (a page reaches nothing; give it its media instead)"),
          (re.compile(r"\bimport\s*\(|\bimport\s+[\w{*][^;\n]*\bfrom\b"), "a script import (put the code inline)"),
          (re.compile(r"\bfile:/|\.\.[\\/]|(?<![\w])[A-Za-z]:[\\/]", re.IGNORECASE), "a path to a file off the page's folder")]


def gsap_files():
    """The GSAP files a page may load by name (gsap.min.js, SplitText.min.js, DrawSVGPlugin.min.js...)."""
    return {p.name for p in GSAP_DIST.glob("*.min.js")} if GSAP_DIST.is_dir() else set()


def check_page(page, width, height, seconds, media_names=()):
    """A page the agent wrote, checked before it is rendered, as it will be rendered: GSAP named on a CDN is loaded from
    the copy here. Raises MotionError with everything wrong at once. media_names: the files given with it (bg.mp4)."""
    if not isinstance(page, str) or not page.strip():
        raise MotionError("The page is empty: write the whole HTML document.")
    if len(page) > PAGE_MOST:
        raise MotionError("The page is {:,} characters; it may have {:,}. Load pictures as media, not inlined.".format(len(page), PAGE_MOST))
    problems = []
    root = re.search(r"<[^>]*\bdata-composition-id\s*=\s*([\"'])main\1[^>]*>", page, re.IGNORECASE)
    if not root:
        problems.append('no root element with data-composition-id="main"')
    else:
        said = {k.lower(): v for k, v in re.findall(r"\b(data-width|data-height|data-duration)\s*=\s*[\"']([^\"']*)[\"']", root.group(0), re.IGNORECASE)}
        for key, wanted in (("data-width", width), ("data-height", height), ("data-duration", seconds)):
            try:
                if abs(float(said.get(key, "nan")) - float(wanted)) > 0.001:
                    raise ValueError
            except ValueError:
                problems.append('the root\'s {} must be "{:g}"'.format(key, wanted))
    if not re.search(r"__timelines\s*\[\s*[\"']main[\"']\s*\]\s*=", page):
        problems.append('no timeline: drive all motion from one paused GSAP timeline set as window.__timelines["main"]')
    for pattern, what in BARRED:
        for found in dict.fromkeys(m.group(1) if m.groups() else m.group(0) for m in pattern.finditer(page)):
            problems.append(what.format(found))
    allowed = gsap_files() | set(media_names) | {"Archivo.woff2"}

    def local(src):
        linked = GSAP_LINK.match(src.strip())
        if linked:
            name = next((n for n in gsap_files() if n.lower() == linked.group(1).lower() + ".min.js"), None)
            if name:
                return name
            problems.append("{} is not one of GSAP's files".format(src[:120]))
        return src

    page = SCRIPT_SRC.sub(lambda m: m.group(0).replace(m.group(2), local(m.group(2))), page)
    for found in LINKS.finditer(page):
        value = next(v for v in (found.group(2), found.group(4), found.group(6)) if v is not None).strip()
        value = value.split(",")[0].split()[0] if value and found.group(0).lower().startswith("srcset") else value
        if not value or value.startswith(("#", "data:", "blob:")) or value.lower().startswith("javascript:void"):
            continue
        site = re.match(r"^(?:https?:)?//([^/?#]+)", value, re.IGNORECASE)
        if value.startswith("\\\\"):   # a share on another machine
            problems.append("{} is a path to a file off the page's folder".format(value[:120]))
        elif site:
            if site.group(1).lower() not in FONT_SITES:
                problems.append("{} is on the web: give the file as media and name it by its file name".format(value[:120]))
        elif re.match(r"^[a-z][\w+.-]*:", value, re.IGNORECASE) or value not in allowed:
            problems.append("{} is not one of the media given ({})".format(value[:120], ", ".join(sorted(media_names)) or "none"))
    if problems:
        raise MotionError("The page can't be rendered: {}.".format("; ".join(dict.fromkeys(problems))))
    return page


def page_budget(page, width, height, seconds, fps):
    """Raises MotionError when a page is more than one render can hold."""
    most = PIXELS_MOST // (VIDEO_SHARE if re.search(r"<\s*video\b", page, re.IGNORECASE) else 1)
    if width * height * seconds * fps > most:
        raise MotionError("That is too much for one render: {:.0f} s at {}x{} and {} fps{} holds at most {:.0f} s. Split it into "
                          "scenes and join them.".format(seconds, width, height, fps, " with a video in it" if most < PIXELS_MOST else "",
                                                        most / (width * height * fps)))


async def render_page(page, width, height, seconds, target, fps=30, fmt="mp4", media_files=None, node="", work_dir=None):
    """Render a page the agent wrote whole to `target`: a video (mp4; webm, see-through; gif) or, with fmt "png", one
    picture of its last moment. media_files: {name: path} of the pictures, clips and sounds it plays, copied in beside it
    under those names. The page is checked first (check_page, then HyperFrames' own check).

    Returns {"seconds", "width", "height"}, "file" when it was written elsewhere than `target`, and "notes"."""
    ready = status(node)
    if not ready["ready"]:
        raise MotionError(ready["detail"])
    media_files = dict(media_files or {})
    page = check_page(page, width, height, seconds, media_files)
    if fmt != "png":
        page_budget(page, width, height, seconds, fps)

    def fill(project):
        (project / "index.html").write_text(page, encoding="utf-8")
        for name in gsap_files():
            if re.search(r"[\"'/]" + re.escape(name) + r"[\"']", page):
                shutil.copy(GSAP_DIST / name, project / name)
        for name, path in media_files.items():
            shutil.copy(path, project / name)

    still = max(0.0, seconds - 1.0 / fps) if fmt == "png" else None
    return await _produce(fill, {}, target, fps, "Page", node, work_dir, fmt="mp4" if fmt == "png" else fmt, still=still, lint=True)
