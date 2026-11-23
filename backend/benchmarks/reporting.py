"""Score benchmark rankings, summarize metrics, and save JSON reports."""

import json

import numpy as np


def score_ranking(output, expected_movie_ids):
    rank = next(
        (
            result.rank
            for result in output.results
            if result.movie_id in expected_movie_ids
        ),
        None,
    )
    return {
        "success_at_5": int(rank is not None and rank <= 5),
        "reciprocal_rank_at_10": 1 / rank if rank else 0,
        "elapsed_ms": output.elapsed_ms,
        "top_10": [
            {"movie_id": result.movie_id, "score": result.score}
            for result in output.results
        ],
    }


def summarize_results(rows):
    names = list(rows[0]["methods"]) if rows else []
    output = {}
    covered = [r for r in rows if r["covered"]]
    for name in names:
        values = [r["methods"][name] for r in rows]
        latencies = [v["elapsed_ms"] for v in values]
        output[name] = {
            "success_at_5": sum(v["success_at_5"] for v in values) / len(values),
            "mrr_at_10": sum(v["reciprocal_rank_at_10"] for v in values) / len(values),
            "latency_ms": {
                "mean": float(np.mean(latencies)),
                "median": float(np.median(latencies)),
                "p95": float(np.percentile(latencies, 95)),
            },
            "covered_only": {
                "success_at_5": sum(r["methods"][name]["success_at_5"] for r in covered)
                / len(covered),
                "mrr_at_10": sum(
                    r["methods"][name]["reciprocal_rank_at_10"] for r in covered
                )
                / len(covered),
            }
            if covered
            else None,
        }
    return {
        "query_count": len(rows),
        "covered_queries": len(covered),
        "methods": output,
    }


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".json.part")
    try:
        partial.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
