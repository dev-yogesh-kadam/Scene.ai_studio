"""${message}

Revision ${up_revision}, after ${down_revision | comma,n}. Made ${create_date}.
See docs/database.md: raw SQL through sql(), an upgrade() and a downgrade(), and expand, migrate, contract."""

from scene.schema import sql

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else 'sql("")'}


def downgrade():
    ${downgrades if downgrades else 'sql("")'}
