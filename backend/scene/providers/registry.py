"""The provider registry: providers, their keys and the models each key unlocks (migration 0015), as the console's
Servers & APIs → Providers lists them.

- A key is sealed with vault.py when it is saved and revealed only to call its provider (secret_of). The console is
  shown its label and last 4 characters (shown), never the key.
- An environment variable can still fix a key, as SCENE_ANTHROPIC_API_KEY does: it is listed as
  a key of its provider that the console can't change ("fixed", id FIXED_IDS), and used before the stored ones.
- Every model the studio offers comes from a provider here: Scene providers over the v1 contract (Studio_automation)
  and On this PC (local_tools, the studio's own tools). ComfyUI is not one any more (migration 0019).
- Which provider the agent uses (Claude on this PC or Anthropic) is the setting `agent_provider`.
  Claude on this PC (claude_local, migration 0016) has no key and no address: it uses the account Claude Code is
  signed in with on this PC.

The functions here touch the database: async code runs them through db.offload."""

import json
import time

from .. import vault
from ..db import as_everyone
from .base import AGENT_LLM, BUILT_IN, CAPABILITY_FOLDERS, CAPABILITY_WORDS, CLAUDE_KINDS, KEYLESS, KINDS, MODEL_KINDS, SELF_HOSTED, STATUSES, last4

AGENT_PROVIDER = "agent_provider"
MOST_CONCURRENT = 64
# The provider kind of each way claude.py reaches Claude Code (claude_connection.MODES), and back.
MODE_OF = {"claude_local": "this_pc", "anthropic": "api_key"}
KIND_OF = {mode: kind for kind, mode in MODE_OF.items()}
LEGACY_OF = {"claude_local": "claude:local", "anthropic": "claude:anthropic"}
# Keys an environment variable fixes: (provider kind, the settings field, the key's id in listings, its label).
FIXED = (("anthropic", "anthropic_api_key", -1, "SCENE_ANTHROPIC_API_KEY"),)
FIXED_IDS = {kind: key_id for kind, _, key_id, _ in FIXED}
KEY_FIELDS = ("label", "active", "priority", "max_concurrent", "daily_cap")
ORDER = "x-scene-order"   # kept in a stored input_schema: its inputs in the provider's order (jsonb sorts keys)


def _json(value):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else None
    except (TypeError, ValueError):
        return None


def _fixed(settings):
    return set(getattr(settings, "from_environment", None) or ())


# ---------------------------------------------------------------- reading

def providers(db, active_only=False):
    with as_everyone():
        return db.all("SELECT * FROM providers{} ORDER BY priority, id".format(" WHERE active = 1" if active_only else ""))


def provider(db, provider_id):
    with as_everyone():
        return db.one("SELECT * FROM providers WHERE id = ?", (int(provider_id),))


def keys(db, provider_id=None):
    with as_everyone():
        if provider_id is None:
            return db.all("SELECT * FROM provider_keys ORDER BY priority, id")
        return db.all("SELECT * FROM provider_keys WHERE provider_id = ? ORDER BY priority, id", (int(provider_id),))


def key(db, key_id):
    with as_everyone():
        return db.one("SELECT * FROM provider_keys WHERE id = ?", (int(key_id),))


def fixed_keys(settings, row):
    """The keys of a provider that an environment variable fixes, as key rows (never stored)."""
    found = []
    for kind, field, key_id, variable in FIXED:
        if row["kind"] == kind and field in _fixed(settings) and str(getattr(settings, field, "") or "").strip():
            secret = str(getattr(settings, field)).strip()
            found.append({"id": key_id, "provider_id": row["id"], "label": variable, "secret": vault.seal(secret),
                          "last4": last4(secret), "active": 1, "priority": -1, "max_concurrent": None, "daily_cap": None,
                          "status": "unknown", "cooldown_until": None, "last_error": "", "last_checked": None,
                          "last_used": None, "info": None, "created": None, "fixed": True})
    return found


def secret_of(row):
    """A key row's secret, revealed to call its provider. Never logged, never sent to a page."""
    return vault.reveal(row.get("secret") or "")


