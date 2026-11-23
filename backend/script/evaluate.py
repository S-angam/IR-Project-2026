"""Save Success@5, MRR@10 and measured latency for the configured labelled split."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.evaluation import evaluate
from services.search import SearchService

if __name__ == "__main__":
    service = SearchService()
    report = evaluate(
        service,
        service.bundle,
        lambda done, total: print(f"Evaluated {done}/{total}", flush=True),
    )
    print(f"Coverage: {report['covered_queries']}/{report['query_count']}")
    for name, values in report["methods"].items():
        print(
            f"{name}: Success@5={values['success_at_5']:.3f}; MRR@10={values['mrr_at_10']:.3f}; "
            f"mean={values['latency_ms']['mean']:.1f} ms"
        )
    print(f"Saved: {service.document['evaluation']['results_path']}")
