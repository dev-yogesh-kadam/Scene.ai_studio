"""Dated copies of the database and of config.json (encrypted with the secret key, see vault.py): one of each per day, made when the app starts and once a day
after that. A database that is lost or overwritten then costs a day of work at most. The finished pictures, videos and
sounds and the kit's uploads are copied too, into files/ in the same folder: only what is new or changed each time.
Nothing is ever deleted from the copy: a file deleted in the studio (with its project, say) keeps its copy there."""

import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path

from . import vault


def make(db, folder, config_file="", keep=14):
    """Write today's copies, in place of earlier ones from today, and delete those older than the newest `keep` days."""
    folder = _claim(db, folder)
    day = date.today().isoformat()
    target = folder / "scene_{}{}".format(day, db.suffix)
    partial = folder / "scene.partial"   # a copy that was cut short never stands in for a whole one
    partial.unlink(missing_ok=True)
    counts = db.backup(partial)   # what the restore test checks the copy against: counted in the copy's own snapshot
    partial.replace(target)
    target.with_name(target.stem + ".counts.json").write_text(json.dumps(counts), encoding="utf-8")
    if config_file and Path(config_file).is_file():   # it holds keys and passwords: its copy is encrypted (vault.py)
        (folder / "config_{}.json.enc".format(day)).write_bytes(vault.seal_bytes(Path(config_file).read_bytes()))
    for plain in folder.glob("config_*.json"):   # the plain copies made before copies were encrypted
        plain.unlink()
    for pattern in ("scene_*" + db.suffix, "scene_*.counts.json", "config_*.json.enc"):
        for old in sorted(folder.glob(pattern))[:-keep] if keep > 0 else []:
            old.unlink()
    return target


def check(db, folder):
    """Whether the newest copy of the database can be read back: pg_restore reads it through and counts its tables of
    data. The finding is kept in the `backup_check` setting: {when, copy, ok, detail}."""
    copies = sorted(Path(folder).glob("scene_*" + db.suffix))
    found = {"when": time.time(), "copy": copies[-1].name if copies else "", "ok": False}
    if not copies:
        found["detail"] = "There is no copy yet."
    else:
        from .db import pg_tool
        try:
            listed = subprocess.run([pg_tool("pg_restore"), "--list", str(copies[-1])], capture_output=True, text=True, timeout=120)
            tables = sum(1 for line in listed.stdout.splitlines() if " TABLE DATA " in line)
            found["ok"] = listed.returncode == 0 and tables > 0
            found["detail"] = "pg_restore reads it: {} tables of data.".format(tables) if found["ok"] else "pg_restore can't read it: " + listed.stderr[:200]
        except (OSError, subprocess.SubprocessError) as error:
            found["detail"] = "pg_restore could not be run: {}".format(error)
    db.set_setting("backup_check", json.dumps(found))
    return found


def row_counts(db):
    """{table: rows} of every table, every user's."""
    from .db import as_everyone
    with as_everyone():
        tables = [r["tablename"] for r in db.all("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")]
        return {t: db.one('SELECT COUNT(*) AS n FROM "{}"'.format(t))["n"] for t in tables}


RESTORE_EVERY = 7 * 86400


