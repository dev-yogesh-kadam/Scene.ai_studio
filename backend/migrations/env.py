"""Alembic's entry point for the studio's migrations (run them with scripts/migrate.py, see docs/database.md).

The migrations are raw SQL run through SQLAlchemy Core's connection: the app itself uses psycopg and no ORM. They run
as the account that owns the tables, in one transaction (PostgreSQL's changes of tables can be rolled back), with
row-level security opened to every row (app.user_id = 'all'), so a migration that changes data sees all of it."""

from alembic import context
from sqlalchemy import create_engine, pool, text

from scene.schema import grant_app, sqlalchemy_url

config = context.config


def run():
    url = config.attributes.get("url") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise SystemExit("No database to migrate: give scripts/migrate.py --url, or set database_owner_url.")
    engine = create_engine(sqlalchemy_url(url), poolclass=pool.NullPool)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.user_id', 'all', false)"))   # every user's rows (row-level security)
        conn.execute(text("SET lock_timeout = '15s'"))   # a table the app holds is waited for this long, then it stops
        conn.commit()
        context.configure(connection=conn, transaction_per_migration=False)
        with context.begin_transaction():
            context.run_migrations()
        app_role = config.attributes.get("app_role") or context.get_x_argument(as_dictionary=True).get("app_role", "")
        if app_role:   # the app's own account may use the rows of every table, new ones included, never change them
            grant_app(lambda statement: conn.execute(text(statement)), app_role)
            conn.commit()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("The migrations run against a database (no --sql mode).")
run()
