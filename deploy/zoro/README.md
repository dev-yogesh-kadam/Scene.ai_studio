# Scene.ai on Zoro

The studio, its PostgreSQL and Langfuse in Docker on Zoro (Ubuntu Server). Code in `~/scene/Scene.ai` (a git clone);
data, outputs and backups beside it, outside the repo:

| On Zoro | In the app container | What |
|---|---|---|
| `~/scene/data` | `/data` | media library (`storage/`), Claude Code's folder (`claude/`), fonts |
| `~/scene/outputs` | `/outputs` | finished images and videos |
| `~/scene/backups` | `/backups` | daily database dumps and file copies (14 days) |
| Docker volume `scene_db` | — | the database itself |

Everything is published on `127.0.0.1` only, since Docker-published ports bypass ufw. Reach it from another machine
with an SSH tunnel (below), or set `SCENE_BIND` / `SCENE_CONSOLE_BIND` in `.env` to Zoro's Tailscale address.

The files: `docker-compose.yml` (this folder), `.env.example` (copy to `.env`, gitignored), and
`../../langfuse/docker-compose.zoro.yml` for Langfuse.

## First install

Run these on Zoro, in order.

**1. Code and folders.** The app runs as uid 10001 in its image, so its folders belong to that account.

```sh
mkdir -p ~/scene && git clone -b founder <your GitHub repo URL> ~/scene/Scene.ai
mkdir -p ~/scene/data ~/scene/outputs ~/scene/backups
sudo chown -R 10001:10001 ~/scene/data ~/scene/outputs ~/scene/backups
docker network create scene-langfuse        # the studio and Langfuse meet here (Caddy's `web` already exists)
```

**2. The studio's secrets** (`deploy/zoro/.env`, never committed). Each password is `openssl rand -hex 24`; the
vault key is a Fernet key (`openssl rand 32 | base64 | tr '+/' '-_'` makes one, as does
`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).

```sh
cd ~/scene/Scene.ai/deploy/zoro
cp .env.example .env && chmod 600 .env
sed -i \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" \
  -e "s|^SCENE_OWNER_PASSWORD=.*|SCENE_OWNER_PASSWORD=$(openssl rand -hex 24)|" \
  -e "s|^SCENE_APP_PASSWORD=.*|SCENE_APP_PASSWORD=$(openssl rand -hex 24)|" \
  -e "s|^SCENE_SECRET_KEY=.*|SCENE_SECRET_KEY=$(openssl rand 32 | base64 | tr '+/' '-_')|" \
  -e "s|/home/<you>|$HOME|" .env
grep -v '^#' .env | grep -c '<'    # 0: nothing left to fill in
```

Copy `SCENE_SECRET_KEY` somewhere safe, apart from the backups: without it the keys saved in the console can't be read.

**3. Langfuse** (optional; the studio runs without it). Fill in its `.env` the same way: `.env.example` lists each
value and how to make it. `docker-compose.zoro.yml` sets `HOSTNAME: "0.0.0.0"` on `langfuse-web`: without it Langfuse
listens on its first Docker network only, and the studio, which comes in on `scene-langfuse`, gets "Connection
refused".

```sh
cd ~/scene/Scene.ai/langfuse
cp .env.example .env && chmod 600 .env
nano .env           # every <...>: passwords with openssl rand -hex 24, as .env.example says
docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.zoro.yml up -d
```

**4. The studio: build, migrate an empty database, make the admin.** `docker compose run` starts the database and
runs the migrations first. The password is asked for twice (it is never an argument).

```sh
cd ~/scene/Scene.ai/deploy/zoro
docker compose build
docker compose run --rm app python -m scene.manage create-admin --email <your email> --name <your name>
docker compose run --rm app python -m scene.manage agent-uses-api-key
docker compose up -d
docker compose ps                               # db and app healthy, migrate exited 0
curl -fsS http://127.0.0.1:8080/readyz && echo  # the database and the media storage answer
```

`agent-uses-api-key` points the agent at the Anthropic API key instead of "Claude on this PC" (a personal Claude
Code sign-in, which a fresh database picks). The key itself is entered in the console in step 5.

**5. Sign in and set the keys.** From your PC:

```sh
ssh -L 8080:127.0.0.1:8080 -L 8090:127.0.0.1:8090 -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 <you>@<zoro>
```

- Console, http://localhost:8090: sign in as the admin. **Servers & APIs → Providers**: add the Anthropic API key
  and the providers' keys. **Servers → Langfuse → Add**: address `http://langfuse-web:3000` and the
  `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `_SECRET_KEY` from `langfuse/.env`.
- Studio, http://localhost:8080. Langfuse, http://localhost:3000.

**6. Later: Caddy.** In `~/caddy/Caddyfile`, proxy the studio only, never the console:

```
studio.example.com {
    reverse_proxy scene-studio:8080
}
```

Then set `SCENE_SECURE_COOKIES=true` in `.env` and `docker compose up -d`.

## Everyday

```sh
cd ~/scene/Scene.ai/deploy/zoro
git pull && docker compose up -d --build   # update: migrations run first, then the app restarts
docker compose logs -f app                 # logs (JSON lines; 5 files of 10 MB kept)
docker compose restart app
docker compose down                        # stop; the database stays in its volume
```

**Never `docker compose down -v` here**: `-v` deletes the database volume. The backups in `~/scene/backups` are
custom-format `pg_dump` files (the console's checks confirm the newest one reads back); restore one with
`pg_restore --no-owner` into an empty `scene` database, with the app stopped.

## What is not here

- **No GPU.** Nothing in the image uses CUDA. Transcription (`transcribe`, `transcribe_video`) and voice separation
  (`separate_voice`, also the lip sync's "clean voice") come from Studio_automation on LUFI, through its key in
  **Servers & APIs → Providers**, as its other models do. "On this PC" (the Windows-only `.venv-audio` tools) is
  switched off here (`SCENE_LOCAL_TOOLS: "off"` in `docker-compose.yml`), so it is not listed and raises no alert.
- **No ComfyUI.** Generation goes through the providers set in the console.
