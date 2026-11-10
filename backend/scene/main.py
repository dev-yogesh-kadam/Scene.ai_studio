"""Scene.ai: the web app. Builds the FastAPI application and wires its parts together."""

import asyncio
import json
import os
import posixpath
import re
import time
from contextlib import asynccontextmanager

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES, GZipMiddleware

from . import aftercare, backup, claude, endpoints, health, langfuse_trace, media, motion, phone_site, roles, semantic, sequence, shared, staff, traces, vault, versions
from .agent import Agent, AgentError
from .api import admin, auth, bulk, client_errors, console as console_api, film, film_ops, kit as kit_api, library, mobile, plans as plans_api, runs, shares, studio, workspace
from .catalog import Catalog
from .comfy import workflows
from .comfy.client import ComfyError
from .config import ROOT, load_settings
from .credits import Credits
from .db import as_everyone, open_database
from .jobs import JobManager
from .outputs import Outputs
from . import storage as stores   # (`storage` is create_app's folder)
from .plans import PlanRunner
from .security import LoginThrottle, RateLimit, is_https, same_origin


class Hub:
    """The open browser connections of each user, for live queue updates, and the page each one has open.

    Its connections live on the event loop. A call from one of the database's threads (a helper run with db.offload)
    is handed to the loop (`elsewhere`)."""

    def __init__(self):
        self.sockets = {}
        self.pages = {}   # connection -> {"page": "#/canvas", "since": when it connected}
        self.watchers = set()   # the admin console's open pages, told the number of people online as it changes
        self.jobs_told = False   # a "jobs changed" for the console is on its way
        self.queue = lambda: {}  # how many jobs run and wait now, sent with it (main.create_app sets it; it queries)
        self.offload = None      # runs a function that queries off the event loop (db.offload; main.create_app sets it)
        self.loop = None         # the app's event loop, once it runs
        self.shared = None       # several processes (shared.py, redis_url): what one sends, every one delivers to its own

    def _everywhere(self, message):
        """With several processes, a message goes through Redis to the one that has the page open: True when it did."""
        if self.shared is None or not self.shared.enabled:
            return False
        asyncio.ensure_future(self.offload(self.shared.publish, message))   # a network call: off the loop
        return True

    def deliver(self, message):
        """A message from Redis (shared.listen): to this process's own open pages."""
        if "drop" in message:
            self._drop_here(message["drop"])
        elif message.get("user") is None:
            self._tell_here(message["text"])
        else:
            self._send_here(message["user"], message["text"])

    def elsewhere(self, fn, *args):
        """True when called off the app's event loop (a database thread): `fn(*args)` is then run on the loop."""
        if self.loop is None or _running_loop() is self.loop:
            return False
        self.loop.call_soon_threadsafe(fn, *args)
        return True

    def add(self, user_id, ws):
        arrived = user_id not in self.sockets
        self.sockets.setdefault(user_id, set()).add(ws)
        self.pages[ws] = {"page": "", "since": time.time()}
        if arrived:
            self.tell_watchers()

    def discard(self, user_id, ws):
        self.sockets.get(user_id, set()).discard(ws)
        self.pages.pop(ws, None)
        if user_id in self.sockets and not self.sockets[user_id]:
            self.sockets.pop(user_id, None)   # nobody with no connection left counts as online
            self.tell_watchers()

    def watch(self, ws):
        """A page of the admin console, told the number at once and again as it changes. It is not someone online."""
        self.watchers.add(ws)
        asyncio.ensure_future(self._send(None, ws, self.headcount()))

    def unwatch(self, ws):
        self.watchers.discard(ws)

    def headcount(self):
        return json.dumps({"online_users": self.online()})

    def tell_watchers(self):
        self.tell({"online_users": self.online()})

    def tell(self, message):
        """Send something to every open page of the admin console: {"online_users": n}, {"jobs": true}, {"alerts": n}."""
        if self.elsewhere(self.tell, message):
            return
        if not self._everywhere({"user": None, "text": json.dumps(message)}):
            self._tell_here(json.dumps(message))

    def _tell_here(self, text):
        for ws in list(self.watchers):
            asyncio.ensure_future(self._send(None, ws, text))

    def jobs_changed(self):
        """Tell the console's pages that a job changed, at most once a second: a busy queue changes many times a second."""
        if not self.watchers or self.jobs_told or self.elsewhere(self.jobs_changed):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:   # not from the app's own loop (a test calling straight in): nothing is listening
            return
        self.jobs_told = True

        async def tell():
            self.jobs_told = False
            counts = await self.offload(self.queue) if self.offload else self.queue()   # no offload: a Hub of a test's own
            self.tell({"jobs": counts or True})
        loop.call_later(1, lambda: asyncio.ensure_future(tell()))

    def set_page(self, ws, page):
        if ws in self.pages:
            self.pages[ws]["page"] = page

    def online(self):
        """How many users have the app open: someone with three tabs is one user."""
        return len(self.sockets)

    def people(self):
        """Who has the app open: user id -> the pages of their open tabs and when the first one opened."""
        found = {}
        for user_id, sockets in self.sockets.items():
            tabs = [self.pages[ws] for ws in sockets if ws in self.pages]
            found[user_id] = {"pages": sorted({t["page"] for t in tabs if t["page"]}),
                              "since": min((t["since"] for t in tabs), default=time.time()), "tabs": len(tabs)}
        return found

    def drop(self, user_id):
        """Close every open page of a user whose sessions were ended (disabled, signed out by an admin)."""
        if self.elsewhere(self.drop, user_id):
            return
        if not self._everywhere({"drop": user_id}):
            self._drop_here(user_id)

    def _drop_here(self, user_id):
        for ws in list(self.sockets.get(user_id, ())):
            asyncio.ensure_future(self._close(user_id, ws))

    async def _close(self, user_id, ws):
        try:
            await ws.close(code=4401)
        except Exception:
            pass
        self.discard(user_id, ws)

    def is_online(self, user_id):
        return bool(self.sockets.get(user_id))

    def send(self, user_id, message):
        if self.elsewhere(self.send, user_id, message):
            return
        if not self._everywhere({"user": user_id, "text": message}):
            self._send_here(user_id, message)

    def _send_here(self, user_id, message):
        for ws in list(self.sockets.get(user_id, ())):
            asyncio.ensure_future(self._send(user_id, ws, message))

    async def _send(self, user_id, ws, message):
        """Send to one connection: a user's (`user_id`), or a console page's (None). One that is gone is forgotten."""
        try:
            await ws.send_text(message)
        except Exception:
            if user_id is None:
                self.unwatch(ws)
            else:
                self.discard(user_id, ws)


