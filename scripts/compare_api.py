"""Ask two studios the same questions as the same users and compare the answers: the API must not change in a database
upgrade (docs/history/db-upgrade-log.md). Each studio runs on a copy of the same data: the old code on a copy of the database
as it was, the new code on the migrated copy. Sessions are made in both copies for each user (the same token), every
GET route without path parameters is asked, and each project's library, placement, boards, agent tabs and NeuralCore.

    python scripts/compare_api.py --old-backend <dir> --old-url <db as it was> --new-url <migrated db> [--users 3]

Read only, but for the sessions it adds to both copies. Never point it at the live database. Numbers are compared to
the fifth decimal (a time kept as seconds and as timestamptz differ in its last microsecond); keys that change by
themselves (now, uptime, how long ago) are left out.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
VOLATILE = {"uptime_seconds", "now", "server_time", "checked", "since", "seen_ago", "age", "page_version", "version",
            "started", "online", "open_connections", "disk_free", "disk_total", "database", "when", "eta_seconds",
            "last_backup", "storage", "copies", "check", "render", "model", "servers", "endpoints"}


def start(backend, url, home, port):
    config = Path(home) / "config.json"
    config.write_text(json.dumps({
        "host": "127.0.0.1", "port": port, "console_host": "127.0.0.1", "console_port": port + 9,
        "comfy_url": "http://127.0.0.1:9", "storage_dir": str(Path(home) / "storage"), "secret_key_file": str(Path(home) / "secret.key"),
        "database_url": url, "backup_keep": 0, "claude_models": "off", "hold_queue_offline": True,
        "web_dist_dir": str(ROOT / "apps/web/dist"), "workflows_dir": str(ROOT / "workflows")}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SCENE_")}
    env.update(SCENE_CONFIG=str(config), PYTHONUNBUFFERED="1",
               SCENE_SECRET_KEY=env.get("COMPARE_SECRET_KEY") or __import__("cryptography.fernet").fernet.Fernet.generate_key().decode())
    log = open(Path(home) / "studio.log", "w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "scene"], cwd=str(backend), env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(240):
        try:
            if httpx.get("http://127.0.0.1:{}/api/auth/state".format(port), timeout=2).status_code == 200:
                return process
        except httpx.HTTPError:
            pass
        if process.poll() is not None:
            break
        time.sleep(0.5)
    raise SystemExit("The studio on {} did not start:\n{}".format(port, (Path(home) / "studio.log").read_text(encoding="utf-8")[-3000:]))


def sessions(url, users, admin):
    """A studio session for each user and a console session for the admin, the same tokens in both copies."""
    import psycopg
    from scene.security import token_hash
    with psycopg.connect(url) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        kind = conn.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'sessions' "
                            "AND column_name = 'created'").fetchone()[0]
        at = "to_timestamp(%s)" if kind.startswith("timestamp") else "%s"
        for user_id, token, console in [(u, t, 0) for u, t in users.items()] + [(admin[0], admin[1], 1)]:
            conn.execute("INSERT INTO sessions (token_hash, user_id, created, expires, console) VALUES (%s, %s, {0}, {0}, %s) "
                         "ON CONFLICT (token_hash) DO NOTHING".format(at), (token_hash(token), user_id, time.time(), time.time() + 7200, console))
        conn.commit()


def places(url, user_id):
    """What to ask about for one user: their projects and modules, and the kinds of their boards in each."""
    import psycopg
    with psycopg.connect(url) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        projects = [r[0] for r in conn.execute("SELECT id FROM projects WHERE user_id = %s ORDER BY id", (user_id,))]
        boards = [(r[0] or 0, r[1]) for r in conn.execute("SELECT project_id, kind FROM boards WHERE user_id = %s ORDER BY 1, 2", (user_id,))]
        items = [r[0] for r in conn.execute("SELECT id FROM generations WHERE user_id = %s ORDER BY id DESC LIMIT 5", (user_id,))]
    return projects, boards, items


def plain(value):
    """An answer as it is compared: numbers to five decimals, volatile keys left out."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [plain(v) for v in value]
    if isinstance(value, float):
        return round(value, 5)
    return value


