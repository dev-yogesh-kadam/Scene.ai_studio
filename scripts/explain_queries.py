"""EXPLAIN ANALYZE of the studio's main queries on a database, as the app runs them (its account, row-level security
on, for the user with the most library items), to see which indexes they use and how long they take.

    python scripts/explain_queries.py --url postgresql://scene_app:<pw>@localhost:5432/scene_upgrade [--runs 7] [--plans]

Read only (EXPLAIN ANALYZE of SELECTs). Prints each query's median execution time over --runs, and with --plans the
plan of each. Never point it at the live database while the studio is busy: it is meant for a restored copy.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from scene import edge  # noqa: E402
from scene.db import postgres_sql  # noqa: E402

IN_PROJECT = "g.project_id IN (SELECT q.id FROM projects q WHERE q.id = p.id OR q.parent_id = p.id)"
LIBRARY = ("SELECT g.*, j.cost, p.name AS project_name, u.name AS made_by FROM generations g LEFT JOIN jobs j ON j.id = g.job_id "
           "LEFT JOIN projects p ON p.id = g.project_id LEFT JOIN users u ON u.id = g.user_id WHERE g.user_id = ? AND g.run = ?")
WORD = " AND (g.name LIKE ? ESCAPE '\\' OR g.workflow LIKE ? ESCAPE '\\' OR g.summary LIKE ? ESCAPE '\\' OR g.settings::text LIKE ? ESCAPE '\\')"
FTS = " AND (g.search @@ to_tsquery('simple', ?) OR ? <% g.name)"   # api/library.search_sql, migration 0009

# name: (SQL with ?, parameters as a function of {user, project, now, session, word}, whose rows: "user" or "all")
QUERIES = {
    "library: newest page": (LIBRARY + " ORDER BY g.created DESC, g.id DESC LIMIT ?",
                             lambda f: (f["user"], "", 61), "user"),
    "library: next page (cursor)": (LIBRARY + " AND (g.created < ? OR (g.created = ? AND g.id < ?)) ORDER BY g.created DESC, g.id DESC LIMIT ?",
                                    lambda f: (f["user"], "", f["middle"], f["middle"], 10 ** 12, 61), "user"),
    "library: one project": (LIBRARY + " AND g.project_id = ? ORDER BY g.created DESC LIMIT 500",
                             lambda f: (f["user"], "", f["project"]), "user"),
    "library: search, 1 word": (LIBRARY + WORD + " ORDER BY g.created DESC, g.id DESC LIMIT ?",
                                lambda f: (f["user"], "", *["%{}%".format(f["word"])] * 4, 61), "user"),
    "library: search, 2 words": (LIBRARY + WORD + WORD + " ORDER BY g.created DESC, g.id DESC LIMIT ?",
                                 lambda f: (f["user"], "", *["%{}%".format(f["word"])] * 4, *["%{}%".format(f["word2"])] * 4, 61), "user"),
    "library: search, 1 word (full text)": (LIBRARY + FTS + " ORDER BY g.created DESC, g.id DESC LIMIT ?",
                                            lambda f: (f["user"], "", f["word"] + ":*", f["word"], 61), "user"),
    "library: search, 2 words (full text)": (LIBRARY + FTS + FTS + " ORDER BY g.created DESC, g.id DESC LIMIT ?",
                                             lambda f: (f["user"], "", f["word"] + ":*", f["word"], f["word2"] + ":*", f["word2"], 61), "user"),
    "jobs: the next queued": ("SELECT * FROM jobs WHERE status = 'queued' AND 1 = 1 ORDER BY priority DESC, created LIMIT 1",
                              lambda f: (), "all"),
    "jobs: queue counts": ("SELECT status, COUNT(*) AS n FROM jobs WHERE status IN ('queued', 'running') GROUP BY status",
                           lambda f: (), "all"),
    "jobs: a user's list (before)": ("SELECT * FROM jobs WHERE user_id = ? AND hidden = 0 AND (status IN ('queued', 'running') OR finished > ? "
                                     "OR id IN (SELECT id FROM jobs WHERE user_id = ? AND hidden = 0 ORDER BY created DESC LIMIT 40)) ORDER BY created DESC",
                                     lambda f: (f["user"], f["now"] - 300, f["user"]), "user"),
    "jobs: a user's list": ("SELECT * FROM jobs WHERE id IN (SELECT id FROM jobs WHERE user_id = ? AND hidden = 0 AND status IN ('queued', 'running') "
                            "UNION SELECT id FROM jobs WHERE user_id = ? AND hidden = 0 AND finished > ? "
                            "UNION (SELECT id FROM jobs WHERE user_id = ? AND hidden = 0 ORDER BY created DESC LIMIT 40)) ORDER BY created DESC",
                            lambda f: (f["user"], f["user"], f["now"] - 300, f["user"]), "user"),
    "credits: spent in 24 h": ("SELECT SUM(amount) n FROM credit_events WHERE user_id = ? AND reason IN ('generation', 'refund', 'agent') AND created > ?",
                               lambda f: (f["user"], f["now"] - 86400), "user"),
    "credits: balance": ("SELECT credits FROM users WHERE id = ?", lambda f: (f["user"],), "user"),
    "projects: a user's list": (
        "SELECT p.id, p.ref, p.name, p.canvas_name, p.created, p.parent_id, p.user_id, pp.name AS parent_name, pp.ref AS parent_ref, ow.name AS owner_name, "
        "(SELECT COUNT(*) FROM project_members pm WHERE pm.project_id = COALESCE(p.parent_id, p.id)) AS members, "
        "(SELECT COUNT(*) FROM projects m WHERE m.parent_id = p.id) AS modules, "
        "(SELECT COUNT(*) FROM generations g WHERE " + IN_PROJECT + " AND g.run = '') AS items, "
        "(SELECT g.id FROM generations g WHERE " + IN_PROJECT + " AND g.run = '' ORDER BY g.created DESC LIMIT 1) AS cover_id, "
        "(SELECT g.kind FROM generations g WHERE " + IN_PROJECT + " AND g.run = '' ORDER BY g.created DESC LIMIT 1) AS cover_kind, "
        "(SELECT MAX(g.created) FROM generations g WHERE " + IN_PROJECT + ") AS updated "
        "FROM projects p LEFT JOIN projects pp ON pp.id = p.parent_id JOIN users ow ON ow.id = p.user_id "
        "WHERE p.user_id = ? ORDER BY lower(p.name)", lambda f: (f["user"],), "user"),
    "boards: one board": ("SELECT data FROM boards WHERE user_id = ? AND project_id = ? AND kind = ?",
                          lambda f: (f["user"], f["project"], "agent"), "user"),
    "boards: agent tabs (phone)": ("SELECT project_id, kind, data, updated FROM boards WHERE user_id = ? AND kind LIKE 'agent-%' ORDER BY updated DESC",
                                   lambda f: (f["user"],), "user"),
    "agent sessions: console list": (
        "SELECT s.*, u.name AS user_name, u.email AS user_email, p.name AS project_name, p.ref AS project_ref, "
        "pp.name AS parent_name, pp.ref AS parent_ref, (SELECT COUNT(*) FROM claude_events e WHERE e.session_id = s.id) AS events "
        "FROM claude_sessions s JOIN users u ON u.id = s.user_id LEFT JOIN projects p ON p.id = s.project_id "
        "LEFT JOIN projects pp ON pp.id = p.parent_id ORDER BY s.active DESC LIMIT ?", lambda f: (50,), "all"),
    "agent sessions: events": ("SELECT id, at, kind, text, data FROM claude_events WHERE session_id = ? AND id > ? ORDER BY id LIMIT ?",
                               lambda f: (f["session"], 0, 500), "all"),
}


def facts(conn):
    conn.execute("SELECT set_config('app.user_id', 'all', false)")
    user = conn.execute("SELECT user_id FROM generations GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 1").fetchone()[0]
    project = conn.execute("SELECT project_id FROM generations WHERE user_id = %s AND project_id IS NOT NULL "
                           "GROUP BY project_id ORDER BY COUNT(*) DESC LIMIT 1", (user,)).fetchone()
    middle = conn.execute("SELECT created FROM generations WHERE user_id = %s ORDER BY created DESC OFFSET 100 LIMIT 1",
                          (user,)).fetchone()
    session = conn.execute("SELECT session_id FROM claude_events GROUP BY session_id ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
    return {"user": user, "project": project[0] if project else 0, "middle": middle[0] if middle else time.time(),
            "now": time.time(), "session": session[0] if session else 0, "word": "night", "word2": "light"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--plans", action="store_true")
    parser.add_argument("--json", help="also write {query: ms} here")
    args = parser.parse_args()
    import psycopg
    out = {}
    with psycopg.connect(args.url, autocommit=True) as conn:
        found = facts(conn)
        shape = edge.Shape.read(conn)   # times and JSON given as the app gives them (edge.with_times)
        if hasattr(found["middle"], "timestamp"):   # a timestamptz column (after migration 0007): the app sends epochs
            found["middle"] = found["middle"].timestamp()
        for name, (sql, params, whose) in QUERIES.items():
            conn.execute("SELECT set_config('app.user_id', %s, false)", (str(found["user"]) if whose == "user" else "all",))
            text = postgres_sql(shape.translate(sql))
            times, plan = [], None
            for _ in range(args.runs):
                rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + text, params(found)).fetchone()[0]
                plan = rows[0] if isinstance(rows, list) else json.loads(rows)[0]
                times.append(plan["Execution Time"])
            out[name] = round(statistics.median(times), 3)
            print("{:34} {:9.3f} ms".format(name, out[name]))
            if args.plans:
                for row in conn.execute("EXPLAIN ANALYZE " + text, params(found)).fetchall():
                    print("      " + row[0])
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
