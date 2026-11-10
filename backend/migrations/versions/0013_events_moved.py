"""When a Claude session's event had its words moved to Langfuse (docs/observability.md): `claude_events.moved`.

With the setting `langfuse_owns_words` on (off by default), an event older than 30 days is sent to Langfuse and then
kept here as a short row: its kind, its time, the first characters of its text and the numbers of its data, with
where it is in Langfuse (retention.move_events). `moved` is when that was done; NULL is an event still whole, which is
every event while the setting is off. A partial index holds only those, so finding the next ones to move stays quick
however many have been moved.

Only adds a column and an index: nothing is changed or dropped, and the downgrade removes just these.

Revision 0013, after 0012. Made 2026-11-10."""

from scene.schema import sql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    sql("ALTER TABLE claude_events ADD COLUMN IF NOT EXISTS moved timestamptz")
    sql("CREATE INDEX IF NOT EXISTS claude_events_unmoved ON claude_events (id) WHERE moved IS NULL")


def downgrade():
    sql("DROP INDEX IF EXISTS claude_events_unmoved")
    sql("ALTER TABLE claude_events DROP COLUMN IF EXISTS moved")
