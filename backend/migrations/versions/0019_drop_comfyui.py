"""ComfyUI leaves the studio: every model comes from a provider now, Studio_automation over the v1 contract or On this
PC (0018), so the ComfyUI servers the renders once ran on are not used again (docs/servers.md, "Providers and keys").

- The ComfyUI providers (kind 'comfyui') are deleted, and with them their keys and models (ON DELETE CASCADE), and their
  `endpoints` rows (kind 'comfy'): the console's Servers section holds Langfuse alone.
- The settings that switched between ComfyUI and the providers go: `provider_router` (the providers are always used),
  `comfyui_off` (ComfyUI switched off by capability) and `comfy_url` (the console's old address of the render server).
- `providers.kind` may no longer be 'comfyui'.

The workflow files ComfyUI ran are kept in workflows/archive/; the jobs and library items made with them stay as they
are. The downgrade lets the kind be 'comfyui' again; the servers are not put back (add one again to use it).

Revision 0019, after 0018. Made 2026-11-18."""

from scene.schema import sql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

KINDS = "('scene_provider_v1', 'claude_local', 'anthropic', 'local_tools')"
KINDS_BEFORE = "('scene_provider_v1', 'comfyui', 'claude_local', 'anthropic', 'local_tools')"


def _kinds(kinds):
    sql("ALTER TABLE providers DROP CONSTRAINT IF EXISTS providers_kind_known")
    sql("ALTER TABLE providers ADD CONSTRAINT providers_kind_known CHECK (kind IN {})".format(kinds))


def upgrade():
    sql("DELETE FROM provider_models WHERE provider_id IN (SELECT id FROM providers WHERE kind = 'comfyui')")
    sql("DELETE FROM provider_keys WHERE provider_id IN (SELECT id FROM providers WHERE kind = 'comfyui')")
    sql("DELETE FROM providers WHERE kind = 'comfyui'")
    sql("DELETE FROM endpoints WHERE kind = 'comfy'")
    sql("DELETE FROM settings WHERE key IN ('provider_router', 'comfyui_off', 'comfy_url')")
    _kinds(KINDS)


def downgrade():
    _kinds(KINDS_BEFORE)