def restore_test(db, folder, url):
    """Put the newest copy back into a scratch database made with `url`'s account (it may CREATE DATABASE), count its
    rows against the counts taken with the copy, and drop it again. Kept in the `restore_test` setting:
    {when, copy, ok, detail, tables, differ}. Sync: run on a thread."""
    import secrets
    from urllib.parse import unquote, urlsplit, urlunsplit
    import psycopg
    from .db import pg_tool
    copies = sorted(Path(folder).glob("scene_*" + db.suffix))
    found = {"when": time.time(), "copy": copies[-1].name if copies else "", "ok": False, "tables": 0, "differ": {}}
    if not copies:
        found["detail"] = "There is no copy to restore yet."
        db.set_setting("restore_test", json.dumps(found))
        return found
    name = "scene_restore_" + secrets.token_hex(4)
    parts = urlsplit(url)
    scratch = urlunsplit((parts.scheme, parts.netloc, "/" + name, parts.query, ""))
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute('CREATE DATABASE "{}"'.format(name))
        env = dict(os.environ, PGPASSWORD=unquote(parts.password or ""), PGOPTIONS="-c app.user_id=all")
        address = urlunsplit((parts.scheme, "{}@{}:{}".format(parts.username, parts.hostname, parts.port or 5432),
                              "/" + name, parts.query, ""))
        restored = subprocess.run([pg_tool("pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error",
                                   "--dbname", address, str(copies[-1])], env=env, capture_output=True, text=True, timeout=1800)
        if restored.returncode != 0:
            found["detail"] = "pg_restore failed: " + restored.stderr[-300:]
        else:
            with psycopg.connect(scratch, autocommit=True) as conn:
                conn.execute("SELECT set_config('app.user_id', 'all', false)")
                tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")]
                got = {t: conn.execute('SELECT COUNT(*) FROM "{}"'.format(t)).fetchone()[0] for t in tables}
            sidecar = copies[-1].with_name(copies[-1].stem + ".counts.json")
            expected = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else {}
            found["tables"] = len(got)
            found["differ"] = {t: [expected.get(t), got.get(t)] for t in set(expected) | set(got)
                               if expected and expected.get(t) != got.get(t)}
            found["ok"] = bool(got.get("users")) and not found["differ"]
            if found["ok"]:
                found["detail"] = "Restored into a scratch database: {} tables, {} rows, every count as when the copy was made.".format(
                    len(got), sum(got.values()))
            elif found["differ"]:
                found["detail"] = "Restored, but {} tables have other counts than when the copy was made: {}".format(
                    len(found["differ"]), ", ".join(sorted(found["differ"]))[:200])
            else:
                found["detail"] = "Restored, but it has no accounts."
    except (OSError, subprocess.SubprocessError, psycopg.Error) as error:
        found["detail"] = "The restore test could not run: {}".format(str(error).splitlines()[0] if str(error) else error)
    finally:
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute('DROP DATABASE IF EXISTS "{}" WITH (FORCE)'.format(name))
        except psycopg.Error:
            pass
    db.set_setting("restore_test", json.dumps(found))
    return found


def last_restore_test(db):
    try:
        return json.loads(db.setting("restore_test", "") or "null")
    except ValueError:
        return None


def last_check(db):
    try:
        return json.loads(db.setting("backup_check", "") or "null")
    except ValueError:
        return None


def _claim(db, folder):
    """The folder remembers which database it holds copies of. A second copy of the app (a test run) that was given the
    same folder is refused, so it cannot put its own database or files in place of the real one's copies."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    owner = folder / "database.txt"
    if owner.is_file() and owner.read_text(encoding="utf-8").strip() != str(db.path):
        raise RuntimeError("it holds the copies of another database, {}".format(owner.read_text(encoding="utf-8").strip()))
    owner.write_text(str(db.path), encoding="utf-8")
    return folder


def copy_files(db, folder, sources, keep=14, now=None):
    """Copy each source folder ({"outputs": path, ...}) into files/<name>/ of the backup folder: the files that are not
    there yet or whose size or time has changed. Nothing is deleted from the copy. Posters and keyframes are not copied:
    they are made again from the file. Returns how many files were copied. (`keep` and `now` are not used.)"""
    files = _claim(db, folder) / "files"
    now = now or time.time()
    copied = 0
    seen = set()
    for name, source in sources.items():
        source = Path(source)
        if not source.is_dir():
            continue
        for path in source.rglob("*"):
            if not path.is_file() or ".posters" in path.parts:
                continue
            seen.add(str(Path(name) / path.relative_to(source)))
            target = files / name / path.relative_to(source)
            info = path.stat()
            if target.is_file():
                there = target.stat()
                if there.st_size == info.st_size and int(there.st_mtime) == int(info.st_mtime):
                    continue
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".partial")   # a copy cut short never stands in for a whole one
            shutil.copy2(path, partial)
            partial.replace(target)
            copied += 1
    return copied


def newest(folder):
    """When the last copy of the database was made, or None if there is none."""
    return max((f.stat().st_mtime for f in Path(folder).glob("scene_*") if f.suffix in (".db", ".dump")), default=None)


def attempt(db, folder, config_file="", keep=14):
    """A backup that fails (a disk that is full or unplugged) must not stop the app: say so and carry on."""
    try:
        return make(db, folder, config_file, keep)
    except Exception as error:
        print("The backup to {} failed: {}".format(folder, error))
        return None


def attempt_files(db, folder, sources, keep=14):
    try:
        return copy_files(db, folder, sources, keep)
    except Exception as error:
        print("The copy of the files to {} failed: {}".format(folder, error))
        return None


CHECK_EVERY = 3600   # seconds between looks at whether the day's copies are made


async def run_forever(db, folder, config_file="", keep=14, sources=None, database=True, restore_url="", retention_days=0):
    """The database was copied as the app started (when `database`); its files follow here (when there are `sources`),
    without holding the start up. Then both once a day; the restore test once a week (when `restore_url` is set); the
    agent's old records archived once a month (when `retention_days`). See Schedule."""
    await Schedule(db, folder, config_file, keep, sources, database, restore_url, retention_days).run_forever()


class Schedule:
    """The daily copies, by the calendar: every CHECK_EVERY seconds it looks whether today's are made, and makes them
    when not. So a studio that runs for weeks makes its copy soon after midnight each day, one that was asleep (the PC
    suspended) or whose copy failed (the backup disk unplugged) makes it within the hour, and a restart on the same day
    does not make a second one. Each part's failure is printed and tried again the next time: none stops the others or
    the schedule."""

    def __init__(self, db, folder, config_file="", keep=14, sources=None, database=True, restore_url="", retention_days=0):
        self.db, self.folder, self.config_file, self.keep = db, Path(folder), config_file, keep
        self.sources, self.database, self.restore_url, self.retention_days = sources, database, restore_url, retention_days
        self.files_day = None   # the day the files were last copied

    def copied_today(self, today):
        return (self.folder / "scene_{}{}".format(today, self.db.suffix)).is_file()

    async def tick(self, today=None):
        """One look: what is due is done. Returns the parts it did."""
        from . import retention
        today = today or date.today().isoformat()
        done = []
        if self.database and not self.copied_today(today):
            if await asyncio.to_thread(attempt, self.db, self.folder, self.config_file, self.keep) is not None:
                done.append("database")
        if self.sources and self.files_day != today:
            if await asyncio.to_thread(attempt_files, self.db, self.folder, self.sources, self.keep) is not None:
                self.files_day = today
                done.append("files")
        try:
            last = (await asyncio.to_thread(last_restore_test, self.db) or {}).get("when") or 0
            if self.restore_url and time.time() - last >= RESTORE_EVERY:
                await asyncio.to_thread(restore_test, self.db, self.folder, self.restore_url)
                done.append("restore_test")
        except Exception as error:
            print("The restore test of the backups could not run: {}".format(error))
        if self.retention_days > 0:
            try:
                if await asyncio.to_thread(retention.due, self.db):
                    await asyncio.to_thread(retention.archive, self.db, self.folder, self.retention_days)
                    done.append("archive")
            except Exception as error:
                print("The agent's old records were not archived: {}".format(error))
        return done

    async def run_forever(self):
        while True:
            try:
                await self.tick()
            except Exception as error:   # whatever it was, the next look comes
                print("The backup schedule's look failed: {}".format(error))
            await asyncio.sleep(CHECK_EVERY)
