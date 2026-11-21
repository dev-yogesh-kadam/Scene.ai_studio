"""One-off jobs on a studio's database, from a shell where the studio runs (in Docker: `docker compose run --rm app
python -m scene.manage ...`). They use the app's own settings (SCENE_* variables, config.json) and its account.

    python -m scene.manage create-admin --email you@example.com [--name You] [--password-stdin]
    python -m scene.manage agent-uses-api-key

create-admin: the first account, the admin, while the studio has no account at all. The sign-in page makes it only
from a browser on the studio's own machine (first_account_local); behind Docker or a proxy no browser is, so this is
the way there. The password is asked for twice (or read from stdin with --password-stdin), never taken as an argument,
so it is not left in the shell's history or the process list.

agent-uses-api-key: the agent uses the Anthropic API key (the provider "Anthropic", made when missing) in place of
Claude on this PC, which a fresh database picks. The key itself is entered in the admin console afterwards (Servers &
APIs → Providers), and the console can change the choice again at any time."""

import argparse
import getpass
import sys
import time
from types import SimpleNamespace

from . import audit
from .api.auth import EMAIL, password_problem
from .config import load_settings
from .db import Database, as_everyone
from .security import hash_password


class _CommandLine:
    """What audit.record reads of a request, for a change made here: the database, and "command line" as the address."""

    def __init__(self, db):
        self.app = SimpleNamespace(state=SimpleNamespace(db=db))
        self.client = SimpleNamespace(host="command line")
        self.headers = {}


def _password(from_stdin):
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Password for the admin: ")
    if getpass.getpass("The same password again: ") != first:
        raise SystemExit("The two passwords are not the same. Nothing was made.")
    return first


def create_admin(db, email, name, password):
    """Make the first account, an admin. Returns its id; raises SystemExit with the reason when it is refused."""
    email = email.strip().lower()[:254]
    name = (name or "").strip()[:80] or email.split("@")[0]
    if not EMAIL.match(email):
        raise SystemExit("Enter a valid email address.")
    if password_problem(password):
        raise SystemExit(password_problem(password))
    with as_everyone():
        if db.one("SELECT 1 FROM users LIMIT 1"):
            raise SystemExit("The studio has accounts already: only the first one, the admin, is made here. "
                             "An admin makes the others in the admin console.")
        user_id = db.run("INSERT INTO users (email, name, password_hash, role, created) VALUES (?, ?, ?, ?, ?)",
                         (email, name, hash_password(password), "admin", time.time()))
        user = db.one("SELECT id, email, name FROM users WHERE id = ?", (user_id,))
        audit.record(_CommandLine(db), user, "Created account", email, "the first admin, from the command line")
    return user_id


def agent_uses_api_key(db):
    from .providers import registry
    with as_everyone():
        registry.save_claude(db, {"claude_connection": "api_key"})
        db.set_setting("claude_connection", "api_key")   # the old card's setting, kept beside the registry


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m scene.manage", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    jobs = parser.add_subparsers(dest="job", required=True)
    admin = jobs.add_parser("create-admin", help="make the first account, the admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="")
    admin.add_argument("--password-stdin", action="store_true", help="read the password from the first line of stdin")
    jobs.add_parser("agent-uses-api-key", help="the agent uses the Anthropic API key (entered in the console)")
    args = parser.parse_args(argv)

    settings = load_settings()
    if not settings.database_url:
        raise SystemExit("No database is set: SCENE_DATABASE_URL (or database_url in config.json).")
    db = Database(settings.database_url, seed=False, loop_guard="off", time_zone=settings.time_zone)
    try:
        if args.job == "create-admin":
            password = _password(args.password_stdin)
            create_admin(db, args.email, args.name, password)
            print("Made the admin {}. Sign in to the studio and the admin console with it.".format(args.email.strip().lower()))
        else:
            agent_uses_api_key(db)
            print("The agent now uses the Anthropic API key. Enter the key in the admin console: Servers & APIs → Providers.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
