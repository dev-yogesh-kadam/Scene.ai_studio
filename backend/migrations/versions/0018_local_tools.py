"""The tools that run on this PC become a provider: "On this PC" (kind 'local_tools'), offering transcription and voice
separation (providers/local.py), the last two things only ComfyUI did for the studio (docs/servers.md, "Tools on this
PC").

- `providers.kind` may be 'local_tools', and one such provider is added ("On this PC", legacy 'local:tools').
- It gets one key with no secret ("This PC", one job at a time), as a ComfyUI server has: the router counts its jobs
  by key. Its models are read from it when the studio starts (router.refresh), like any key's.

The downgrade deletes it (its key and models go with it: ON DELETE CASCADE) and takes the kind away again.

Revision 0018, after 0017. Made 2026-11-18."""

from scene.schema import sql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

KINDS = "('scene_provider_v1', 'comfyui', 'claude_local', 'anthropic', 'local_tools')"
KINDS_BEFORE = "('scene_provider_v1', 'comfyui', 'claude_local', 'anthropic')"


def _kinds(kinds):
    sql("ALTER TABLE providers DROP CONSTRAINT IF EXISTS providers_kind_known")
    sql("ALTER TABLE providers ADD CONSTRAINT providers_kind_known CHECK (kind IN {})".format(kinds))


def upgrade():
    _kinds(KINDS)
    sql("""
    INSERT INTO providers (kind, name, base_url, active, priority, legacy)
    VALUES ('local_tools', 'On this PC', '', 1, 0, 'local:tools')
    ON CONFLICT (legacy) WHERE legacy <> '' DO NOTHING""")
    sql("""
    INSERT INTO provider_keys (provider_id, label, secret, last4, active, priority, max_concurrent, status)
    SELECT p.id, 'This PC', '', '', 1, 0, 1, 'unknown' FROM providers p
    WHERE p.legacy = 'local:tools' AND NOT EXISTS (SELECT 1 FROM provider_keys k WHERE k.provider_id = p.id)""")


def downgrade():
    sql("DELETE FROM provider_models WHERE provider_id IN (SELECT id FROM providers WHERE kind = 'local_tools')")
    sql("DELETE FROM provider_keys WHERE provider_id IN (SELECT id FROM providers WHERE kind = 'local_tools')")
    sql("DELETE FROM providers WHERE kind = 'local_tools'")
    _kinds(KINDS_BEFORE)
