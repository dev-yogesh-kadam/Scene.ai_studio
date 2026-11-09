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
    mobile_site_dir: str = "mobile/dist"   # the phone site, built from mobile/ (npm run build), served at /m/
    share_days: int = 30          # how long a share link opens its item without signing in; 0 turns share links off
    workflows_dir: str = "workflows"
    storage_dir: str = "storage"
    # PostgreSQL, as postgresql://<account>:<password>@localhost:5432/scene; empty = SQLite in storage_dir. The owner
    # account makes and changes the tables when the app starts; the app itself then only reads and writes rows.
    database_url: str = ""
    database_owner_url: str = ""
    output_dir: str = ""          # where finished images and videos are kept; empty = "outputs" inside storage_dir
    backup_dir: str = ""          # where the daily copies of the database go; empty = "backups" inside storage_dir
    backup_keep: int = 14         # how many days of copies are kept; 0 = no backups
    config_file: str = ""         # the config.json these settings were read from, so it is backed up too
    # The key the secrets kept in the database are encrypted with (vault.py), made on first start. SCENE_SECRET_KEY, when
    # set, is used instead. Keep a copy of it apart from the backups: they can't be read without it.
    secret_key_file: str = "secret.key"
    frontend_dir: str = "frontend"
    node_path: str = ""           # the Node.js program that renders motion graphics; empty = the one that is installed
    default_workflow: str = ""
    allow_signup: bool = True
    first_account_local: bool = True   # the first account (the admin) can only be made from the machine the app runs on
    session_days: int = 30
    # While the render server does not answer, renders wait in the queue instead of failing one after another, and a
    # render cut off by it going away goes back to the front of the queue (at most RESUMES times). Off only where there
    # is no render server at all (the tests).
    hold_queue_offline: bool = True
    secure_cookies: bool = False  # set true when the app is served over https
    signup_credits: int = 1000    # credits a new account starts with
    signups_per_day: int = 3      # new accounts one visitor address may make in a day; 0 = no limit

    def path(self, name):
        path = Path(getattr(self, name)).expanduser()
        return path if path.is_absolute() else ROOT / path


def load_settings(config_file=None):
    settings = Settings()
    config_file = Path(config_file or os.environ.get("SCENE_CONFIG") or ROOT / "config.json")
    saved = json.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file() else {}
    for field in fields(Settings):
        value = os.environ.get("SCENE_" + field.name.upper(), saved.get(field.name))
        if value is None:
            continue
        if field.type is bool and isinstance(value, str):
            value = value.lower() in ("1", "true", "yes", "on")
        setattr(settings, field.name, field.type(value))
    settings.config_file = str(config_file) if config_file.is_file() else ""
    return settings
