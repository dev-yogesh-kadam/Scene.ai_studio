"""The models the agent uses for each of its roles, as chosen in the admin console; config.json gives the first choice.

- "main": the agent's own model when the user picks none (agent_model)
- "fast": the quicker Claude model for the small jobs: captions, notes, the check of a skill (claude_fast_model)

An empty choice means config.json's. They are kept in the `agent_roles` setting and set on the Agent as they change,
with no restart. The models are Claude's, named "claude/<name>" or just "<name>" ("haiku").
"""

import json

ROLES = ("main", "fast")


def chosen(db):
    try:
        found = json.loads(db.setting("agent_roles", "") or "{}")
    except ValueError:
        found = {}
    return {role: str(found.get(role) or "") for role in ROLES}


def _fast_of(agent):
    s = agent.services.get("claude")
    return (s or {}).get("fast", "")


def apply(db, agent):
    """Set the chosen models on the agent, over what config.json said (kept as `configured` for an empty choice)."""
    if not hasattr(agent, "configured"):
        agent.configured = {"main": agent.model, "fast": _fast_of(agent)}
    choice = chosen(db)
    agent.model = choice["main"] or agent.configured["main"]
    s = agent.services.get("claude")
    if s is not None:
        s["fast"] = (choice["fast"] or agent.configured["fast"]).split("/", 1)[-1]


def save(db, agent, choices):
    found = {role: str(choices.get(role) or "").strip()[:120] for role in ROLES}
    db.set_setting("agent_roles", json.dumps(found))
    apply(db, agent)
    return found