def _running_loop():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def quiet_resets(loop):
    """Leave out of the console a browser closing a connection (Windows: "ConnectionResetError: [WinError 10054]" with a
    traceback from asyncio's proactor). A video player does it all the time, dropping a download it no longer needs; it
    is no error of the studio. Anything else is reported as before."""
    before = loop.get_exception_handler()

    def handle(loop, context):
        if isinstance(context.get("exception"), (ConnectionResetError, ConnectionAbortedError)):
            return
        if before:
            before(loop, context)
        else:
            loop.default_exception_handler(context)
    loop.set_exception_handler(handle)


def create_app(settings=None):
    settings = settings or load_settings()
    for warning in getattr(settings, "warnings", ()):
        print("WARNING: " + warning)
    storage = settings.path("storage_dir")
    vault.configure(settings.path("secret_key_file"))
    if hasattr(time, "tzset"):   # Linux, macOS: the app's local time is the studio's (time_zone), not the machine's
        os.environ["TZ"] = settings.time_zone
        time.tzset()
    db = open_database(settings, storage)
    with as_everyone():
        vault.seal_stored(db)   # secrets saved before they were encrypted
    endpoints.seed(db, settings)   # the servers and APIs of the console's Servers section
    comfy_pool = endpoints.ComfyPool(db, settings.comfy_url)
    comfy = comfy_pool.main
    staff.configure(db)   # the console's roles as an admin last saved them
    catalog = Catalog(settings.path("workflows_dir"), comfy, storage / "cache" / "node_definitions.json")
    credits = Credits(db, settings)
    agent = Agent(settings.agent_model, services=list(filter(None, [
        claude.service(settings.claude_models, settings.claude_path, settings.claude_timeout, settings.claude_fast_model,
                       settings.path("claude_home") if settings.claude_home else ROOT, settings.claude_context)])))
    hub = Hub()

    def queue_counts():
        with as_everyone():
            rows = db.all("SELECT status, COUNT(*) AS n FROM jobs WHERE status IN ('queued', 'running') GROUP BY status")
        found = {r["status"]: r["n"] for r in rows}
        return {"running": found.get("running", 0), "waiting": found.get("queued", 0)}
    hub.queue = queue_counts
    hub.offload = db.offload

    def live_message(user_id, library_changed=False):
        """What a user's open pages are sent whenever something of theirs changes."""
        return json.dumps({"jobs": app.state.jobs.snapshot(user_id), "credits": credits.balance(user_id),
                           "library_changed": library_changed})

    told, waiting = {}, set()   # when each user was last sent their jobs; who has a send waiting

    async def send_live(user_id, library_changed=False, plans=None):
        """Make a user's live message on the database's threads (it queries), then send it from the loop."""
        message = await db.offload(live_message, user_id, library_changed)
        hub.send(user_id, message if plans is None else json.dumps(dict(json.loads(message), plans=plans)))

    def tell_plans(user_id, plans):
        """The agent's plans that changed, with where the user's jobs stand (plans.py): the live message's `plans`."""
        if hub.elsewhere(tell_plans, user_id, plans):
            return
        if hub.is_online(user_id):
            asyncio.ensure_future(send_live(user_id, plans=plans))
    app_tell_plans = tell_plans

    def tell(user_id, library_changed=False):
        told[user_id] = time.monotonic()
        if _running_loop() is None:   # a test calling straight in, with no loop: made and sent here
            return hub.send(user_id, live_message(user_id, library_changed))
        asyncio.ensure_future(send_live(user_id, library_changed))

    def notify(user_id, library_changed=False):
        """Send a user's open pages where their jobs stand. A render's progress changes many times a second: a user is
        sent at most one update a second (a finished result at once), and nothing is made for one with no page open.
        Safe to call from a database thread: it is handed to the event loop."""
        if hub.elsewhere(notify, user_id, library_changed):
            return
        hub.jobs_changed()   # the console's Jobs and Overview follow every job
        if not hub.is_online(user_id):
            return
        since = time.monotonic() - told.get(user_id, 0)
        if library_changed or since >= LIVE_EVERY:
            return tell(user_id, library_changed)
        if user_id in waiting:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:   # not from the app's own loop (a test calling straight in)
            return tell(user_id)
        waiting.add(user_id)

        def later():
            waiting.discard(user_id)
            tell(user_id)
        loop.call_later(LIVE_EVERY - since, later)

    @asynccontextmanager
    async def lifespan(app):
        quiet_resets(asyncio.get_running_loop())
        hub.loop = asyncio.get_running_loop()
        app.state.jobs = JobManager(db, comfy, catalog, credits, app.state.outputs, notify, storage / "tmp", settings.node_path,
                                    storage / "assets")
        app.state.jobs.pool = comfy_pool
        app.state.jobs.hold_offline = settings.hold_queue_offline
        app.state.jobs.agent = agent   # writes the captions some image models need, just before they render
        app.state.jobs.langfuse = app.state.traces.langfuse   # each finished job, as a span of its turn in Langfuse
        aftercare.install(app.state)   # a shot the agent planned is checked once it is made, with its panel open or not
        # The agent's approved plans run here, step by step (plans.py); the ones a restart interrupted go on.
        app.state.plans = PlanRunner(app.state)
        app.state.jobs.finished.append(app.state.plans.job_ended)
        app.state.plans.start()
        workers = [asyncio.create_task(app.state.jobs.run_forever()), asyncio.create_task(app.state.jobs.run_forever(local=True)),
                   asyncio.create_task(health.Watcher(app.state).run_forever()),   # alerts, sent while nobody watches
                   asyncio.create_task(app.state.traces.langfuse.run_forever())]   # the agent's calls, to Langfuse when one is set
        if settings.backup_keep > 0:
            copies = (db, app.state.backup_dir, settings.config_file, settings.backup_keep)
            if settings.backup_database:
                backup.attempt(*copies)   # one at every start, before anything is changed
            workers.append(asyncio.create_task(backup.run_forever(
                *copies, app.state.backup_files if settings.backup_files else None, database=settings.backup_database,
                restore_url=settings.restore_test_url, retention_days=settings.retention_days)))
        if app.state.embedder is not None:   # the vectors of new and changed items, in the background
            workers.append(asyncio.create_task(semantic.run_forever(app.state)))
        if app.state.shared.enabled:   # live messages from the other processes (and this one's own, through Redis)
            workers.append(asyncio.create_task(app.state.shared.listen(hub.deliver)))
        db.serving = True   # from here on, a database call that would block the loop is what db.loop_guard watches
        yield
        db.serving = False
        for worker in workers + list(app.state.plans.tasks.values()):   # a plan goes on after the next start
            worker.cancel()
        await comfy_pool.close()
        await claude.close_all()   # the conversations' live Claude Code programs
        db.close()

    # No /docs, /redoc or /openapi.json: a map of every route is of no use to the studio's users, only to an attacker.
    app = FastAPI(title="Scene.ai", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.db = db
    app.state.tell_plans = app_tell_plans
    app.state.comfy = comfy
    app.state.comfy_pool = comfy_pool
    app.state.catalog = catalog
    app.state.hub = hub
    app.state.credits = credits
    app.state.agent = agent
    app.state.notify = notify
    app.state.live_message = live_message
    app.state.assets_dir = storage / "assets"
    app.state.showcase_dir = storage / "showcase"   # the work an admin picked for the Home page (showcase.py)
    # What several app processes share, when there are several (redis_url): otherwise in this process, as always.
    app.state.shared = hub.shared = db.shared = shared.open_shared(settings.redis_url)
    app.state.throttle = shared.SharedLoginThrottle(app.state.shared) if app.state.shared.enabled else LoginThrottle()
    app.state.limits = shared.SharedRateLimit(app.state.shared) if app.state.shared.enabled else RateLimit()
    # Search by meaning, when it is on and the database has its table (pgvector, migration 0011).
    app.state.embedder = None
    if settings.semantic_search:
        if semantic.available(db):
            app.state.embedder = semantic.Embedder(settings.embedding_provider, settings.embedding_api_key,
                                                   settings.embedding_endpoint, settings.embedding_model)
        else:
            print("semantic_search is on, but the database has no embeddings table (pgvector, migration 0011): it stays off.")
    # Settings an admin changes in another process: the console's roles and the agent's models, read again here.
    app.state.shared.on_changed("settings", lambda: (staff.configure(db), roles.apply(db, agent)))
    app.state.view_codes = {}   # one-time codes to view the studio as a user (api/admin.start_view), by their hash
    app.state.started = time.time()
    app.state.storage_dir = storage
    app.state.output_dir = settings.path("output_dir") if settings.output_dir else storage / "outputs"
    app.state.outputs = Outputs(app.state.output_dir, db)
    # Where the media are kept for good (storage.py): these folders, or Azure Blob Storage with these folders its cache.
    app.state.storage = stores.open_storage(settings, {"outputs": app.state.output_dir, "posters": app.state.output_dir,
                                                         "kit": app.state.assets_dir, "showcase": app.state.showcase_dir})
    app.state.outputs.storage = stores.ACTIVE = app.state.storage
    media.on_removed = app.state.outputs.forget   # a result deleted here is deleted there too
    media.on_made = app.state.outputs.keep        # and a poster made here is kept there
    app.state.versions = versions.Shelf(db, catalog, storage / "workflow_versions")
    agent.recorder = app.state.traces = traces.Recorder(db, storage / "agent_calls")   # every call to its models
    app.state.traces.langfuse = langfuse_trace.Sender(db, credits)
    roles.apply(db, agent)   # the models an admin chose in the console for the agent's roles, over config.json
    with as_everyone():
        versions.look(app.state)   # what arrived while the app was stopped
    app.state.backup_dir = settings.path("backup_dir") if settings.backup_dir else storage / "backups"
    # The files a lost disk would take with it: the finished work and the kit's uploads. Copied into files/ beside the backups.
    app.state.backup_files = {"outputs": app.state.output_dir, "assets": app.state.assets_dir, "showcase": app.state.showcase_dir}
    # Whether the render server answered the last time anyone asked, and since when that has been so.
    app.state.server_seen = {"online": None, "since": time.time()}
    app.state.model_seen = {"online": None, "since": time.time()}   # the same for the agent's model, Claude (health.py)

    def saw_server(online):
        seen = app.state.server_seen
        if seen["online"] is not online:
            seen.update(online=online, since=time.time())
    app.state.saw_server = saw_server

    @app.middleware("http")
    async def no_console_here(request, call_next):
        """The studio does not serve the admin console's page or scripts; the console's own port does."""
        path = posixpath.normpath(request.url.path).lower()   # as the files are found: "//" and ".." resolved, any case
        if path == "/console.html" or CONSOLE_FILES.match(path):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return await call_next(request)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        """Liveness: the process answers (a container's restart rule)."""
        return {"ok": True}

    @app.get("/readyz", include_in_schema=False)
    async def readyz():
        """Readiness: the database and the media storage answer (a load balancer sends requests only then)."""
        found = {}
        for name, check in (("database", lambda: db.one("SELECT 1 AS ok")["ok"] == 1),
                            ("storage", app.state.storage.ready)):
            try:
                found[name] = bool(await db.offload(check))
            except Exception as error:
                found[name] = False
                found[name + "_error"] = type(error).__name__
        return JSONResponse(found, status_code=200 if found["database"] and found["storage"] else 503)

    _answer_errors(app)
    _guard(app)   # after the one above, so its answers get the headers too
    # The admin routes are not here: they are the admin console's, a site of its own (create_console).
    for module in (auth, studio, library, workspace, film_ops, film, runs, kit_api, bulk, mobile, shares, plans_api, client_errors):
        app.include_router(module.router)

    built = settings.path("web_dist_dir").resolve()   # the web app's build (apps/web)

    seen_version = [0, 0.0]   # the version, and when the files were last looked at

    def page_version():
        """The time of the last build. A tab opened before it runs old code: /api/status says this, and the tab offers
        to reload. The build is looked at once every few seconds at most."""
        if time.time() - seen_version[1] > PAGE_LOOK:
            seen_version[:] = [_build_version(built / "studio", "studio.html"), time.time()]
        return seen_version[0]
    app.state.page_version = page_version

    # The studio's pages have addresses of their own (/library, /canvas), all answered by the one page, which routes them.
    # /admin, where the console used to be, sends an admin on to it.
    PAGE_PATHS = ("/", "/index.html", "/signin", "/signup", "/home", "/projects", "/library", "/skills", "/create", "/canvas",
                  "/settings", "/admin", "/project", "/analytics", "/guide",
                  # a project's pages by its id and its module's: /project/PRJ..., /canvas/PRJ.../module/MOD...
                  "/project/{place:path}", "/canvas/{place:path}", "/analytics/{place:path}")
    phone_site.install(app, settings)   # phones get the studio's phone site (/m/), before the studio's pages answer
    _built_pages(app, built / "studio", "studio.html", PAGE_PATHS)
    _built_files(app, built / "studio")
    app.state.console = create_console(app) if settings.console_port else None
    return app


def _answer_errors(app):
    """The errors of the studio's parts, answered with what went wrong instead of as a crash."""
    @app.exception_handler(workflows.WorkflowError)
    @app.exception_handler(media.MediaError)
    @app.exception_handler(motion.MotionError)
    @app.exception_handler(sequence.SequenceError)
    @app.exception_handler(AgentError)
    @app.exception_handler(ComfyError)
    async def known_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(httpx.HTTPError)
    async def comfy_unreachable(request, exc):
        return JSONResponse({"detail": "The render server (ComfyUI) can't be reached right now."}, status_code=502)

    @app.exception_handler(RequestValidationError)
    async def wrong_fields(request, exc):
        """Fields missing or of the wrong kind: FastAPI's list of them, without the "input" it would echo back. That
        echo could not be made of a body that is not text (a file sent where JSON goes failed as a crash), and it sent
        back whatever was sent, however large."""
        return JSONResponse({"detail": [{k: e[k] for k in ("type", "loc", "msg") if k in e} for e in exc.errors()]},
                            status_code=422)

    @app.exception_handler(psycopg.errors.DataError)
    async def wrong_kind_of_value(request, exc):
        """A value the database can't take for its column (a word where an id goes, a number too large): the request's
        fault, said as such, not a crash. What the database said is not repeated: it names tables and columns."""
        return JSONResponse({"detail": "A value in this request is not of the right kind (an id, a number or a text)."},
                            status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        """Anything else that went wrong, as JSON the pages can show, with no trace of the code: the server's log has
        that (the error is raised on after this answer, so it is still logged)."""
        return JSONResponse({"detail": "Something went wrong on the studio's side. Try again; if it keeps happening, "
                                       "tell an admin."}, status_code=500)


def _guard(app):
    """What both sites do with every request: refuse a change from another site's page, and tell the browser what
    the page may do and to check for newer files."""
    # Scripts, styles and answers go compressed (a fifth of their size); pictures, videos, sounds, fonts and other files
    # already are, or would not shrink. A streamed answer (the agent at work) is sent piece by piece as before.
    app.add_middleware(GZipMiddleware, minimum_size=1024,
                       exclude_content_types=(*DEFAULT_EXCLUDED_CONTENT_TYPES, "application/octet-stream"))

    @app.middleware("http")
    async def always_current_pages(request, call_next):
        """Make the browser check for a newer page file every time, so an update shows without clearing its cache.

        Unchanged files are still answered with "not modified", so this costs almost nothing.
        """
        response = await call_next(request)
        if request.url.path.startswith("/_app/") and response.status_code == 200:
            # The build's files (/_app/) have their content's hash in their names, so what one serves never changes:
            # kept a year.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif not request.url.path.startswith(("/api/", "/m/_expo/")):   # the phone site's scripts are named by their content
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.middleware("http")
    async def guarded(request, call_next):
        """Refuse a change sent from another site's page (cross-site request forgery), and send every answer with the
        headers that tell the browser what the page may do."""
        if (request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS")
                and not same_origin(request)):
            return JSONResponse({"detail": "This request came from another site and was refused."}, status_code=403)
        traces.new_run()   # the agent's calls made for this request are one run (traces.py)
        response = await call_next(request)
        host = re.sub(r"[^\w.:\[\]-]", "", request.headers.get("host", ""))[:255]   # nothing that could end the policy early
        headers = response.headers
        # Scripts, styles, pictures, sounds and connections only from this site; nothing may frame the studio.
        # No inline style either: the pages set sizes and colours through the style object (CSSOM), which the policy
        # allows, never in a style attribute or a <style> element (X2).
        headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
            "media-src 'self' blob:; font-src 'self'; connect-src 'self' ws://{0} wss://{0}; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'".format(host))
        headers["X-Content-Type-Options"] = "nosniff"   # a file is only ever read as the type it is served as
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "same-origin"
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        if is_https(request):
            headers["Strict-Transport-Security"] = "max-age=31536000"
        return response


def _build_version(folder, html_file):
    """The build's version: when its page was last written (every build writes it anew)."""
    try:
        return int((folder / html_file).stat().st_mtime)
    except OSError:
        return 0


# What the page says while there is no build to serve.
NOT_BUILT = ("<!doctype html><meta name=viewport content='width=device-width'><body>"
             "This page isn't built yet. On the studio PC, run <code>npm run build -w apps/web</code> in the repository, "
             "then reload.</body>")


def _built_pages(app, folder, html_file, paths):
    """`paths` answered by the build's page `html_file` (apps/web, built into `folder`). Its scripts and styles
    are under /_app/ with their content's hash in their names, so the page itself names the current ones."""
    async def page():
        target = folder / html_file
        if not target.is_file():
            return HTMLResponse(NOT_BUILT, status_code=503)
        return HTMLResponse(target.read_text(encoding="utf-8"))

    for page_path in paths:
        app.get(page_path, include_in_schema=False)(page)
    return page


def _built_files(app, folder):
    """The build's files: its scripts and styles (/_app/), fonts, images and theme.js. Only these: the console's
    one-word section addresses (/users) are its pages, not files."""
    for name in BUILT_FOLDERS:
        app.mount("/" + name, StaticFiles(directory=folder / name, check_dir=False), name="web-" + name)

    @app.get("/theme.js", include_in_schema=False)
    async def theme():
        """Applies the saved theme before the page paints: a classic script, loaded before the styles."""
        target = folder / "theme.js"
        if not target.is_file():
            raise HTTPException(404, "No such file.")
        return FileResponse(target)


BUILT_FOLDERS = ("_app", "fonts", "img")   # the folders of the build (apps/web/public and Vite's output)
PAGE_LOOK = 10   # seconds between looks at the page files for a change (page_version)
LIVE_EVERY = 1.0   # seconds: the most often a user's open pages are sent where their jobs stand (notify)
# The admin console's scripts, should one ever be asked for on the studio's port (its build is in a folder of its own).
CONSOLE_FILES = re.compile(r"^/_app/console[-./]")
SECTION = re.compile(r"^[a-z]{1,30}$")


def create_console(studio):
    """The admin console: a site of its own, on its own port and address (settings console_host and console_port),
    with its own sign-in. It shares the studio's state (the database, the queue, who is online), and the admin routes
    are only here: the studio's port, the one on the internet, has none of them."""
    settings = studio.state.settings
    if settings.console_port == settings.port:
        raise ValueError("The admin console needs a port of its own: console_port is {}, the same as port.".format(settings.port))
    console = FastAPI(title="Scene.ai admin console", docs_url=None, redoc_url=None, openapi_url=None)
    console.state = studio.state   # request.app.state is the studio's, whichever site the request came to
    _answer_errors(console)
    _guard(console)
    for module in (console_api, admin):
        console.include_router(module.router)
    console.include_router(client_errors.admin_router)   # the console's read of what browsers reported
    built = settings.path("web_dist_dir").resolve() / "console"   # a build of its own (apps/web), never in the studio's folder
    page = _built_pages(console, built, "console.html", ("/", "/signin"))
    _built_files(console, built)

    @console.get("/{section}", include_in_schema=False)
    async def section_page(section: str):
        """Each section of the console has an address of its own (/users, /jobs), all answered by the one page."""
        if not SECTION.match(section):
            raise HTTPException(404, "No such page.")
        return await page()

    @console.get("/sessions/{ref}", include_in_schema=False)
    async def session_page(ref: str):
        """A Claude session of the Sessions section, by its id (/sessions/SES...): the same page, opened on it."""
        return await page()
    return console


class Doors:
    """The studio and the admin console, served by one server on two ports: a request goes to the site of the port it
    came in on. Both share one process, so the console sees the live queue and who is online."""

    def __init__(self, studio):
        self.studio = studio
        self.console = studio.state.console
        self.console_port = studio.state.settings.console_port

    async def __call__(self, scope, receive, send):
        port = (scope.get("server") or (None, None))[1]
        if self.console is not None and scope["type"] != "lifespan" and port == self.console_port:
            return await self.console(scope, receive, send)
        return await self.studio(scope, receive, send)   # the start and stop of the app (lifespan) are the studio's
