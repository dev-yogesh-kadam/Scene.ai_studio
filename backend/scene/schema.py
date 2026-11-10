"""The database's shape is kept by Alembic migrations (backend/migrations/versions/), not by the app: the app checks at
start that its database is at the newest one and refuses to start if not (require_current). scripts/migrate.py runs
them, as the account that owns the tables. How to write one: docs/database.md."""

import importlib.util
import re
from pathlib import Path
from urllib.parse import urlsplit

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
BASELINE = "0001"


class SchemaError(RuntimeError):
    """The database is not at the migration this code was written for."""


def sqlalchemy_url(url):
    """postgresql://... as SQLAlchemy names the psycopg 3 driver."""
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+psycopg://", url)


def alembic_config(url="", app_role=""):
    from alembic.config import Config
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.attributes["url"] = url
    config.attributes["app_role"] = app_role
    return config


def head():
    """The newest migration of this code."""
    from alembic.script import ScriptDirectory
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def sql(statement):
    """Run SQL in a migration, as written: on psycopg's own connection, in the migration's transaction, with no
    placeholders (a % or a :name is just text)."""
    from alembic import op
    op.get_bind().connection.driver_connection.execute(statement)


def grant_app(execute, app_role):
    """The app's account may read and write the rows of every table and use its numbering, nothing more. `execute`
    runs one statement."""
    role = '"{}"'.format(app_role.replace('"', ""))
    execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO " + role)
    execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO " + role)
    execute("REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM " + role)   # it reads which migration, never sets it


def version_of(conn):
    """The migration a database is at (psycopg connection), None for one Alembic has never run on."""
    if not conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()[0]:
        return None
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row else None


def require_current(db):
    """Refuse to start on a database that is not at this code's newest migration, with what to do about it."""
    wanted = head()
    row = db.one("SELECT to_regclass('public.alembic_version') IS NOT NULL AS there")
    found = db.one("SELECT version_num FROM alembic_version")["version_num"] if row["there"] else None
    if found == wanted:
        return
    where = db.path
    if found is None:
        problem = "{} has never been migrated (no alembic_version table).".format(where)
    else:
        problem = "{} is at migration {}; this code needs {}.".format(where, found, wanted)
    raise SchemaError(problem + " Stop the studio, back up the database, and run:  python scripts/migrate.py upgrade  "
                      "(as the owner account, see docs/database.md). The app does not change tables itself.")


def _baseline():
    path = next((MIGRATIONS / "versions").glob(BASELINE + "_*.py"))
    spec = importlib.util.spec_from_file_location("baseline_" + BASELINE, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade(url, target="head", app_role=""):
    """Bring a database up to `target`. One that was made before migrations (by the app's own start, which changed
    tables then) is adopted first: stamped at the baseline if it already has the baseline's whole shape, otherwise
    the baseline is run on it, which only adds what it lacks. Returns what was done, in words."""
    import psycopg
    from alembic import command
    done = []
    with psycopg.connect(url, autocommit=True) as conn:
        version = version_of(conn)
        made = conn.execute("SELECT to_regclass('public.users') IS NOT NULL").fetchone()[0]
        gaps = _baseline().gaps(conn) if version is None and made else []
    config = alembic_config(url, app_role)
    if version is None and made:
        if gaps:
            done.append("An existing database without migrations, short of the baseline: " + "; ".join(gaps)
                        + ". The baseline adds only what is missing.")
        else:
            command.stamp(config, BASELINE)
            done.append("An existing database at the baseline's shape: stamped {} (nothing ran).".format(BASELINE))
    command.upgrade(config, target)
    with psycopg.connect(url, autocommit=True) as conn:
        done.append("Now at {}.".format(version_of(conn)))
    return done


def downgrade(url, target, app_role=""):
    from alembic import command
    command.downgrade(alembic_config(url, app_role), target)


def app_role_for(owner_url, app_url):
    """The app's account, to grant the rows of new tables to: the user of database_url when it is another account than
    the owner's on the same database."""
    owner, app = urlsplit(owner_url or ""), urlsplit(app_url or "")
    if app.username and app.username != owner.username and (app.hostname, app.path) == (owner.hostname, owner.path):
        return app.username
    return ""
