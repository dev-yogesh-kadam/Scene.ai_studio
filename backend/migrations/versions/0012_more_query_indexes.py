"""Indexes for two sequential scans on hot paths that EXPLAIN found on a grown, made-up copy (2,666 projects, 80,000
jobs, 60,000 items, 500 alerts; the hardening pass of 10 Nov 2026, docs/history/db-upgrade-log.md):

- `projects WHERE user_id = ?`: the projects list (every Home and Library page), a user's top-level projects, and
  the row rule's own filter on projects had no index starting with user_id, so each read every project of everyone.
- `alerts WHERE ended IS NULL`: the console's live socket counts the open alerts on every tick, and alerts are
  never deleted. A partial index holds only the open ones, so it stays a few rows however long the table grows.

Only adds indexes: nothing is changed or dropped, and the downgrade removes just these.

Revision 0012, after 0011. Made 2026-11-10."""

from scene.schema import sql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

INDEXES = {
    # A user's projects (and their top-level ones: parent_id IS NULL), as the list and the row rule read them.
    "projects_user": "projects (user_id, parent_id)",
    # The open alerts, oldest first (the console's count and its Alerts list).
    "alerts_open": "alerts (started) WHERE ended IS NULL",
}


def upgrade():
    for name, on in INDEXES.items():
        sql("CREATE INDEX IF NOT EXISTS {} ON {}".format(name, on))


def downgrade():
    for name in INDEXES:
        sql("DROP INDEX IF EXISTS {}".format(name))
