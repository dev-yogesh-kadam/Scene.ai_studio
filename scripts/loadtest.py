"""Load test: many users at once on Home, Library and Create, each with the live socket open, while jobs render.

    python scripts/loadtest.py [--users 50] [--seconds 60] [--items 200] [--backend backend] [--out result.json]

It never touches the live studio: it starts a studio of its own (this tree's backend, or --backend's) on port 8781
with a throwaway database (scripts/testdb.py, beside SCENE_TEST_DATABASE_URL's) and the fake ComfyUI (node, apps/web/
tests/support/fake-comfy.mjs). Each user has --items library items, signs in, keeps /api/events open, and loads the
pages one after another with the API requests a browser makes for them (recorded from the React build, 10 Nov 2026),
each page's requests at once as a browser sends them. A few of them keep queueing image jobs, which the fake ComfyUI
"renders" in half a second, so the queue, the job workers and the live messages are busy throughout. At the end it
prints requests per second and the latency (p50, p95, p99) of each request kind and of a whole page.
"""

import argparse
import asyncio
import json
import os
import random
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
PORT, CONSOLE_PORT, COMFY_PORT = 8781, 8790, 8799
PASSWORD = "Load-test-2026-pass"

# What each page asks for as it opens (a browser's requests, the React build of 10 Nov 2026): GETs at once, then the
# page's own. {flux} and {video} are workflows the page opens.
PAGES = {
    "home": ["/api/auth/me", "/api/agent/preferences", "/api/preferences", "/api/library?limit=60", "/api/workflows",
             "/api/projects", "/api/showcase", "/api/announcement", "/api/status", "/api/jobs",
             "/api/workflows/{flux}"],
    "library": ["/api/auth/me", "/api/agent/preferences", "/api/preferences", "/api/projects", "/api/announcement",
                "/api/status", "/api/jobs", "/api/library?limit=60"],
    "library search": ["/api/library?limit=60&q={word}"],
    "create": ["/api/auth/me", "/api/agent/preferences", "/api/preferences", "/api/library?limit=4", "/api/jobs",
               "/api/workflows", "/api/projects", "/api/announcement", "/api/status", "/api/workflows/{flux}"],
}
WORDS = "neon rain street night portrait dolly warm light shadow road glass".split()


