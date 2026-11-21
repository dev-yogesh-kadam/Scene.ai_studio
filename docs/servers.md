# Servers and folders on the studio PC

Scene.ai makes everything with **providers**: Studio_automation (the generation server) over the Scene Provider API v1,
and **On this PC**, the studio's own tools. The agent's models are Anthropic's Claude. The settings are in `config.json`
in the repo root. That file is ignored by git, so it has to be set on every machine the app runs on, and it is where the
secret keys are: **do not open, print or copy it**; change single lines of it, and check the models with
`scripts/check_models.py`.

| Service | Address | Set in | Where it runs |
|---|---|---|---|
| Studio_automation (videos, pictures, voiceover, music, sound effects, lip sync, upscales, control maps) | `http://127.0.0.1:8189` | the console (Servers & APIs → Providers): one `sa_live_…` key per kind of work | This PC (LUFI), `D:\Studio_automation`. It reaches the cloud models (Frameo) itself; the studio only ever sends it jobs with keys |
| On this PC (transcription, voice separation) | none | built in (migration 0018); its Python is `local_tools_python` | This PC: `backend/local_tools/run.py`, run with `.venv-audio` on the GPU (Tools on this PC, below) |
| Claude (the agent's models) | Anthropic, through Claude Code | the console's Providers (Claude on this PC, Anthropic); `claude_models` | The `claude` signed in on this PC, run by the studio itself, or the same `claude` with an API key ("Claude on this PC", below) |

**No ComfyUI** (since 18 November). The studio once rendered on ComfyUI servers (the render PC, Zoro) and reached
Studio_automation dressed as one. Both are gone: the load balancer, the ComfyUI client and adapter, the
generation server's ComfyUI disguise (`generation_*` workflows, `generation_models.py`), the render-server checks, the
workflow-file history and the settings `comfy_url`, `workflows_dir` and `hold_queue_offline` (migration 0019 took the
ComfyUI rows out of the database). The workflow files are kept in `workflows/archive/comfyui_2026-11-18/`, never read.
`scene/comfy/workflows.py` keeps its name: it is the studio's own workflow format, which every provider model is
offered in (`providers/workflows.py`).

**The agent uses Anthropic's Claude models only** (since 31 October). Ollama, Gemini, Kimi and every other
OpenAI-style service were taken out, with their settings and the endpoints of the admin console that pointed at them
(`scene/endpoints.py` deletes any left in the database).

| Key | Default | What |
|---|---|---|
| `agent_model` | the first of `claude_models` | The model the agent uses unless the user picks another in the Agent tab (`sonnet`). |
| `claude_models` | `sonnet, opus, haiku` | The models offered, as Claude Code names them. |
| `claude_fast_model` | `haiku` | The model for small jobs: the Ideogram caption, notes, the check of a result. Empty uses the one in use. |
| `claude_timeout` | 600 | Seconds one call may take. |
| `claude_context` | 1000000 | Tokens of context the models have; a session is compacted at 90% of it. |
| `claude_connection` | `this_pc` | How the studio reaches Claude Code: `this_pc` (Claude on this PC: its sign-in) or `api_key` (below). |
| `anthropic_api_key` | | The Anthropic API key. A secret: `SCENE_ANTHROPIC_API_KEY` or the console, never `config.json`. |
| `local_tools_python` | `.venv-audio/Scripts/python.exe` | The Python the tools on this PC run with (Tools on this PC, below). Missing: those tools are not offered. |

The Claude ones are set in the admin console (Servers & APIs → **Providers**: "The agent uses", and the Anthropic
provider's key), which wins over `config.json`; a `SCENE_*` variable wins over both, and the console then shows that
key as fixed.

The agent's model is used for: the agent's answers and plans, the structured caption that Ideogram 4 needs (written
just before the job is sent), describing NeuralCore's pictures, Compact, and the check of a result. With Claude
unreachable, those stop and everything else works.

```json
{
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

## Providers and keys

Every model the studio uses comes from a **provider** with **one or more keys**, in one registry (migrations
0015-0019, `backend/scene/providers/`), listed in the admin console under Servers & APIs → **Providers**. Adding a key is
the only step to use a provider's models.

| Word | Meaning | Example |
|---|---|---|
| Capability | a kind of job | `text_to_video`, `image`, `speech`, `transcribe`, `agent_llm` |
| Provider | a service with one address and one adapter (`kind`) | "Studio automation" (`scene_provider_v1`), "On this PC" (`local_tools`: built in, one key with no secret), "Anthropic", "Claude on this PC" (`claude_local`: no address, no key) |
| Key | a credential for one provider; a provider can have many | `sa_live_…` "Scene.ai · Video: all", "Scene.ai · Music: all" |
| Model | something a key unlocks, for one capability, by the provider's own id | `seedance_2_5`, `nano-banana-pro`, `speech`, `transcribe` |

**The tables.** `providers` (kind, name, base_url, active, priority), `provider_keys` (label, the key sealed with
`vault.py`, its last 4, active, priority, `max_concurrent`, `daily_cap` in studio credits, `status` ok / invalid /
no_credit / rate_limited / unknown, `cooldown_until`, `last_error`, what the provider's whoami last said), and
`provider_models` (each key's `GET /v1/models`, read at start and every 10 minutes, the last good answer kept). A job
made through a provider keeps the key it ran with (`jobs.provider_key`, for the daily cap) and `jobs.provider`:
provider, model, key **label**, the provider's job id and `X-Request-Id`, its quote and cost (a chain's lists each
clip). Never a key. Job logs and the job's Langfuse span carry the same.

**Models in the studio.** Each model a key unlocks is offered in the pickers, Create, the phone site and the agent's
catalog as `<folder>/@<model id>` (`video/@seedance_2_5`, `audio/@transcribe`), its form built from `input_schema` and
`limits` (`providers/workflows.py`). A model's length and reference counts are checked before a job is charged. A model
with a prompt, a length and a first frame makes **long videos of several clips** (`jobs._run_provider_chain`): each clip
its own call (`Idempotency-Key` `scene-job-<id>-clip-<n>`), starting on the last frame of the one before, the prompt's
parts split by a line of dashes, then joined. A **lip sync whose voice track has music under it** (`clean_voice`) has
the voice taken out on this PC first (`jobs._clean_voice_here`). The provider's price is shown in the console's Pricing
beside each model, as a starting point; the studio's price is set there as for any workflow. With "new models start for
admins only" (Workflows section) a model a key newly unlocks is offered to admins alone until one offers it to everyone.

**Adding a key.** Add key: pick a provider (or "New: …" a type, with its address the first time), paste the key,
optionally a label, max at once and daily cap, Save. The studio asks the provider at once (`whoami` and `models`) and
says "Works · 22 models · 91,296 credits" or the provider's exact words; a key that fails is saved only on **Save
anyway**. Per key: Test, Edit (label, max at once, daily cap), Switch off, Remove. Keys are never sent back to a page:
only their label and last 4. An environment variable can still fix a key (`SCENE_ANTHROPIC_API_KEY`, an env file): it is
listed, marked as set by that variable, and can only be tested. On this PC takes no key and can't be removed (switch it
off instead).

**A key per model or per kind of work.** Studio_automation's keys have scopes (`*`, `text_to_video:*`,
`text_to_video:seedance_2_5`, `speech:*` …), so its panel can make one key for each model or each kind of work, many at
once ("Make keys for…", then **Copy all**: one `label<TAB>key` a line). In Add key, **Several keys** takes that paste
(`POST /api/admin/providers/keys/many`, `registry.parse_keys`): one key a line, as `label<TAB>key`, `label: key` or the
key alone, at most 50; each is checked like a single key (4 at a time) and saved when it works (or on Save anyway); a key
with no label takes the label the provider's whoami gives it; a key the provider already has is left out ("Already here
as …"); a new provider is made by the first key saved. Under each key the console says what it unlocks ("Unlocks Video:
Seedance 2.5 · Voiceover: Speech", `registry.unlocks`). The router needs nothing more: for each job it takes the keys
whose models include the job's model, so a key per model spreads the work by model, and several keys for one model
share it. On 18 November the studio was given nine live keys, one per kind of work.

**What makes what** (under Providers; `GET /api/admin/providers/capabilities`, `registry.coverage`) lists each kind of
work (`base.CAPABILITY_WORDS`) and the models that make it, with their keys (a model only test keys have is marked).
Video to video, outpaint and character animation are made by the video models that edit a reference video
(`limits.reference_video_edits`: Seedance, Wan); the agent's recipes for them are in `agent.py`.

**Voices.** `GET /api/voices?q=&language=` (any signed-in user) and the agent's `voices` tool list the voiceover
model's voices from the provider's `GET /v1/voices`, asked with the first key that has the `speech` model, kept 10
minutes (`Router.voices`). A provider without that route (404) gives none: "… has no voice list yet: type a voice id".

**The adapters** (`providers/`): one small interface (`whoami`, `models`, `start`, `status`, `cancel`, `fetch_output`) and
three kinds of problem: **KeyProblem** (bad key, no credit, rate limited, not in scope), **ProviderProblem** (down, 5xx,
model unavailable), **RequestProblem** (invalid, refused: never retried).

- `scene_provider_v1` (`v1.py`): the contract in `C:\Scene\provider-plan\02-provider-api-v1.md`, with its first
  implementer's changes. Bearer key; `Idempotency-Key` `scene-job-<job id>` (`-clip-<n>` for a clip), the same on every
  retry; `metadata.scene` = `{"user", "project", "module", "job"}`; polling every 3 s, backing off to 15 s; errors by the
  contract's table. A test key's job ends `test_mode`: "The provider: Test mode: would cost N credits", never retried.
  The quote is `{credits, source}` (the price list's estimate at POST, the provider's once quoted); `cost` is null until
  the job ends. File inputs are those marked `x-file` in the model's `input_schema`, sent as `POST /v1/files` ids.
  The provider has no cancel: a job cancelled once it started is still finished and charged there; the studio gives
  the user's credits back and says so.
- `local_tools` (`local.py`): On this PC (below). It answers as a Scene provider does, free (quote and cost 0), one job
  at a time.
- `anthropic` (`anthropic_api.py`): the agent's model (`agent_llm`) with an API key. Only the check of a key lives here
  (Anthropic's `GET /v1/models`); the agent's calls go through `claude.py`. `claude_local` (Claude on this PC) has no
  adapter: it has no key to check, and its card's status is `claude_connection.status` (below).

**The router** (`router.py`). For a model: the providers offering it → their keys switched on and not invalid → leave out
keys in cooldown, at their max at once (else what whoami says, else 1) or over their daily cap → the least busy
(running ÷ allowed), ties by provider priority, then key priority (lower first). On a KeyProblem the key is marked
(retry_after, else 60 s; an hour for no credit; until fixed for invalid) and the next key is tried once; on a
ProviderProblem the next provider offering the model, once; a RequestProblem fails the job with the provider's words.
It fails over only before a job has started at a provider. A model no key could ever make fails at once, its credits
given back: "No provider has a key for Seedance 2.5: add one in Servers & APIs → Providers." The queue (`jobs.py`)
starts each waiting job as soon as a key that can make it has room, and a job of a workflow that is not a model (an old
ComfyUI one) fails at once, saying so.

### Tools on this PC

**On this PC** (`local_tools`, migration 0018) makes what no cloud provider offers the studio: **transcription**
(`audio/@transcribe`, `audio/@transcribe_video`: faster-whisper large-v3) and **voice separation**
(`audio/@separate_voice`: Demucs htdemucs). `providers/local.py` runs `backend/local_tools/run.py` with the Python of
`local_tools_python`, one process a job, one job at a time (the GPU is shared), and never imports it: PyTorch and the
models stay out of the studio's own Python.

- A transcript is `transcript.json` `{"language", "segments": [{"start", "end", "speaker", "text"}], "words": [{"start",
  "end", "word", "speaker", "aligned"}]}` (seconds, 3 decimals) and `transcript.srt` (`[SPEAKER_00] text` a line), as
  ComfyUI's SceneTranscribe made them. **Speaker labels are not set up yet**: every line is `SPEAKER_00` (they need
  pyannote and a Hugging Face token).
- Voice separation makes `voice.wav` and `music_fx.wav` at the input's sample rate and exact length; `music_fx` is the
  input minus the voice, so the two add back up to it.
- A tool whose software is missing is not offered, and the provider's alerts say what to install.

Setting it up (done on LUFI on 18 November; about 6 GB with the models):

```bat
py -3.14 -m venv .venv-audio
.venv-audio\Scripts\python -m pip install torch==2.11.0 torchaudio --index-url https://download.pytorch.org/whl/cu128
.venv-audio\Scripts\python -m pip install faster-whisper demucs soundfile
.venv-audio\Scripts\python backend\local_tools\run.py check
```

The models download on first use into `storage/models` (faster-whisper large-v3, about 3 GB; htdemucs, about 80 MB).
On LUFI's RTX 4060 Ti a 5-minute voice-over transcribes in about a minute once the model is in, and separates in 22 s.

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
- A `SCENE_*` variable (`SCENE_AGENT_MODEL` …) overrides `config.json`.
- Providers and their keys are changed in the admin console (Servers & APIs → Providers) while the app runs: no
  restart.

## Checking that they answer

```bash
curl http://127.0.0.1:8189/v1/whoami -H "Authorization: Bearer <a sa_live_ key>"
.venv-audio\Scripts\python.exe backend\local_tools\run.py check
.venv\Scripts\python.exe scripts\check_models.py
```

The first needs Studio_automation running (its panel: `http://127.0.0.1:8189/panel/`); the console's Providers page
does the same with **Test** on each key. The second says whether transcription and voice separation can run on this
PC. The third needs the Claude connection working (the console's card says so).

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
Studio_automation is not behind the tunnel and must stay that way: the app reaches it on this PC.

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

**Inputs.** A reference file added to a job is kept by the studio (`storage\references\`, named
`scene_<hash>_<name>`, `references.keep_reference`) and sent to the provider when the job runs (`POST /v1/files`).
Files saved as **assets** are kept in `storage\assets\<user id>\`.