def shown_key(row):
    """A key as the console sees it: never the key, only its label and last 4."""
    info = _json(row.get("info")) or {}
    return {"id": row["id"], "provider_id": row["provider_id"], "label": row["label"], "last4": row["last4"],
            "has_secret": bool(row.get("secret")), "active": bool(row["active"]), "priority": row["priority"],
            "max_concurrent": row["max_concurrent"], "daily_cap": row["daily_cap"], "status": row["status"],
            "cooldown_until": row["cooldown_until"], "last_error": row["last_error"], "last_checked": row["last_checked"],
            "last_used": row["last_used"], "fixed": bool(row.get("fixed")),
            "credits": info.get("credits") if isinstance(info.get("credits"), dict) else None,
            "alerts": [str(a) for a in info.get("alerts") or []][:6],
            "mode": str((info.get("key") or {}).get("mode") or ""),
            "said_max_concurrent": (info.get("key") or {}).get("max_concurrent")}


def models(db, provider_id=None, key_id=None):
    """The cached models, rows of provider_models with their JSON read."""
    sql, params = "SELECT * FROM provider_models WHERE 1 = 1", []
    if provider_id is not None:
        sql += " AND provider_id = ?"
        params.append(int(provider_id))
    if key_id is not None:
        sql += " AND key_id = ?"
        params.append(int(key_id))
    with as_everyone():
        rows = db.all(sql + " ORDER BY capability, model_id", tuple(params))
    for row in rows:
        for field in ("input_schema", "limits", "pricing"):
            row[field] = _json(row[field]) or {}
    return rows


def listing(db, settings):
    """Every provider with its keys (shown), its models count and kinds, for the console."""
    agent = agent_provider_id(db)
    every_key = keys(db)
    counts, opened = {}, unlocks(db)
    with as_everyone():
        for r in db.all("SELECT provider_id, COUNT(DISTINCT model_id) AS n FROM provider_models GROUP BY provider_id"):
            counts[r["provider_id"]] = r["n"]
    found = []
    for row in providers(db):
        own = fixed_keys(settings, row) + [k for k in every_key if k["provider_id"] == row["id"]]
        shown = [dict(shown_key(k), unlocks=opened.get(k["id"], []) if row["kind"] in MODEL_KINDS else []) for k in own]
        found.append({"id": row["id"], "kind": row["kind"], "kind_name": KINDS.get(row["kind"], row["kind"]),
                      "name": row["name"], "base_url": row["base_url"], "active": bool(row["active"]),
                      "priority": row["priority"], "created": row["created"], "legacy": row["legacy"],
                      "keys": shown, "models": counts.get(row["id"], 0),
                      "agent": row["id"] == agent, "keyless": row["kind"] in KEYLESS})
    return found


def unlocks(db):
    """What each key unlocks, from its last read models: {key id: [{"capability", "words", "models": [{"id", "name"}]}]},
    capabilities in the console's order (CAPABILITY_WORDS), each one's models by name."""
    with as_everyone():
        rows = db.all("SELECT key_id, capability, model_id, name FROM provider_models ORDER BY key_id, capability, name, model_id")
    order = list(CAPABILITY_WORDS)
    found = {}
    for r in rows:
        groups = found.setdefault(r["key_id"], {})
        groups.setdefault(r["capability"], []).append({"id": r["model_id"], "name": r["name"] or r["model_id"]})
    return {key_id: [{"capability": c, "words": CAPABILITY_WORDS.get(c, c.replace("_", " ").capitalize()), "models": ms}
                     for c, ms in sorted(groups.items(), key=lambda item: order.index(item[0]) if item[0] in order else len(order))]
            for key_id, groups in found.items()}


# ---------------------------------------------------------------- several keys pasted at once

KEY_LINE_MOST = 50   # keys one paste may hold


