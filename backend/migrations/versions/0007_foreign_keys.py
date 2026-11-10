"""Foreign keys for the references that had none, each with what happens when the row it names is deleted.

Orphans found on a copy of the real data first (scripts/orphans.py, 10 Nov 2026): 32 credit events and 3 Claude
sessions named projects 25, 26 and 27, deleted since. They are fixed here, as the key's rule would have: the project
is set to NULL (the credits were spent, the sessions happened; only the project is gone). Every other reference had
no orphan. Whatever this finds on another database is fixed the same way, and counted in the log of the run.

assets.from_scene is a scene's number (1, 2, 3...), not a row: it gets a check (0008), not a key.

Revision 0007, after 0006. Made 2026-11-10."""

from alembic import op

from scene.schema import sql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# (table, column, referenced table, on delete): SET NULL where the row is history that outlives what it named; CASCADE
# where it is part of what it names (a project's modules, boards and NeuralCore entries, a session's events, an item's
# share links, the admin's view-as sign-ins).
KEYS = [
    ("jobs", "project_id", "projects", "SET NULL"),
    ("jobs", "plan_id", "agent_plans", "SET NULL"),
    ("generations", "project_id", "projects", "SET NULL"),
    ("generations", "job_id", "jobs", "SET NULL"),
    ("projects", "parent_id", "projects", "CASCADE"),
    ("project_members", "added_by", "users", "SET NULL"),
    ("boards", "project_id", "projects", "CASCADE"),
    ("assets", "project_id", "projects", "CASCADE"),
    ("assets", "made_from", "generations", "SET NULL"),
    ("assets", "look_of", "assets", "SET NULL"),
    ("credit_events", "project_id", "projects", "SET NULL"),
    ("credit_events", "job_id", "jobs", "SET NULL"),
    ("agent_calls", "user_id", "users", "SET NULL"),
    ("claude_sessions", "user_id", "users", "CASCADE"),
    ("claude_sessions", "project_id", "projects", "SET NULL"),
    ("claude_events", "session_id", "claude_sessions", "CASCADE"),
    ("moderation", "generation_id", "generations", "SET NULL"),
    ("moderation", "user_id", "users", "SET NULL"),
    ("shares", "item_id", "generations", "CASCADE"),
    ("agent_plans", "project_id", "projects", "SET NULL"),
    ("sessions", "view_as", "users", "CASCADE"),
]


def name(table, column):
    return "{}_{}_fkey".format(table, column)


def upgrade():
    conn = op.get_bind().connection.driver_connection
    for table, column, target, rule in KEYS:
        orphan = "{c} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {r} y WHERE y.id = {t}.{c})".format(t=table, c=column, r=target)
        if rule == "CASCADE":
            fixed = conn.execute("DELETE FROM {} WHERE {}".format(table, orphan)).rowcount
        else:
            fixed = conn.execute("UPDATE {t} SET {c} = NULL WHERE {o}".format(t=table, c=column, o=orphan)).rowcount
        if fixed:
            print("0007: {}.{}: {} rows named a missing {} row: {}".format(
                table, column, fixed, target, "deleted" if rule == "CASCADE" else "set to NULL"))
        sql("ALTER TABLE {t} ADD CONSTRAINT {n} FOREIGN KEY ({c}) REFERENCES {r}(id) ON DELETE {rule}".format(
            t=table, n=name(table, column), c=column, r=target, rule=rule))
        # A key is looked up from the other side when the row it names is deleted: an index on it, where none starts with it.
        if not conn.execute("SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0] "
                            "WHERE i.indrelid = %s::regclass AND a.attname = %s", (table, column)).fetchone():
            sql("CREATE INDEX {t}_{c} ON {t} ({c})".format(t=table, c=column))


def downgrade():
    conn = op.get_bind().connection.driver_connection
    for table, column, target, rule in reversed(KEYS):
        sql("ALTER TABLE {} DROP CONSTRAINT {}".format(table, name(table, column)))
        if conn.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", ("{}_{}".format(table, column),)).fetchone():
            sql("DROP INDEX {}_{}".format(table, column))