def first_difference(a, b, path=""):
    if type(a) is not type(b):
        return "{}: {!r} vs {!r}".format(path or "/", str(a)[:120], str(b)[:120])
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return "{}/{}: only in the {}".format(path, k, "old" if k in a else "new")
            found = first_difference(a[k], b[k], path + "/" + k)
            if found:
                return found
    elif isinstance(a, list):
        if len(a) != len(b):
            return "{}: {} items vs {}".format(path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            found = first_difference(x, y, "{}[{}]".format(path, i))
            if found:
                return found
    elif a != b:
        return "{}: {!r} vs {!r}".format(path or "/", str(a)[:120], str(b)[:120])
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--old-backend", required=True)
    parser.add_argument("--old-url", required=True)
    parser.add_argument("--new-url", required=True)
    parser.add_argument("--users", type=int, default=3, help="the users with the most library items")
    args = parser.parse_args()

    import psycopg
    with psycopg.connect(args.new_url) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        users = [r[0] for r in conn.execute("SELECT user_id FROM generations GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT %s",
                                            (args.users,))]
        admin = conn.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()[0]
    tokens = {u: secrets.token_urlsafe(32) for u in users}
    console_token = (admin, secrets.token_urlsafe(32))
    for url in (args.old_url, args.new_url):
        sessions(url, tokens, console_token)
    os.environ["COMPARE_SECRET_KEY"] = __import__("cryptography.fernet").fernet.Fernet.generate_key().decode()
    old = start(Path(args.old_backend).resolve(), args.old_url, tempfile.mkdtemp(prefix="scene-cmp-old-"), 8881)
    new = start(ROOT / "backend", args.new_url, tempfile.mkdtemp(prefix="scene-cmp-new-"), 8981)
    asked = same = 0
    differences = []
    try:
        from scene.main import create_app  # noqa: F401  (the routes of the new code)
        studio_routes, console_routes = routes()
        for user in users:
            projects, boards, items = places(args.new_url, user)
            paths = list(studio_routes)
            for p in [0] + projects:
                paths += ["/api/library?project={}&all=1".format(p or "none"), "/api/library/placement?project={}".format(p),
                          "/api/kit?project={}".format(p), "/api/projects/{}".format(p) if p else None]
            paths += ["/api/boards/{}?project={}".format(kind, p) for p, kind in boards]
            paths += ["/api/library/{}".format(i) for i in items]
            paths = [p for p in paths if p]
            for path in paths:
                asked += 1
                same += compare(path, {"scene_session": tokens[user]}, 8881, 8981, differences, "user {}".format(user))
        for path in console_routes:
            asked += 1
            same += compare(path, {"scene_console": console_token[1]}, 8890, 8990, differences, "admin")
    finally:
        for process in (old, new):
            process.terminate()
    print("{} answers compared, {} the same".format(asked, same))
    for line in differences:
        print("  " + line)


def compare(path, cookies, old_port, new_port, differences, who):
    headers = {"Sec-Fetch-Site": "same-origin"}
    a = httpx.get("http://127.0.0.1:{}{}".format(old_port, path), cookies=cookies, headers=headers, timeout=60)
    b = httpx.get("http://127.0.0.1:{}{}".format(new_port, path), cookies=cookies, headers=headers, timeout=60)
    if a.status_code != b.status_code:
        differences.append("{} {}: status {} vs {}".format(who, path, a.status_code, b.status_code))
        return 0
    if "json" not in a.headers.get("content-type", ""):
        return 1
    found = first_difference(plain(a.json()), plain(b.json()))
    if found:
        differences.append("{} {}: {}".format(who, path, found))
        return 0
    return 1


def routes():
    """The GET routes of the studio and the console that take no path parameter (the live socket and files left out)."""
    from fastapi.routing import APIRoute
    from scene.api import admin, auth, bulk, console, film, kit, library, mobile, plans, runs, shares, studio, workspace
    pick = lambda modules: sorted({r.path for m in modules for r in m.router.routes
                                    if isinstance(r, APIRoute) and "GET" in r.methods and "{" not in r.path
                                    and not r.path.endswith(("/events", "/download", "/export"))})
    return (pick([auth, studio, library, workspace, film, runs, kit, bulk, mobile, shares, plans]),
            pick([console, admin]))


if __name__ == "__main__":
    main()
