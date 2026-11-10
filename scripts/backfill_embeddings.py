"""Make the search-by-meaning vectors of every library item and NeuralCore entry that has none, or whose words changed
(scene/semantic.py). The app makes them in the background for new items; this does the old ones at once.

    python scripts/backfill_embeddings.py [--dry-run]

It needs `semantic_search`'s settings (embedding_provider and its key) and the embeddings table (pgvector, migration
0011). Runs as the app's account (database_url), for every user's rows. Safe to stop and run again.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from scene import semantic  # noqa: E402
from scene.config import load_settings  # noqa: E402
from scene.db import Database, as_everyone  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="only count what has no vector yet")
    args = parser.parse_args()
    settings = load_settings()
    db = Database(settings.database_url, seed=False, loop_guard="off", time_zone=settings.time_zone)
    if not semantic.available(db):
        raise SystemExit("The database has no embeddings table: install pgvector, CREATE EXTENSION vector, then "
                         "migrate.py downgrade 0010 and upgrade (docs/azure.md).")
    embedder = semantic.Embedder(settings.embedding_provider, settings.embedding_api_key, settings.embedding_endpoint,
                                 settings.embedding_model)
    with as_everyone():
        if args.dry_run:
            have = db.one("SELECT COUNT(*) AS n FROM embeddings WHERE model = ?", (embedder.model,))["n"]
            items = db.one("SELECT (SELECT COUNT(*) FROM generations WHERE run = '') + (SELECT COUNT(*) FROM assets) AS n")["n"]
            print("{} items and entries, {} with a vector of {}".format(items, have, embedder.model))
            return
        total = 0
        while True:
            made = semantic.fill(db, embedder)
            total += made
            if not made:
                break
            print("made {} vectors ({} so far)".format(made, total))
    print("Done: {} vectors made.".format(total))
    db.close()


if __name__ == "__main__":
    main()
