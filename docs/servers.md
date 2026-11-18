# Servers and folders on the studio PC

Scene.ai talks to a render server, and to Anthropic's Claude models for the agent. All of it is set in
`config.json` in the repo root. That file is ignored by git, so it has to be set on every machine
the app runs on, and it is where the secret keys are: **do not open, print or copy it**; change single
lines of it, and check the models with `scripts/check_models.py`.

| Server | Address | `config.json` key | Where it runs |
|---|---|---|---|
| ComfyUI (rendering) | `http://100.123.221.34:8188` | `comfy_url` | The Windows render PC (Zoro), reached over Tailscale |
| Generation server (provider videos, pictures, sound) | `http://100.71.159.106:8189` | the console (Servers & APIs → Providers): one `sa_live_…` key per model or kind of work | This PC (LUFI), `D:\Studio_automation`: the Scene Provider API v1, and ComfyUI's API while the router is off. The studio's way to everything it generates, ComfyUI less and less (Moving off ComfyUI, below) |
| Claude (the agent's models) | Anthropic, through Claude Code | the console's Providers (Claude on this PC, Anthropic); `claude_models` | The `claude` signed in on this PC, run by the studio itself, or the same `claude` with an API key ("Claude on this PC", below) |

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
| `claude_connection` | `this_pc` | How the studio reaches Claude Code: `this_pc` (Claude on this PC: its sign-in) or `api_key` (below). |
| `anthropic_api_key` | | The Anthropic API key. A secret: `SCENE_ANTHROPIC_API_KEY` or the console, never `config.json`. |

The last two are set in the admin console (Servers & APIs → **Providers**: "The agent uses", and the Anthropic
provider's key), which wins over `config.json`; a `SCENE_*` variable wins over both, and the console then shows that
key as fixed.

The agent's model is used for: the agent's answers and plans, the structured caption that Ideogram 4 needs (written
by the render worker just before the render), describing NeuralCore's pictures, Compact, and the check of a result.
With Claude unreachable, those stop and everything else works.

```json
{
  "comfy_url": "http://100.123.221.34:8188",
  "agent_model": "sonnet",
  "default_workflow": ""
}
```

`default_workflow` is empty since 12 November: the studio sets no model. The agent asks which model and resolution
before the first video and the first picture of a conversation (and keeps the answers in its direction), and Create's
quick actions and the composer open on the model the user picked last, or on none until they pick one.

Write the addresses without a trailing slash.

The tunnel closes a request that sends nothing for 100 seconds, and a long answer can be quiet longer. So the agent's
answer sends a sign of life every 15 seconds, and the single answers that wait on the model (review, compact, motion
scenes) send spaces until their JSON is ready.

**Checking them.** This checks the Claude connection in use, says which models it offers and sends one small message to each:

```bash
.venv\Scripts\python.exe scripts\check_models.py
```

## The render servers and the load balancer

Every ComfyUI server of the console (Servers & APIs → Providers, the ComfyUI ones) is a row of `endpoints`, kept in step with its provider. The load balancer
(`backend/scene/balancer.py`, run by the queue's worker in `jobs.py`) places each waiting render:

- **What a server can do.** "Workflows" (the column `models`): patterns of the workflow ids it takes, fnmatch style,
  matched against the whole id and the file's name (`generation_*` takes `video/generation_video`). A server
  with patterns takes only those, and a workflow some server's patterns claim goes only to the servers that claim it.
  A server without patterns takes everything no server claims, when it has the workflow's nodes (its `/object_info`,
  read the first time a render could go there and every 30 minutes; unknown counts as having them).
- **How much it runs at once.** "Jobs at once" (the column `slots`, 1 to 16, migration 0014): 1 for ComfyUI, about 4
  for the generation server, which spreads its jobs over the provider accounts itself.
- **Which one.** Of the servers that can do it and have a slot free, the least busy (running / slots), the first on a
  tie, asked whether it answers. A render that has to wait does not hold up the renders behind it that another server
  can do. A render no server in use could ever do fails at once, saying why, and its credits come back.
- **Who and where.** Every graph is sent with `extra_data` = `{"scene": {"user", "project", "module", "job"}}`: the
  generation server logs, limits and sorts its jobs by it (a job on a project's own canvas is in the module "Main
  canvas"). ComfyUI ignores it.

The generation server's models reach the studio two ways, picked by the provider router's switch (below): as its own
provider over the Scene Provider API v1 (router `on`), or, the way it was first added, dressed as a ComfyUI server
(router `off` or `shadow`). That second way stays working until the router has been on for a week; it is described
under "The fallback path".

## Providers and keys

Every model service the studio uses is a **provider** with **one or more keys**, in one registry (migration 0015,
`backend/scene/providers/`), listed in the admin console under Servers & APIs → **Providers**. Adding a key is the only
step to use a provider's models.

| Word | Meaning | Example |
|---|---|---|
| Capability | a kind of job | `text_to_video`, `image`, `speech`, `transcribe`, `agent_llm` |
| Provider | a service with one address and one adapter (`kind`) | "Generation server" (`scene_provider_v1`), "Zoro" (`comfyui`), "Anthropic", "Claude on this PC" (`claude_local`: no address, no key) |
| Key | a credential for one provider; a provider can have many | `sa_live_…` "studio A", "studio B" |
| Model | something a key unlocks, for one capability, by the provider's own id | `seedance_2_5`, `nano-banana-pro`, `speech` |

**The tables.** `providers` (kind, name, base_url, active, priority), `provider_keys` (label, the key sealed with
`vault.py`, its last 4, active, priority, `max_concurrent`, `daily_cap` in studio credits, `status` ok / invalid /
no_credit / rate_limited / unknown, `cooldown_until`, `last_error`, what the provider's whoami last said), and
`provider_models` (each key's `GET /v1/models`, read every 10 minutes, the last good answer kept). A job made through a
provider keeps the key it ran with (`jobs.provider_key`, for the daily cap) and `jobs.provider`: provider, model, key
**label**, the provider's job id and `X-Request-Id`, its quote and cost. Never a key. Job logs and the job's Langfuse
span carry the same.

**Adding a key.** Add key: pick a provider (or "New: …" a type, with its address the first time for a self-hosted
one), paste the key, optionally a label, max at once and daily cap, Save. The studio asks the provider at once
(`whoami` and `models`) and says "Works · 22 models · 91,296 credits" or the provider's exact words; a key that fails is
saved only on **Save anyway**. Per key: Test, Edit (label, max at once, daily cap), Switch off, Remove. Keys are never
sent back to a page: only their label and last 4. An environment variable can still fix a key (`SCENE_ANTHROPIC_API_KEY`,
an env file): it is listed, marked as set by that variable, and can only be tested.

**A key per model or per kind of work.** The generation server's keys have scopes (`*`, `text_to_video:*`,
`text_to_video:seedance_2_5`, `speech:*` …), so its panel can make one key for each model or each kind of work, many at
once ("Make keys for…", then **Copy all**: one `label<TAB>key` a line). In Add key, **Several keys** takes that paste
(`POST /api/admin/providers/keys/many`, `registry.parse_keys`): one key a line, as `label<TAB>key`, `label: key` or the
key alone, at most 50; each is checked like a single key (4 at a time) and saved when it works (or on Save anyway); a key
with no label takes the label the provider's whoami gives it; a key the provider already has is left out ("Already here
as …"); a new provider is made by the first key saved. Under each key of a Scene provider the console says what it
unlocks ("Unlocks Video: Seedance 2.5 · Voiceover: Speech", `registry.unlocks`, from its last read `/v1/models`). The
router needs nothing more: for each job it takes the keys whose models include the job's model, so a key per model
spreads the work by model, and several keys for one model share it.

**Voices.** `GET /api/voices?q=&language=` (any signed-in user) and the agent's `voices` tool list the voiceover
model's voices from the provider's `GET /v1/voices`, asked with the first key that has the `speech` model, kept 10
minutes (`Router.voices`). A provider without that route (404) gives none: "… has no voice list yet: type a voice id".

**The adapters** (`providers/`): one small interface (`whoami`, `models`, `start`, `status`, `cancel`, `fetch_output`) and
three kinds of problem: **KeyProblem** (bad key, no credit, rate limited, not in scope), **ProviderProblem** (down, 5xx,
model unavailable), **RequestProblem** (invalid, refused: never retried).

- `scene_provider_v1` (`v1.py`): the contract in `C:\Scene\provider-plan\02-provider-api-v1.md`, with its first
  implementer's changes. Bearer key; `Idempotency-Key` `scene-job-<job id>` (`-clip-<n>` for a clip), the same on every
  retry; `metadata.scene` as ComfyUI's `extra_data.scene`; polling every 3 s, backing off to 15 s; errors by the
  contract's table. A test key's job ends `test_mode`: "The provider: Test mode: would cost N credits", never retried.
  The quote is `{credits, source}` (the price list's estimate at POST, the provider's once quoted); `cost` is null until
  the job ends. File inputs are those marked `x-file` in the model's `input_schema`, sent as `POST /v1/files` ids.
- `comfyui` (`comfyui.py`): wraps what always rendered. Its "models" are the studio's ComfyUI workflows this server takes
  (its Workflows patterns), each with a capability from its folder and name (`video/*v2v*` video_to_video,
  `*outpaint*` outpaint, `*animate*` animate, `*talking_head*` talking_head, any other `video/` text_to_video,
  `audio/*transcribe*` transcribe …). ComfyUI renders still go through `jobs.py` and the load balancer: nothing about them changed. Each
  ComfyUI provider is kept in step with its row of `endpoints` both ways, so the balancer reads them as before.
- `anthropic` (`anthropic_api.py`): the agent's model (`agent_llm`) with an API key. Only the check of a key lives here
  (Anthropic's `GET /v1/models`); the agent's calls go through `claude.py`. `claude_local` (Claude on this PC) has no
  adapter: it has no key to check, and its card's status is `claude_connection.status` (below).

**The router** (`router.py`). For a model: the providers offering it → their keys switched on and not invalid → leave out
keys in cooldown, at their max at once (else what whoami says, else 1) or over their daily cap → the least busy
(running ÷ allowed), ties by provider priority, then key priority (lower first). On a KeyProblem the key is marked
(retry_after, else 60 s; an hour for no credit; until fixed for invalid) and the next key is tried once; on a
ProviderProblem the next provider offering the model, once; a RequestProblem fails the job with the provider's words.
It fails over only before a job has started at a provider. A model no key could ever make fails at once, its credits
given back: "No provider has a key for Seedance 2.5: add one in Servers & APIs → Providers."

**The switch** `provider_router` (a setting, on the Providers page; **off** by default):

- `off`: today's paths only. The generation server is reached as a ComfyUI server (the fallback path below).
- `shadow`: today's paths do the work; for each render the router also notes which provider and key it would have
  picked, on the job (`jobs.provider` → `shadow`: would, did, agree) and in the log. It changes nothing about where a
  job runs. To compare: `SELECT provider->'shadow'->>'agree' AS agree, COUNT(*) FROM jobs GROUP BY 1`.
- `on`: the v1 providers' models are offered in the pickers, Create and the agent's catalog as `<folder>/@<model id>`
  (`video/@seedance_2_5`, `audio/@speech`), under "Models", their forms built from `input_schema` and `limits`
  (`providers/workflows.py`), and made through their providers. The `generation_*` workflow files are not offered.
  ComfyUI's workflows stay with the load balancer. A model's length and reference counts are checked before a job is
  charged. Long videos of several clips are not offered for these models yet. The provider's price is shown in the
  console's Pricing beside each model, as a starting point; the studio's price is set there as for any workflow.

### Moving off ComfyUI

The plan is that the studio makes everything through the generation server's keys, and ComfyUI goes, one kind of work
at a time (`C:\Scene\provider-plan\06-comfyui-overlap-and-removal.md`; the generation server's side:
`07-prompt-studio-automation-keys-and-gateway.md`). The console's **What makes what** (under Providers;
`GET /api/admin/providers/capabilities`, `registry.coverage`) lists each kind of work (`base.CAPABILITY_WORDS`): the
providers' models that make it, with their keys (a model only test keys have is marked "(test key)"), ComfyUI's
workflows that make it, and who makes it now: Providers and ComfyUI, Providers only, ComfyUI only.

**Stop using ComfyUI** for a kind of work (`PUT /api/admin/providers/capabilities/<capability>` `{"comfyui": false}`,
the setting `comfyui_off`, audited) takes ComfyUI's workflows of that kind out of Create, the agent's catalog and the
phone site, and refuses a job sent to one: "Transcription is no longer made on ComfyUI: pick one of the providers'
models." (`credits.enabled`, `studio.switched_on`). It is allowed only while the router is `on` and a **live** key makes
that kind of work, so something always makes it; **Use ComfyUI again** is allowed at any time. With the router not
`on` the list is kept but has no effect, so switching the router off brings every ComfyUI workflow back. The studio's
own inner steps (taking the voice out before a ComfyUI lip sync, `jobs.CLEAN_VOICE`) still run on ComfyUI while there is
one. Kinds of work no provider makes yet (video to video, outpaint, character animation) stay on ComfyUI until the
generation server offers them (part 4 of the prompt: ComfyUI behind the generation server).

The order, with a week of watching between steps (06's plan): music, video upscale, lip sync, pictures, video; then
transcription and voice separation once the generation server makes them; then the rest. When What makes what says
"ComfyUI makes nothing now" for a month, the `comfyui` provider, `comfy/`, `balancer.py`'s node code and the
`generation_*` workflows can be removed.

**The agent's provider.** "The agent uses" picks Claude on this PC (the default) or Anthropic (the setting
`agent_provider`); it is in use from the next call to Claude, in every process, with no restart. Anthropic's key is
the provider's first working key (a fixed one first); Anthropic with no key is refused ("Paste an Anthropic API key, or
pick Claude on this PC"), never run on the PC's sign-in. Claude on this PC is a **personal subscription**: while it is
in use the console says "Personal Claude subscription", sign-up is closed whatever Settings says, and only admins can
use the agent. Picking Anthropic lifts both. Switching reopens each conversation's live session the new way, going on
with the same session (both run in the studio's one `home`). The route `/api/admin/claude-connection` gives the card
its status (and still takes the old card's save, written into the registry); `claude_connection.py` reads the registry
first, the settings rows only on a database without it.

**Migrations 0016 and 0017.** 0016 added the `claude_local` provider ("Claude on this PC") and moved `agent_provider`
to it when the agent used the LUFI bridge. On a new database (Anthropic with no key, never picked) it leaves the agent
unset, so the studio's start picks by `config.json`'s `claude_connection`: Claude on this PC by default, the API key
for the test studios. 0017 deleted the LUFI bridge's provider (`claude_bridge`) with its keys and the settings
`claude_bridge_url` and `claude_bridge_key`; its downgrade puts the provider back with no address and no key.

**Migration 0015** copied what was there: each ComfyUI server of `endpoints` → a `comfyui` provider with one key (its
api_key; its Jobs at once as max at once); the Claude connection → an `anthropic` provider (always) and a
`claude_bridge` provider (when it had an address or a key), with `agent_provider` set to the one in use. Langfuse stays
in `endpoints`. Nothing was deleted: `endpoints`, the settings and the generation-server code stay until the router has
been on for a week (`C:\Scene\provider-plan\01-design.md`, section 8).

### The fallback path: the generation server as a ComfyUI server

While the router is `off` or `shadow`, the generation server is a ComfyUI provider whose Workflows are `generation_*`
(4 at once). Its models are workflows: `workflows/video/generation_video` and `workflows/image/generation_image`, whose
Model setting is the model; its Resolution, Shape and Sound are that model's own (`backend/scene/generation_models.py`).
What each model takes comes from its `GET /generation/models`, kept 10 minutes. Beside them are its single-model tools:
`audio/generation_speech`, `audio/generation_music`, `audio/generation_sound_effect`, `video/generation_lipsync`,
`upscaler/generation_upscale`. Its errors read "The provider: <reason>". The provider has no cancel: a job cancelled once
it started is still finished and charged there; the studio gives the user's credits back and says so.

### Claude on this PC

The agent reaches Claude through the `claude` signed in on this PC (LUFI), run by the studio itself
(`claude.LocalProgram`), with no key, no address and no second app. It replaced the SceneCloude bridge, a separate app
on the same PC that the studio reached over a WebSocket on `127.0.0.1:8765`, which existed only so a studio on Azure
could use this PC's sign-in; with the move to Azure cancelled, its network hop, keys and lockout protected nothing.
The design, and why, for someone new: `docs/claude-on-this-pc.md`.

**What is checked, on every run** (`backend/scene/claude_policy.py`, ported from the bridge's `policy.py`), with
either connection:

- **The arguments.** `--tools` is empty or `WebSearch` only (never `WebFetch`, which would read this PC's network);
  `--setting-sources ""` and `--strict-mcp-config` are required, so none of this PC's own settings, hooks, MCP servers
  or tools are used; `--allowedTools` holds only `WebSearch` and the studio's own in-process tools
  (`mcp__studio__<tool>`); `--mcp-config` declares only in-process (`"type":"sdk"`) servers; `--settings` holds only
  `autoMemoryEnabled` and `autoCompactWindow`; `--system-prompt-file` must be a file in the run's own temporary folder.
  `--dangerously-skip-permissions`, `--add-dir`, `--permission-mode`, `--plugin-dir`, subcommands and any flag not
  listed are refused, naming the flag. The SDK's `--flag=value` form is read as two.
- **The environment.** The studio may add only the SDK's own variables and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.
  `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are taken out of `claude`'s environment on Claude on this PC (so the
  subscription is used, never a key that happens to be in the studio's environment) and put in with the API key.
- **Each line of stdin.** Every user message gets `"client_composed": true`, so Claude Code delivers it as written: a
  `@C:\path` in it is not read from this PC's disk, and `/logout` or any slash command does not run. Only a message
  that is exactly `/compact` or `/rename <title>` (the studio's own) runs as a command. A message may hold text and
  base64 pictures only. A control request other than `initialize` (with hooks only), `interrupt`, `mcp_status`,
  `get_context_usage`, `set_model` and `stop_task` is answered by the studio with an error, and the session goes on.

A refused call is never started: "The studio would not let this through to Claude Code (<what>)". That would be a bug
in how the studio builds the call, not something a user did.

**Its card** (Servers & APIs → Providers). "Signed in as name@… · Pro · Claude Code 2.1.x", or why not and the fix
("Signed out. Press Sign in on Claude on this PC"); "This 5-hour window: 27% (resets 14:10) · This week: 34% (resets
Mon)"; "2 of 3 running"; **Check**, **Sign in** (or **Switch account**) and **Sign out**.

**Signing in from the console** (`claude_connection.login_start`, `login_code`, `logout`). Sign in runs `claude auth
login --claudeai` on this PC, with no key in its environment, and shows the link it prints. The admin opens it in
their own browser, on any machine, signs in to their Claude account, and pastes the code Anthropic's page shows into
the card; the studio writes it to the waiting `claude`, then asks `claude auth status` again. A sign-in waits 15
minutes for its code, then stops. Sign out runs `claude auth logout`. It is the same sign-in as `claude` then
`/login` in a terminal here, so it also signs this PC's own Claude Code in or out. The sign-in waits in the process
that started it: with several processes (`redis_url`), a code that reaches another is answered "press Sign in
again". Endpoints (admins only, audited): `POST /api/admin/claude-connection/signin` → `{"link"}`,
`POST …/signin/code` `{"code"}`, `DELETE …/signin`, `POST …/signout`. The sign-in is
`claude auth status --json` (Claude Code's own files: no call to Claude, nothing spent), kept 5 minutes; Check asks
again. The plan's limits are the last `rate_limit_event` a call reported (`claude.LIMITS`), kept in the `settings` row
`claude_plan_limits` so they survive a restart; a window whose reset has passed shows 0. The health check
(`health.py`) asks the same, never a paid call.

**What stays as it was.** A stuck turn is stopped after `claude_timeout` seconds of silence while Claude works, paused
while one of the studio's tools runs (a video generation may take hours) and between turns (`claude._next`); a live
session idle for 15 minutes is closed and resumed with its next message. At most 3 calls answer at once
(`claude.PARALLEL`); more wait their turn. Both were already in the studio, so nothing was ported for them.

**Conversations started through the bridge** had their sessions in the bridge's folder
(`%LOCALAPPDATA%\SceneCloude\home`). Here Claude Code looks in the studio's `home`, does not find the session, and says
so; the studio then starts a new session with the whole conversation (`claude.Lost`, `workspace.py`), as it does for any
session that is gone. Nothing is copied.

### Switching off the old bridge app (by hand, on LUFI)

Once Claude on this PC works:

1. `C:\SceneCloude\stop.ps1`
2. `Unregister-ScheduledTask "SceneCloude Bridge"` (an admin PowerShell)
3. Optional: delete `%LOCALAPPDATA%\SceneCloude`, and the bridge's grant in the Tailscale ACL.

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
