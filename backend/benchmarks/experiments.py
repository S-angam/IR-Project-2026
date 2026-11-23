"""Paired wrong-detail experiments using the exact live retrieval rankers."""

import json
from datetime import datetime, timezone
from threading import Lock

from retrieval.corpus import extract_year, records

from .evaluation import benchmark_queries
from .reporting import save_json, score_ranking, summarize_results


def target_metadata(service, queries, progress):
    ids = {mid for q in queries for mid in q["expected_movie_ids"]}
    corpus = (
        service.config_path.parent / service.document["bm25"]["corpus_path"]
    ).resolve()
    stat = corpus.stat()
    signature = [str(corpus), stat.st_size, stat.st_mtime_ns, sorted(ids)]
    cache = service.config_path.parent.parent / "data/processed/benchmark_targets.json"
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved["signature"] == signature:
            return saved["movies"]
        if saved["signature"][:3] == signature[:3] and ids <= saved["movies"].keys():
            return {movie_id: saved["movies"][movie_id] for movie_id in ids}
    found = {}
    for number, movie in enumerate(records(corpus), 1):
        movie_id = str(movie.get("doc_id"))
        if movie_id in ids:
            found[movie_id] = {
                "title": movie.get("page_title"),
                "year": extract_year(movie),
            }
        if number % 1000 == 0:
            progress("Reading target metadata", len(found), len(ids))
        if len(found) == len(ids):
            break
    save_json(cache, {"signature": signature, "movies": found})
    return found


def manual_original_baseline(original):
    # With no marked original clue, relaxed Hybrid delegates to Hybrid exactly.
    return {
        **original,
        "methods": {
            **original["methods"],
            "hybrid_relaxed": {
                **original["methods"]["hybrid"],
                "reused_identical_input": True,
            },
        },
        "measurement_note": "No original clue is manually marked; relaxed Hybrid equals Hybrid, whose measurement is reused.",
    }


