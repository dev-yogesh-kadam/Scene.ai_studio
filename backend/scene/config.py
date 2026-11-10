"""Application settings: defaults, then config.json in the project root, then SCENE_* environment variables."""

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    comfy_url: str = "http://127.0.0.1:8188"
    agent_model: str = ""         # the model the agent uses unless the user picks another ("sonnet"); empty = the first one
    # The agent's models are Anthropic's Claude, and only Claude: through Claude Code on this machine (the CLI or the VS
    # Code extension), signed in with its owner's Claude account, so no API key, and its usage limits are that account's.
    # Offered as "claude/<name>" in the model picker.
    claude_models: str = "sonnet, opus, haiku"   # the models to offer, as Claude Code names them
    claude_fast_model: str = "haiku"   # one of claude_models for the small jobs (captions, notes, checks); empty = the one in use
    claude_path: str = ""         # the claude program; empty = the one on PATH, else the VS Code extension's
    claude_timeout: int = 600     # seconds one call to Claude may take
    # The folder the agent tabs' Claude sessions run in: VS Code lists them with this folder's sessions. Empty = the
    # studio's own folder.
    claude_home: str = ""
    claude_context: int = 1000000   # tokens of context the Claude models have; a session is compacted at 90% of it
    host: str = "0.0.0.0"
    port: int = 8080
    # The admin console is a site of its own, on its own port, with its own sign-in. It listens only where console_host
    # says: 127.0.0.1 is this machine alone; a Tailscale address (100.x.y.z) lets your other machines in; several, comma-separated,
    # listen on each ("127.0.0.1,100.x.y.z"). Never point a public tunnel at it. console_port 0 turns it off.
    console_host: str = "127.0.0.1"
    console_port: int = 8090
    console_url: str = ""         # the console's address as an admin's browser reaches it, for the studio's link; empty = this host, console_port
    console_hours: int = 12       # how long a sign-in to the console lasts
    mobile_site_dir: str = "apps/mobile/dist"   # the phone site, built from apps/mobile/ (npm run build), served at /m/
    share_days: int = 30          # how long a share link opens its item without signing in; 0 turns share links off
    workflows_dir: str = "workflows"
    storage_dir: str = "storage"
    # PostgreSQL, the only database, as postgresql://<account>:<password>@localhost:5432/scene: the account the app works
    # as, which only reads and writes rows. The owner account makes and changes the tables, through the migrations
    # (scripts/migrate.py), never when the app starts.
    database_url: str = ""
    database_owner_url: str = ""
    database_pool_size: int = 10     # connections the app keeps open at most (and threads that wait on them)
    # A database call that blocks the event loop (db.py): "warn" says where, once per place; "raise" refuses it (the
    # tests); "off" says nothing.
    database_loop_guard: str = "warn"
    # The studio's time zone: what a "day" is in the console's charts and the analytics, whatever the database server's
    # or the machine's own is (on Azure both are UTC). An IANA name.
    time_zone: str = "Asia/Kolkata"
    output_dir: str = ""          # where finished images and videos are kept; empty = "outputs" inside storage_dir
    # Where the media are kept for good (storage.py): "local" (these folders, the default) or "azure" (Azure Blob Storage,
    # with these folders as its cache). For Azure: a connection string (an account key, or Azurite's), or, on Azure
    # itself, the account's URL (https://<account>.blob.core.windows.net) and the app's managed identity; the container;
    # how long a link a browser is given stays good.
    storage_backend: str = "local"
    azure_storage_connection_string: str = ""
    azure_storage_account_url: str = ""
    azure_storage_container: str = "scene"
    storage_sas_minutes: int = 15
    # Redis, for what several app processes share (shared.py): caches, live messages, rate limits. Empty = off, one
    # process, as always. Azure Cache for Redis: rediss://:<access key>@<name>.redis.cache.windows.net:6380/0.
    redis_url: str = ""
    log_format: str = ""          # "json": each line the app writes as a JSON object (logs.py), for Azure Monitor
    # Search by meaning (semantic.py; needs pgvector and migration 0011's table): off by default. The vectors come from
    # an embedding API: "voyage" (Voyage AI, embedding_api_key) or "azure_openai" (embedding_endpoint, the deployment in
    # embedding_model, embedding_api_key).
    semantic_search: bool = False
    embedding_provider: str = "voyage"
    embedding_api_key: str = ""
    embedding_endpoint: str = ""
    embedding_model: str = ""
    backup_dir: str = ""          # where the daily copies of the database go; empty = "backups" inside storage_dir
    backup_keep: int = 14         # how many days of copies are kept; 0 = no backups
    # Which copies are made: the database's (pg_dump) and the media files'. On Azure both are off: the database has
    # Azure's backups, Blob Storage its soft delete and versions.
    backup_database: bool = True
    backup_files: bool = True
    # A weekly test that the newest database copy restores: it is loaded into a scratch database made with this account
    # (one that may CREATE DATABASE, on the same server) and its rows counted. Empty = the test does not run.
    restore_test_url: str = ""
    # How many days of the agent's records are kept in the database (claude_events, agent_calls): older ones go, each
    # month, into compressed files in the backup folder (retention.py). 0 = keep everything. The audit log is never touched.
    retention_days: int = 0
    config_file: str = ""         # the config.json these settings were read from, so it is backed up too
    # The key the secrets kept in the database are encrypted with (vault.py), made on first start. SCENE_SECRET_KEY, when
    # set, is used instead. Keep a copy of it apart from the backups: they can't be read without it.
    secret_key_file: str = "secret.key"
    # The web app the studio and the admin console serve: apps/web, built by `npm run build -w apps/web` into web_dist_dir
    # (dist/studio/ and dist/console/). An older config.json may still say "web_app" or "frontend_dir": they are ignored.
    web_dist_dir: str = "apps/web/dist"
    node_path: str = ""           # the Node.js program that renders motion graphics; empty = the one that is installed
    default_workflow: str = ""
    # Who may make an account, after the first (the admin, made on this machine). Closed until an admin opens it, here or
    # in the admin console's Settings (which then wins): a fresh installation on the internet never lets strangers in
    # by accident. signup_invite: when set, an open sign-up also asks for this code, so only people given it get in.
    # signup_credits: what a new account starts with; 0 until an admin decides to give credits away.
    allow_signup: bool = False
    signup_invite: str = ""
    first_account_local: bool = True   # the first account (the admin) can only be made from the machine the app runs on
    session_days: int = 30
    # While the render server does not answer, renders wait in the queue instead of failing one after another, and a
    # render cut off by it going away goes back to the front of the queue (at most RESUMES times). Off only where there
    # is no render server at all (the tests).
    hold_queue_offline: bool = True
    secure_cookies: bool = False  # set true when the app is served over https
    signup_credits: int = 0       # credits a new account starts with (the console's Settings may set another number)
    signups_per_day: int = 3      # new accounts one visitor address may make in a day; 0 = no limit

    def path(self, name):
        path = Path(getattr(self, name)).expanduser()
        return path if path.is_absolute() else ROOT / path


