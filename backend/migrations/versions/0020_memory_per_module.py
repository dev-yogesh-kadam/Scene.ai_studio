"""What the agent remembers of a user belongs to one module (recall.py): `user_memory` gets a `project_id`, and nothing
of it is shared between modules or projects any more.

- Every row there was is deleted: it was kept for all of a user's projects at once, and the user chose to drop it
  rather than guess which module each entry belongs to.
- `project_id` (the module, or a project's main canvas) is added, NOT NULL, and goes with its project (ON DELETE CASCADE).
- The key is (user_id, project_id, key) instead of (user_id, key), with an index on (user_id, project_id).

The downgrade takes `project_id` away again and puts the old key back; the rows of a module are deleted with it (the
same key may be in several modules, and the old key holds one).

Revision 0020, after 0019. Made 2026-11-21."""

from scene.schema import sql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    sql("DELETE FROM user_memory")
    sql("ALTER TABLE user_memory DROP CONSTRAINT IF EXISTS user_memory_pkey")
    sql("ALTER TABLE user_memory ADD COLUMN project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE")
    sql("ALTER TABLE user_memory ADD CONSTRAINT user_memory_pkey PRIMARY KEY (user_id, project_id, key)")
    sql("CREATE INDEX user_memory_module ON user_memory (user_id, project_id)")


def downgrade():
    sql("DELETE FROM user_memory")
    sql("DROP INDEX IF EXISTS user_memory_module")
    sql("ALTER TABLE user_memory DROP CONSTRAINT IF EXISTS user_memory_pkey")
    sql("ALTER TABLE user_memory DROP COLUMN project_id")
    sql("ALTER TABLE user_memory ADD CONSTRAINT user_memory_pkey PRIMARY KEY (user_id, key)")
