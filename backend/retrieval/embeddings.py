"""Prepare and persist movie vectors in ChromaDB."""

import html
import json
from hashlib import sha256

import chromadb
import numpy as np
from chromadb.config import Settings
from chromadb.errors import NotFoundError


def dense_text(movie):
    return " ".join(html.unescape(movie.plot).split())


class EmbeddingStore:
    """Persist plot vectors and search them in a model-specific Chroma collection."""

    def __init__(self, config, root):
        self.config = config
        self.path = (
            root / config.get("chroma_path", "../data/processed/chroma")
        ).resolve()
        self.model_cache = (root / config["model_cache_path"]).resolve()
        self.recipe = {
            "model": config["model"],
            "revision": config["model_revision"],
            "repository": config["model_repository"],
            "recipe": "fastembed-minilm-first256-v1",
        }
        self.recipe_text = json.dumps(self.recipe, sort_keys=True)
        self.hnsw = {"space": "cosine", "ef_search": config.get("ef_search", 200)}
        signature = json.dumps(
            {"recipe": self.recipe, "hnsw": self.hnsw}, sort_keys=True
        )
        self.collection_name = (
            "movie_plots_" + sha256(signature.encode()).hexdigest()[:12]
        )

    def key(self, movie):
        return sha256(
            (self.recipe_text + "\n" + dense_text(movie)).encode()
        ).hexdigest()

    def record_id(self, movie):
        return f"{movie.movie_id}:{self.key(movie)}"

    def collection(self, create=False):
        if not create and not self.path.is_dir():
            return None
        client = chromadb.PersistentClient(
            path=str(self.path), settings=Settings(anonymized_telemetry=False)
        )
        if create:
            return client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=None,
                configuration={"hnsw": self.hnsw},
                metadata={
                    "embedding_model": self.recipe["model"],
                    "embedding_revision": self.recipe["revision"],
                },
            )
        try:
            return client.get_collection(self.collection_name, embedding_function=None)
        except NotFoundError:
            return None

    def count_present(self, collection, ids):
        return sum(
            len(collection.get(ids=ids[start : start + 1000], include=[])["ids"])
            for start in range(0, len(ids), 1000)
        )

    def encoder(self, local_only=True):
        from fastembed import TextEmbedding
        from huggingface_hub import snapshot_download

        model_path = snapshot_download(
            self.config["model_repository"],
            revision=self.config["model_revision"],
            cache_dir=str(self.model_cache),
            local_files_only=local_only,
            allow_patterns=["*.json", "*.onnx"],
        )
        return TextEmbedding(
            model_name=self.config["model"],
            cache_dir=str(self.model_cache),
            threads=self.config.get("threads", 4),
            local_files_only=local_only,
            specific_model_path=model_path,
        )

    def prepare(self, movies, on_progress=None, read_cached=None):
        """Prepare missing plot vectors in resumable batches."""
        collection = self.collection(create=True)
        model = None
        size = self.config.get("batch_size", 32)
        for start in range(0, len(movies), size):
            batch = {
                self.record_id(movie): movie for movie in movies[start : start + size]
            }
            present = set(collection.get(ids=list(batch), include=[])["ids"])
            pending = {
                record_id: movie
                for record_id, movie in batch.items()
                if record_id not in present
            }
            if pending:
                texts = {
                    record_id: dense_text(movie) for record_id, movie in pending.items()
                }
                vectors = read_cached(list(pending)) if read_cached else {}
                missing = [
                    record_id for record_id in pending if record_id not in vectors
                ]
                if missing:
                    if model is None:
                        try:
                            model = self.encoder()
                        except Exception:
                            model = self.encoder(local_only=False)
                    generated = model.passage_embed(
                        [texts[record_id] for record_id in missing], batch_size=size
                    )
                    vectors.update(zip(missing, generated, strict=True))
                embeddings = np.asarray(
                    [vectors[record_id] for record_id in pending], dtype=np.float32
                )
                if (
                    embeddings.shape != (len(pending), 384)
                    or not np.isfinite(embeddings).all()
                ):
                    raise ValueError(
                        "Expected finite 384-dimensional movie embeddings."
                    )
                metadata = [
                    {
                        "movie_id": movie.movie_id,
                        "title": movie.title,
                        **({"year": movie.year} if movie.year is not None else {}),
                    }
                    for movie in pending.values()
                ]
                collection.upsert(
                    ids=list(pending),
                    embeddings=embeddings,
                    documents=list(texts.values()),
                    metadatas=metadata,
                )
            if on_progress:
                on_progress(min(start + size, len(movies)), len(movies))