# Settings that hold a password or a key: they belong in the environment (SCENE_*, an env file, Key Vault on Azure),
# not in config.json. One there is still read, for one more release, with a warning at start.
SECRETS = ("database_url", "database_owner_url", "restore_test_url", "azure_storage_connection_string", "redis_url",
           "embedding_api_key")


def read_env_file(path):
    """KEY=VALUE lines (# for a comment): what an env file next to config.json, or SCENE_ENV_FILE, holds."""
    found = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            found[key.strip()] = value.strip().strip('"').strip("'")
    return found


def load_settings(config_file=None):
    settings = Settings()
    config_file = Path(config_file or os.environ.get("SCENE_CONFIG") or ROOT / "config.json")
    saved = json.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file() else {}
    env_file = Path(os.environ.get("SCENE_ENV_FILE") or config_file.with_name("scene.env"))
    environment = {**(read_env_file(env_file) if env_file.is_file() else {}), **os.environ}   # the real environment wins
    settings.warnings = []
    for field in fields(Settings):
        value = environment.get("SCENE_" + field.name.upper(), saved.get(field.name))
        if field.name in SECRETS and saved.get(field.name) and "SCENE_" + field.name.upper() not in environment:
            settings.warnings.append(
                "config.json holds {0}, a password or a key: move it to the environment variable SCENE_{1} (or to {2}); "
                "config.json's will not be read after the next release.".format(field.name, field.name.upper(), env_file))
        if value is None:
            continue
        if field.type is bool and isinstance(value, str):
            value = value.lower() in ("1", "true", "yes", "on")
        setattr(settings, field.name, field.type(value))
    settings.config_file = str(config_file) if config_file.is_file() else ""
    return settings