def parse_keys(text):
    """The keys of a paste, one a line: "label<TAB>key" (Studio_automation's "Copy all"), "label: key", "label key"
    (the last word is the key) or the key alone. Blank lines and lines starting with # are left out. Returns
    [{"line", "label", "secret"}]; raises ValueError naming a line that holds no key, or when there are too many."""
    found = []
    for n, raw in enumerate(str(text or "").replace("\r", "").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            label, _, secret = line.rpartition("\t")
        else:
            words = line.split()
            secret, label = words[-1], " ".join(words[:-1])
        label, secret = label.strip().rstrip(":").strip(), secret.strip()
        if len(secret) < 8 or any(c.isspace() for c in secret):
            raise ValueError("Line {} holds no key: write one key a line, as label<TAB>key or the key alone.".format(n))
        found.append({"line": n, "label": " ".join(label.split())[:60], "secret": secret})
    if not found:
        raise ValueError("Paste at least one key.")
    if len(found) > KEY_LINE_MOST:
        raise ValueError("At most {} keys at once; this paste has {}.".format(KEY_LINE_MOST, len(found)))
    if len({k["secret"] for k in found}) != len(found):
        raise ValueError("The same key is pasted twice.")
    return found


def has_secret(db, provider_id, secret):
    """The label of a key of this provider that is this very key already, or ""."""
    for row in keys(db, provider_id):
        if row.get("secret") and secret_of(row) == secret:
            return row["label"]
    return ""


# ---------------------------------------------------------------- what makes what

def provider_offers(db):
    """{capability: [{"id", "name", "providers": [names], "keys": [{"label", "mode", "status"}]}]}: the models of the
    providers that are on (Scene providers and On this PC), from keys that are on and not invalid."""
    with as_everyone():
        rows = db.all(
            "SELECT m.capability, m.model_id, m.name, p.name AS p_name, k.label, k.status, k.info FROM provider_models m "
            "JOIN provider_keys k ON k.id = m.key_id JOIN providers p ON p.id = m.provider_id "
            "WHERE p.kind IN ('scene_provider_v1', 'local_tools') AND p.active = 1 AND k.active = 1 AND k.status <> 'invalid' "
            "ORDER BY m.capability, m.name, m.model_id, p.priority, k.priority, k.id")
    found = {}
    for r in rows:
        models_ = found.setdefault(r["capability"], {})
        model = models_.setdefault(r["model_id"], {"id": r["model_id"], "name": r["name"] or r["model_id"], "providers": [], "keys": []})
        if r["p_name"] not in model["providers"]:
            model["providers"].append(r["p_name"])
        mode = str(((_json(r["info"]) or {}).get("key") or {}).get("mode") or "")
        model["keys"].append({"label": r["label"], "mode": mode, "status": r["status"]})
    return {c: list(ms.values()) for c, ms in found.items()}


# Work a model that edits a reference video does as well as making new clips (its limits say reference_video_edits):
# the agent's recipes for these use such a model (agent.py), so they count as made when one is offered.
EDITS = ("video_to_video", "outpaint", "animate")


def coverage(db):
    """What makes what, by capability, for the console: each row {"capability", "words", "models", "live" (a live key
    covers it), "state": "provider" | "none"}. Video to video, outpaint and character animation are made by the video
    models that edit a reference video (EDITS)."""
    offers = provider_offers(db)
    with as_everyone():
        editing = {r["model_id"] for r in db.all("SELECT model_id, limits FROM provider_models WHERE capability = 'text_to_video'")
                   if (_json(r["limits"]) or {}).get("reference_video_edits")}
    rows = []
    for capability in CAPABILITY_WORDS:
        models_ = offers.get(capability, [])
        if capability in EDITS:
            models_ = [m for m in offers.get("text_to_video", []) if m["id"] in editing]
        live = any(k["mode"] != "test" for m in models_ for k in m["keys"])
        rows.append({"capability": capability, "words": CAPABILITY_WORDS[capability], "models": models_, "live": live,
                     "state": "provider" if models_ else "none"})
    return rows


# ---------------------------------------------------------------- the agent's provider

def agent_provider_id(db):
    try:
        return int(db.setting(AGENT_PROVIDER, "") or 0) or None
    except (TypeError, ValueError):
        return None


def agent_choice(db, settings):
    """What the agent uses: {"kind": "claude_local" | "anthropic", "provider", "secret", "base_url"}:
    the provider of `agent_provider` (else Claude on this PC, else the first Anthropic one), with its best key (a fixed
    one first, then by priority, leaving out keys switched off or found invalid; none for Claude on this PC). None when
    the registry has no Claude provider."""
    rows = [r for r in providers(db) if r["kind"] in CLAUDE_KINDS]
    if not rows:
        return None
    wanted = agent_provider_id(db)
    row = next((r for r in rows if r["id"] == wanted), None) or next((r for r in rows if r["kind"] == "claude_local"), None) \
        or next((r for r in rows if r["kind"] == "anthropic"), rows[0])
    usable = [k for k in fixed_keys(settings, row) + keys(db, row["id"]) if k["active"]]
    best = next((k for k in usable if k["status"] != "invalid"), usable[0] if usable else None)
    return {"kind": row["kind"], "provider": row, "secret": secret_of(best) if best else "", "base_url": row["base_url"],
            "key": best}


def _best(db, settings, kind):
    """(provider row, its best key row or None) of the first provider of this kind, or (None, None)."""
    row = next((r for r in providers(db) if r["kind"] == kind), None)
    if row is None:
        return None, None
    usable = [k for k in fixed_keys(settings, row) + keys(db, row["id"]) if k["active"]]
    return row, next((k for k in usable if k["status"] != "invalid"), usable[0] if usable else None)


def claude_values(db, settings):
    """The Claude connection as the registry has it, in claude_connection's fields: {"claude_connection",
    "anthropic_api_key"}; None when the registry has no Claude provider (a
    database from before migration 0015). Environment variables are applied by the caller."""
    choice = agent_choice(db, settings)
    if choice is None:
        return None
    anthropic, anthropic_key = _best(db, settings, "anthropic")
    return {"claude_connection": MODE_OF[choice["kind"]],
            "anthropic_api_key": secret_of(anthropic_key) if anthropic_key else ""}


def save_claude(db, changes):
    """The old Claude connection card's save (claude_connection.save), written into the registry: the connection picked
    (agent_provider), a new API key (put in place of the provider's first key, or added). `changes`: {field: value} of claude_connection's fields."""
    def provider_of(kind, name, legacy, base_url=""):
        row = next((r for r in providers(db) if r["kind"] == kind), None)
        if row is None:
            with as_everyone():
                db.run("INSERT INTO providers (kind, name, base_url, active, priority, legacy, created) VALUES (?, ?, ?, 1, ?, ?, ?) "
                       "ON CONFLICT DO NOTHING", (kind, name, base_url, 0, legacy, time.time()))
            row = next(r for r in providers(db) if r["kind"] == kind)
        return row

    def put_key(row, secret, label):
        first = (keys(db, row["id"]) or [None])[0]
        if first is None:
            add_key(db, row["id"], secret, label)
        else:
            change_key(db, first["id"], {"secret": secret, "active": 1})

    if changes.get("anthropic_api_key"):
        put_key(provider_of("anthropic", "Anthropic", "claude:anthropic"), changes["anthropic_api_key"], "API key")
    if "claude_connection" in changes:
        kind = KIND_OF[changes["claude_connection"]]
        db.set_setting(AGENT_PROVIDER, str(provider_of(kind, KINDS[kind], LEGACY_OF[kind])["id"]))


def set_agent_provider(db, provider_id):
    row = provider(db, provider_id)
    if row is None or row["kind"] not in CLAUDE_KINDS:
        raise ValueError("The agent uses Claude on this PC or Anthropic: pick one of those.")
    db.set_setting(AGENT_PROVIDER, str(row["id"]))
    return row


# ---------------------------------------------------------------- changing

def clean_url(text):
    text = "".join(str(text or "").split()).rstrip("/")[:300]
    if text and "://" not in text:
        text = "http://" + text
    return text


def add_provider(db, kind, name="", base_url="", priority=0, active=True):
    if kind not in KINDS:
        raise ValueError("Pick a provider type: " + ", ".join(KINDS.values()) + ".")
    if kind in BUILT_IN:
        raise ValueError("{} is made by the studio itself: there is one already.".format(KINDS[kind]))
    if kind in KEYLESS and any(r["kind"] == kind for r in providers(db)):
        raise ValueError("{} is there already: this PC has one Claude Code.".format(KINDS[kind]))
    base_url = clean_url(base_url) if kind in SELF_HOSTED else ""
    if kind in SELF_HOSTED and not base_url:
        raise ValueError("A {} provider needs its address, like http://100.64.0.7:8189.".format(KINDS[kind]))
    name = " ".join(str(name or "").split())[:60] or KINDS[kind]
    with as_everyone():
        provider_id = db.run("INSERT INTO providers (kind, name, base_url, active, priority, created) VALUES (?, ?, ?, ?, ?, ?)",
                             (kind, name, base_url, 1 if active else 0, int(priority or 0), time.time()))
    return provider_id


def change_provider(db, provider_id, body):
    row = provider(db, provider_id)
    if row is None:
        raise LookupError("There is no such provider.")
    name = " ".join(str(body.get("name", row["name"]) or "").split())[:60] or row["name"]
    base_url = clean_url(body.get("base_url", row["base_url"])) if row["kind"] in SELF_HOSTED else ""
    if row["kind"] in SELF_HOSTED and not base_url:
        raise ValueError("A {} provider needs its address.".format(KINDS[row["kind"]]))
    active = 1 if body.get("active", row["active"]) else 0
    priority = _int(body.get("priority", row["priority"]), 0)
    with as_everyone():
        db.run("UPDATE providers SET name = ?, base_url = ?, active = ?, priority = ? WHERE id = ?",
               (name, base_url, active, priority, row["id"]))
    return provider(db, provider_id)


def remove_provider(db, provider_id):
    row = provider(db, provider_id)
    if row is None:
        raise LookupError("There is no such provider.")
    if row["id"] == agent_provider_id(db):
        raise ValueError("The agent uses {}: pick another for the agent first.".format(row["name"]))
    if row["kind"] in BUILT_IN:
        raise ValueError("{} is part of the studio: switch it off instead.".format(row["name"]))
    with as_everyone():
        db.run("DELETE FROM providers WHERE id = ?", (row["id"],))
    return row


def _int(value, default=None, low=None, high=None):
    if value in (None, ""):
        return default
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError("'{}' is not a whole number.".format(value))
    if low is not None and value < low or high is not None and value > high:
        raise ValueError("{} is out of range ({} to {}).".format(value, low, high))
    return value


def add_key(db, provider_id, secret, label="", max_concurrent=None, daily_cap=None, priority=0, status="unknown",
            info=None, error=""):
    row = provider(db, provider_id)
    if row is None:
        raise LookupError("There is no such provider.")
    if row["kind"] in KEYLESS:
        raise ValueError("{} has no key: it uses the account Claude Code is signed in with on this PC.".format(KINDS[row["kind"]]))
    if row["kind"] in BUILT_IN and keys(db, row["id"]):
        raise ValueError("{} needs no key: its tools run on this PC.".format(KINDS[row["kind"]]))
    secret = str(secret or "").strip()[:2000]
    if not secret:
        raise ValueError("Paste the key.")
    label = " ".join(str(label or "").split())[:60] or "Key {}".format(len(keys(db, row["id"])) + 1)
    with as_everyone():
        key_id = db.run(
            "INSERT INTO provider_keys (provider_id, label, secret, last4, active, priority, max_concurrent, daily_cap, status, "
            "last_error, last_checked, info, created) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["id"], label, vault.seal(secret), last4(secret), _int(priority, 0),
             _int(max_concurrent, None, 1, MOST_CONCURRENT), _int(daily_cap, None, 0),
             status if status in STATUSES else "unknown", str(error or "")[:500],
             time.time() if status != "unknown" else None, json.dumps(info) if info else None, time.time()))
    return key_id


