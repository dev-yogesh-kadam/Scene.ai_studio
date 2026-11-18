"""The LUFI bridge leaves the studio: the agent reaches the Claude Code signed in on this PC itself, as "Claude on this
PC" (0016), so the SceneCloude bridge it once reached over a WebSocket is not used again (docs/servers.md, "Claude on
this PC").

- The bridge's providers (kind 'claude_bridge') are deleted, and with them their keys (provider_keys and
  provider_models go with their provider: ON DELETE CASCADE) and its sealed key in the old card's settings
  (claude_bridge_key), with its address (claude_bridge_url).
- `agent_provider` still naming one moves to Claude on this PC; `claude_connection` = 'lufi_bridge' becomes 'this_pc'.
- `providers.kind` may no longer be 'claude_bridge'.

The downgrade lets the kind be 'claude_bridge' again and puts back one bridge provider, "LUFI bridge", with no address
and no key (a key is a secret: it is not kept to be put back). The agent stays on Claude on this PC.

Revision 0017, after 0016. Made 2026-11-16."""

from scene.schema import sql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

KINDS = "('scene_provider_v1', 'comfyui', 'claude_local', 'anthropic')"
KINDS_BEFORE = "('scene_provider_v1', 'comfyui', 'claude_local', 'anthropic', 'claude_bridge')"


def _kinds(kinds):
    sql("ALTER TABLE providers DROP CONSTRAINT IF EXISTS providers_kind_known")
    sql("ALTER TABLE providers ADD CONSTRAINT providers_kind_known CHECK (kind IN {})".format(kinds))


def upgrade():
    sql("""
    UPDATE settings SET value = COALESCE((SELECT id::text FROM providers WHERE kind = 'claude_local' ORDER BY id LIMIT 1), value)
    WHERE key = 'agent_provider' AND value IN (SELECT id::text FROM providers WHERE kind = 'claude_bridge')""")
    sql("UPDATE settings SET value = 'this_pc' WHERE key = 'claude_connection' AND value = 'lufi_bridge'")
    sql("DELETE FROM settings WHERE key IN ('claude_bridge_url', 'claude_bridge_key')")
    sql("DELETE FROM provider_models WHERE provider_id IN (SELECT id FROM providers WHERE kind = 'claude_bridge')")
    sql("DELETE FROM provider_keys WHERE provider_id IN (SELECT id FROM providers WHERE kind = 'claude_bridge')")
    sql("DELETE FROM providers WHERE kind = 'claude_bridge'")
    _kinds(KINDS)


def downgrade():
    _kinds(KINDS_BEFORE)
    sql("""
    INSERT INTO providers (kind, name, base_url, active, priority, legacy)
    VALUES ('claude_bridge', 'LUFI bridge', '', 1, 1, 'claude:bridge')
    ON CONFLICT (legacy) WHERE legacy <> '' DO NOTHING""")
