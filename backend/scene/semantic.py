"""Search by meaning (optional, off by default: `semantic_search`; needs pgvector and migration 0011's table).

Each library item and NeuralCore entry gets a vector of what it is about: its name, its summary and prompt, the
agent's description of it (`about`) and what it learnt by looking (`facts`). A background task makes the missing ones
and the ones whose words changed (`fill`, a few each minute); scripts/backfill_embeddings.py makes them all at once.
GET /api/library?q=...&meaning=1 then orders the user's items by how close they are to the words asked.

The vectors come from an embedding API (`embedding_provider`): "voyage" (Voyage AI, the embeddings Anthropic points
to; voyage-3.5, 1024 dimensions, `embedding_api_key`), "azure_openai" (an Azure OpenAI deployment of text-embedding-3,
asked for 1024 dimensions: `embedding_endpoint` https://<name>.openai.azure.com, `embedding_model` the deployment,
`embedding_api_key`), or "fake" (words hashed into a vector: tests only). Sync: offload it from async code."""

import hashlib
import json
import math
import re

import httpx

DIMENSIONS = 1024
BATCH = 32   # items embedded in one call


class SemanticError(RuntimeError):
    pass


class Embedder:
    def __init__(self, provider, api_key="", endpoint="", model=""):
        self.provider, self.api_key, self.endpoint = provider, api_key, endpoint.rstrip("/")
        self.model = model or {"voyage": "voyage-3.5", "azure_openai": "text-embedding-3-small", "fake": "fake"}.get(provider, "")
        if provider not in ("voyage", "azure_openai", "fake"):
            raise SemanticError("embedding_provider is {!r}: voyage, azure_openai or fake.".format(provider))

    def embed(self, texts, query=False):
        """A vector of DIMENSIONS for each text (a document, or with `query` the words a user searches with)."""
        if self.provider == "fake":
            return [_hashed(t) for t in texts]
        try:
            answer = self._ask(texts, query)
        except httpx.HTTPError as error:   # the service unreachable or slow: said as the search's own error
            raise SemanticError("The embedding API could not be reached ({}).".format(type(error).__name__))
        if answer.status_code != 200:
            raise SemanticError("The embedding API said {}: {}".format(answer.status_code, answer.text[:300]))
        try:
            return [row["embedding"] for row in sorted(answer.json()["data"], key=lambda r: r["index"])]
        except (ValueError, KeyError, TypeError):
            raise SemanticError("The embedding API gave back something that is not a list of vectors.")

    def _ask(self, texts, query):
        if self.provider == "voyage":
            return httpx.post("https://api.voyageai.com/v1/embeddings", timeout=60,
                              headers={"Authorization": "Bearer " + self.api_key},
                              json={"model": self.model, "input": texts, "input_type": "query" if query else "document",
                                    "output_dimension": DIMENSIONS})
        return httpx.post("{}/openai/deployments/{}/embeddings?api-version=2024-10-21".format(self.endpoint, self.model),
                          timeout=60, headers={"api-key": self.api_key}, json={"input": texts, "dimensions": DIMENSIONS})


def _hashed(text):
    """The fake's vector: each word (and its first four letters) in a few hashed places, normalised. Texts sharing
    words come out close, which is all the tests need."""
    vector = [0.0] * DIMENSIONS
    for word in re.findall(r"\w+", text.lower()):
        for piece in (word, word[:4]):
            digest = hashlib.md5(piece.encode()).digest()
            for k in range(3):
                vector[int.from_bytes(digest[k * 4:k * 4 + 4], "little") % DIMENSIONS] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def available(db):
    """Whether the embeddings table is there (migration 0011 makes it only where pgvector is)."""
    return bool(db.one("SELECT to_regclass('public.embeddings') IS NOT NULL AS there")["there"])


def item_text(row):
    settings = _json(row.get("settings"))
    facts = _json(row.get("facts"))
    return _joined(row.get("name"), row.get("summary"), settings.get("prompt") if isinstance(settings, dict) else "",
                   row.get("about"), facts.get("description") if isinstance(facts, dict) else "",
                   " ".join(facts.get("tags") or []) if isinstance(facts, dict) else "")


def entry_text(row):
    facts = _json(row.get("facts"))
    return _joined(row.get("name"), row.get("tag"), row.get("variant"), row.get("about"), row.get("use_note"),
                   facts.get("description") if isinstance(facts, dict) else "")


def _json(text):
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {}


def _joined(*parts):
    return " · ".join(str(p).strip() for p in parts if p and str(p).strip())[:4000]


def _vector(values):
    return "[" + ",".join("{:.6f}".format(v) for v in values) + "]"


def fill(db, embedder, most=BATCH):
    """Embed up to `most` items and entries that have no vector of this model, or whose words changed. Returns how many."""
    todo = []
    for row in db.all(
            "SELECT g.id, g.user_id, g.name, g.summary, g.settings, g.about, g.facts, e.digest FROM generations g "
            "LEFT JOIN embeddings e ON e.generation_id = g.id AND e.model = ? WHERE g.run = '' ORDER BY g.id DESC",
            (embedder.model,)):
        text = item_text(row)
        digest = hashlib.md5(text.encode()).hexdigest()
        if text and row["digest"] != digest:
            todo.append(("generation_id", row["id"], row["user_id"], text, digest))
        if len(todo) >= most:
            break
    if len(todo) < most:
        for row in db.all(
                "SELECT a.id, a.user_id, a.name, a.tag, a.variant, a.about, a.use_note, a.facts, e.digest FROM assets a "
                "LEFT JOIN embeddings e ON e.asset_id = a.id AND e.model = ? ORDER BY a.id DESC", (embedder.model,)):
            text = entry_text(row)
            digest = hashlib.md5(text.encode()).hexdigest()
            if text and row["digest"] != digest:
                todo.append(("asset_id", row["id"], row["user_id"], text, digest))
            if len(todo) >= most:
                break
    if not todo:
        return 0
    vectors = embedder.embed([t[3] for t in todo])
    for (column, key, user_id, _, digest), vector in zip(todo, vectors):
        db.run("INSERT INTO embeddings ({c}, user_id, model, digest, embedding) VALUES (?, ?, ?, ?, CAST(? AS vector)) "
               "ON CONFLICT ({c}) DO UPDATE SET model = excluded.model, digest = excluded.digest, "
               "embedding = excluded.embedding, created = now()".format(c=column),
               (key, user_id, embedder.model, digest, _vector(vector)))
    return len(todo)


def nearest(db, embedder, words, where, params, most=60):
    """The ids of the items `where` (SQL on generations g) closest in meaning to `words`, closest first."""
    query = _vector(embedder.embed([words], query=True)[0])
    return [r["id"] for r in db.all(
        "SELECT g.id FROM generations g JOIN embeddings e ON e.generation_id = g.id WHERE " + where +
        " ORDER BY e.embedding <=> CAST(? AS vector) LIMIT ?", (*params, query, most))]


async def run_forever(state, every=60):
    """Make the missing vectors, a batch each `every` seconds, for as long as the app runs (main.py starts it)."""
    import asyncio
    from .db import as_everyone, offload
    while True:
        try:
            with as_everyone():
                while await offload(fill, state.db, state.embedder):
                    await asyncio.sleep(1)
        except Exception as error:   # the API down, a key wrong: said, and tried again later
            print("Semantic search: vectors not made ({}).".format(error))
        await asyncio.sleep(every)

