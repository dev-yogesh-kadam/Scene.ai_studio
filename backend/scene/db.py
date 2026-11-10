"""Storage: users, sessions, jobs, finished generations, projects, boards, assets, credits, pricing, settings and the
state of long runs (runs.py), in PostgreSQL, the only database the studio supports.

The app's SQL is written with ? for each value (postgres_sql turns it into psycopg's). The tables are made and changed
by migrations (backend/migrations/, run with scripts/migrate.py), never by the app: it checks at start that the database
is at the newest migration and refuses to start if not (schema.require_current)."""

import asyncio
import contextlib
import contextvars
import functools
import inspect
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from . import edge, refs, schema

# The studio's two machines, added to an installation that has no servers yet. Every value can be changed in the
# admin console; the power of Zoro is a first assumption until it is measured at the wall.
SERVERS = [
    ("Lufi", "Ryzen 9 7900X", "RTX 4060 Ti", 8, "Hosting the studio, light workflows", 0, None),
    ("Zoro", "Ryzen 9 9950X", "RTX 5090", 32, "Heavy image, video and audio generation", 1, 950),
]



# Whose rows a statement may see: a user's id, or EVERYONE. Each request that signs a user in narrows it to that user
# (api/deps.py), the admin console widens it again, and work that is no one request's (the queue, backups, signing in)
# keeps the default. PostgreSQL enforces it with row-level security (the policies own_rows, migration 0001).
EVERYONE = "all"
ACTING = contextvars.ContextVar("acting", default=EVERYONE)
# (database, connection) of the transaction the code running now is in (Database.transaction), or None.
_IN_TRANSACTION = contextvars.ContextVar("in_transaction", default=None)


def act_for(user_id):
    """From here to the end of this request, statements see only this user's rows."""
    ACTING.set(str(user_id))


def act_for_everyone():
    ACTING.set(EVERYONE)


@contextlib.contextmanager
def as_everyone():
    """For a read inside a user's request that is meant to span all users (queue positions, time estimates)."""
    token = ACTING.set(EVERYONE)
    try:
        yield
    finally:
        ACTING.reset(token)


def open_database(settings, storage=None):
    """The database config.json (database_url) or SCENE_DATABASE_URL names. There is no other kind."""
    if not settings.database_url:
        raise RuntimeError("No database is set. The studio runs on PostgreSQL only: set database_url in config.json or "
                           "SCENE_DATABASE_URL to postgresql://<account>:<password>@<host>:5432/<database> "
                           "(docs/database.md).")
    return Database(settings.database_url, pool_size=settings.database_pool_size, loop_guard=settings.database_loop_guard,
                    time_zone=settings.time_zone)


