"""Indexes for the queries EXPLAIN ANALYZE found slow on a copy of the real data grown a hundredfold (docs/db-upgrade-log.md,
Part 2): a project's library, the projects list's counts and covers, the library's pages, a user's job list.

Revision 0003, after 0002. Made 2026-11-10."""

from scene.schema import sql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

INDEXES = {
    # A project's (or module's) items, newest first: its library page, and the projects list's count, cover and
    # newest item. user_id and kind ride along so row-level security and the cover's kind are read from the index.
    "generations_project_run": "generations (project_id, run, created DESC, id DESC) INCLUDE (user_id, kind)",
    # When a project was last worked on: its newest item of any run.
    "generations_project_created": "generations (project_id, created DESC) INCLUDE (user_id)",
    # The library's pages: a user's items of one run (the library's own: ''), newest first, by the page's cursor.
    "generations_user_run": "generations (user_id, run, created DESC, id DESC)",
    # The same in one project or module (the canvas, a project's library): without it the planner reads the user's
    # items in parallel and starts workers for it, which costs more than the reading.
    "generations_user_project_run": "generations (user_id, project_id, run, created DESC, id DESC)",
    # A user's job list (jobs.snapshot): the ones waiting or running, and the ones finished a moment ago.
    "jobs_user_live": "jobs (user_id) WHERE status IN ('queued', 'running')",
    "jobs_user_finished": "jobs (user_id, finished DESC)",
}


def upgrade():
    for name, on in INDEXES.items():
        sql("CREATE INDEX IF NOT EXISTS {} ON {}".format(name, on))


def downgrade():
    for name in INDEXES:
        sql("DROP INDEX IF EXISTS {}".format(name))
