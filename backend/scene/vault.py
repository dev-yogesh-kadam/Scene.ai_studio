"""Secrets kept in the database (hosted API keys, two-step sign-in secrets, the Telegram bot's token) are stored
encrypted, so a copy of the database or of its backups gives none of them away.

The key is SCENE_SECRET_KEY when it is set, else the file secret_key_file names (secret.key in the project root),
made on first start. It is never in the database or the backups: keep a copy of it somewhere safe, since without it
the stored secrets can't be read (they are then entered again in the console and the studio's Settings)."""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

MARK = "enc1:"   # what a sealed value starts with; one without it is from before secrets were sealed
_box = None


def configure(key_file):
    """Use SCENE_SECRET_KEY, or the key in `key_file`, made there when there is none yet."""
    global _box
    key = os.environ.get("SCENE_SECRET_KEY", "").strip()
    if not key:
        key_file = Path(key_file)
        if not key_file.is_file():
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_bytes(Fernet.generate_key())
            try:
                key_file.chmod(0o600)
            except OSError:
                pass
        key = key_file.read_text(encoding="ascii").strip()
    _box = Fernet(key.encode("ascii"))


def _fernet():
    global _box
    if _box is None:   # not configured (a test calling straight in): a key for this process alone
        _box = Fernet(Fernet.generate_key())
    return _box


def seal(text):
    """`text` encrypted for the database. Empty stays empty; a value already sealed is left as it is."""
    text = str(text or "")
    if not text or text.startswith(MARK):
        return text
    return MARK + _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def reveal(text):
    """The secret a sealed value holds. A value from before sealing is returned as it is; one sealed with another key
    (the key was lost or changed) is returned empty."""
    text = str(text or "")
    if not text.startswith(MARK):
        return text
    try:
        return _fernet().decrypt(text[len(MARK):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        print("A stored secret can't be read with this secret key: enter it again in the console.")
        return ""


def seal_bytes(data):
    return _fernet().encrypt(data)


def seal_stored(db):
    """Once at start: seal the secrets stored before they were sealed."""
    for row in db.all("SELECT id, api_key FROM endpoints WHERE api_key != ''"):
        if not row["api_key"].startswith(MARK):
            db.run("UPDATE endpoints SET api_key = ? WHERE id = ?", (seal(row["api_key"]), row["id"]))
    for row in db.all("SELECT id, mfa_secret FROM users WHERE mfa_secret != ''"):
        if not row["mfa_secret"].startswith(MARK):
            db.run("UPDATE users SET mfa_secret = ? WHERE id = ?", (seal(row["mfa_secret"]), row["id"]))