def _seed(db):
    """What the app puts in a database at its migration once it starts: its starting rows, and fixes of old rows."""
    with as_everyone():
        refs.fill_projects(db)
        _kit_per_module(db)
        _films_shown(db)
    if not db.one("SELECT 1 FROM servers"):
        for server in SERVERS:
            db.run("INSERT INTO servers (name, cpu, gpu, vram_gb, role, renders, generation_power_w, created) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (*server, time.time()))


def _films_shown(db):
    """A run's whole film (placement.FINISHED) used to be filed as a working file of the run, so no canvas listed it."""
    db.run("UPDATE generations SET run = '' WHERE run <> '' AND workflow IN ('edit/film', 'edit/assemble')")


def _kit_per_module(db):
    """Once: NeuralCore was the project's, shared by its modules; now each module has its own. An entry kept on a
    project's top that was made in one of its modules moves to that module; the rest stay with the main canvas."""
    if db.one("SELECT 1 FROM settings WHERE key = 'kit_per_module'"):
        return
    db.run("UPDATE assets SET project_id = (SELECT g.project_id FROM generations g WHERE g.id = assets.made_from) "
           "WHERE made_from IS NOT NULL AND EXISTS (SELECT 1 FROM generations g JOIN projects m ON m.id = g.project_id "
           "WHERE g.id = assets.made_from AND m.parent_id = assets.project_id)")
    db.run("INSERT INTO settings (key, value) VALUES ('kit_per_module', '1')")


# ---------------------------------------------------------------- PostgreSQL

# The tables whose rows get a number of their own; an INSERT into one of them returns it. A migration that adds such a
# table adds it here (test_schema checks this against the database).
ID_TABLES = {"agent_calls", "agent_plans", "alerts", "assets", "audit_log", "boards", "claude_events", "claude_sessions",
             "conversation_messages", "conversations",
             "client_errors", "credit_events", "credit_packages", "endpoints", "generations", "moderation", "projects",
             "servers", "users", "workflow_versions"}

@functools.lru_cache(maxsize=1024)
def postgres_sql(sql):
    """A statement written with ? for each value, as psycopg takes it: %s for each value outside quotes, and every
    % of the text doubled. An INSERT into a numbered table also returns the new number."""
    out, quote = [], None
    for ch in sql:
        if ch == "%":
            out.append("%%")
        elif quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            out.append(ch)
            quote = ch
        else:
            out.append("%s" if ch == "?" else ch)
    sql = "".join(out)
    table = re.match(r"\s*INSERT INTO (\w+)", sql, re.I)
    if table and table.group(1) in ID_TABLES and not re.search(r"\bRETURNING\b", sql, re.I):
        sql += " RETURNING id"   # how PostgreSQL tells the new row's number (run returns it)
    return sql


def _plain(value):
    """A sum or a rounded number comes back from PostgreSQL as a Decimal, which does not mix with float. The app
    expects an int or a float, as it always had."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


class Database:
    """PostgreSQL through a pool of connections (psycopg_pool): statements from different threads run side by side.
    The app works as an account that may only read and write rows (database_url); the tables belong to another one,
    which only the migrations use (database_owner_url, scripts/migrate.py).

    Row-level security: each statement tells the connection it takes whose rows it is for (ACTING, as app.user_id), in
    the same round trip as the statement, unless that connection already shows that user's rows: a pooled connection
    never carries one request's user into another's statement. (A RESET as each connection went back doubled the cost
    of every statement: docs/history/db-upgrade-log.md, Part 2.)

    The event loop never waits for the database: async code awaits aall/aone/arun/achange/asetting/aset_setting (or
    offload(fn) for a helper that queries), which run on the database's own threads with the caller's context (and so
    its ACTING). A plain call on the event loop's thread is what `loop_guard` catches: "warn" says where, once per place;
    "raise" refuses it (the tests); "off" lets it be."""

    kind = "postgres"
    suffix = ".dump"   # of its backup copies: pg_dump's own format, put back with pg_restore

    def __init__(self, url, seed=True, pool_size=10, loop_guard="warn", time_zone="Asia/Kolkata"):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        self.psycopg = psycopg
        self.url = url
        parts = urlsplit(url)
        # What the backup folder records as the database it holds copies of: the address without the password.
        self.path = urlunsplit((parts.scheme, "{}:{}".format(parts.hostname, parts.port or 5432), parts.path, "", ""))
        self.pool = ConnectionPool(url, min_size=1, max_size=max(1, pool_size), open=True, timeout=30, name="scene",
                                   kwargs={"autocommit": True, "row_factory": dict_row},
                                   configure=edge.configure)   # timestamptz read as seconds, JSONB as its text
        _threads(pool_size)
        self.loop_guard = loop_guard
        self.time_zone = str(ZoneInfo(time_zone))   # a real zone's name (so it is safe to write into SQL)
        self.warned = set()   # the places a plain call on the event loop was reported from ("warn")
        self.serving = False  # true while the app serves requests (main.lifespan): what it does on start blocks no one
        self.shared = None    # what several processes share (shared.py; main.py sets it): the settings' cache
        self.shape = edge.Shape()
        schema.require_current(self)   # the tables are the migrations' to make: a database behind them is refused
        with self.pool.connection() as conn:   # which columns are times, to give them times (edge.with_times)
            self.shape = edge.Shape.read(conn)
        if seed:
            _seed(self)

    def _execute(self, sql, params):
        """Run one statement on a connection of the pool, for ACTING's rows. A connection the server dropped (it
        restarted) is thrown away and the statement tried once more on another. Inside transaction(), on its
        connection (and never tried again: the transaction is what failed)."""
        open_one = _IN_TRANSACTION.get()
        if open_one is not None and open_one[0] is self:
            return self._statement(open_one[1], sql, params)
        if self.serving and self.loop_guard != "off" and _on_event_loop():
            self._on_loop(sql)
        for attempt in (1, 2):
            conn = None
            try:
                with self.pool.connection() as conn:
                    return self._statement(conn, sql, params)
            except self.psycopg.OperationalError:
                if attempt == 2 or conn is None or not conn.broken:
                    raise

    def _statement(self, conn, sql, params):
        """One statement on `conn`, for ACTING's rows: (rows, how many rows it changed)."""
        acting = ACTING.get()
        statement = postgres_sql(self.shape.translate(sql))
        if getattr(conn, "acting", None) == acting:
            cursor = conn.execute(statement, tuple(params))   # it already shows this user's rows
        else:
            with conn.pipeline():   # whose rows, then the statement: sent together, one round trip
                conn.execute("SELECT set_config('app.user_id', %s, false)", (acting,))
                cursor = conn.execute(statement, tuple(params))
            conn.acting = acting
        empty_json = edge.json_columns(cursor.description)   # NULL there was '' (migration 0004)
        hidden = edge.hidden_columns(cursor.description)   # a search column (0009): `SELECT *` stays as it was
        rows = [{k: "" if v is None and k in empty_json else _plain(v) for k, v in row.items() if k not in hidden}
                for row in cursor.fetchall()] if cursor.description else []
        return rows, cursor.rowcount

    @contextlib.contextmanager
    def transaction(self):
        """Every statement of this database inside the block, on this thread, runs in one transaction on one
        connection: all of it is kept, or (an exception) none of it. For a read-then-write that must not interleave
        with another request's (a row lock, `SELECT ... FOR UPDATE`, holds until the block ends). A transaction
        inside another is part of it. Sync: keep it short, and never await inside it."""
        open_one = _IN_TRANSACTION.get()
        if open_one is not None and open_one[0] is self:
            yield
            return
        if self.serving and self.loop_guard != "off" and _on_event_loop():
            self._on_loop("BEGIN (a transaction)")
        with self.pool.connection() as conn:
            token = _IN_TRANSACTION.set((self, conn))
            try:
                with conn.transaction():
                    yield
            except BaseException:
                conn.acting = None   # a set_config made inside a transaction that rolled back is undone with it
                raise
            finally:
                _IN_TRANSACTION.reset(token)

    def _on_loop(self, sql):
        """A plain (blocking) statement on the event loop's thread: where it came from, once, or refused."""
        place = blocking_place()
        if self.loop_guard == "raise":
            raise RuntimeError("A database call on the event loop ({}): await db.a{}(...) or db.offload(...) instead. "
                               "SQL: {}".format(place, "all/one/run/change", " ".join(sql.split())[:120]))
        if place not in self.warned:
            self.warned.add(place)
            print("The database was called on the event loop at {} (it waits there for the answer).".format(place))

    def offload(self, fn, *args, **kwargs):   # the same as the module's offload(); kept as a method for code holding a db
        """Run `fn` (anything that queries the database) on the database's threads, with this context (whose rows):
        awaitable. For a helper of sync code called from async code."""
        context = contextvars.copy_context()
        return asyncio.get_running_loop().run_in_executor(_threads(), functools.partial(context.run, fn, *args, **kwargs))

    async def aall(self, sql, params=()):
        return await self.offload(self.all, sql, params)

    async def aone(self, sql, params=()):
        return await self.offload(self.one, sql, params)

    async def arun(self, sql, params=()):
        return await self.offload(self.run, sql, params)

    async def achange(self, sql, params=()):
        return await self.offload(self.change, sql, params)

    async def asetting(self, key, default=None):
        return await self.offload(self.setting, key, default)

    async def aset_setting(self, key, value):
        return await self.offload(self.set_setting, key, value)

    def size(self):
        return self.one("SELECT pg_database_size(current_database()) AS n")["n"]

    def close(self):
        self.pool.close()

    def local_day(self, column):
        """SQL for the studio's calendar day (YYYY-MM-DD, in time_zone) of a time column."""
        return "to_char({} AT TIME ZONE '{}', 'YYYY-MM-DD')".format(column, self.time_zone)

    @staticmethod
    def utc_text(column):
        return "to_char({} AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')".format(column)

    def backup(self, target):
        """A whole copy of the database in pg_dump's format. The password goes in the environment, not the command.
        It reads as EVERYONE, so row-level security lets it see every row; without that, pg_dump refuses to run.
        Returns {table: rows}, counted in the very snapshot pg_dump copies (exported from a transaction held open while
        it runs): what the restore test checks the copy against, exact even while the studio goes on writing."""
        parts = urlsplit(self.url)
        env = dict(os.environ, PGPASSWORD=unquote(parts.password or ""), PGOPTIONS="-c app.user_id=" + EVERYONE)
        address = urlunsplit((parts.scheme, "{}@{}:{}".format(parts.username, parts.hostname, parts.port or 5432),
                              parts.path, parts.query, ""))
        with self.psycopg.connect(self.url) as conn:   # its own connection: it stays in one transaction for the dump
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            conn.execute("SELECT set_config('app.user_id', %s, true)", (EVERYONE,))
            snapshot = conn.execute("SELECT pg_export_snapshot()").fetchone()[0]
            tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")]
            counts = {t: conn.execute('SELECT COUNT(*) FROM "{}"'.format(t)).fetchone()[0] for t in tables}
            subprocess.run([pg_tool("pg_dump"), "--format=custom", "--enable-row-security", "--snapshot", snapshot,
                            "--file", str(target), "--dbname", address], env=env, check=True, capture_output=True, timeout=600)
            conn.rollback()
        return counts

    def run(self, sql, params=()):
        """Run a statement and return the new row id (for INSERT into a numbered table)."""
        rows, _ = self._execute(sql, params)
        return rows[0]["id"] if rows and "id" in rows[0] else None

    def change(self, sql, params=()):
        return self._execute(sql, params)[1]

    def all(self, sql, params=()):
        return self._execute(sql, params)[0]

    def one(self, sql, params=()):
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def setting(self, key, default=None):
        def read():
            row = self.one("SELECT value FROM settings WHERE key = ?", (key,))
            return row["value"] if row else None
        found = self.shared.cached("settings", key, read) if self.shared is not None else read()   # shared.py
        return default if found is None else found

    def set_setting(self, key, value):
        self.run("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, str(value)))
        if self.shared is not None:
            self.shared.changed("settings")   # every process reads it again


PostgresDatabase = Database   # its name while there were two kinds (scripts/move_to_postgres.py)


def blocking_place():
    """Where a plain call on the event loop came from: the first line outside this file, and the async function that
    called it, when that is another ("credits.py:254 in spend, from workspace.py:880 in agent_message")."""
    frame = sys._getframe(1)
    while frame and (frame.f_code.co_filename == __file__ or frame.f_code.co_name in ("_on_loop", "_report")):
        frame = frame.f_back
    if frame is None:
        return "?"
    where = "{}:{} in {}".format(Path(frame.f_code.co_filename).name, frame.f_lineno, frame.f_code.co_name)
    caller, called = frame, frame
    while caller and not caller.f_code.co_flags & (inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR):
        caller, called = caller.f_back, caller
    if caller and caller is not frame:
        where += ", from {}:{} in {} (calling {})".format(Path(caller.f_code.co_filename).name, caller.f_lineno,
                                                           caller.f_code.co_name, called.f_code.co_name)
    return where


async def offload(fn, *args, **kwargs):
    """Run `fn` (sync code that queries the database) on the database's threads, with this context (and so whose rows
    it acts for). For async code that calls such a helper: `await offload(credits.balance, user_id)`."""
    context = contextvars.copy_context()
    return await asyncio.get_running_loop().run_in_executor(_threads(), functools.partial(context.run, fn, *args, **kwargs))


_THREADS = []


def _threads(size=None):
    """The threads database work runs on, one set for the process (as many as the pool has connections, so a thread
    never waits for one). Made by the first Database; never shut down while the process runs."""
    if not _THREADS:
        _THREADS.append(ThreadPoolExecutor(max_workers=max(1, size or 10), thread_name_prefix="db"))
    return _THREADS[0]


def _on_event_loop():
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def pg_tool(name):
    """A PostgreSQL program (pg_dump, pg_restore): on the PATH, or where the Windows installer puts it."""
    found = shutil.which(name)
    if found:
        return found
    for folder in sorted(Path(os.environ.get("ProgramFiles", r"C:\Program Files"), "PostgreSQL").glob("*/bin"), reverse=True):
        if (folder / (name + ".exe")).is_file():
            return str(folder / (name + ".exe"))
    raise RuntimeError("{} was not found. Install PostgreSQL's command-line tools.".format(name))
