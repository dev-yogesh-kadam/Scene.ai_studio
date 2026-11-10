"""Every row of every table of a database, as values that mean the same before and after a type change (a time as
seconds to the microsecond, JSON in one canonical form whether it is TEXT or JSONB, "no project" 0 or NULL as NULL),
hashed by primary key. Compares two fingerprints and lists the rows that differ. Read only.

    python scripts/fingerprint.py --url <database> --out before.json
    python scripts/fingerprint.py --url <database> --out after.json --compare before.json
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path

NO_PROJECT = {("boards", "project_id"), ("claude_sessions", "project_id")}
JSON_TEXT = {("jobs", "settings"), ("generations", "settings"), ("generations", "context"), ("generations", "review"),
             ("generations", "facts"), ("assets", "facts"), ("assets", "relations"),
             ("boards", "data"), ("workflow_pricing", "factors"), ("agent_plans", "steps"), ("agent_plans", "progress"),
             ("users", "mfa_recovery"), ("run_state", "value")}


def canonical(table, column, value, jsonb=False):
    if isinstance(value, datetime.datetime):
        return round(value.timestamp(), 6)
    if isinstance(value, float):
        return round(value, 6)
    if (table, column) in NO_PROJECT and value in (0, None):
        return None
    if (table, column) in JSON_TEXT:
        if value in ("", None):
            return None
        return json.dumps(value if jsonb else json.loads(value), sort_keys=True)   # JSONB comes parsed, TEXT does not
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def fingerprint(url):
    import psycopg
    found = {}
    with psycopg.connect(url) as conn:
        conn.execute("SELECT set_config('app.user_id', 'all', false)")
        tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                                             "AND tablename <> 'alembic_version' ORDER BY 1")]
        for table in tables:
            key = conn.execute("SELECT string_agg(a.attname, ',' ORDER BY a.attname) FROM pg_index i JOIN pg_attribute a "
                               "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                               "WHERE i.indrelid = %s::regclass AND i.indisprimary", (table,)).fetchone()[0] or ""
            if table == "boards":   # its key became a number of its own (0006): rows are known by their place
                key = "kind,project_id,user_id"
            cursor = conn.execute("SELECT * FROM {}".format(table))
            names = [d.name for d in cursor.description]
            jsonb = {d.name for d in cursor.description if d.type_code == 3802}
            names = [n for n in names if n != "search"]   # generated from the row (0009): nothing of its own
            rows = {}
            for row in cursor.fetchall():
                values = dict(zip(names, row))
                ident = json.dumps([canonical(table, k, values[k]) for k in key.split(",") if k], default=str)
                shown = {k: canonical(table, k, v, k in jsonb) for k, v in values.items() if not (table == "boards" and k == "id")}
                rows[ident] = {"hash": hashlib.sha256(json.dumps(shown, sort_keys=True, default=str).encode()).hexdigest(),
                               "values": {k: str(v)[:80] for k, v in shown.items()}}
            found[table] = {"count": len(rows), "rows": rows}
    return found


def _same_but_microseconds(a, b):
    """Two rows whose only differences are times a microsecond apart: a time kept as seconds (REAL) and as timestamptz
    round their last microsecond each their own way."""
    for column in set(a) | set(b):
        x, y = a.get(column), b.get(column)
        if x == y:
            continue
        try:
            if abs(float(x) - float(y)) <= 2e-6:
                continue
        except (TypeError, ValueError):
            pass
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--compare")
    args = parser.parse_args()
    found = fingerprint(args.url)
    Path(args.out).write_text(json.dumps(found), encoding="utf-8")
    print("{} tables, {} rows".format(len(found), sum(t["count"] for t in found.values())))
    if not args.compare:
        return
    before = json.loads(Path(args.compare).read_text(encoding="utf-8"))
    same = True
    for table in sorted(set(before) | set(found)):
        a, b = before.get(table), found.get(table)
        if a is None or b is None:
            print("{}: only {}".format(table, "after" if a is None else "before"))
            same = False
            continue
        changed = [k for k in a["rows"] if k in b["rows"] and a["rows"][k]["hash"] != b["rows"][k]["hash"]
                   and not _same_but_microseconds(a["rows"][k]["values"], b["rows"][k]["values"])]
        gone = [k for k in a["rows"] if k not in b["rows"]]
        new = [k for k in b["rows"] if k not in a["rows"]]
        if changed or gone or new or a["count"] != b["count"]:
            same = False
            print("{}: {} -> {} rows, {} changed, {} gone, {} new".format(table, a["count"], b["count"], len(changed), len(gone), len(new)))
            for k in changed[:3]:
                diff = {c: (a["rows"][k]["values"].get(c), b["rows"][k]["values"].get(c))
                        for c in set(a["rows"][k]["values"]) | set(b["rows"][k]["values"])
                        if a["rows"][k]["values"].get(c) != b["rows"][k]["values"].get(c)}
                print("    row {}: {}".format(k, diff))
    print("every row the same" if same else "(differences above)")


if __name__ == "__main__":
    main()
