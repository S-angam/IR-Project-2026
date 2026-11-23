"""Own the reusable index and atomically apply settings changes."""

import logging
import tomllib
from threading import Lock
from time import perf_counter

import tomli_w

from models.answers import AnswerSource
from models.index import ConfigResponse, DenseIndexInfo, IndexProgress, SearchSettings
from models.retrieval import RetrievalQuery
from models.search import MethodResults, SearchResponse, SearchResult
from retrieval.bm25 import DEFAULT_CONFIG, build_index
from retrieval.corpus import excerpt
from retrieval.rankers import RankerBundle
from retrieval.relaxation import relaxation_details

SCORE_TYPES = {
    "bm25": "BM25 score",
    "tfidf": "Cosine similarity",
    "dense": "Cosine similarity",
    "hybrid": "RRF score",
    "hybrid_relaxed": "RRF score",
}


class SearchService:
    def __init__(self, config_path=DEFAULT_CONFIG):
        self.config_path = config_path
        self.document = tomllib.loads(config_path.read_text(encoding="utf-8"))
        self.settings = SearchSettings(
            **{
                k: v
                for k, v in self.document["bm25"].items()
                if k in SearchSettings.model_fields
            }
        )
        self._state_lock = Lock()
        self._rebuild_lock = Lock()

        # Serialize searches because they share a Snowball stemmer.
        self._search_lock = Lock()

        # Both benchmark entry points write the original-results file.
        self._evaluation_lock = Lock()

        self.progress = IndexProgress(
            phase="reading", target=self.settings.max_movies or None
        )
        self.index = self._build(self.settings)
        self.bundle = RankerBundle(self.index, self.document, self.config_path.parent)
        self._progress(
            "ready", len(self.index.movies), self.index.stats["scanned"], self.settings
        )

    def _progress(self, phase, indexed, scanned, settings):
        with self._state_lock:
            self.progress = IndexProgress(
                phase=phase,
                indexed=indexed,
                scanned=scanned,
                target=settings.max_movies or None,
            )

    def _build(self, settings):
        config = self.document["bm25"] | settings.model_dump()
        path = (self.config_path.parent / config["corpus_path"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing corpus: {path}. Run uv run script/download_dataset.py first."
            )
        return build_index(
            path,
            config,
            on_progress=lambda phase, indexed, scanned: self._progress(
                phase, indexed, scanned, settings
            ),
        )

    def info(self):
        with self._state_lock:
            return ConfigResponse(
                settings=self.settings,
                indexed_movies=len(self.index.movies),
                stats=self.index.stats,
                rebuilding=self._rebuild_lock.locked(),
                progress=self.progress,
                methods=self.bundle.availability(),
                dense_index=DenseIndexInfo(
                    collection=self.bundle.store.collection_name,
                    stored_vectors=self.bundle.stored_vectors,
                    missing_vectors=self.bundle.missing_embeddings,
                ),
                index_fingerprint=self.bundle.fingerprint,
            )

    def configure(self, settings):
        if not self._rebuild_lock.acquire(blocking=False):
            raise RuntimeError(
                "An index update is already running. Try again when it finishes."
            )
        try:
            changes = {
                key
                for key, value in settings.model_dump().items()
                if value != getattr(self.settings, key)
            }

            # Rebuild the index only when a ranking or corpus setting changes.
            index = (
                self._build(settings)
                if changes - {"top_k", "show_images"}
                else self.index
            )
            document = self.document | {
                "bm25": self.document["bm25"] | settings.model_dump()
            }
            self._progress(
                "loading", len(index.movies), index.stats["scanned"], settings
            )
            bundle = (
                RankerBundle(index, document, self.config_path.parent)
                if index is not self.index
                else self.bundle
            )
            self._progress(
                "saving", len(index.movies), index.stats["scanned"], settings
            )
            partial = self.config_path.with_suffix(".toml.part")
            try:
                partial.write_text(tomli_w.dumps(document), encoding="utf-8")
                partial.replace(self.config_path)
            finally:
                partial.unlink(missing_ok=True)
            with self._state_lock:
                self.document, self.settings, self.index, self.bundle = (
                    document,
                    settings,
                    index,
                    bundle,
                )
            self._progress("ready", len(index.movies), index.stats["scanned"], settings)
        except Exception:
            with self._state_lock:
                self.progress = self.progress.model_copy(update={"phase": "failed"})
            raise
        finally:
            self._rebuild_lock.release()
        return self.info()

    def begin_preparation(self):
        if not self._rebuild_lock.acquire(blocking=False):
            raise RuntimeError("An index update is already running.")
        self._progress("embedding", 0, self.index.stats["scanned"], self.settings)

    def prepare_dense(self):
        """Explicit preparation job, separate from startup and query handling."""
        try:
            index = self.index

            def progress(done, total):
                with self._state_lock:
                    self.progress = IndexProgress(
                        phase="embedding",
                        indexed=done,
                        scanned=index.stats["scanned"],
                        target=total,
                    )

            self.bundle.store.prepare(index.movies, progress)
            self._progress(
                "loading", len(index.movies), index.stats["scanned"], self.settings
            )
            bundle = RankerBundle(
                index,
                self.document,
                self.config_path.parent,
                {name: self.bundle.rankers[name] for name in ("bm25", "tfidf")},
            )
            if "dense" not in bundle.rankers:
                raise RuntimeError(
                    bundle.dense_error or "Embedding preparation incomplete"
                )
            with self._state_lock:
                self.bundle = bundle
            self._progress(
                "ready", len(index.movies), index.stats["scanned"], self.settings
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "Dense preparation failed; previous rankers remain active"
            )
            self._progress(
                "failed", self.progress.indexed, self.progress.scanned, self.settings
            )
        finally:
            self._rebuild_lock.release()

    def search(self, request):
        with self._state_lock:
            bundle = self.bundle
        unavailable = set(request.methods) - bundle.rankers.keys()
        if unavailable:
            raise ValueError(
                f"Prepare dense embeddings first. Unavailable methods: {', '.join(sorted(unavailable))}"
            )
        return self.search_bundle(
            bundle,
            request.query,
            list(dict.fromkeys(request.methods)),
            request.top_k,
            request.uncertain_clues,
            request.auto_relax,
        )

    def answer_context(self, request):
        with self._state_lock:
            bundle = self.bundle
        context = RetrievalQuery(
            request.query, tuple(request.uncertain_clues), request.auto_relax
        )
        details = relaxation_details(context)
        method = "hybrid_relaxed" if details["applied"] else "hybrid"
        if method not in bundle.rankers:
            method = "bm25"
        response = self.search_bundle(
            bundle,
            request.query,
            [method],
            5,
            request.uncertain_clues,
            request.auto_relax,
        )
        hits = response.methods[method].results
        wanted = {hit.movie_id for hit in hits}
        movies = {
            movie.movie_id: movie
            for movie in bundle.index.movies
            if movie.movie_id in wanted
        }
        with self._search_lock:
            tokenizer = bundle.index.tokenizer
            terms = set(tokenizer(details["variants"][-1]))
            sources = [
                AnswerSource(
                    movie_id=hit.movie_id,
                    title=hit.title,
                    year=hit.year,
                    wikipedia_url=hit.wikipedia_url,
                    excerpt=excerpt(
                        movies[hit.movie_id],
                        terms,
                        tokenizer,
                        limit=900,
                        sentence_count=3,
                    ),
                )
                for hit in hits
            ]
        return method, details["uncertain_clues"], sources

    def search_bundle(
        self, bundle, query, methods, top_k, uncertain_clues=(), auto_relax=False
    ):
        index = bundle.index
        outputs = {}
        context = RetrievalQuery(query, tuple(uncertain_clues), auto_relax)
        details = relaxation_details(context)

        # Work against one snapshot, even if a rebuild completes during a search.
        with self._search_lock:
            for method in methods:
                start = perf_counter()
                hits = bundle.rankers[method].search(
                    context if method == "hybrid_relaxed" else query, top_k
                )
                terms = index.tokenizer(query)
                results = []
                for rank, hit in enumerate(hits, 1):
                    movie = index.movies[hit.position]
                    results.append(
                        SearchResult(
                            movie_id=movie.movie_id,
                            title=movie.title,
                            year=movie.year,
                            rank=rank,
                            snippet=excerpt(movie, terms, index.tokenizer),
                            score=hit.score,
                            wikipedia_url=f"https://en.wikipedia.org/?curid={movie.movie_id}",
                        )
                    )
                elapsed = round((perf_counter() - start) * 1000, 3)
                outputs[method] = MethodResults(
                    elapsed_ms=elapsed,
                    score_type=SCORE_TYPES[method],
                    results=results,
                    relaxation=details if method == "hybrid_relaxed" else None,
                )
        return SearchResponse(
            query=query,
            indexed_movies=len(index.movies),
            index_fingerprint=bundle.fingerprint,
            methods=outputs,
        )
