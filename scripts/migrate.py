"""Run the database migrations (backend/migrations/) against a database, as the account that owns its tables.

Run it from the repo root with the project's Python, with the studio stopped and a fresh backup made:

    .venv\\Scripts\\python.exe scripts\\migrate.py upgrade                 bring it to the newest migration
    .venv\\Scripts\\python.exe scripts\\migrate.py current                 which migration it is at, and the newest
    .venv\\Scripts\\python.exe scripts\\migrate.py downgrade 0003          back to migration 0003 (each step's downgrade)
    .venv\\Scripts\\python.exe scripts\\migrate.py history                 every migration, oldest last

The database is database_owner_url from config.json (or SCENE_DATABASE_OWNER_URL), or --url. The app's own account
(database_url's user, or --app-role) is granted the rows of every table, new ones included. Addresses are printed
without their passwords. The start scripts never run this: changing the tables is a step of its own (docs/database.md).
A database made by the app before migrations is adopted: stamped at 0001 if it has all of the baseline, otherwise the
baseline adds what it lacks. Going below 0001 drops every table and needs --drop-everything.
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from scene import schema  # noqa: E402
from scene.config import load_settings  # noqa: E402


def safe(url):
    """An address with its password left out, for printing."""
    parts = urlsplit(url)
    return "{}@{}:{}{}".format(parts.username, parts.hostname, parts.port or 5432, parts.path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("upgrade", "downgrade", "current", "history"))
    parser.add_argument("target", nargs="?", help="a migration number (upgrade: default head; downgrade: required)")
    parser.add_argument("--url", help="the database, as its owner: postgresql://<owner>:<password>@<host>:5432/<db>")
    parser.add_argument("--app-role", help="the app's account to grant the rows to (default: database_url's user)")
    parser.add_argument("--drop-everything", action="store_true", help="allow a downgrade below 0001 (drops all tables)")
    args = parser.parse_args()

    settings = load_settings()
    url = args.url or settings.database_owner_url
    if not url:
        raise SystemExit("Give --url, or set database_owner_url in config.json (or SCENE_DATABASE_OWNER_URL).")
    app_role = args.app_role if args.app_role is not None else schema.app_role_for(url, settings.database_url)
    print("Database  {}{}".format(safe(url), "   (app account: {})".format(app_role) if app_role else ""))

    import psycopg
    from alembic import command
    config = schema.alembic_config(url, app_role)
    if args.command == "current":
        with psycopg.connect(url) as conn:
            print("At        {}".format(schema.version_of(conn) or "no migration yet"))
        print("Newest    {}".format(schema.head()))
    elif args.command == "history":
        command.history(config)
    elif args.command == "upgrade":
        for line in schema.upgrade(url, args.target or "head", app_role):
            print(line)
    else:
        if not args.target:
            raise SystemExit("Say which migration to go back to, e.g.  migrate.py downgrade 0003")
        config.cmd_opts = argparse.Namespace(x=["drop_everything=yes"] if args.drop_everything else [])
        command.downgrade(config, args.target)
        with psycopg.connect(url) as conn:
            print("Now at {}.".format(schema.version_of(conn) or "no migration (every table dropped)"))


if __name__ == "__main__":
    main()
