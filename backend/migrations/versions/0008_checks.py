"""Checks: the columns whose values come from a fixed set in the code take nothing else, and credits never go below
zero. Each set is the code's own (named beside it) and every row of a copy of the real data was inside it.

Left open on purpose: jobs.kind (the first part of a workflow's name: a new workflow folder is a new kind),
users.role (the console's staff roles can be added to), assets.tag and boards.kind (open by design).

Revision 0008, after 0007. Made 2026-11-10."""

from alembic import op

from scene.schema import sql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

CHECKS = {
    # table: {name: condition}
    "jobs": {
        "jobs_status_known": "status IN ('queued', 'running', 'done', 'failed', 'cancelled')",   # jobs.py
        "jobs_credits_not_negative": "cost >= 0 AND credits_required >= 0 AND credits_reserved >= 0 "
                                     "AND credits_consumed >= 0 AND credits_refunded >= 0",
    },
    "generations": {
        "generations_kind_known": "kind IN ('image', 'video', 'audio', 'text')",   # catalog.KINDS and texts
        "generations_rating_known": "rating IN (-1, 0, 1)",                         # thumbs down, none, up
    },
    "agent_plans": {
        "agent_plans_state_known": "state IN ('waiting', 'approved', 'running', 'stopping', 'stopped', 'done', 'failed')",
        "agent_plans_credits_not_negative": "total >= 0 AND reserved_left >= 0",
    },
    "claude_events": {   # sessions.KINDS (anything else is recorded as a note)
        "claude_events_kind_known": "kind IN ('user', 'prompt', 'thinking', 'text', 'tool_call', 'tool_result', 'answer', "
                                    "'compact', 'model', 'error', 'note')",
    },
    "endpoints": {"endpoints_kind_known": "kind IN ('comfy', 'langfuse')"},                    # endpoints.KINDS
    "project_members": {"project_members_role_known": "role IN ('viewer', 'creator', 'manager')"},   # sharing.ROLES
    "alerts": {"alerts_level_known": "level IN ('critical', 'serious', 'warning')"},           # health.py
    "users": {"users_credits_not_negative": "credits >= 0"},                                  # credits.add: never below 0
    "credit_packages": {"credit_packages_not_negative": "price_inr >= 0 AND credits >= 0 AND bonus_credits >= 0"},
    "assets": {"assets_from_scene_is_a_scene": "from_scene IS NULL OR from_scene > 0"},       # kit.py: 1, 2, 3...
}


def upgrade():
    # Servers of kinds the code no longer has (the model APIs of before the agent was Claude's only): the app's own
    # start took them out (endpoints.seed); here before the check that keeps them out.
    gone = op.get_bind().connection.driver_connection.execute(
        "DELETE FROM endpoints WHERE kind NOT IN ('comfy', 'langfuse')").rowcount
    if gone:
        print("0008: {} endpoints of kinds no longer used were removed".format(gone))
    for table, checks in CHECKS.items():
        for name, condition in checks.items():
            sql("ALTER TABLE {} ADD CONSTRAINT {} CHECK ({})".format(table, name, condition))


def downgrade():
    for table, checks in CHECKS.items():
        for name in checks:
            sql("ALTER TABLE {} DROP CONSTRAINT {}".format(table, name))
