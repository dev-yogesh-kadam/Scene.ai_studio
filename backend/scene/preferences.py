"""A user's own choices, kept on the server so they follow the user to any browser: the agent's (which model, how hard
it thinks per model, whether a plan runs without Approve, the "explain" switch per conversation) and the studio's
(the workflow used last for each kind, the kind and the project Create opened on last, the skills used lately). Kept as
JSON in the settings table, one row each. Only the browser's own view stays in it: theme, motion, panel width, tab."""

import json
import re

AGENT_KEY = "agent_prefs.{}"
STUDIO_KEY = "studio_prefs.{}"
PERMISSIONS = ("all", "videos", "always")   # run at once; ask before videos; ask before every plan (the default)
NAME = re.compile(r"^[\w./:@ -]{1,120}$")   # a model, a workflow or a skill id; a conversation's id; an effort level


def _read(db, key):
    try:
        found = json.loads(db.setting(key, "{}"))
    except ValueError:
        found = {}
    return found if isinstance(found, dict) else {}


def _names(value, most):
    """A map of short names to short names (effort per model, workflow per kind); None when it is not one."""
    if not isinstance(value, dict) or len(value) > most:
        return None
    if not all(isinstance(k, str) and isinstance(v, str) and NAME.match(k) and NAME.match(v) for k, v in value.items()):
        return None
    return dict(value)


def agent(db, user_id):
    """{"model": name or None (the studio's default), "effort": {model: level}, "permission", "explain": {tab: bool}}."""
    kept = _read(db, AGENT_KEY.format(int(user_id)))
    permission = kept.get("permission")
    return {"model": kept.get("model") if isinstance(kept.get("model"), str) else None,
            "effort": kept.get("effort") if isinstance(kept.get("effort"), dict) else {},
            "permission": permission if permission in PERMISSIONS else "always",
            "explain": kept.get("explain") if isinstance(kept.get("explain"), dict) else {}}


def set_agent(db, user_id, body):
    """Change what the body names; anything else stays. A bad value is refused (ValueError), nothing changed."""
    kept = agent(db, user_id)
    if "model" in body:
        if body["model"] is not None and not (isinstance(body["model"], str) and NAME.match(body["model"])):
            raise ValueError("That is not a model's name.")
        kept["model"] = body["model"]
    if "effort" in body:
        effort = _names(body["effort"], 50)
        if effort is None:
            raise ValueError("Effort is a level for each model.")
        kept["effort"] = dict(list({**kept["effort"], **effort}.items())[-50:])
    if "permission" in body:
        if body["permission"] not in PERMISSIONS:
            raise ValueError("The permission is one of: {}.".format(", ".join(PERMISSIONS)))
        kept["permission"] = body["permission"]
    if "explain" in body:
        explain = body["explain"]
        if not isinstance(explain, dict) or not all(isinstance(v, bool) and isinstance(k, str) and NAME.match(k)
                                                     for k, v in explain.items()):
            raise ValueError("Explain is on or off for each conversation.")
        kept["explain"] = dict(list({**kept["explain"], **explain}.items())[-200:])
    db.set_setting(AGENT_KEY.format(int(user_id)), json.dumps(kept))
    return kept


def runs_without_approve(prefs, kinds):
    """Whether a plan of steps of these kinds may start without the user's Approve, under their permission."""
    return prefs["permission"] == "all" or (prefs["permission"] == "videos" and "video" not in kinds)


def studio(db, user_id):
    """{"workflows": {kind: workflow id}, "kind": the kind Create shows, "project": id or None, "skills": [ids, newest
    first], "seen": the one-time tips already shown}."""
    kept = _read(db, STUDIO_KEY.format(int(user_id)))
    project = kept.get("project")
    return {"workflows": kept.get("workflows") if isinstance(kept.get("workflows"), dict) else {},
            "kind": kept.get("kind") if isinstance(kept.get("kind"), str) else None,
            "project": project if isinstance(project, int) and not isinstance(project, bool) else None,
            "skills": kept.get("skills") if isinstance(kept.get("skills"), list) else [],
            "seen": kept.get("seen") if isinstance(kept.get("seen"), list) else []}


def set_studio(db, user_id, body):
    kept = studio(db, user_id)
    if "workflows" in body:
        workflows = _names(body["workflows"], 20)
        if workflows is None:
            raise ValueError("Workflows are a workflow for each kind.")
        kept["workflows"] = dict(list({**kept["workflows"], **workflows}.items())[-20:])
    if "kind" in body:
        if body["kind"] is not None and not (isinstance(body["kind"], str) and NAME.match(body["kind"])):
            raise ValueError("That is not a kind.")
        kept["kind"] = body["kind"]
    if "project" in body:
        if body["project"] is not None and (not isinstance(body["project"], int) or isinstance(body["project"], bool)):
            raise ValueError("A project is its number.")
        kept["project"] = body["project"]
    if "skills" in body:
        skills = body["skills"]
        if not isinstance(skills, list) or not all(isinstance(s, str) and NAME.match(s) for s in skills):
            raise ValueError("Skills are a list of their ids.")
        kept["skills"] = skills[:5]
    if "seen" in body:   # the one-time tips the user has seen (the canvas's first tip): added to, never taken from
        seen = body["seen"]
        if not isinstance(seen, list) or not all(isinstance(s, str) and NAME.match(s) for s in seen):
            raise ValueError("Seen is a list of the tips' names.")
        kept["seen"] = list(dict.fromkeys(kept["seen"] + seen))[:50]
    db.set_setting(STUDIO_KEY.format(int(user_id)), json.dumps(kept))
    return kept
