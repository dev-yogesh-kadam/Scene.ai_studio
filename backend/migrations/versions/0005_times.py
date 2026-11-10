"""Times kept as seconds since 1970 (REAL) become timestamptz. The app still gets and gives seconds (db.py turns a
timestamptz into them as it reads, and the SQL turns the seconds it is given into a time with to_timestamp), so what it
does does not change. Time zones are the app's (time_zone, Asia/Kolkata), not the database server's.

Each column is changed in place; the migration checks that every value is the same to the microsecond before and after
(a timestamptz keeps microseconds; time.time() gave more digits than that, which were never shown) and stops, changing
nothing, if one is not.

Left as seconds on purpose: audit_log.created (each entry is sealed with a hash over its fields: never changed).

Revision 0005, after 0004. Made 2026-11-10."""

from alembic import op

from scene.schema import sql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

COLUMNS = {
    "users": ["created"],
    "sessions": ["created", "expires", "seen"],
    "jobs": ["created", "started", "finished"],
    "generations": ["created"],
    "projects": ["created"],
    "project_members": ["created"],
    "boards": ["updated"],
    "assets": ["created"],
    "credit_events": ["created"],
    "uploads": ["created"],
    "workflow_versions": ["seen"],
    "agent_calls": ["started"],
    "claude_sessions": ["started", "active"],
    "claude_events": ["at"],
    "moderation": ["created"],
    "alerts": ["started", "ended"],
    "credit_packages": ["created"],
    "user_memory": ["updated"],
    "shares": ["created", "expires"],
    "agent_plans": ["created", "approved", "finished"],
    "run_state": ["updated"],
    "servers": ["created"],
    "endpoints": ["created"],
    "client_errors": ["created"],
}


def _conn():
    return op.get_bind().connection.driver_connection


def _change(table, columns, new_type, using, as_seconds_new, as_seconds_old):
    """Change `columns` of `table` to `new_type`, keeping the old values beside, by primary key, and stop if any row's
    value moved by more than a microsecond or a row came or went."""
    conn = _conn()
    key = conn.execute("SELECT string_agg(a.attname, ', ') FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
                       "AND a.attnum = ANY(i.indkey) WHERE i.indrelid = %s::regclass AND i.indisprimary", (table,)).fetchone()[0]
    conn.execute("CREATE TEMP TABLE before_change ON COMMIT DROP AS SELECT {}, {} FROM {}".format(
        key, ", ".join("{} AS old_{}".format(as_seconds_old(c), c) for c in columns), table))
    for column in columns:
        sql("ALTER TABLE {t} ALTER COLUMN {c} TYPE {n} USING {u}".format(t=table, c=column, n=new_type, u=using(column)))
    rows = conn.execute("SELECT count(*) FROM {}".format(table)).fetchone()[0]
    kept = conn.execute("SELECT count(*) FROM before_change").fetchone()[0]
    moved = conn.execute("SELECT count(*) FROM before_change b JOIN {t} n USING ({k}) WHERE {w}".format(
        t=table, k=key, w=" OR ".join("(b.old_{c} IS NULL) <> (n.{c} IS NULL) OR abs({new} - b.old_{c}) > 0.000001".format(
            c=c, new=as_seconds_new("n." + c)) for c in columns))).fetchone()[0]
    conn.execute("DROP TABLE before_change")
    if rows != kept or moved:
        raise RuntimeError("{}: {} rows before, {} after, {} values moved".format(table, kept, rows, moved))


def upgrade():
    for table, columns in COLUMNS.items():
        _change(table, columns, "timestamptz", lambda c: "to_timestamp({})".format(c),
                lambda c: "extract(epoch FROM {})::float8".format(c), lambda c: c)


def downgrade():
    for table, columns in COLUMNS.items():
        _change(table, columns, "double precision", lambda c: "extract(epoch FROM {})".format(c),
                lambda c: c, lambda c: "extract(epoch FROM {})::float8".format(c))
