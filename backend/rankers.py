"""Rankers share search(query, top_k) -> list[Hit], with stable corpus-order ties."""

from dataclasses import dataclass
from contextlib import closing
from collections import Counter
from hashlib import sha256
import html
import json
import sqlite3
from typing import Protocol

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from relaxation import relaxation_details


@dataclass(frozen=True)
class Hit:
    position: int
    score: float


class Ranker(Protocol):
    def search(self, query: str, top_k: int) -> list[Hit]: ...


def best(scores, top_k, positive_only=False):
    order = np.argsort(-scores, kind="stable")
    if positive_only:
        order = order[scores[order] > 0]
    return [Hit(int(i), float(scores[i])) for i in order[:top_k]]


class BM25Ranker:
    def __init__(self, index):
        self.index = index

    def search(self, query, top_k):
        _, scores, positions = self.index.search(query, top_k)
        return [Hit(i, float(scores[i])) for i in positions]


class TfidfRanker:
    def __init__(self, index):
        # Use exactly the BM25 plot tokens, without another preprocessing pass.
        self.vectorizer = DictVectorizer(dtype=np.float32)
        self.transformer = TfidfTransformer()
        counts = self.vectorizer.fit_transform(index.bm25.doc_freqs)
        self.matrix = self.transformer.fit_transform(counts)
        self.tokenizer = index.tokenizer

    def search(self, query, top_k):
        counts = self.vectorizer.transform([Counter(self.tokenizer(query))])
        vector = self.transformer.transform(counts)
        # Both operands are L2-normalized, so their dot product is cosine.
        scores = (self.matrix @ vector.T).toarray().ravel()
        return best(scores, top_k, positive_only=True)


def dense_text(movie):
    return " ".join(html.unescape(movie.plot).split())


class EmbeddingStore:
    """Resumable per-plot cache. Never reuse a vector for changed text or model."""
    def __init__(self, config, root):
        self.config = config
        self.path = (root / config["cache_path"]).resolve()
        self.model_cache = (root / config["model_cache_path"]).resolve()
        # Increment recipe when preprocessing or the inference backend changes.
        self.recipe = {"model": config["model"], "revision": config["model_revision"],
                       "repository": config["model_repository"], "recipe": "fastembed-minilm-first256-v1"}

    def key(self, movie):
        return sha256((json.dumps(self.recipe, sort_keys=True) + "\n" +
                       dense_text(movie)).encode()).hexdigest()

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE IF NOT EXISTS embeddings "
                           "(key TEXT PRIMARY KEY, vector BLOB NOT NULL)")
        return connection

    def load(self, movies):
        vectors, missing = [], 0
        with closing(self.connect()) as connection:
            for movie in movies:
                row = connection.execute("SELECT vector FROM embeddings WHERE key=?",
                                         (self.key(movie),)).fetchone()
                vector = np.frombuffer(row[0], dtype=np.float32) if row and len(row[0]) == 384 * 4 else None
                if vector is None or vector.shape != (384,) or not np.isfinite(vector).all():
                    missing += 1
                vectors.append(vector)
        return (np.stack(vectors) if not missing else None), missing

    def encoder(self, local_only=True):
        from fastembed import TextEmbedding
        from huggingface_hub import snapshot_download
        model_path = snapshot_download(self.config["model_repository"],
                                       revision=self.config["model_revision"],
                                       cache_dir=str(self.model_cache), local_files_only=local_only,
                                       allow_patterns=["*.json", "*.onnx"])
        return TextEmbedding(model_name=self.config["model"], cache_dir=str(self.model_cache),
                             threads=self.config.get("threads", 4), local_files_only=local_only,
                             specific_model_path=model_path)

    def prepare(self, movies, on_progress=None):
        """Run explicitly before search, committing each batch to survive interruption."""
        try:
            model = self.encoder()
        except Exception:
            # ONNX/Hugging Face also raise provider-specific exception classes.
            model = self.encoder(local_only=False)
        size = self.config.get("batch_size", 32)
        with closing(self.connect()) as connection:
            for start in range(0, len(movies), size):
                batch = movies[start:start + size]
                pending = []
                for movie in batch:
                    key = self.key(movie)
                    row = connection.execute("SELECT vector FROM embeddings WHERE key=?", (key,)).fetchone()
                    vector = np.frombuffer(row[0], dtype=np.float32) if row and len(row[0]) == 384 * 4 else None
                    if vector is None or vector.shape != (384,) or not np.isfinite(vector).all():
                        pending.append((key, dense_text(movie)))
                if pending:
                    vectors = model.passage_embed([text for _, text in pending], batch_size=size)
                    for (key, _), vector in zip(pending, vectors, strict=True):
                        vector = np.asarray(vector, dtype=np.float32)
                        if vector.shape != (384,) or not np.isfinite(vector).all():
                            raise ValueError("The embedding model did not produce a valid 384-dimensional vector.")
                        vector /= max(float(np.linalg.norm(vector)), 1e-12)
                        connection.execute("INSERT OR REPLACE INTO embeddings VALUES (?, ?)",
                                           (key, vector.tobytes()))
                    connection.commit()
                if on_progress:
                    on_progress(min(start + size, len(movies)), len(movies))