def change_key(db, key_id, body):
    row = key(db, key_id)
    if row is None:
        raise LookupError("There is no such key.")
    values = {"label": " ".join(str(body.get("label", row["label"]) or "").split())[:60] or row["label"],
              "active": 1 if body.get("active", row["active"]) else 0,
              "priority": _int(body.get("priority", row["priority"]), 0),
              "max_concurrent": _int(body.get("max_concurrent", row["max_concurrent"]), None, 1, MOST_CONCURRENT),
              "daily_cap": _int(body.get("daily_cap", row["daily_cap"]), None, 0)}
    with as_everyone():
        db.run("UPDATE provider_keys SET label = ?, active = ?, priority = ?, max_concurrent = ?, daily_cap = ? WHERE id = ?",
               (values["label"], values["active"], values["priority"], values["max_concurrent"], values["daily_cap"], row["id"]))
        if str(body.get("secret") or "").strip():   # a new key in its place: its health is not known yet
            secret = str(body["secret"]).strip()[:2000]
            db.run("UPDATE provider_keys SET secret = ?, last4 = ?, status = 'unknown', cooldown_until = NULL, last_error = '' "
                   "WHERE id = ?", (vault.seal(secret), last4(secret), row["id"]))
    return key(db, key_id)


def remove_key(db, key_id):
    row = key(db, key_id)
    if row is None:
        raise LookupError("There is no such key.")
    with as_everyone():
        db.run("DELETE FROM provider_keys WHERE id = ?", (row["id"],))
    return row