def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def start_fake_comfy():
    loader = ("import('{}').then(async (m) => {{ await m.startFakeComfy({{port: {}, renderMs: 500}}); "
              "console.log('ready'); }})").format((ROOT / "apps/web/tests/support/fake-comfy.mjs").as_uri(), COMFY_PORT)
    process = subprocess.Popen(["node", "-e", loader], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    process.stdout.readline()
    return process


def start_studio(backend, database, home):
    config = Path(home) / "config.json"
    config.write_text(json.dumps({
        "host": "127.0.0.1", "port": PORT, "console_host": "127.0.0.1", "console_port": CONSOLE_PORT,
        "comfy_url": "http://127.0.0.1:{}".format(COMFY_PORT), "storage_dir": str(Path(home) / "storage"),
        "secret_key_file": str(Path(home) / "secret.key"), "database_url": database, "backup_keep": 0,
        "signups_per_day": 0, "first_account_local": False, "claude_models": "off",
        "web_dist_dir": str(ROOT / "apps/web/dist"), "workflows_dir": str(ROOT / "workflows")}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SCENE_")}
    env.update(SCENE_CONFIG=str(config), PYTHONUNBUFFERED="1")
    log = open(Path(home) / "studio.log", "w", encoding="utf-8")
    return subprocess.Popen([PYTHON, "-m", "scene"], cwd=str(backend), env=env, stdout=log, stderr=subprocess.STDOUT)


async def wait_until_up(httpx, base, studio, home):
    async with httpx.AsyncClient() as http:
        for _ in range(180):
            if studio.poll() is not None:
                raise SystemExit("The studio stopped:\n" + (Path(home) / "studio.log").read_text(encoding="utf-8")[-3000:])
            try:
                if (await http.get(base + "/api/auth/state")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    raise SystemExit("The studio did not answer within 90 s.")


def make_users(database, emails):
    """The test's users, each with credits for the jobs it queues and a session of its own (sign-ins, like sign-ups,
    are limited per address, and every user here comes from one): {email: session token}."""
    import psycopg
    sys.path.insert(0, str(ROOT / "backend"))
    from scene.security import hash_password, new_token, token_hash
    hashed = hash_password(PASSWORD)
    with psycopg.connect(database) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        types = dict(conn.execute("SELECT column_name, data_type FROM information_schema.columns "
                                  "WHERE table_name = 'users'").fetchall())
        at = "to_timestamp(%s)" if types["created"].startswith("timestamp") else "%s"
        tokens = {}
        for email in emails:
            user = conn.execute("INSERT INTO users (email, name, password_hash, role, credits, created) "
                                "VALUES (%s, %s, %s, 'user', 1000000, {}) RETURNING id".format(at),
                                (email, email[:12], hashed, time.time())).fetchone()[0]
            tokens[email] = new_token()
            conn.execute("INSERT INTO sessions (token_hash, user_id, created, expires) VALUES (%s, %s, {0}, {0})".format(at),
                         (token_hash(tokens[email]), user, time.time(), time.time() + 86400))
        conn.commit()
    return tokens


def seed(database, users, items):
    """Library items for every user, written straight into the throwaway database (no files: the pages list them)."""
    import psycopg
    with psycopg.connect(database) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        types = dict(conn.execute("SELECT column_name, data_type FROM information_schema.columns "
                                  "WHERE table_name = 'generations'").fetchall())
        cast = {c: ("to_timestamp(%s)" if types.get(c, "").startswith("timestamp") else
                    "%s::jsonb" if types.get(c) == "jsonb" else "%s")
                for c in ("user_id", "workflow", "kind", "name", "filename", "summary", "settings", "context", "created")}
        now = time.time()
        rows = []
        for user_id in users:
            for n in range(items):
                prompt = " ".join(random.sample(WORDS, 6))
                rows.append((user_id, "image/image_t2i_flux2_dev", "image", "Item {} {}".format(n, prompt[:20]),
                             "seed_{}_{}.png".format(user_id, n), prompt, json.dumps({"prompt": prompt}), "{}",
                             now - n * 60))
        with conn.cursor() as cursor:
            cursor.executemany("INSERT INTO generations ({}) VALUES ({})".format(", ".join(cast), ", ".join(cast.values())),
                               rows)
        conn.commit()


async def user_loop(httpx, websockets, base, token, deadline, results, workflows, sockets):
    async with httpx.AsyncClient(base_url=base, headers={"Sec-Fetch-Site": "same-origin"}, timeout=60,
                                 cookies={"scene_session": token}) as http:
        cookie = "scene_session=" + token
        socket_task = asyncio.create_task(listen(websockets, base, cookie, deadline, sockets))
        while time.monotonic() < deadline:
            for page in ("home", "library", "library search", "create"):
                paths = [p.format(flux=workflows["flux"], word=random.choice(WORDS)) for p in PAGES[page]]
                started = time.perf_counter()
                answers = await asyncio.gather(*(timed(http, path, results) for path in paths))
                results["pages"].setdefault(page, []).append(time.perf_counter() - started)
                results["errors"] += sum(1 for ok in answers if not ok)
                if time.monotonic() >= deadline:
                    break
        await socket_task


async def timed(http, path, results):
    started = time.perf_counter()
    try:
        answer = await http.get(path)
        ok = answer.status_code == 200
        results["status"][answer.status_code] = results["status"].get(answer.status_code, 0) + 1
    except Exception as error:
        ok = False
        results["status"][type(error).__name__] = results["status"].get(type(error).__name__, 0) + 1
    key = path.split("?")[0] + ("?q" if "q=" in path else "")
    key = "/api/workflows/<id>" if key.startswith("/api/workflows/") else key
    results["requests"].setdefault(key, []).append(time.perf_counter() - started)
    return ok


async def listen(websockets, base, cookie, deadline, sockets):
    try:
        async with websockets.connect(base.replace("http", "ws") + "/api/events", additional_headers={"Cookie": cookie},
                                      origin=base) as ws:
            sockets["open"] += 1
            while time.monotonic() < deadline:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
                    sockets["messages"] += 1
                except asyncio.TimeoutError:
                    break
    except Exception as error:
        sockets["failed"] += 1
        sockets["error"] = str(error)[:200]


async def job_loop(httpx, base, token, deadline, workflows, counts):
    async with httpx.AsyncClient(base_url=base, headers={"Sec-Fetch-Site": "same-origin"}, timeout=60,
                                 cookies={"scene_session": token}) as http:
        while time.monotonic() < deadline:
            settings = {"workflow": workflows["flux"], "values": {"prompt": random.choice(WORDS)}, "name": "load"}
            answer = await http.post("/api/jobs", files={"settings": (None, json.dumps(settings))})
            counts["queued" if answer.status_code == 200 else "refused"] += 1
            await asyncio.sleep(1.0)


async def run(args):
    import httpx
    import websockets
    database = subprocess.run([PYTHON, str(ROOT / "scripts/testdb.py"), "create"], capture_output=True, text=True,
                              check=True).stdout.strip()
    home = tempfile.mkdtemp(prefix="scene-load-")
    comfy = start_fake_comfy()
    reached = database
    if args.via:   # the studio reaches its database through another address (a proxy that adds a network's delay)
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(database)
        reached = urlunsplit((parts.scheme, "{}@{}".format(parts.netloc.rsplit("@", 1)[0], args.via), parts.path, parts.query, ""))
    studio = start_studio(Path(args.backend).resolve(), reached, home)
    base = "http://127.0.0.1:{}".format(PORT)
    try:
        await wait_until_up(httpx, base, studio, home)
        emails = ["load-{}@local.test".format(n) for n in range(args.users)]
        async with httpx.AsyncClient(base_url=base, headers={"Sec-Fetch-Site": "same-origin"}) as http:
            made = await http.post("/api/auth/register", json={"email": "load-admin@local.test", "name": "Admin",
                                                               "password": PASSWORD})
            if made.status_code != 200:
                raise SystemExit("Could not make the admin: {}".format(made.text[:200]))
            flux = next(w["id"] for w in (await http.get("/api/workflows")).json()["workflows"] if w["kind"] == "image")
        tokens = make_users(database, emails)   # straight into the database: sign-ups are limited per address
        with __import__("psycopg").connect(database) as conn:
            conn.execute("SELECT set_config('app.user_id', 'all', false)")
            ids = [r[0] for r in conn.execute("SELECT id FROM users WHERE email LIKE 'load-%%@local.test' "
                                              "AND email <> 'load-admin@local.test'").fetchall()]
        seed(database, ids, args.items)
        workflows = {"flux": flux}
        results = {"requests": {}, "pages": {}, "errors": 0, "status": {}}
        sockets, jobs = {"open": 0, "failed": 0, "messages": 0}, {"queued": 0, "refused": 0}
        started = time.monotonic()
        deadline = started + args.seconds
        await asyncio.gather(
            *(user_loop(httpx, websockets, base, tokens[e], deadline, results, workflows, sockets) for e in emails),
            *(job_loop(httpx, base, tokens[e], deadline, workflows, jobs) for e in emails[:args.job_users]))
        elapsed = time.monotonic() - started
    finally:
        studio.terminate()
        comfy.terminate()
        try:
            studio.wait(timeout=20)
        except subprocess.TimeoutExpired:
            studio.kill()
        subprocess.run([PYTHON, str(ROOT / "scripts/testdb.py"), "drop", database], capture_output=True)

    every = [t for times in results["requests"].values() for t in times]
    report = {
        "backend": str(args.backend), "via": args.via or "", "users": args.users, "seconds": round(elapsed, 1), "items_each": args.items,
        "requests": len(every), "requests_per_second": round(len(every) / elapsed, 1), "errors": results["errors"],
        "p50_ms": round(percentile(every, 50) * 1000, 1), "p95_ms": round(percentile(every, 95) * 1000, 1),
        "p99_ms": round(percentile(every, 99) * 1000, 1), "statuses": results["status"], "sockets": sockets, "jobs": jobs,
        "by_request": {k: {"n": len(v), "p50_ms": round(percentile(v, 50) * 1000, 1),
                           "p95_ms": round(percentile(v, 95) * 1000, 1)} for k, v in sorted(results["requests"].items())},
        "by_page": {k: {"n": len(v), "p50_ms": round(percentile(v, 50) * 1000, 1),
                        "p95_ms": round(percentile(v, 95) * 1000, 1)} for k, v in results["pages"].items()},
    }
    print(json.dumps(report, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--job-users", type=int, default=5, help="how many of them keep queueing jobs")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--items", type=int, default=200, help="library items of each user")
    parser.add_argument("--backend", default=str(ROOT / "backend"), help="the backend folder to run (for a before/after)")
    parser.add_argument("--out", help="also write the report here (JSON)")
    parser.add_argument("--via", help="host:port the studio reaches PostgreSQL at instead (a latency proxy, as Azure is)")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
