# Servers and folders on the studio PC

Scene.ai talks to a render server, and to Anthropic's Claude models for the agent. All of it is set in
`config.json` in the repo root. That file is ignored by git, so it has to be set on every machine
the app runs on, and it is where the secret keys are: **do not open, print or copy it**; change single
lines of it, and check the models with `scripts/check_models.py`.

| Server | Address | `config.json` key | Where it runs |
|---|---|---|---|
| ComfyUI (rendering) | `http://100.123.221.34:8188` | `comfy_url` | The Windows render PC (Zoro), reached over Tailscale |
| Claude (the agent's models) | Anthropic, through Claude Code | the console's Claude connection; `claude_models` | Claude Code in the studio with an API key, or on LUFI through its bridge (below) |

**The agent uses Anthropic's Claude models only** (since 31 October). Ollama, Gemini, Kimi and every other
OpenAI-style service were taken out, with their settings, the GPU sharing that existed only for Ollama, and the
endpoints of the admin console that pointed at them (`scene/endpoints.py` deletes any left in the database).

| Key | Default | What |
|---|---|---|
| `agent_model` | the first of `claude_models` | The model the agent uses unless the user picks another in the Agent tab (`sonnet`). |
| `claude_models` | `sonnet, opus, haiku` | The models offered, as Claude Code names them. |
| `claude_fast_model` | `haiku` | The model for small jobs: the Ideogram caption, notes, the check of a result. Empty uses the one in use. |
| `claude_timeout` | 600 | Seconds one call may take. |
| `claude_context` | 1000000 | Tokens of context the models have; a session is compacted at 90% of it. |
| `claude_connection` | `api_key` | How the studio reaches Claude Code: `api_key` or `lufi_bridge` (below). |
| `claude_bridge_url` | | The LUFI bridge's address, `http://<LUFI's Tailscale address>:<port>`. |
| `claude_bridge_key` | | The bridge's key. A secret: `SCENE_CLAUDE_BRIDGE_KEY` or the console, never `config.json`. |
| `anthropic_api_key` | | The Anthropic API key. A secret: `SCENE_ANTHROPIC_API_KEY` or the console, never `config.json`. |

The last four are set in the admin console (Servers & APIs, **Claude connection**), which wins over `config.json`; a
`SCENE_*` variable wins over both (Key Vault on Azure), and the console then shows that field as fixed.

The agent's model is used for: the agent's answers and plans, the structured caption that Ideogram 4 needs (written
by the render worker just before the render), describing NeuralCore's pictures, Compact, and the check of a result.
With Claude unreachable, those stop and everything else works.

```json
{
  "comfy_url": "http://100.123.221.34:8188",
  "agent_model": "sonnet",
  "default_workflow": "video/h3_master"
}
```

Write the addresses without a trailing slash.

The tunnel closes a request that sends nothing for 100 seconds, and a long answer can be quiet longer. So the agent's
answer sends a sign of life every 15 seconds, and the single answers that wait on the model (review, compact, motion
scenes) send spaces until their JSON is ready.

**Checking them.** This checks the Claude connection in use, says which models it offers and sends one small message to each:

```bash
.venv\Scripts\python.exe scripts\check_models.py
```

## The Claude connection

The studio reaches Claude Code one of two ways, picked in the admin console (Servers & APIs, **Claude connection**):
pick one, paste its key, Save. It is used from the next call to Claude, with no restart, in every process of the app.
**Test** checks it at once; the card says whether it works, the Claude Code version, and the calls running.

- **Anthropic API key** (`api_key`): the `claude` installed in the studio's image runs in the studio, with the key in
  its environment (`ANTHROPIC_API_KEY`). The check asks Anthropic's API for one model (no tokens) and runs `claude -v`.
  On a developer's PC, the `claude` on PATH is used; without a key it uses whatever account it is signed in with.
- **LUFI bridge** (`lufi_bridge`), **for testing only**: a separate app on the PC LUFI (built in `C:\SceneCloude`) runs
  the Claude Code signed in there, and the studio reaches it over Tailscale at one address with one key. While it is
  picked, the studio runs on a personal Claude subscription: the card says "Testing on a personal Claude
  subscription", sign-up is closed whatever Settings says (the choice is kept for later), and only admins can use the
  agent. Picking the API key lifts both.

Switching the connection reopens each conversation's live session the new way. Sessions are not shared between the
two, so a conversation started on one starts its Claude session again on the other (the studio sends it whole).

### The bridge protocol

The bridge and the studio are built separately: this contract is the one thing they share. Change it on both sides at
once, never on one. Every call carries `Authorization: Bearer <key>`.

The console card takes the bridge's base address, `http://<host>:<port>` (on LUFI `http://127.0.0.1:8765`, from
elsewhere its Tailscale address); the studio uses `ws://<host>:<port>/run`, `<base>/health` and `<base>/forget`.

