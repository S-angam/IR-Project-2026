"""Rankers share search(query, top_k) -> list[Hit], with stable corpus-order ties."""

import json
from collections import Counter
from hashlib import sha256
from typing import Protocol

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfTransformer

from models.retrieval import Hit

from .embeddings import EmbeddingStore
from .relaxation import relaxation_details


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


class DenseRanker:
    def __init__(self, collection, ids, encoder, stored_count):
        self.collection = collection
        self.ids = ids
        self.positions = {record_id: position for position, record_id in enumerate(ids)}
        self.restrict = stored_count != len(self.positions)
        self.encoder = encoder

    def search(self, query, top_k):
        if not query.strip():
            return []
        vector = np.asarray(
            next(iter(self.encoder.query_embed(query))), dtype=np.float32
        )
        options = {
            "query_embeddings": vector,
            "n_results": min(top_k, len(self.positions)),
            "include": ["distances"],
        }
        result = self.collection.query(
            **options, ids=self.ids if self.restrict else None
        )
        if any(record_id not in self.positions for record_id in result["ids"][0]):
            # A background preparation may have extended the collection since startup.
            result = self.collection.query(**options, ids=self.ids)
        hits = [
            Hit(self.positions[record_id], 1.0 - distance)
            for record_id, distance in zip(
                result["ids"][0], result["distances"][0], strict=True
            )
        ]
        return sorted(hits, key=lambda hit: (-hit.score, hit.position))


class HybridRanker:
    def __init__(self, bm25, dense, rrf_k=60, candidate_k=100):
        self.bm25, self.dense = bm25, dense
        self.rrf_k, self.candidate_k = rrf_k, candidate_k

    def search(self, query, top_k):
        scores = {}
        for ranker in (self.bm25, self.dense):
            for rank, hit in enumerate(
                ranker.search(query, max(top_k, self.candidate_k)), 1
            ):
                scores[hit.position] = scores.get(hit.position, 0.0) + 1 / (
                    self.rrf_k + rank
                )
        order = sorted(scores, key=lambda position: (-scores[position], position))[
            :top_k
        ]
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
            for rank, hit in enumerate(
                self.hybrid.search(variant, max(top_k, self.candidate_k)), 1
            ):
                scores[hit.position] = scores.get(hit.position, 0.0) + 1 / (
                    self.rrf_k + rank
                )
        order = sorted(scores, key=lambda i: (-scores[i], i))[:top_k]
        return [Hit(i, scores[i]) for i in order]


class RankerBundle:
    def __init__(self, index, document, root, lexical=None):
        self.index = index
        self.rankers: dict[str, Ranker] = (
            dict(lexical)
            if lexical
            else {"bm25": BM25Ranker(index), "tfidf": TfidfRanker(index)}
        )
        self.store = EmbeddingStore(document["dense"], root)
        ids = [self.store.record_id(movie) for movie in index.movies]
        self.missing_embeddings = len(ids)
        self.stored_vectors = 0
        self.dense_error = None
        try:
            collection = self.store.collection()
            if collection is not None:
                self.stored_vectors = collection.count()
                unique_ids = list(dict.fromkeys(ids))
                missing = len(unique_ids) - self.store.count_present(
                    collection, unique_ids
                )
                self.missing_embeddings = missing
            if collection is not None and not self.missing_embeddings:
                dense = DenseRanker(
                    collection, ids, self.store.encoder(), self.stored_vectors
                )
                self.rankers["dense"] = dense
                self.rankers["hybrid"] = HybridRanker(
                    self.rankers["bm25"], dense, **document["hybrid"]
                )
                self.rankers["hybrid_relaxed"] = RelaxedHybridRanker(
                    self.rankers["hybrid"], **document["hybrid"]
                )
        except Exception as error:
            self.dense_error = (
                f"ChromaDB or the local embedding model is unavailable: {error}"
            )
        dense_config = {
            **self.store.recipe,
            "backend": "chromadb",
            "hnsw": self.store.hnsw,
        }
        identity = {
            "version": 4,
            "movies": ids,
            "lexical": {
                k: v
                for k, v in document["bm25"].items()
                if k not in {"top_k", "show_images", "max_movies", "corpus_path"}
            },
            "dense": dense_config,
            "hybrid": document["hybrid"],
        }
        self.fingerprint = sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest()
        self.configuration = {
            "lexical": identity["lexical"],
            "dense": dense_config,
            "hybrid": dict(document["hybrid"]),
        }

    def availability(self):
        return {
            name: {
                "available": name in self.rankers,
                "reason": None
                if name in self.rankers
                else self.dense_error
                or f"Prepare embeddings for {self.missing_embeddings:,} missing plots.",
            }
            for name in ("bm25", "tfidf", "dense", "hybrid", "hybrid_relaxed")
        }
