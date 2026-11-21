"""The studio's servers, as the admin console's Servers section lists them: Langfuse, which is sent the agent's calls
(langfuse_trace.py; its key is "public:secret"). It is added, switched off or removed in the console while the app runs.
The models the studio makes things with come from its providers (providers/registry.py), not from a server here; the
agent's model is Claude's, through Claude Code on this machine. (ComfyUI servers were listed here once: migration 0019
took them out.)
"""

import asyncio
import re

import httpx

from . import vault
from .db import offload

KINDS = {"langfuse": "Langfuse"}
FIELDS = ("kind", "name", "url", "api_key", "models", "slots", "active")
MOST_SLOTS = 16   # "Jobs at once" a server may be given


def seed(db, settings):
    """The servers and APIs of before (ComfyUI, Ollama, Kimi, Gemini) are taken out, keys and all."""
    db.run("DELETE FROM endpoints WHERE kind NOT IN ({})".format(", ".join("'{}'".format(k) for k in KINDS)))


def listed(db, kind=None, active_only=False):
    sql, params = "SELECT * FROM endpoints WHERE 1 = 1", []
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if active_only:
        sql += " AND active = 1"
    return db.all(sql + " ORDER BY id", tuple(params))


def clean(body, before=None):
    """What an admin typed for one, tidied: {"kind", "name", "url", "api_key", "models", "slots", "active"}. Nothing is
    refused but another kind than Langfuse: a missing name gets one, an address without http:// gets it, "Jobs at once" is kept between 1 and
    MOST_SLOTS, and one that does not answer is shown as not answering."""
    row = dict(before or {"kind": "langfuse", "name": "", "url": "", "api_key": "", "models": "", "slots": 1, "active": 1})
    for key in FIELDS:
        if key in body:
            row[key] = body[key]
    row["kind"] = str(row["kind"])
    if row["kind"] not in KINDS:
        raise ValueError("The Servers section holds Langfuse only: the models come from Servers & APIs → Providers.")
    row["name"] = " ".join(str(row["name"] or "").split())[:60] or KINDS[row["kind"]]
    row["url"] = "".join(str(row["url"] or "").split()).rstrip("/")[:300]
    if row["url"] and not re.match(r"^[a-z][a-z0-9+.-]*://", row["url"], re.I):
        row["url"] = "http://" + row["url"]
    row["api_key"] = str(row["api_key"] or "").strip()[:500]
    row["models"] = ", ".join(m.strip() for m in str(row["models"] or "").split(",") if m.strip())[:500]
    try:
        row["slots"] = max(1, min(MOST_SLOTS, int(row.get("slots") or 1)))
    except (TypeError, ValueError):
        row["slots"] = 1
    row["active"] = 1 if row["active"] else 0
    return row


def shown(row):
    """A row as the console sees it: the key is never sent back, only whether there is one."""
    return {k: row.get(k) for k in ("id", "kind", "name", "url", "models", "slots", "active", "created")} | {"has_key": bool(row.get("api_key"))}


async def status(state):
    """Every row with whether it answers now and what it runs. All are asked at once, briefly."""
    async def one(http, row):
        item = shown(row)
        if not row["url"]:
            return dict(item, online=False)
        try:
            if row["kind"] == "langfuse":
                r = await http.get(row["url"] + "/api/public/health")
                r.raise_for_status()
                item.update(online=True, detail="Langfuse " + str(r.json().get("version") or ""))
                keys = vault.reveal(row["api_key"])
                if ":" not in keys:
                    item["detail"] += " · no keys yet"
                else:   # the keys are tried too: the project they open, or that they are refused
                    public, _, secret = keys.partition(":")
                    r = await http.get(row["url"] + "/api/public/projects", auth=(public, secret))
                    projects = (r.json().get("data") or []) if r.status_code == 200 else None
                    item["detail"] += " · project " + projects[0].get("name", "") if projects else " · the keys are refused"
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            item["online"] = False
        sender = getattr(getattr(state, "traces", None), "langfuse", None)
        if row["kind"] == "langfuse" and row["active"] and sender is not None:   # how the sending goes (Sender.status)
            sending = item["sending"] = sender.status()
            said = [part for part in (item.get("detail") or "",
                                      "{:,} call(s) waiting".format(sending["backlog"]) if sending["backlog"] else "",
                                      "{:,} lost while it did not answer".format(sending["dropped"]) if sending["dropped"] else "")
                    if part]
            item["detail"] = " · ".join(said)
        return item

    async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2)) as http:
        return list(await asyncio.gather(*(one(http, row) for row in await offload(listed, state.db))))
