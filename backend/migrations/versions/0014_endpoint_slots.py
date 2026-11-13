"""How many renders a server runs at once: `endpoints.slots`, the console's "Jobs at once" (balancer.py).

A ComfyUI server renders one at a time (1, the default, which every server has after this migration, as before it).
The generation server takes several at once: it spreads them over its provider accounts itself. Kept between 1 and 16
(endpoints.MOST_SLOTS) by a check.

`endpoints.models`, there since the baseline and read by nothing until now, becomes the server's "Workflows": the
patterns of the workflows it takes. It keeps its type; nothing is changed in it.

Only adds a column and its check: nothing is changed or dropped, and the downgrade removes just these.

Revision 0014, after 0013. Made 2026-11-12."""

from scene.schema import sql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    sql("ALTER TABLE endpoints ADD COLUMN IF NOT EXISTS slots integer NOT NULL DEFAULT 1")
    sql("ALTER TABLE endpoints DROP CONSTRAINT IF EXISTS endpoints_slots_range")
    sql("ALTER TABLE endpoints ADD CONSTRAINT endpoints_slots_range CHECK (slots BETWEEN 1 AND 16)")


def downgrade():
    sql("ALTER TABLE endpoints DROP CONSTRAINT IF EXISTS endpoints_slots_range")
    sql("ALTER TABLE endpoints DROP COLUMN IF EXISTS slots")
