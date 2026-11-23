"""Prepare the local Chroma collection. Reruns reuse completed plot vectors."""

import argparse
import sqlite3
import sys
import tomllib
from contextlib import closing, nullcontext
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrieval.bm25 import DEFAULT_CONFIG, build_index
from retrieval.embeddings import EmbeddingStore


def legacy_vectors(connection, record_ids):
    keys = [record_id.rsplit(":", 1)[1] for record_id in record_ids]
    placeholders = ",".join("?" for _ in keys)
    rows = connection.execute(
        f"SELECT key, vector FROM embeddings WHERE key IN ({placeholders})", keys
    )
    found = {
        key: np.frombuffer(blob, dtype=np.float32)
        for key, blob in rows
        if len(blob) == 384 * 4
    }
    return {
        record_id: found[key]
        for record_id, key in zip(record_ids, keys, strict=True)
        if key in found and np.isfinite(found[key]).all()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--import-sqlite",
        type=Path,
        metavar="PATH",
        help="Reuse compatible vectors from the previous SQLite cache (read-only).",
    )
    args = parser.parse_args()
    config = args.config.resolve()
    document = tomllib.loads(config.read_text(encoding="utf-8"))
    index = build_index(
        (config.parent / document["bm25"]["corpus_path"]).resolve(), document["bm25"]
    )
    store = EmbeddingStore(document["dense"], config.parent)

    def progress(done, total):
        print(f"Embeddings: {done:,}/{total:,} ({done / total:.1%})", flush=True)

    legacy = (
        closing(
            sqlite3.connect(
                args.import_sqlite.resolve().as_uri() + "?mode=ro", uri=True
            )
        )
        if args.import_sqlite
        else nullcontext(None)
    )
    with legacy as connection:
        read_cached = (
            (lambda ids: legacy_vectors(connection, ids))
            if connection is not None
            else None
        )
        store.prepare(index.movies, progress, read_cached=read_cached)
    print(
        f"ChromaDB collection {store.collection_name}: {store.path}\nRestart the API to load it."
    )


if __name__ == "__main__":
    main()