def mark(db, key_id, status=None, cooldown_until=None, error=None, info=None, checked=True, used=False):
    """What was learned of a key from a call: its status, a cooldown, the error in words, what whoami said."""
    if key_id is None or key_id < 0:   # a fixed key: nothing stored
        return
    sets, params = [], []
    if status is not None:
        sets.append("status = ?")
        params.append(status if status in STATUSES else "unknown")
        sets.append("cooldown_until = ?")
        params.append(cooldown_until)
    if error is not None:
        sets.append("last_error = ?")
        params.append(str(error)[:500])
    if info is not None:
        sets.append("info = ?")
        params.append(json.dumps(info))
    if checked:
        sets.append("last_checked = ?")
        params.append(time.time())
    if used:
        sets.append("last_used = ?")
        params.append(time.time())
    if sets:
        with as_everyone():
            db.run("UPDATE provider_keys SET {} WHERE id = ?".format(", ".join(sets)), (*params, int(key_id)))


def save_models(db, provider_id, key_id, found):
    """A key's models as its provider just listed them: replaced whole. (A list that can't be read is not saved: the
    last good one stays.)"""
    if key_id is None or key_id < 0:
        return
    now = time.time()
    with as_everyone():
        db.run("DELETE FROM provider_models WHERE key_id = ?", (int(key_id),))
        for m in found:
            schema = m.get("input_schema") if isinstance(m.get("input_schema"), dict) else {}
            if isinstance(schema.get("properties"), dict):   # jsonb keeps no order: the provider's order of its inputs
                schema = dict(schema, **{ORDER: list(schema["properties"])})
            m = dict(m, input_schema=schema)
            typical = m.get("typical_seconds")
            db.run("INSERT INTO provider_models (provider_id, key_id, model_id, capability, name, best_for, input_schema, limits, "
                   "pricing, typical_seconds, can_cancel, seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                   "ON CONFLICT (key_id, model_id) DO NOTHING",
                   (int(provider_id), int(key_id), str(m["id"])[:200], str(m["capability"])[:60], str(m.get("name") or m["id"])[:200],
                    str(m.get("best_for") or "")[:1000], json.dumps(m.get("input_schema") or {}), json.dumps(m.get("limits") or {}),
                    json.dumps(m.get("pricing") or {}),
                    float(typical) if isinstance(typical, (int, float)) and not isinstance(typical, bool) else None,
                    1 if m.get("can_cancel") else 0, now))