def run_experiment(service, bundle, progress):
    queries, cohort = benchmark_queries(service)
    metadata = target_metadata(service, queries, progress)
    mutations, skipped = {}, []
    for q in queries:
        years = [metadata.get(mid, {}).get("year") for mid in q["expected_movie_ids"]]
        if not years or any(year is None for year in years):
            skipped.append(
                {
                    "query_id": q["query_id"],
                    "reason": "No verified release year for every relevant movie.",
                }
            )
            continue
        actual = {year // 10 * 10 for year in years}
        base = years[0] // 10 * 10
        wrong = base + 10 if base < 2010 else base - 10
        while wrong in actual:
            wrong -= 10
        phrase = f"Maybe it was released in the {wrong}s"
        mutations[q["query_id"]] = {
            "operation": "append_wrong_decade",
            "original_years": years,
            "wrong_decade": wrong,
            "uncertain_clue": phrase,
            "query": q["query"].rstrip() + ". " + phrase + ".",
        }
    movie_ids = {m.movie_id for m in bundle.index.movies}
    methods = list(bundle.rankers)
    report = {
        "schema_version": 1,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split": service.document["evaluation"]["split"],
        "cohort": cohort,
        "indexed_movies": len(movie_ids),
        "index_fingerprint": bundle.fingerprint,
        "configuration": bundle.configuration,
        "conditions": {},
        "queries": [],
        "mutations": mutations,
        "skipped_mutations": skipped,
        "notes": [
            "Original paired and wrong-detail conditions use identical query IDs and targets.",
            "Synthetic decade is incompatible with every known relevant release year; source metadata can be imperfect.",
            "Manual relaxation receives the injected phrase; automatic relaxation detects uncertainty without target labels.",
            "A heuristic detector is not a learned uncertainty model. Dense retrieval uses first 256 tokens.",
            "All-query relevance denominators include targets outside the active index.",
            "No-clue manual baseline reuses the identical Hybrid measurement.",
        ],
    }
    path = (
        service.config_path.parent / service.document["experiment"]["results_path"]
    ).resolve()
    service.search_bundle(
        bundle, "a person remembers a movie", methods, 10, auto_relax=True
    )
    total = len(queries) + len(mutations) * 2
    done = 0
    for condition in ("original", "wrong_detail", "wrong_detail_manual"):
        rows = []
        for number, q in enumerate(queries):
            mutation = mutations.get(q["query_id"])
            if condition != "original" and not mutation:
                continue
            text = q["query"] if condition == "original" else mutation["query"]
            uncertain = (
                [mutation["uncertain_clue"]]
                if condition == "wrong_detail_manual"
                else []
            )

            # Reuse the results for methods that receive the same input in both conditions.
            selected_methods = (
                ["hybrid_relaxed"]
                if condition == "wrong_detail_manual"
                else methods[number % len(methods) :] + methods[: number % len(methods)]
            )
            response = service.search_bundle(
                bundle,
                text,
                selected_methods,
                10,
                uncertain,
                auto_relax=condition != "wrong_detail_manual",
            )
            expected = set(q["expected_movie_ids"])
            row = {
                "condition": condition,
                "query_id": q["query_id"],
                "query": text,
                "covered": bool(expected & movie_ids),
                "methods": {},
            }
            if condition == "wrong_detail_manual":
                source = next(
                    r
                    for r in report["queries"]
                    if r["condition"] == "wrong_detail"
                    and r["query_id"] == q["query_id"]
                )
                row["methods"] = {
                    k: dict(v, reused_identical_input=True)
                    for k, v in source["methods"].items()
                    if k != "hybrid_relaxed"
                }
            for method, output in response.methods.items():
                row["methods"][method] = {
                    **score_ranking(output, expected),
                    "relaxation": output.relaxation,
                }
            rows.append(row)
            done += 1
            progress(f"Retrieval: {condition}", done, total)
        report["queries"].extend(rows)
        report["conditions"][condition] = summarize_results(rows)
        if condition == "original":
            report["conditions"]["original_paired"] = summarize_results(
                [r for r in rows if r["query_id"] in mutations]
            )
            report["conditions"]["original_manual_paired"] = manual_original_baseline(
                report["conditions"]["original_paired"]
            )
            baseline = {
                "schema_version": 1,
                "created_at": report["created_at"],
                "split": report["split"],
                "cohort": cohort,
                "indexed_movies": report["indexed_movies"],
                "index_fingerprint": bundle.fingerprint,
                "configuration": bundle.configuration,
                **report["conditions"]["original"],
                "queries": rows,
                "query_fields": ["title", "text"],
                "uncovered_queries": len(rows)
                - report["conditions"]["original"]["covered_queries"],
                "latency_scope": "Warm ranking, query embedding and top-10 snippets; excludes queueing, network, images and preparation.",
                "metric_scope": "All benchmark queries. Relaxed Hybrid uses automatic uncertainty detection.",
            }
            save_json(
                (
                    service.config_path.parent
                    / service.document["evaluation"]["results_path"]
                ).resolve(),
                baseline,
            )
        save_json(path, report)
    report["status"] = "complete"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_json(path, report)
    return report


class ExperimentJob:
    def __init__(self, service):
        self.service = service
        self.lock, self.state_lock = service._evaluation_lock, Lock()
        self.state = {
            "running": False,
            "phase": "Idle",
            "completed": 0,
            "total": 0,
            "error": None,
        }

    def info(self):
        with self.state_lock:
            state = dict(self.state)
        path = (
            self.service.config_path.parent
            / self.service.document["experiment"]["results_path"]
        ).resolve()
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            report.pop("queries", None)
            report.pop("mutations", None)
        except FileNotFoundError:
            report = None
        except (OSError, ValueError, KeyError):
            report = None
            state["error"] = "Saved experiment is unreadable. Run the experiment again."
        return {
            **state,
            "results": report,
            "stale": bool(
                report
                and report["index_fingerprint"] != self.service.bundle.fingerprint
            ),
        }

    def begin(self):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("A benchmark or experiment is already running.")
        with self.service._state_lock:
            bundle = self.service.bundle
        if "hybrid_relaxed" not in bundle.rankers:
            self.lock.release()
            raise ValueError("Prepare all rankers before running the experiment.")
        with self.state_lock:
            self.state = {
                "running": True,
                "phase": "Starting",
                "completed": 0,
                "total": 0,
                "error": None,
            }
        return bundle

    def run(self, bundle):
        def progress(phase, done, total):
            with self.state_lock:
                self.state.update(phase=phase, completed=done, total=total)

        try:
            run_experiment(self.service, bundle, progress)
        except Exception as error:
            with self.state_lock:
                self.state["error"] = str(error)
        finally:
            with self.state_lock:
                self.state["running"] = False
            self.lock.release()