**Run `claude`: WebSocket `GET /run`.** The studio's first frame is
`{"type":"start","args":[...],"files":{"system_prompt":"<text>"},"env":{...}}`:

- `args`: the arguments for `claude`, without the program's name. A `--flag=value` is always sent as two arguments.
- Where the studio would pass `--system-prompt-file <path>`, it passes `--system-prompt-file @system_prompt` and the
  text in `files.system_prompt`; the bridge writes it to a temp file and puts that path in its place.
- `env`: only `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. Never a key.
- Then, in any order: `{"type":"stdin","data":"<text>"}` and `{"type":"stdin_close"}`.
- The bridge sends `{"type":"stdout","data":"..."}` and `{"type":"stderr","data":"..."}` unbuffered and in order, then
  `{"type":"exit","code":<n>}`, and closes.
- A refusal is `{"type":"error","code":"<code>","message":"<words>"}`, then it closes. The codes, and what the user is
  told: `busy` (Claude is busy: try again), `not_signed_in` ("Claude on LUFI is signed out"), `bad_key` and `locked`
  ("the bridge key is wrong"), `off`, `timeout`, `refused_flag`, `internal`. A bridge that can't be reached: "the LUFI
  bridge is not reachable".
- When the studio closes the socket, the bridge kills that `claude`.
- `args` `["-v"]` prints Claude Code's version.
- The bridge runs every `claude` in one folder that never changes: Claude Code finds a session by its folder, so
  `--resume` works across runs.

**`GET /health`**: `{"ok":true,"signed_in":true,"claude_version":"x.y.z","bridge_version":"x.y.z","running":0,"limit":4,"last_error":null}`.

**`POST /forget`**, body `{"session_id":"<id>"}`: `{"ok":true}`, the session's files deleted (a conversation deleted).

**Flags the bridge takes**; anything else is `refused_flag`: `-p`, `-v`, `--version`, `--input-format`,
`--output-format`, `--verbose`, `--model`, `--tools`, `--allowedTools`, `--strict-mcp-config`, `--setting-sources`,
`--disable-slash-commands`, `--max-turns`, `--settings`, `--effort`, `--resume`, `--no-session-persistence`,
`--json-schema`, `--system-prompt-file @system_prompt`, `--mcp-config`. No positional argument: a command of Claude
Code's (`/compact`, `/rename`) goes on stdin as a message.

- `--tools`: empty, or the web-search tools only (`WebSearch`).
- `--allowedTools`: empty, the web-search tools, or `mcp__<server>__<tool>` where `<server>` is a `"type":"sdk"`
  server of the same run's `--mcp-config`, in letters, digits, `_` and `-` only, never a wildcard. Those are the
  studio's own tools: they run in the studio, not on LUFI.
- `--mcp-config`: only inline JSON whose servers are all `"type":"sdk"` (`{"mcpServers":{"studio":{"type":"sdk","name":"studio"}}}`).
- `--settings`: inline JSON with only `autoMemoryEnabled` and `autoCompactWindow`.
- A flag and its value are always two arguments: the bridge refuses `--flag=value`. The SDK sends `--resume=<id>` and
  `--setting-sources=`; the studio splits them (an empty value stays as an empty second argument).

The live sessions (Claude Agent SDK 0.2.174) send exactly these flags: the studio starts them through a transport of
its own (`claude._Through`) with the arguments the SDK itself builds, so no flag is added for them. The SDK's own
environment variables (`CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_AGENT_SDK_VERSION`, `CLAUDE_CODE_SDK_READS_SESSION_STATE`)
are not sent: the SDK works without them.

## Changing them

- **Restart the app** after editing `config.json`. It is read once, when the app starts.
- The `SCENE_COMFY_URL` and `SCENE_AGENT_MODEL` variables override `config.json`.
- The ComfyUI address can also be changed in the admin console (Settings tab). That value is saved
  in the database and **wins over `config.json`** from then on. If a change to `comfy_url` in
  `config.json` seems to have no effect, check the admin console.

## Checking that they answer

```bash
curl http://100.123.221.34:8188/system_stats
.venv\Scripts\python.exe scripts\check_models.py
```

The first needs Tailscale connected and ComfyUI running on the render PC. The second needs the Claude connection working
(the console's card says so).

# The public address (Cloudflare Tunnel)

`https://sceneai.in` (and `www.sceneai.in`) reaches the app on the studio PC. This section is from yogesh's
hosting notes of 4 October; the tunnel was set up outside this repo.

```
Browser -> sceneai.in -> Cloudflare (DNS, https) -> tunnel "studio" -> studio PC -> http://127.0.0.1:8081
```

