"""Who a workflow (a provider's model) is offered to: everyone, admins alone (to try it before users see it), or nobody.

(This file once kept every version of the ComfyUI workflow files the render PC handed over, and what they needed that
the render server lacked. Those files are archived (workflows/archive/) and that record ended with them: the
`workflow_versions` table keeps what it saw, for history.)
"""

AUDIENCES = ("everyone", "admins", "off")


def set_audience(db, workflow_id, audience):
    """Who is offered a workflow: everyone, admins alone (to try it first), or nobody (switched off). Its pricing stays."""
    db.run("INSERT INTO workflow_pricing (workflow, enabled, admins_only) VALUES (?, ?, ?) "
           "ON CONFLICT (workflow) DO UPDATE SET enabled = excluded.enabled, admins_only = excluded.admins_only",
           (workflow_id, int(audience != "off"), int(audience == "admins")))
    if db.shared is not None:
        db.shared.changed("pricing")   # every process sees who is offered it now (shared.py)


def audience(row):
    """The audience of a workflow from its pricing row (None: it has none, so everyone)."""
    if row and not row["enabled"]:
        return "off"
    return "admins" if row and row["admins_only"] else "everyone"
