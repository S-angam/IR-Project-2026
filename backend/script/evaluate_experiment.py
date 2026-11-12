"""Run paired retrieval evaluation using the API's rankers."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments import run_experiment
from search_service import SearchService

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    service = SearchService()
    run_experiment(service, service.bundle,
                   lambda phase, done, total: print(f"{phase}: {done}/{total}", flush=True))
    print("Saved", service.document["experiment"]["results_path"])
