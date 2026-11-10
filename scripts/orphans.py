"""Rows that point at a row that is not there: for each reference migration 0007 makes a foreign key, how many rows
of a database have a value with nothing behind it. Read only.

    python scripts/orphans.py --url postgresql://<account>:<pw>@localhost:5432/scene_upgrade
"""

import argparse

# (table, column, referenced table, what the migration does with an orphan)
REFERENCES = [
    ("jobs", "project_id", "projects", "set NULL"),
    ("jobs", "plan_id", "agent_plans", "set NULL"),
    ("generations", "project_id", "projects", "set NULL"),
    ("generations", "job_id", "jobs", "set NULL"),
    ("projects", "parent_id", "projects", "delete the module (its project is gone)"),
    ("project_members", "added_by", "users", "set NULL"),
    ("boards", "project_id", "projects", "delete the board (its project is gone)"),
    ("assets", "project_id", "projects", "set NULL"),
    ("assets", "made_from", "generations", "set NULL"),
    ("assets", "look_of", "assets", "set NULL"),
    ("credit_events", "project_id", "projects", "set NULL"),
    ("credit_events", "job_id", "jobs", "set NULL"),
    ("agent_calls", "user_id", "users", "set NULL"),
    ("claude_sessions", "user_id", "users", "delete the session and its events"),
    ("claude_sessions", "project_id", "projects", "set NULL"),
    ("claude_events", "session_id", "claude_sessions", "delete the event"),
    ("moderation", "generation_id", "generations", "set NULL"),
    ("moderation", "user_id", "users", "set NULL"),
    ("shares", "item_id", "generations", "delete the link"),
    ("agent_plans", "project_id", "projects", "set NULL"),
    ("sessions", "view_as", "users", "delete the session"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    import psycopg
    with psycopg.connect(args.url) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        for table, column, target, fix in REFERENCES:
            orphans = conn.execute(
                "SELECT count(*), array_agg(DISTINCT {c}) FROM {t} x WHERE {c} IS NOT NULL AND {c}::text <> '0' "
                "AND NOT EXISTS (SELECT 1 FROM {r} y WHERE y.id = x.{c})".format(t=table, c=column, r=target)).fetchone()
            zeros = conn.execute("SELECT count(*) FROM {t} WHERE {c}::text = '0'".format(t=table, c=column)).fetchone()[0]
            print("{:34} {:5} orphans{}{}{}".format(
                "{}.{} -> {}".format(table, column, target), orphans[0],
                " ({})".format(", ".join(str(v) for v in (orphans[1] or [])[:8])) if orphans[0] else "",
                ", {} zeros (no project: NULL, migration 0006)".format(zeros) if zeros else "",
                "  => " + fix if orphans[0] else ""))


if __name__ == "__main__":
    main()
