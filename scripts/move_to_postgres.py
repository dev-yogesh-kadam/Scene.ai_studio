"""Copy the studio's SQLite database into PostgreSQL, then check that every row arrived unchanged.

Run it from the repo root with the project's Python, with the app stopped (or on a copy of the database):

    .venv\\Scripts\\python.exe scripts\\move_to_postgres.py [path to scene.db]     (Windows)
    .venv/bin/python scripts/move_to_postgres.py [path to scene.db]                (macOS, Linux)

Add --leave-out-removed to copy a file that still has columns of features since removed (users.agent): those columns
are named and left out, instead of the copy being refused.

The SQLite file defaults to scene.db in the storage folder. The PostgreSQL database is the one config.json names
(database_url, and database_owner_url for the account that owns the tables), or the SCENE_DATABASE_URL and
SCENE_DATABASE_OWNER_URL environment variables. The PostgreSQL database must be empty: the script refuses to copy
over accounts that are already there. It reads the SQLite file and never changes it, and the copy is all or
nothing: if anything fails, PostgreSQL is left as it was. The rows are copied into the tables as migration 0001 (the
baseline) made them, then the database is migrated to the newest (scripts/migrate.py does the same for one copied before).
Kept for history: the studio left SQLite on 8 October 2026 and runs on PostgreSQL only. Addresses are printed without
their passwords.
"""

import math
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from scene.config import load_settings  # noqa: E402
from scene import schema  # noqa: E402
from scene.db import ID_TABLES  # noqa: E402

# Users first: every other table that names a user refers to this one.
FIRST = ["users"]


def snapshot(path, folder):
    """A consistent copy of a SQLite database, read without changing it, even while the app has it open."""
    source = sqlite3.connect("file:{}?mode=ro".format(Path(path).resolve().as_posix()), uri=True)
    copy = Path(folder) / "snapshot.db"
    target = sqlite3.connect(str(copy))
    source.backup(target)
    source.close()
    target.row_factory = sqlite3.Row
    return target


def tables(sqlite):
    names = [r["name"] for r in sqlite.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return FIRST + sorted(n for n in names if n not in FIRST)


def postgres_columns(conn, table):
    """{column: type} of a table in PostgreSQL."""
    rows = conn.execute("SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = current_schema() AND table_name = %s", (table,)).fetchall()
    return {name: kind for name, kind in rows}


def fit(value, kind, where):
    """A SQLite value as PostgreSQL's column takes it. SQLite lets a whole-number column hold 3.0; PostgreSQL does not."""
    if kind == "bigint" and isinstance(value, float):
        if not value.is_integer():
            raise SystemExit("{} holds {}, which is not a whole number.".format(where, value))
        return int(value)
    if kind == "bigint" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return value


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-9)
    return a == b


def safe(url):
    """An address with its password left out, for printing."""
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return "{}://{}@{}:{}{}".format(parts.scheme, parts.username, parts.hostname, parts.port or 5432, parts.path)


