"""Where the app's values meet PostgreSQL's types (db.py uses it for every statement and every connection).

The app thinks in seconds since 1970 and in JSON text, as it did when every column was REAL or TEXT. Since migrations
0004 and 0005 the times are timestamptz and the JSON is JSONB. The conversion happens here, at the edge, so no other
code changes:

- reading: a timestamptz comes back as seconds (a float) and a JSONB value as its JSON text (`configure`), and an
  empty JSONB column (NULL, which was '') as '' (`json_columns`, used by db.py);
- writing and comparing: a `?` that goes into a time column (an INSERT's value, `SET created = ?`, `created < ?`,
  `BETWEEN ? AND ?`) is given to PostgreSQL as `to_timestamp(?)`, and one that goes into a JSONB column as
  `NULLIF(?, '')::jsonb`, so '' still means "nothing" (`with_times`). Which columns are which is read from the database
  itself (`Shape`), so the same code runs before and after those migrations.

SQL that does arithmetic with a time (`finished - started`) says so itself, with extract(epoch FROM ...)."""

import functools
import re

JSONB_OID = 3802
KEYWORDS = {"where", "set", "on", "left", "right", "inner", "outer", "join", "order", "group", "values", "using", "limit",
            "union", "returning", "having", "and", "or", "as", "select", "natural", "cross", "full", "lateral", "default"}
OPS = r"(?:=|<>|!=|<=|>=|<|>)"
COLUMN = r"(?:(\w+)\.)?([a-z_]\w*)"
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


TIME, JSON = "time", "json"   # the kinds of column whose values are converted (any other: "")
WRAP = {TIME: "to_timestamp(?)", JSON: "NULLIF(?, '')::jsonb"}


class Ambiguous(ValueError):
    """A column of a statement that is a time (or JSON) in one of its tables and not in another: qualify it."""


class Shape:
    """Which columns of which tables are times (timestamptz) or JSON (jsonb), read from the database once it is open."""

    def __init__(self, columns=None):
        self.columns = columns or {}   # table -> {column: TIME, JSON or ""}
        self.translate = functools.lru_cache(maxsize=4096)(self._translate)

    @classmethod
    def read(cls, conn):
        found = {}
        for row in conn.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public'").fetchall():
            table, column, kind = row.values() if isinstance(row, dict) else row   # the pool's rows are dicts
            found.setdefault(table, {})[column] = {"timestamp with time zone": TIME, "jsonb": JSON}.get(kind, "")
        return cls(found)

    def converts(self):
        return any(any(t.values()) for t in self.columns.values())

    def _translate(self, sql):
        return with_times(sql, self.columns) if self.converts() else sql


def _masked(sql):
    """The statement with the inside of each quoted string blanked out (same length), so nothing in a string matches."""
    return re.sub(r"'(?:[^']|'')*'|\"[^\"]*\"", lambda m: m.group(0)[0] + " " * (len(m.group(0)) - 2) + m.group(0)[-1], sql)


def _tables(masked):
    """{name or alias: table} of the tables a statement reads or writes."""
    found = {}
    for table, alias in re.findall(r"\b(?:from|join|update|into)\s+(\w+)(?:\s+(?:as\s+)?(\w+))?", masked, re.I):
        found[table] = table
        if alias and alias.lower() not in KEYWORDS:
            found[alias] = table
    return found


def _kind(columns, tables, alias, column):
    """TIME, JSON or "" for a column of the statement: by its table's alias, or the one kind its tables give it."""
    if alias:
        return columns.get(tables.get(alias, alias), {}).get(column, "")
    kinds = {columns[t][column] for t in set(tables.values()) if column in columns.get(t, {})}
    if len(kinds) > 1:
        raise Ambiguous("{} is a {} in one table of this statement and not in another: name its table".format(
            column, " or ".join(sorted(k for k in kinds if k))))
    return kinds.pop() if kinds else ""


