"""Baseline: the studio's tables as they were on 10 Nov 2026, when migrations took over from the app's own start.

This is a frozen copy of what db.py made when the app started (SCHEMA, COLUMNS, INDEXES and the row rules), in the
words it used then (SQLite's, turned into PostgreSQL's by postgres_types). Never change it: a later change is a migration
of its own.

It is written so that it can run on a database the app made before, at any older shape: every statement only adds
what is missing. scripts/migrate.py stamps a database that already has all of it, so nothing runs there."""

import re

from scene.schema import sql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    workflow TEXT NOT NULL,
    kind TEXT NOT NULL,
    settings TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    error TEXT,
    est_seconds REAL,
    hidden INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    started REAL,
    finished REAL
);
CREATE INDEX IF NOT EXISTS jobs_user ON jobs(user_id, created);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created);
CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id TEXT,
    workflow TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    filename TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    settings TEXT NOT NULL,
    context TEXT NOT NULL,
    seconds REAL,
    size INTEGER,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS generations_user ON generations(user_id, created);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created REAL NOT NULL
);
-- People a project is shared with (sharing.py): its owner is in projects.user_id, its members here, each with a role.
CREATE TABLE IF NOT EXISTS project_members (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    added_by INTEGER,
    created REAL NOT NULL,
    PRIMARY KEY (project_id, user_id)
);
CREATE TABLE IF NOT EXISTS boards (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL,
    data TEXT NOT NULL,
    updated REAL NOT NULL,
    PRIMARY KEY (user_id, project_id, kind)
);
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    tag TEXT NOT NULL DEFAULT 'character',
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_events (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    job_id TEXT,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS uploads (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created REAL NOT NULL,
    PRIMARY KEY (user_id, name)
);
-- Each version of each workflow file and its presets, kept in storage/workflow_versions/<hash>.json.gz (versions.py).
CREATE TABLE IF NOT EXISTS workflow_versions (
    id INTEGER PRIMARY KEY,
    workflow TEXT NOT NULL,
    hash TEXT NOT NULL,
    change TEXT NOT NULL,
    seen REAL NOT NULL
);
-- Each call to the agent's models (traces.py): what it was for, which model, how long, what it cost, what it chose.
CREATE TABLE IF NOT EXISTS agent_calls (
    id INTEGER PRIMARY KEY,
    run TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    purpose TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    asked TEXT NOT NULL DEFAULT '',
    started REAL NOT NULL,
    seconds REAL NOT NULL DEFAULT 0,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    answer_tokens INTEGER NOT NULL DEFAULT 0,
    tool TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    chars INTEGER NOT NULL DEFAULT 0
);
-- The Claude session of an agent tab (sessions.py): one for each tab of a project, kept for good, for admins to watch.
-- ref is its own id (SES...), agent the tab's (AGT...), claude_id the session Claude Code keeps it in.
CREATE TABLE IF NOT EXISTS claude_sessions (
    id INTEGER PRIMARY KEY,
    ref TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL DEFAULT 0,   -- 0: all work, in no project
    run TEXT NOT NULL,
    agent TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    claude_id TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    context_tokens INTEGER NOT NULL DEFAULT 0,
    context_window INTEGER NOT NULL DEFAULT 0,
    messages INTEGER NOT NULL DEFAULT 0,
    compacts INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'idle',
    started REAL NOT NULL,
    active REAL NOT NULL
);
-- What happened in a Claude session, in order: the user's messages, what Claude wrote and thought, the tools it
-- called and what they gave, its answers, compactions, model changes and errors. Kept for good.
CREATE TABLE IF NOT EXISTS claude_events (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    at REAL NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT ''
);
-- Moderation (moderation.py): a verdict on an item ("fine", "removed"), or a prompt refused before it was made.
CREATE TABLE IF NOT EXISTS moderation (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    generation_id INTEGER,
    user_id INTEGER,
    verdict TEXT NOT NULL,
    words TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL DEFAULT '',
    by_name TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
-- What the watcher (health.py) found wrong, from when it was sent until it was gone (`ended` NULL while it lasts).
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL,
    level TEXT NOT NULL,
    text TEXT NOT NULL,
    tab TEXT NOT NULL DEFAULT '',
    started REAL NOT NULL,
    ended REAL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    actor_id INTEGER,
    actor_name TEXT NOT NULL DEFAULT '',
    actor_email TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_pricing (
    workflow TEXT PRIMARY KEY,
    credits_per_second REAL,
    base_credits REAL,
    resolution_multiplier REAL NOT NULL DEFAULT 1,
    quality_multiplier REAL NOT NULL DEFAULT 1,
    preferred_server TEXT NOT NULL DEFAULT '',
    fallback_servers TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS credit_packages (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    price_inr REAL NOT NULL DEFAULT 0,
    credits INTEGER NOT NULL DEFAULT 0,
    bonus_credits INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created REAL NOT NULL
);
-- What the agent remembers of a user across all their projects (recall.py): preferences, what they keep using, lessons.
CREATE TABLE IF NOT EXISTS user_memory (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated REAL NOT NULL,
    PRIMARY KEY (user_id, key)
);
-- Links that open one library item without signing in (api/shares.py), by the hash of their token.
CREATE TABLE IF NOT EXISTS shares (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL,
    created REAL NOT NULL,
    expires REAL NOT NULL,
    views INTEGER NOT NULL DEFAULT 0
);
-- An agent's plan the server carries out after Approve (plans.py): its steps as the agent made them, where each one
-- stands, and the credits reserved for what is not queued yet.
CREATE TABLE IF NOT EXISTS agent_plans (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id INTEGER,
    tab TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    steps TEXT NOT NULL,
    progress TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    reserved_left INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    approved REAL,
    finished REAL
);
CREATE INDEX IF NOT EXISTS agent_plans_user ON agent_plans(user_id, created);
CREATE INDEX IF NOT EXISTS agent_plans_state ON agent_plans(state);
CREATE TABLE IF NOT EXISTS run_state (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    run TEXT NOT NULL,
    path TEXT NOT NULL,
    value TEXT NOT NULL,
    writer TEXT NOT NULL DEFAULT '',
    updated REAL NOT NULL,
    PRIMARY KEY (user_id, run, path)
);
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    cpu TEXT NOT NULL DEFAULT '',
    gpu TEXT NOT NULL DEFAULT '',
    vram_gb REAL,
    role TEXT NOT NULL DEFAULT '',
    renders INTEGER NOT NULL DEFAULT 0,
    idle_power_w REAL,
    generation_power_w REAL,
    max_power_w REAL,
    preferred_workflows TEXT NOT NULL DEFAULT '',
    supported_workflows TEXT NOT NULL DEFAULT '',
    purchase_price_inr REAL,
    purchase_date TEXT NOT NULL DEFAULT '',
    life_months REAL,
    salvage_value_inr REAL,
    productive_hours REAL,
    active INTEGER NOT NULL DEFAULT 1,
    created REAL NOT NULL
);
-- The ComfyUI servers the studio renders on (endpoints.py), set in the console's Servers section.
CREATE TABLE IF NOT EXISTS endpoints (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    models TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created REAL NOT NULL
);
"""

# Columns added after the first release: (table, column, definition). Added to older databases on start.
COLUMNS = [
    ("users", "credits", "INTEGER NOT NULL DEFAULT 0"),
    # The plan and step a job was queued for (plans.py), written in the same INSERT that queues it.
    ("jobs", "plan_id", "INTEGER"),
    ("jobs", "plan_step", "INTEGER"),
    ("users", "disabled", "INTEGER NOT NULL DEFAULT 0"),
    ("jobs", "project_id", "INTEGER"),
    ("jobs", "cost", "INTEGER NOT NULL DEFAULT 0"),
    ("generations", "project_id", "INTEGER"),
    ("credit_events", "note", "TEXT NOT NULL DEFAULT ''"),
    # What a job was asked for and what became of its credits. `cost` stays the price of the job.
    ("jobs", "seconds_requested", "REAL"),
    ("jobs", "credits_required", "INTEGER NOT NULL DEFAULT 0"),
    ("jobs", "credits_reserved", "INTEGER NOT NULL DEFAULT 0"),
    ("jobs", "credits_consumed", "INTEGER NOT NULL DEFAULT 0"),
    ("jobs", "credits_refunded", "INTEGER NOT NULL DEFAULT 0"),
    ("jobs", "server", "TEXT NOT NULL DEFAULT ''"),
    ("jobs", "retries", "INTEGER NOT NULL DEFAULT 0"),
    ("jobs", "output_size", "INTEGER"),
    # Two-step sign-in: the authenticator secret, whether it is on, the last code's time step (a code is used once)
    # and the hashes of the unused recovery codes, as a JSON list.
    ("users", "mfa_secret", "TEXT NOT NULL DEFAULT ''"),
    ("users", "mfa_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "mfa_step", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "mfa_recovery", "TEXT NOT NULL DEFAULT '[]'"),
    # The most credits a user may spend in 24 hours: NULL follows the studio's limit, 0 means no limit for them.
    ("users", "daily_cap", "INTEGER"),
    # A job an admin moved to the front of the queue is taken before older ones: higher first, then oldest first.
    ("jobs", "priority", "INTEGER NOT NULL DEFAULT 0"),
    # NeuralCore of the agent: what a saved asset or a library item shows, written by the agent's model looking at
    # it, and the user's own note on when and how to use a saved asset.
    ("assets", "about", "TEXT NOT NULL DEFAULT ''"),
    ("assets", "use_note", "TEXT NOT NULL DEFAULT ''"),
    ("generations", "about", "TEXT NOT NULL DEFAULT ''"),
    # Shared memory: a reference file dropped into a job is kept as an asset of the project it was used in
    # (origin "upload"), beside the ones saved on purpose (origin "saved", which belong to no one project).
    ("assets", "origin", "TEXT NOT NULL DEFAULT 'saved'"),
    ("assets", "project_id", "INTEGER"),
    # An asset the agent made for reuse (a character, a place, a voice): the library item it was kept from. A retake of
    # the same name replaces it, where an asset the user saved is never replaced.
    ("assets", "made_from", "INTEGER"),
    # Review: the agent's verdict on a library item it looked at after it was made (JSON, see review.py).
    ("generations", "review", "TEXT NOT NULL DEFAULT ''"),
    # The user's thumbs on a result: 1 up, -1 down, 0 not rated. The agent reuses what was liked and avoids the rest.
    ("generations", "rating", "INTEGER NOT NULL DEFAULT 0"),
    # The run (of a long skill such as Pocket Motion) a working file belongs to: its slices, trims and references. The
    # library leaves them out unless that run is asked for; "" for everything else.
    ("generations", "run", "TEXT NOT NULL DEFAULT ''"),
    # The run a job was made for: what a long run has spent is counted from it (runs.spent).
    ("jobs", "run", "TEXT NOT NULL DEFAULT ''"),
    # The kit of a project (kit.py): its assets in order, the ones always attached to its shots (what the cast was),
    # and the ones attached without a name yet, which the agent asks about.
    ("assets", "always", "INTEGER NOT NULL DEFAULT 0"),
    ("assets", "position", "REAL NOT NULL DEFAULT 0"),
    ("assets", "named", "INTEGER NOT NULL DEFAULT 1"),
    # A module: a project inside a project, with a canvas and agent tabs of its own, sharing the kit of the
    # project it is in. NULL for a project.
    ("projects", "parent_id", "INTEGER"),
    # The name of a project's own canvas, the first of its modules; empty = "Main canvas".
    ("projects", "canvas_name", "TEXT NOT NULL DEFAULT ''"),
    # A sign-in to the admin console (1) or to the studio (0). Neither one's cookie opens the other.
    ("sessions", "console", "INTEGER NOT NULL DEFAULT 0"),
    # Where a session was started (the address, the browser) and when it was last used (written every few minutes).
    ("sessions", "ip", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "agent", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "seen", "REAL"),
    # The seal of an audit entry: a hash of it and the entry before it (audit.py). '' for entries from before seals.
    ("audit_log", "seal", "TEXT NOT NULL DEFAULT ''"),
    # A session in which an admin views the studio as this user, read only: the admin's id (api/admin.view_as).
    ("sessions", "view_as", "INTEGER"),
    # The project an agent message was charged in (a job's spend is found through its job): for a project's analytics.
    ("credit_events", "project_id", "INTEGER"),
    # A workflow's own resolution and quality factors over the studio's (credits.Credits.factors), as JSON.
    ("workflow_pricing", "factors", "TEXT NOT NULL DEFAULT ''"),
    # How many times a render was put back in the queue because the render server went away while it ran (jobs.RESUMES).
    ("jobs", "resumes", "INTEGER NOT NULL DEFAULT 0"),
    # A workflow offered to admins alone, to try it before users see it (with `enabled` still 1).
    ("workflow_pricing", "admins_only", "INTEGER NOT NULL DEFAULT 0"),
    # A project's or module's public id, what its links show (refs.py): PRJ... for a project, MOD... for a module.
    ("projects", "ref", "TEXT NOT NULL DEFAULT ''"),
    # What the agent learnt of an item or a NeuralCore entry by looking at it, as JSON (core.py, the asset catalogue):
    # photoreal, has_person, subjects, scene, description, tags and any key of its own.
    ("generations", "facts", "TEXT NOT NULL DEFAULT ''"),
    ("assets", "facts", "TEXT NOT NULL DEFAULT ''"),
    # The id an item or an entry has in a module's memory (core.py, /assets/<id>): twelve random hex digits, given the
    # first time it is listed there, so the memory never shows the database's own numbers.
    ("generations", "public_id", "TEXT NOT NULL DEFAULT ''"),
    ("assets", "public_id", "TEXT NOT NULL DEFAULT ''"),
    # How NeuralCore entries hang together (kit.py): a look of a character or a time of day of a location ("Maya - torn
    # sleeve", "Kitchen - night") is an entry of its own with look_of its base entry and variant its words, from_scene
    # the scene a changed look starts in; a location's palette (shadow and highlight colours); a character's relatives,
    # as JSON [{"to": entry id, "relation": "mother", "blood": true}], "to" being this entry's <relation>.
    ("assets", "look_of", "INTEGER"),
    ("assets", "variant", "TEXT NOT NULL DEFAULT ''"),
    ("assets", "from_scene", "INTEGER"),
    ("assets", "palette", "TEXT NOT NULL DEFAULT ''"),
    ("assets", "relations", "TEXT NOT NULL DEFAULT ''"),
]

# Indexes for what the studio looks up often, made once the columns of later releases are there (some are on those).
INDEXES = """
CREATE INDEX IF NOT EXISTS jobs_plan ON jobs(plan_id, plan_step);
CREATE INDEX IF NOT EXISTS generations_project ON generations(project_id);
CREATE INDEX IF NOT EXISTS assets_project ON assets(user_id, project_id);
CREATE INDEX IF NOT EXISTS jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS jobs_run ON jobs(user_id, run);
CREATE INDEX IF NOT EXISTS credit_events_user ON credit_events(user_id, created);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS project_members_user ON project_members(user_id);
CREATE INDEX IF NOT EXISTS audit_log_action ON audit_log(action, ip, created);
CREATE INDEX IF NOT EXISTS agent_calls_started ON agent_calls(started);
CREATE INDEX IF NOT EXISTS projects_ref ON projects(ref);
CREATE UNIQUE INDEX IF NOT EXISTS claude_sessions_tab ON claude_sessions(user_id, run, project_id);
CREATE INDEX IF NOT EXISTS claude_sessions_active ON claude_sessions(active);
CREATE INDEX IF NOT EXISTS claude_events_session ON claude_events(session_id, id);
CREATE INDEX IF NOT EXISTS agent_calls_run ON agent_calls(run);
CREATE INDEX IF NOT EXISTS moderation_item ON moderation(generation_id);
CREATE INDEX IF NOT EXISTS generations_public ON generations(public_id);
CREATE INDEX IF NOT EXISTS assets_public ON assets(public_id);
DROP TABLE IF EXISTS brands;
DROP TABLE IF EXISTS brand_fonts;
DROP TABLE IF EXISTS brand_assets;
DROP TABLE IF EXISTS kit_overrides;
"""

# Row-level security: each row of these tables belongs to the user in this column (docs/database.md).
OWNED = {"users": "id", "sessions": "user_id", "jobs": "user_id", "generations": "user_id", "projects": "user_id",
         "boards": "user_id", "assets": "user_id", "credit_events": "user_id", "uploads": "user_id", "run_state": "user_id",
         "user_memory": "user_id", "shares": "user_id", "agent_plans": "user_id"}
ACTING_SQL = "current_setting('app.user_id', true)"
OWN_ROWS = ("{acting} = 'all' OR {column} = (CASE WHEN {acting} ~ '^[0-9]+$' THEN {acting}::bigint END)")


def postgres_types(text):
    """SQLite's column types in PostgreSQL's words: a numbered row, 64-bit whole numbers, double-precision decimals."""
    text = re.sub(r"\bid INTEGER PRIMARY KEY\b", "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY", text)
    text = re.sub(r"\bINTEGER\b", "BIGINT", text)
    return re.sub(r"\bREAL\b", "DOUBLE PRECISION", text)


def statements(text):
    return [s.strip() for s in text.split(";") if s.strip() and not all(
        line.strip().startswith("--") or not line.strip() for line in s.splitlines())]


TABLES = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(", SCHEMA)


def upgrade():
    for statement in statements(postgres_types(SCHEMA)):
        sql(statement)
    for table, column, definition in COLUMNS:
        sql("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} {}".format(table, column, postgres_types(definition)))
    for statement in statements(INDEXES):
        sql(statement)
    for table, column in OWNED.items():
        rule = OWN_ROWS.format(acting=ACTING_SQL, column=column)
        sql("ALTER TABLE {} ENABLE ROW LEVEL SECURITY".format(table))
        sql("ALTER TABLE {} FORCE ROW LEVEL SECURITY".format(table))   # for the tables' owner as well
        sql("DROP POLICY IF EXISTS own_rows ON {}".format(table))
        sql("CREATE POLICY own_rows ON {} USING ({}) WITH CHECK ({})".format(table, rule, rule))


def downgrade():
    """Back to no tables at all: every row is lost. scripts/migrate.py refuses it unless asked in so many words."""
    from alembic import context
    if context.get_x_argument(as_dictionary=True).get("drop_everything") != "yes":
        raise SystemExit("Going below the baseline drops every table. Give -x drop_everything=yes if that is meant.")
    for table in reversed(TABLES):
        sql("DROP TABLE IF EXISTS {} CASCADE".format(table))


def gaps(conn):
    """What a database made before migrations lacks of this baseline (psycopg connection): tables, columns, indexes,
    row rules. Empty when it has all of it."""
    found = {(t, c) for t, c in conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'").fetchall()}
    tables = {t for t, _ in found}
    missing = ["table " + t for t in TABLES if t not in tables]
    for table, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", SCHEMA, re.S):
        if table in tables:
            for line in body.splitlines():
                name = re.match(r"\s*(\w+)\s+(INTEGER|TEXT|REAL)\b", line)
                if name and (table, name.group(1)) not in found:
                    missing.append("column {}.{}".format(table, name.group(1)))
    missing += ["column {}.{}".format(t, c) for t, c, _ in COLUMNS if t in tables and (t, c) not in found]
    indexes = {r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'").fetchall()}
    missing += ["index " + i for i in re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)", SCHEMA + INDEXES)
                if i not in indexes]
    policies = {r[0] for r in conn.execute("SELECT tablename FROM pg_policies WHERE policyname = 'own_rows'").fetchall()}
    missing += ["row rule on " + t for t in OWNED if t not in policies]
    return missing
