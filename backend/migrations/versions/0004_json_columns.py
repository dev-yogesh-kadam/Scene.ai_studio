"""JSON kept as TEXT becomes JSONB: the settings and context of jobs and library items, reviews, facts,
relations, price factors, boards, plans' steps and progress, recovery codes, a run's state.

"Nothing" was '' in the columns that could be empty; it is NULL now (JSON has no empty text), and the app reads NULL
back as '' (db.py), so the code sees what it saw. Each column is changed in place; the migration checks that every
value means the same JSON before and after (row counts, the empty ones, and a hash of each row's JSON) and stops,
changing nothing, if one does not.

Left as TEXT on purpose: claude_events.data (cut to a length as it is written, so not always whole JSON),
settings.value (JSON for some keys, plain words for others), assets.palette (words: "soft lavender-grey shadows,
warm golden highlights", kit.py), audit_log (sealed: never changed).

Revision 0004, after 0003. Made 2026-11-10."""

from alembic import op

from scene.schema import sql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# (table, column, may be empty, default as JSON or None)
COLUMNS = [
    ("jobs", "settings", False, None),
    ("generations", "settings", False, None),
    ("generations", "context", False, None),
    ("generations", "review", True, None),
    ("generations", "facts", True, None),
    ("assets", "facts", True, None),
    ("assets", "relations", True, None),
    ("boards", "data", False, None),
    ("workflow_pricing", "factors", True, None),
    ("agent_plans", "steps", False, None),
    ("agent_plans", "progress", False, "[]"),
    ("users", "mfa_recovery", False, "[]"),
    ("run_state", "value", False, None),
]


def _check(table, column, as_json):
    """Rows, empty ones, and the sum of a hash of each row's JSON (written out by PostgreSQL in one way)."""
    conn = op.get_bind().connection.driver_connection
    return conn.execute("SELECT count(*), count(*) FILTER (WHERE {c} IS NULL OR {c}::text = ''), "
                        "coalesce(sum(hashtextextended({j}::text, 0)), 0) FROM {t}".format(
                            t=table, c=column, j=as_json)).fetchone()


def upgrade():
    for table, column, empty, default in COLUMNS:
        before = _check(table, column, "NULLIF({}, '')::jsonb".format(column))
        sql("ALTER TABLE {} ALTER COLUMN {} DROP DEFAULT".format(table, column))
        if empty:
            sql("ALTER TABLE {} ALTER COLUMN {} DROP NOT NULL".format(table, column))
        sql("ALTER TABLE {t} ALTER COLUMN {c} TYPE jsonb USING NULLIF({c}, '')::jsonb".format(t=table, c=column))
        if default is not None:
            sql("ALTER TABLE {} ALTER COLUMN {} SET DEFAULT '{}'::jsonb".format(table, column, default))
        after = _check(table, column, column)
        if before != after:
            raise RuntimeError("{}.{} changed in the move to JSONB: before {}, after {}".format(table, column, before, after))
    # The phone's plans waiting for approval are found inside agent boards' JSON (api/mobile.py).
    sql("CREATE INDEX boards_data ON boards USING gin (data jsonb_path_ops)")


def downgrade():
    sql("DROP INDEX IF EXISTS boards_data")
    for table, column, empty, default in reversed(COLUMNS):
        before = _check(table, column, column)
        sql("ALTER TABLE {} ALTER COLUMN {} DROP DEFAULT".format(table, column))
        sql("ALTER TABLE {t} ALTER COLUMN {c} TYPE text USING coalesce({c}::text, '')".format(t=table, c=column))
        if empty:   # as it was: not null, '' when nothing was written
            sql("ALTER TABLE {} ALTER COLUMN {} SET NOT NULL".format(table, column))
            sql("ALTER TABLE {} ALTER COLUMN {} SET DEFAULT ''".format(table, column))
        elif default is not None:
            sql("ALTER TABLE {} ALTER COLUMN {} SET DEFAULT '{}'".format(table, column, default))
        after = _check(table, column, "NULLIF({}, '')::jsonb".format(column))
        if before != after:
            raise RuntimeError("{}.{} changed in the move back to TEXT: before {}, after {}".format(table, column, before, after))
