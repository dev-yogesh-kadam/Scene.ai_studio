"""The library's search: full-text search over an item's name, summary, workflow and the words of its settings (its
prompt), and trigram matching of its name for a word typed wrong. It replaces LIKE '%word%' over the same text.

`search` is a generated column (PostgreSQL keeps it up to date); the app never reads it (db.py leaves tsvector columns
out of every row). 'simple' (no stemming): prompts are in English, Hindi and more, and a word is found as typed.
pg_trgm is a trusted extension: the database's owner may create it (on Azure, allow it first: azure.extensions).

Revision 0009, after 0008. Made 2026-11-10."""

from scene.schema import sql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SEARCH = ("setweight(to_tsvector('simple', coalesce(name, '')), 'A') || "
          "setweight(to_tsvector('simple', coalesce(summary, '')), 'B') || "
          "setweight(to_tsvector('simple', translate(workflow, '/_-', '   ')), 'C') || "
          "setweight(jsonb_to_tsvector('simple', coalesce(settings, '{}'::jsonb), '[\"string\"]'), 'D')")


def upgrade():
    sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    sql("ALTER TABLE generations ADD COLUMN search tsvector GENERATED ALWAYS AS ({}) STORED".format(SEARCH))
    sql("CREATE INDEX generations_search ON generations USING gin (search)")
    sql("CREATE INDEX generations_name_trigram ON generations USING gin (name gin_trgm_ops)")


def downgrade():
    sql("DROP INDEX generations_name_trigram")
    sql("DROP INDEX generations_search")
    sql("ALTER TABLE generations DROP COLUMN search")
    # pg_trgm stays: other databases' objects may use it, and it changes nothing by being there.