def _split(text):
    """Top-level comma-separated parts of a parenthesised list, with their offsets."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append((start, text[start:i]))
            start = i + 1
    parts.append((start, text[start:]))
    return parts


def _closing(text, opening):
    depth = 0
    for i in range(opening, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i
    return len(text) - 1


def with_times(sql, columns):
    """`sql` with each ? that goes into a time column written to_timestamp(?), and each that goes into a JSON column
    NULLIF(?, '')::jsonb. Raises Ambiguous when a bare column name is a time (or JSON) in one of the statement's tables
    and not in another."""
    masked = _masked(sql)
    tables = _tables(masked)
    wraps = {}   # offset of a ? to wrap -> its column's kind
    literals = {}   # offset of a number written for a time column -> the number

    insert = re.match(r"\s*insert\s+into\s+(\w+)\s*\(", masked, re.I)
    if insert:
        table, open_cols = insert.group(1), insert.end() - 1
        close_cols = _closing(masked, open_cols)
        names = [n.strip() for _, n in _split(masked[open_cols + 1:close_cols])]
        for values in re.finditer(r"\bvalues\s*\(|\),\s*\(", masked[close_cols:], re.I):
            opening = close_cols + values.end() - 1
            closing = _closing(masked, opening)
            for (offset, part), name in zip(_split(masked[opening + 1:closing]), names):
                kind = columns.get(table, {}).get(name)
                if part.strip() == "?" and kind:
                    wraps[opening + 1 + offset + part.index("?")] = kind
                elif kind == TIME and NUMBER.fullmatch(part.strip()):   # a time written as seconds: 0, 1762700000.5
                    literals[opening + 1 + offset + part.index(part.strip())] = part.strip()

    for m in re.finditer(r"\b" + COLUMN + r"\s*" + OPS + r"\s*\?", masked, re.I):
        alias, column = m.group(1), m.group(2)
        kind = column.lower() not in KEYWORDS and _kind(columns, tables, alias, column)
        if kind:
            wraps[m.end() - 1] = kind
    for m in re.finditer(r"\b" + COLUMN + r"\s*" + OPS + r"\s*(-?\d+(?:\.\d+)?)\b(?!\s*[-+*/])", masked, re.I):
        if m.group(2).lower() not in KEYWORDS and _kind(columns, tables, m.group(1), m.group(2)) == TIME:
            literals[m.start(3)] = m.group(3)   # a time written as seconds: finished = 1
    for m in re.finditer(r"\?\s*" + OPS + r"\s*" + COLUMN + r"\b", masked, re.I):
        kind = _kind(columns, tables, m.group(1), m.group(2))
        if kind:
            wraps[m.start()] = kind
    for m in re.finditer(r"\b" + COLUMN + r"\s+between\s+(\?)\s+and\s+(\?)", masked, re.I):
        if _kind(columns, tables, m.group(1), m.group(2)) == TIME:
            wraps.update({m.start(3): TIME, m.start(4): TIME})
    for m in re.finditer(r"\bcoalesce\(\s*" + COLUMN + r"\s*,\s*(\?)\s*\)", masked, re.I):
        if _kind(columns, tables, m.group(1), m.group(2)) == TIME:
            wraps[m.start(3)] = TIME

    edits = [(at, 1, WRAP[kind]) for at, kind in wraps.items()] +             [(at, len(number), "to_timestamp({})".format(number)) for at, number in literals.items()]
    for at, length, text in sorted(edits, reverse=True):
        sql = sql[:at] + text + sql[at + length:]
    return sql


def configure(conn):
    """What every connection of the pool does once: timestamptz read as seconds, JSONB as its text."""
    from psycopg.types.datetime import TimestamptzLoader
    from psycopg.types.string import TextLoader

    class SecondsLoader(TimestamptzLoader):
        def load(self, data):
            return super().load(data).timestamp()

    conn.adapters.register_loader("timestamptz", SecondsLoader)
    conn.adapters.register_loader("jsonb", TextLoader)
    # The library's search (api/library.search_sql): a name is near what was typed from this likeness on (0 to 1; pg_trgm's
    # own is 0.6). Two letters swapped in a word score about 0.56; a word that only shares a letter or two, 0.25.
    conn.execute("SET pg_trgm.word_similarity_threshold = 0.5")


TSVECTOR_OID = 3614


def hidden_columns(description):
    """The columns of a result the app is never given: a full-text search column (generations.search, 0009)."""
    return {d.name for d in description or () if d.type_code == TSVECTOR_OID}


def json_columns(description):
    """The positions of a result's JSONB columns, whose NULL the app reads as ''."""
    return {d.name for d in description or () if d.type_code == JSONB_OID}
