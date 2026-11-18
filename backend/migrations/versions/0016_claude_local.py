"""Claude on this PC: a third way for the agent to reach Claude (docs/servers.md, "Claude on this PC"). The studio runs
the `claude` signed in on this PC itself, with no key and no address, in place of the SceneCloude bridge it reached
over a WebSocket on the same PC.

- `providers.kind` may be 'claude_local', and one such provider is added ("Claude on this PC", legacy 'claude:local',
  so it is added once however often this runs). It has no keys.
- `agent_provider` moves to it when the agent uses the LUFI bridge today; the old card's setting `claude_connection`
  becomes 'this_pc' beside it.
- `agent_provider` naming an Anthropic provider with no key, when no one ever picked a connection (no
  `claude_connection` row: a new database, where 0015 named Anthropic only because there was nothing else), is taken
  out, so the studio's start (`registry.seed`) picks by `config.json`'s `claude_connection`: Claude on this PC by
  default. Anthropic with no key that someone picked stays picked, and is refused with "Paste an Anthropic API key, or
  pick Claude on this PC": a subscription is used only when someone picks it.
- Nothing else changes: the bridge's provider and its keys stay (removed by 0017), and so does the Anthropic one.

The downgrade puts `agent_provider` back on the bridge (when there is one) or Anthropic (also when it was taken out),
removes the provider and puts the old check back.

Revision 0016, after 0015. Made 2026-11-16."""

from scene.schema import sql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

KINDS = "('scene_provider_v1', 'comfyui', 'claude_local', 'anthropic', 'claude_bridge')"
KINDS_BEFORE = "('scene_provider_v1', 'comfyui', 'anthropic', 'claude_bridge')"


def _kinds(kinds):
    sql("ALTER TABLE providers DROP CONSTRAINT IF EXISTS providers_kind_known")
    sql("ALTER TABLE providers ADD CONSTRAINT providers_kind_known CHECK (kind IN {})".format(kinds))


def upgrade():
    _kinds(KINDS)
    sql("""
    INSERT INTO providers (kind, name, base_url, active, priority, legacy)
    VALUES ('claude_local', 'Claude on this PC', '', 1, 0, 'claude:local')
    ON CONFLICT (legacy) WHERE legacy <> '' DO NOTHING""")
    sql("""
    INSERT INTO settings (key, value)
    SELECT 'agent_provider', p.id::text FROM providers p
    WHERE p.legacy = 'claude:local' AND EXISTS (
        SELECT 1 FROM settings s JOIN providers a ON a.id::text = s.value
        WHERE s.key = 'agent_provider' AND a.kind = 'claude_bridge')
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""")
    sql("""
    DELETE FROM settings WHERE key = 'agent_provider'
    AND NOT EXISTS (SELECT 1 FROM settings WHERE key = 'claude_connection')
    AND value IN (SELECT a.id::text FROM providers a WHERE a.kind = 'anthropic'
                  AND NOT EXISTS (SELECT 1 FROM provider_keys k WHERE k.provider_id = a.id))""")
    sql("""
    INSERT INTO settings (key, value)
    SELECT 'claude_connection', 'this_pc' FROM settings s JOIN providers p ON p.id::text = s.value
    WHERE s.key = 'agent_provider' AND p.kind = 'claude_local'
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""")


def downgrade():
    sql("""
    UPDATE settings SET value = COALESCE(
        (SELECT id::text FROM providers WHERE kind = 'claude_bridge' ORDER BY id LIMIT 1),
        (SELECT id::text FROM providers WHERE kind = 'anthropic' ORDER BY id LIMIT 1), '')
    WHERE key = 'agent_provider' AND value IN (SELECT id::text FROM providers WHERE kind = 'claude_local')""")
    sql("""
    INSERT INTO settings (key, value)
    SELECT 'agent_provider', id::text FROM providers WHERE kind = 'anthropic' ORDER BY id LIMIT 1
    ON CONFLICT (key) DO NOTHING""")
    sql("""
    UPDATE settings SET value = CASE WHEN EXISTS (SELECT 1 FROM providers WHERE kind = 'claude_bridge')
                                     THEN 'lufi_bridge' ELSE 'api_key' END
    WHERE key = 'claude_connection' AND value = 'this_pc'""")
    sql("DELETE FROM providers WHERE kind = 'claude_local'")
    _kinds(KINDS_BEFORE)