class DenseRanker:
    def __init__(self, embeddings, encoder):
        self.embeddings = embeddings
        self.encoder = encoder

    def search(self, query, top_k):
        if not query.strip():
            return []
        vector = np.asarray(next(iter(self.encoder.query_embed(query))), dtype=np.float32)
        vector /= max(float(np.linalg.norm(vector)), 1e-12)
        return best(self.embeddings @ vector, top_k)


class HybridRanker:
    def __init__(self, bm25, dense, rrf_k=60, candidate_k=100):
        self.bm25, self.dense = bm25, dense
        self.rrf_k, self.candidate_k = rrf_k, candidate_k

    def search(self, query, top_k):
        scores = {}
        for ranker in (self.bm25, self.dense):
            for rank, hit in enumerate(ranker.search(query, max(top_k, self.candidate_k)), 1):
                scores[hit.position] = scores.get(hit.position, 0.0) + 1 / (self.rrf_k + rank)
        order = sorted(scores, key=lambda position: (-scores[position], position))[:top_k]
        return [Hit(position, scores[position]) for position in order]


class RelaxedHybridRanker:
    def __init__(self, hybrid, rrf_k=60, candidate_k=100):
        self.hybrid, self.rrf_k, self.candidate_k = hybrid, rrf_k, candidate_k

    def search(self, query, top_k):
        variants = relaxation_details(query)["variants"]
        if len(variants) == 1:
            return self.hybrid.search(variants[0], top_k)
        scores = {}
        for variant in variants:
            for rank, hit in enumerate(self.hybrid.search(variant, max(top_k, self.candidate_k)), 1):
                scores[hit.position] = scores.get(hit.position, 0.0) + 1 / (self.rrf_k + rank)
        order = sorted(scores, key=lambda i: (-scores[i], i))[:top_k]
        return [Hit(i, scores[i]) for i in order]


class RankerBundle:
    def __init__(self, index, document, root, lexical=None):
        self.index = index
        self.rankers: dict[str, Ranker] = dict(lexical) if lexical else {
            "bm25": BM25Ranker(index), "tfidf": TfidfRanker(index)}
        self.store = EmbeddingStore(document["dense"], root)
        embeddings, self.missing_embeddings = self.store.load(index.movies)
        self.dense_error = None
        if embeddings is not None:
            try:
                dense = DenseRanker(embeddings, self.store.encoder())
                self.rankers["dense"] = dense
                self.rankers["hybrid"] = HybridRanker(self.rankers["bm25"], dense, **document["hybrid"])
                self.rankers["hybrid_relaxed"] = RelaxedHybridRanker(self.rankers["hybrid"], **document["hybrid"])
            except Exception as error:
                self.dense_error = f"Local embedding model unavailable: {error}"
        identity = {"version": 2, "movies": [(m.movie_id, self.store.key(m)) for m in index.movies],
                    "lexical": {k: v for k, v in document["bm25"].items()
                                if k not in {"top_k", "show_images", "max_movies", "corpus_path"}},
                    "dense": self.store.recipe, "hybrid": document["hybrid"]}
        self.fingerprint = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        self.configuration = {"lexical": identity["lexical"], "dense": self.store.recipe,
                              "hybrid": dict(document["hybrid"])}

    def availability(self):
        return {name: {"available": name in self.rankers,
                       "reason": None if name in self.rankers else self.dense_error or
                       f"Prepare embeddings for {self.missing_embeddings:,} missing plots."}
                for name in ("bm25", "tfidf", "dense", "hybrid", "hybrid_relaxed")}