# ---------------------------------------------------------------- at start

def seed(db, settings):
    """At start: the last 4 of copied keys filled in (migration 0015 copies them sealed); Claude on this PC, an Anthropic
    provider and On this PC always there; `agent_provider` set when it is not (Claude on this PC, unless config.json
    says otherwise)."""
    with as_everyone():
        for row in db.all("SELECT id, secret FROM provider_keys WHERE last4 = '' AND secret <> ''"):
            found = last4(vault.reveal(row["secret"]))
            if found:
                db.run("UPDATE provider_keys SET last4 = ? WHERE id = ?", (found, row["id"]))
        if not db.one("SELECT 1 FROM providers WHERE kind = 'claude_local'"):
            db.run("INSERT INTO providers (kind, name, base_url, active, priority, legacy, created) "
                   "VALUES ('claude_local', 'Claude on this PC', '', 1, 0, 'claude:local', ?) ON CONFLICT DO NOTHING", (time.time(),))
        if not db.one("SELECT 1 FROM providers WHERE kind = 'anthropic'"):
            db.run("INSERT INTO providers (kind, name, base_url, active, priority, legacy, created) "
                   "VALUES ('anthropic', 'Anthropic', '', 1, 0, 'claude:anthropic', ?) ON CONFLICT DO NOTHING", (time.time(),))
        if not db.one("SELECT 1 FROM providers WHERE kind = 'local_tools'"):   # On this PC (migration 0018) and its one key
            db.run("INSERT INTO providers (kind, name, base_url, active, priority, legacy, created) "
                   "VALUES ('local_tools', 'On this PC', '', 1, 0, 'local:tools', ?) ON CONFLICT DO NOTHING", (time.time(),))
        db.run("INSERT INTO provider_keys (provider_id, label, secret, last4, active, priority, max_concurrent, status) "
               "SELECT p.id, 'This PC', '', '', 1, 0, 1, 'unknown' FROM providers p WHERE p.kind = 'local_tools' "
               "AND NOT EXISTS (SELECT 1 FROM provider_keys k WHERE k.provider_id = p.id)")
    if agent_provider_id(db) is None or provider(db, agent_provider_id(db)) is None:
        mode = db.setting("claude_connection") or getattr(settings, "claude_connection", "this_pc")
        wanted = KIND_OF.get(mode, "claude_local")
        row = next((r for r in providers(db) if r["kind"] == wanted), None) or \
            next((r for r in providers(db) if r["kind"] == "claude_local"), None)
        if row is not None:
            db.set_setting(AGENT_PROVIDER, str(row["id"]))


def capabilities_of(kind):
    """The capabilities a provider kind can offer, for the console's words."""
    if kind in CLAUDE_KINDS:
        return [AGENT_LLM]
    return sorted(CAPABILITY_FOLDERS)