def main():
    settings = load_settings()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    leave_out = "--leave-out-removed" in sys.argv
    source = Path(args[0]) if args else settings.path("storage_dir") / "scene.db"
    if not source.is_file():
        raise SystemExit("There is no SQLite database at {}.".format(source))
    if not settings.database_url:
        raise SystemExit("Set database_url in config.json (or SCENE_DATABASE_URL) to the PostgreSQL database to copy into.")
    owner_url = settings.database_owner_url or settings.database_url
    print("From  {}".format(source))
    print("To    {} (tables owned by {})".format(safe(settings.database_url), safe(owner_url).split("://")[1].split("@")[0]))

    import psycopg
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        sqlite = snapshot(source, folder)
        left_out = {}
        # Make the tables as they were when the studio left SQLite (migration 0001, the baseline), with the app's
        # account granted its rights. The SQLite rows are copied in that shape; the later migrations then bring them to
        # today's (step 'Now at the newest migration' below), exactly as they did for the studio's own database.
        app_role = schema.app_role_for(owner_url, settings.database_url)
        schema.upgrade(owner_url, schema.BASELINE, app_role)
        with psycopg.connect(owner_url) as conn:   # one transaction: all of it, or none
            conn.execute("SELECT set_config('app.user_id', 'all', false)")   # row-level security: every user's rows
            if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                raise SystemExit("The PostgreSQL database already has accounts. Copy only into an empty one.")
            names = tables(sqlite)
            # The app put its two starting servers in on its first start; the copy brings the real ones.
            conn.execute("TRUNCATE {} CASCADE".format(", ".join(n for n in names if postgres_columns(conn, n))))
            counts = {}
            for table in names:
                columns = postgres_columns(conn, table)
                if not columns:
                    raise SystemExit("PostgreSQL has no table {}.".format(table))
                rows = sqlite.execute("SELECT * FROM {}".format(table)).fetchall()
                shared = [c for c in (rows[0].keys() if rows else []) if c in columns]
                missing = [c for c in (rows[0].keys() if rows else []) if c not in columns]
                if missing and not leave_out:
                    sqlite.close()
                    raise SystemExit("PostgreSQL's {} has no column {} (a removed feature's? then give --leave-out-removed)."
                                     .format(table, ", ".join(missing)))
                left_out.update({table: missing} if missing else {})
                if rows:
                    sql = "INSERT INTO {} ({}) VALUES ({})".format(table, ", ".join(shared), ", ".join(["%s"] * len(shared)))
                    with conn.cursor() as cursor:
                        cursor.executemany(sql, [tuple(fit(r[c], columns[c], "{}.{}".format(table, c)) for c in shared) for r in rows])
                if table in ID_TABLES:   # new rows continue after the highest number copied
                    conn.execute("SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE((SELECT MAX(id) FROM {}), 0) + 1, false)"
                                 .format(table), (table,))
                counts[table] = len(rows)

            # Check: every row of every table, value by value, in the same order on both sides.
            problems = []
            for table in names:
                keys = [r["name"] for r in sqlite.execute("PRAGMA table_info({})".format(table)) if r["pk"]] or ["rowid"]
                order = ", ".join(keys)
                left = sqlite.execute("SELECT * FROM {} ORDER BY {}".format(table, order)).fetchall()
                cursor = conn.execute("SELECT * FROM {} ORDER BY {}".format(table, order))
                fields = [d.name for d in cursor.description]
                right = [dict(zip(fields, r)) for r in cursor.fetchall()]
                if len(left) != len(right):
                    problems.append("{}: {} rows in SQLite, {} in PostgreSQL".format(table, len(left), len(right)))
                    continue
                for a, b in zip(left, right):
                    wrong = [c for c in a.keys() if c not in left_out.get(table, ()) and not same(a[c], b.get(c))]
                    if wrong:
                        problems.append("{} row {}: {} differ".format(table, [a[k] for k in keys if k != "rowid"], ", ".join(wrong)))
                        break
            credits = (sqlite.execute("SELECT COALESCE(SUM(credits), 0) FROM users").fetchone()[0],
                       conn.execute("SELECT COALESCE(SUM(credits), 0) FROM users").fetchone()[0])
            if credits[0] != credits[1]:
                problems.append("credits held: {} in SQLite, {} in PostgreSQL".format(*credits))
            if problems:
                conn.rollback()
                sqlite.close()
                raise SystemExit("Not copied; PostgreSQL was left as it was:\n  " + "\n  ".join(problems))
        sqlite.close()
    for line in schema.upgrade(owner_url, "head", app_role):   # Now at the newest migration
        print(line)

    for table, columns in left_out.items():
        print("  left out (removed features): " + ", ".join("{}.{}".format(table, c) for c in columns))
    width = max(len(t) for t in counts)
    for table, n in counts.items():
        print("  {:<{}}  {:>6} rows".format(table, width, n))
    print("Copied and checked: {} rows in {} tables, every value the same, {} credits held.".format(
        sum(counts.values()), len(counts), credits[0]))


if __name__ == "__main__":
    main()
