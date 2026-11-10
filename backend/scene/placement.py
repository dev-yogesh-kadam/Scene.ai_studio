"""Where a finished result goes on its project's canvas, when its job says so.

A job's settings may carry:
- "shot_number": the number of the story shot it is (1, 2, 3...). The canvas puts it in the row of that shot, rows in
  order of their numbers, and a retake (same number) stacks on the shot: the newest on top, the earlier takes behind.
- "board": the name of a board of the canvas ("Characters", "Locations", "Props", "Styles", "Outputs", or any other).
  The result goes on that board, which is made the first time a result names it. The whole film, the clips patched
  into one (FINISHED), goes on "Final video" whether its job names no board or "Outputs".
- "placement_group": what the result is a version of. Results of one group stack on their board instead of each taking
  a card: a re-render of the same deliverable lands on top of the one before. Without it, the shot or step id the job
  came from stands for it.

The boards and their stacks are kept here, by the server, as the job finishes, in the boards table under kind
"placement" (one row per canvas, the project owner's, as the canvas layout is). The canvas reads them; it never writes
them, so a result that lands while the canvas is open is never lost to the layout the canvas saves.
"""

import json
import re
import time

from .db import as_everyone

KIND = "placement"
BOARDS = ("Characters", "Locations", "Props", "Styles", "Outputs", "Final video")   # the names the agent uses
OUTPUTS = "Outputs"
FINAL_VIDEO = "Final video"   # the whole film, its clips patched into one: a board of its own, left of Outputs
FINISHED = ("edit/film", "edit/assemble")   # the whole film: on Final video, one card, unless its job names another board
FINAL = "final"
MAX_SHOT = 999
MAX_NAME = 40
MAX_BOARDS = 40     # boards on one canvas
MAX_STACKS = 200    # cards on one board
MAX_TAKES = 20      # versions kept in one stack; older ones fall off the stack (they stay in the library)
GROUP = re.compile(r"[^A-Za-z0-9:_./-]")


def clean_shot_number(value):
    """A shot number from 1 to MAX_SHOT, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    return value if isinstance(value, int) and 1 <= value <= MAX_SHOT else None


def clean_board(name):
    """A board's name in one line, or None. One of BOARDS in any case is written as BOARDS writes it."""
    if not isinstance(name, str):
        return None
    name = " ".join(re.sub(r"[<>\"'`/\\]", "", name).split())[:MAX_NAME].strip()
    if not name:
        return None
    return next((known for known in BOARDS if known.lower() == name.lower()), name)


def clean_group(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    return GROUP.sub("", str(value))[:64] or None


def group_of(settings, item_id):
    """What a result is a version of: its placement group, else the shot it was made for (the agent's shot id), else
    the place in the run state it is saved to, else its shot number. A result with none of these is a card of its own."""
    settings = settings or {}
    shot = settings.get("shot") if isinstance(settings.get("shot"), dict) else {}
    for key, value in (("", settings.get("placement_group")), ("shot:", shot.get("id")),
                       ("state:", settings.get("save_to_state")), ("number:", clean_shot_number(settings.get("shot_number")))):
        found = clean_group(value)
        if found:
            return key + found
    return "item:{}".format(item_id)


def canvas_of(db, user_id, project_id):
    """(whose canvas, which project) a result of `user_id` in `project_id` lands on: a project's canvas is its owner's."""
    if not project_id:
        return user_id, 0
    from . import sharing
    top, _ = sharing.top_of(db, project_id)
    return (top["user_id"] if top else user_id), project_id


def read(db, owner, project_id):
    with as_everyone():
        row = db.one("SELECT data FROM boards WHERE user_id = ? AND project_id IS NOT DISTINCT FROM NULLIF(?, 0) AND kind = ?", (owner, project_id or 0, KIND))
    try:
        data = json.loads(row["data"]) if row else {}
    except ValueError:
        data = {}
    boards = data.get("boards") if isinstance(data.get("boards"), list) else []
    return {"boards": [b for b in boards if isinstance(b, dict) and b.get("name") and isinstance(b.get("stacks"), list)]}


def _write(db, owner, project_id, data):
    with as_everyone():
        db.run("INSERT INTO boards (user_id, project_id, kind, data, updated) VALUES (?, NULLIF(?, 0), ?, ?, ?) "
               "ON CONFLICT(user_id, project_id, kind) DO UPDATE SET data = excluded.data, updated = excluded.updated",
               (owner, project_id or 0, KIND, json.dumps(data), time.time()))


def run_of(job):
    """The run a result is a working file of, "" when it is none. What goes on a board is there to be seen, so a run's
    whole film, or anything else its job names a board for, is listed like any other result."""
    settings = job.get("settings") or {}
    if job.get("workflow") in FINISHED or clean_board(settings.get("board")):
        return ""
    return str(settings.get("run") or "")


def place(db, job, item_id):
    """Put a finished result on the board its job names, making the board on first use, and on the stack of its group.
    Returns {"board", "group"}, or None when the job names no board. The whole film (FINISHED) goes on Final video when
    it names none or Outputs, each new cut stacking on the one before."""
    settings = job.get("settings") or {}
    finished = job.get("workflow") in FINISHED and clean_board(settings.get("board")) in (None, OUTPUTS)
    name = FINAL_VIDEO if finished else clean_board(settings.get("board"))
    if not name or not item_id:
        return None
    owner, project_id = canvas_of(db, job["user_id"], job.get("project_id"))
    data = read(db, owner, project_id)
    board = next((b for b in data["boards"] if str(b["name"]).lower() == name.lower()), None)
    if board is None:
        if len(data["boards"]) >= MAX_BOARDS:
            return None
        board = {"name": name, "created": time.time(), "stacks": []}
        data["boards"].append(board)
    group = FINAL if finished and not settings.get("placement_group") else group_of(settings, item_id)
    stack = next((s for s in board["stacks"] if s.get("group") == group), None)
    if stack is None:
        stack = {"group": group, "items": []}
        board["stacks"].append(stack)
        board["stacks"] = board["stacks"][-MAX_STACKS:]
    stack["items"] = ([item_id] + [i for i in stack.get("items") or [] if i != item_id])[:MAX_TAKES]   # the newest on top
    if settings.get("shot_number"):
        stack["shot_number"] = clean_shot_number(settings["shot_number"])
    _write(db, owner, project_id, data)
    return {"board": board["name"], "group": group}


def boards(db, owner, project_id, known=None):
    """The canvas's boards for a page or the agent: [{"name", "stacks": [{"group", "items", "shot_number"?}]}], each stack's
    newest item first. With `known` (the ids of the items there are now), items no longer there are left out, and so
    are stacks left empty; a board stays, empty, once it was made."""
    found = read(db, owner, project_id)["boards"]
    shown = []
    for board in found:
        stacks = []
        for stack in board["stacks"]:
            items = [i for i in stack.get("items") or [] if isinstance(i, int) and (known is None or i in known)]
            if items:
                stacks.append(dict(stack, items=items))
        shown.append({"name": board["name"], "created": board.get("created"), "stacks": stacks})
    return shown