The tunnel goes to port 8081 only (the studio's `port` on this PC; every port is in [ports.md](ports.md)). The admin console (port 8090, `console_host` `127.0.0.1`) is not behind it and must
stay that way: open it on the studio PC, or set `console_host` to the PC's Tailscale address to reach it from your
other machines.

The studio PC's internet connection is behind the provider's shared address (CGNAT), so a port cannot
be forwarded to it. The tunnel dials out to Cloudflare instead, and no port is opened on the router.
ComfyUI is not behind the tunnel and must stay that way: the app reaches it over Tailscale.

| Thing | Where |
|---|---|
| Domain | `sceneai.in` and `www.sceneai.in` (as in the tunnel's `config.yml`); earlier `developmenttestinghere.in`, registered at Hostinger. Name servers at Cloudflare (free plan) |
| `cloudflared` | `C:\cloudflared\cloudflared.exe` |
| Tunnel | named `studio`; its settings are in `C:\Users\LUFI\.cloudflared\config.yml`, which sends the domain to `http://127.0.0.1:8081` |
| Secrets | `cert.pem` and the tunnel's `.json` credentials file in `C:\Users\LUFI\.cloudflared\`. Never copy them into the repo. |

**After a reboot** nothing starts by itself. Start the app, then the tunnel in a second window:

```
C:\Scene\Scene.ai\scripts\start.bat
C:\cloudflared\cloudflared.exe tunnel run studio
```

The tunnel is up when its window says `Registered tunnel connection`. Do not make the tunnel, the DNS
record or the config again after a reboot: they are kept.

**If the public address does not work**, check in this order: `http://localhost:8081` on the studio PC
(if that fails, the app is not running); `cloudflared.exe tunnel ingress validate` (expects `OK`);
`cloudflared.exe tunnel list`; then the output of `tunnel run studio`.

**Errors in the tunnel's window that are not faults:**

- `stream … canceled by remote with error code 0` followed by `Request failed … /api/library/<n>/file`:
  the visitor's browser closed a download it no longer needed, which a browser does when it has read
  enough of a video, when a video is scrubbed, or when the page is left. Thumbnails used to cause a
  burst of these on every page; they are posters now and no longer do.
- `Failed to dial a quic connection` or `timeout: no recent network activity`, followed by a new
  `Registered tunnel connection`: a short loss of connection that mended itself.

Not done yet: `cloudflared` as a Windows service, the app starting with Windows, and logs kept anywhere.

# Folders

| What | Where | Set by |
|---|---|---|
| The studio (code) | `C:\Scene\Scene.ai` | where the repo is |
| HyperFrames and its packages | `C:\Scene\Scene.ai\motion\node_modules\` | `npm install` in `motion/`; see [motion.md](motion.md) |
| Node.js | `C:\Program Files\nodejs\` | its installer; `node_path` in `config.json` if it is elsewhere |
| Finished images and videos | `C:\Scene\Outputs\<user email>\`, for example `C:\Scene\Outputs\admin@gmail.com\` | `output_dir` in `config.json` |
| Video thumbnails (posters) | `.posters\` inside each user's folder of finished work | made by the app the first time a thumbnail is shown; safe to delete, they are made again |
| Saved assets, cache, working files (the database is PostgreSQL: database.md) | `C:\Scene\Data\` | `storage_dir` in `config.json` |
| PostgreSQL's data | `C:\Scene\Data\postgres\` | the PostgreSQL service; see [database.md](database.md) |
| Langfuse (tracing; running, connected in the console's Servers) | `C:\Scene\langfuse\`: its Docker files and `.env` of passwords | made on 30 October; see [langfuse.md](langfuse.md) |
| Database passwords | `C:\Scene\Data\secrets\` | made on 8 October; never copy them into the repo |
| Daily copies of the database and of `config.json` | `E:\SceneBackups\` (the disk named External Disk) | `backup_dir` in `config.json`; `backup_keep` days are kept, 14 unless set |

The data is kept outside the repo on purpose: on 8 October a branch switch overwrote a database that
lived in `storage\` inside it. Without `storage_dir` the app falls back to `storage` in the repo, and
without `backup_dir` to `backups` inside the storage folder; set both on a real installation, the
backups on another disk. The copies are `pg_dump` files (`scene_<date>.dump`); how to restore one is in
[database.md](database.md). The backup folder holds the secret keys (in its copies of `config.json`), so
treat it like `config.json`.

`output_dir` is optional. Without it, finished work goes to `outputs` inside the storage folder.
Restart the app after changing it. The database records only file names, so files already made have
to be moved by hand into the new folder, keeping their sub-folders. A sub-folder still named by user
id (`1`, `2`, …), as they were before 4 October, is renamed to the email the first time it is needed.

**Inputs.** A reference file added to a job is not kept by the studio. It is sent straight to the
render PC and stays in ComfyUI's `input` folder there, named `scene_<hash>_<name>`. Only files saved
as **assets** are kept here, in `storage\assets\<user id>\`.
