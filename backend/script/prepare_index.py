"""Compute movie embeddings offline. Reruns reuse completed plot vectors."""
import argparse
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bm25_search import DEFAULT_CONFIG, build_index
from rankers import EmbeddingStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = args.config.resolve()
    document = tomllib.loads(config.read_text(encoding="utf-8"))
    index = build_index((config.parent / document["bm25"]["corpus_path"]).resolve(), document["bm25"])
    store = EmbeddingStore(document["dense"], config.parent)
    def progress(done, total):
        print(f"Embeddings: {done:,}/{total:,} ({done / total:.1%})", flush=True)
    store.prepare(index.movies, progress)
    print(f"Saved embeddings: {store.path}\nRestart the API or click Prepare dense index to reload.")


if __name__ == "__main__":
    main()
