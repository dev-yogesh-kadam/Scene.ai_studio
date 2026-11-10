"""Throwaway PostgreSQL databases for the test studios (smoke, Playwright, screenshots: apps/web/tests/support/studio.mjs).

    python scripts/testdb.py create          make scene_tmp_<random> at the newest migration; prints its address
    python scripts/testdb.py drop <address>  drop it (its open connections are ended first)
    python scripts/testdb.py sweep           drop every scene_tmp_* that nothing is connected to (left by a killed run)

Each is made beside the test database SCENE_TEST_DATABASE_URL names, by its account (which needs CREATEDB), and owned
by it. Never the test database itself (pytest's), never the studio's: so runs at the same time keep their own rows.
"""

import contextlib
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

PREFIX = "scene_tmp_"


def base():
    url = os.environ.get("SCENE_TEST_DATABASE_URL", "")
    if not url:
        raise SystemExit("Set SCENE_TEST_DATABASE_URL to the test database "
                         "(postgresql://scene_test:<password>@localhost:5432/scene_test, docs/database.md).")
    return url


def with_database(url, name):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + name, parts.query, ""))


def main():
    import psycopg
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    url = base()
    with psycopg.connect(url, autocommit=True) as conn:
        if command == "create":
            from scene import schema
            name = PREFIX + secrets.token_hex(6)
            conn.execute('CREATE DATABASE "{}"'.format(name))
            made = with_database(url, name)
            with contextlib.redirect_stdout(sys.stderr):   # what the migrations say: only the address goes to stdout
                schema.upgrade(made)
            print(made)
        elif command == "drop" and len(sys.argv) > 2:
            name = urlsplit(sys.argv[2]).path.lstrip("/") or sys.argv[2]
            if not name.startswith(PREFIX):
                raise SystemExit("Only a throwaway database ({}*) is dropped here, not {}.".format(PREFIX, name))
            for attempt in range(30):   # autovacuum may be at work in it for a moment: only a superuser may stop that
                try:
                    conn.execute('DROP DATABASE IF EXISTS "{}" WITH (FORCE)'.format(name))
                    break
                except psycopg.errors.InsufficientPrivilege:
                    if attempt == 29:
                        raise
                    time.sleep(0.2)
        elif command == "sweep":
            idle = [r[0] for r in conn.execute(
                "SELECT datname FROM pg_database d WHERE datname LIKE %s AND NOT EXISTS "
                "(SELECT 1 FROM pg_stat_activity a WHERE a.datname = d.datname)", (PREFIX + "%",)).fetchall()]
            for name in idle:
                conn.execute('DROP DATABASE IF EXISTS "{}"'.format(name))
            print("dropped {}".format(len(idle)))
        else:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
