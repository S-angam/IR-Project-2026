"""Evaluate held-out labelled queries, without ever indexing their answers."""
from collections import defaultdict
from datetime import datetime, timezone
import json
from threading import Lock

import numpy as np


def labelled_queries(service):
    config = service.document["evaluation"]
    split = config["split"]
    if split not in {"train", "dev"}:
        raise ValueError("Use train or dev: the distributed test split has no relevance labels.")
    folder = (service.config_path.parent / config["data_path"] / split).resolve()
    qrels = defaultdict(set)
    for line in (folder / "qrel.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        query_id, _, movie_id, relevance = line.split()
        if float(relevance) > 0:
            qrels[query_id].add(movie_id)
    queries = [json.loads(line) for line in (folder / "queries.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    queries = [q for q in queries if str(q["id"]) in qrels]
    if not queries:
        raise ValueError("No labelled queries found.")
    return [{"query_id": str(q["id"]), "title": q.get("title") or "",
             "description": q.get("text") or "",
             "query": " ".join(str(q.get(key) or "") for key in ("title", "text")).strip(),
             "expected_movie_ids": sorted(qrels[str(q["id"])])} for q in queries]


def query_catalog(service):
    with service._state_lock:
        bundle = service.bundle
    movies = {m.movie_id: m for m in bundle.index.movies}
    queries = labelled_queries(service)
    for query in queries:
        query["targets"] = [{"movie_id": movie_id,
                             "title": movies[movie_id].title if movie_id in movies else None,
                             "indexed": movie_id in movies} for movie_id in query["expected_movie_ids"]]
    return {"split": service.document["evaluation"]["split"], "count": len(queries),
            "index_fingerprint": bundle.fingerprint, "queries": queries}


def evaluate_query(service, request):
    with service._state_lock:
        bundle = service.bundle
    unavailable = set(request.methods) - bundle.rankers.keys()
    if unavailable:
        raise ValueError(f"Prepare unavailable rankers first: {', '.join(sorted(unavailable))}")
    expected = set(request.expected_movie_ids)
    # Expected IDs are used only to grade results; rankers receive just the description.
    response = service.search_bundle(bundle, request.query, list(dict.fromkeys(request.methods)),
                                     max(10, request.top_k), request.uncertain_clues, request.auto_relax)
    metrics = {}
    for method, output in response.methods.items():
        rank = next((r.rank for r in output.results[:10] if r.movie_id in expected), None)
        metrics[method] = {"rank_at_10": rank, "success_at_5": rank is not None and rank <= 5,
                           "reciprocal_rank_at_10": 1 / rank if rank else 0,
                           "elapsed_ms": output.elapsed_ms}
        output.results = output.results[:request.top_k]
    movies = {m.movie_id: m for m in bundle.index.movies}
    return {**response.model_dump(), "evaluation": {
        "targets": [{"movie_id": movie_id, "title": movies[movie_id].title if movie_id in movies else None,
                     "indexed": movie_id in movies} for movie_id in sorted(expected)],
        "covered": bool(expected & movies.keys()), "methods": metrics,
        "retrieved_top_k": max(10, request.top_k),
    }}


def evaluate(service, bundle, on_progress=None):
    config = service.document["evaluation"]
    split = config["split"]
    queries = labelled_queries(service)
    methods = list(bundle.rankers)
    if "hybrid_relaxed" not in methods:
        raise ValueError("Prepare dense embeddings before running the five-method benchmark.")
    corpus_ids = {movie.movie_id for movie in bundle.index.movies}
    rows = []
    # One untimed warmup, and rotate method order to reduce systematic ordering bias.
    service.search_bundle(bundle, "a person remembers a movie", methods, 10)
    for number, query in enumerate(queries):
        query_id = query["query_id"]
        text = query["query"]
        expected = set(query["expected_movie_ids"])
        order = methods[number % len(methods):] + methods[:number % len(methods)]
        response = service.search_bundle(bundle, text, order, 10, auto_relax=True)
        row = {"query_id": query_id, "covered": bool(expected & corpus_ids), "methods": {}}
        for method, output in response.methods.items():
            rank = next((r.rank for r in output.results if r.movie_id in expected), None)
            row["methods"][method] = {
                "success_at_5": int(rank is not None and rank <= 5),
                "reciprocal_rank_at_10": 1 / rank if rank else 0,
                "elapsed_ms": output.elapsed_ms,
                "top_10": [{"movie_id": r.movie_id, "score": r.score} for r in output.results],
            }
        rows.append(row)
        if on_progress:
            on_progress(number + 1, len(queries))
    covered = [row for row in rows if row["covered"]]
    summaries = {}
    for method in methods:
        values = [row["methods"][method] for row in rows]
        latencies = [v["elapsed_ms"] for v in values]
        summaries[method] = {
            "success_at_5": sum(v["success_at_5"] for v in values) / len(values),
            "mrr_at_10": sum(v["reciprocal_rank_at_10"] for v in values) / len(values),
            "latency_ms": {"mean": float(np.mean(latencies)), "median": float(np.median(latencies)),
                           "p95": float(np.percentile(latencies, 95))},
            "covered_only": {
                "success_at_5": sum(r["methods"][method]["success_at_5"] for r in covered) / len(covered),
                "mrr_at_10": sum(r["methods"][method]["reciprocal_rank_at_10"] for r in covered) / len(covered),
            } if covered else None,
        }
    report = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "split": split, "query_fields": ["title", "text"], "query_count": len(rows),
        "covered_queries": len(covered), "uncovered_queries": len(rows) - len(covered),
        "indexed_movies": len(bundle.index.movies), "index_fingerprint": bundle.fingerprint,
        "configuration": bundle.configuration,
        "latency_scope": "Warm process; ranking, query embedding and top-10 snippets. Excludes queueing, network, images and index preparation.",
        "metric_scope": "All labelled queries, including targets outside the selected corpus. Covered-only metrics are secondary diagnostics.",
        "methods": summaries, "queries": rows,
    }
    path = (service.config_path.parent / config["results_path"]).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".json.part")
    try:
        partial.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return report


class EvaluationJob:
    def __init__(self, service):
        self.service = service
        self.lock = service._evaluation_lock
        self.state_lock = Lock()
        self.state = {"running": False, "completed": 0, "total": 0, "error": None}

    def info(self):
        with self.state_lock:
            state = dict(self.state)
        path = (self.service.config_path.parent / self.service.document["evaluation"]["results_path"]).resolve()
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            report.pop("queries", None)  # Detailed per-query evidence stays in the JSON file.
        except FileNotFoundError:
            report = None
        except (OSError, ValueError):
            report = None
            state["error"] = "Saved evaluation is unreadable. Run the benchmark again."
        return {**state, "results": report,
                "stale": bool(report and report["index_fingerprint"] != self.service.bundle.fingerprint)}

    def begin(self):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("A benchmark or experiment is already running.")
        with self.service._state_lock:
            bundle = self.service.bundle
        if "hybrid_relaxed" not in bundle.rankers:
            self.lock.release()
            raise ValueError("Prepare dense embeddings before evaluating all five methods.")
        with self.state_lock:
            self.state = {"running": True, "completed": 0, "total": 0, "error": None}
        return bundle

    def run(self, bundle):
        def progress(done, total):
            with self.state_lock:
                self.state.update(completed=done, total=total)
        try:
            evaluate(self.service, bundle, progress)
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception("Evaluation failed")
            with self.state_lock:
                self.state["error"] = str(error)
        finally:
            with self.state_lock:
                self.state["running"] = False
            self.lock.release()
