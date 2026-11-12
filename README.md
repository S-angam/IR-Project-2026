# IRSangam

Movie identification from remembered details, with BM25, TF-IDF, dense and hybrid
rankers behind FastAPI, clue relaxation, and a simple React comparison page with benchmark charts.

- `backend/`: Python project initialized with `uv init --python 3.13`.
- `frontend/`: React (JavaScript) project scaffolded with Vite.
- `data/`: TREC ToT 2023 dataset documentation and local downloads.

## Backend

```powershell
cd backend
uv sync
uv run script/download_dataset.py
uv run script/prepare_index.py
uv run script/evaluate.py
uv run main.py
```

The downloader skips data already present. `main.py` starts the API at
http://127.0.0.1:8000 and prepares the reusable index before accepting searches.
Interactive API documentation is at http://127.0.0.1:8000/docs.

For standalone BM25 plot search, run `uv run bm25_search.py` from `backend/`.
Set the indexed movie limit in `backend/config.toml` (currently 20,000 usable plots).
See [backend/README.md](backend/README.md) for query examples and inspected results.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Use `npm run build` for a production build and `npm run lint` for linting.
The development UI is at http://127.0.0.1:5173; Vite proxies `/api` requests to
FastAPI. After a frontend build, restarting `uv run main.py` also serves the built
UI at http://127.0.0.1:8000. Use one backend process for this local app.

The UI lets you choose the number of results and save collection size, stemming,
stopword, BM25, and image preferences to `backend/config.toml`. Changes that
affect ranking rebuild the index; searches otherwise reuse it. Missing years are
returned as null, and unavailable images use a placeholder.

Choose a method or click **Compare all** for rankings, scores and elapsed times.
The **Benchmark** section displays Success@5, MRR@10 and measured latency from
`data/processed/results.json`. It reports target coverage and marks old results
when index settings change. **Run again** evaluates the current index.

Movie embeddings are prepared separately and cached by plot content and model
revision. After increasing the movie limit, click **Prepare dense index** (with
live progress), or rerun the preparation script and restart the backend. Lower
limits reuse saved vectors. Startup and search never embed movie plots.

## Clue relaxation and experiment charts

Select a phrase and click **Mark selection uncertain**, or enable automatic
detection of “maybe” and “I think”. **Compare all** includes **Hybrid + clue
relaxation**, fusing full-query and reduced-query Hybrid rankings with RRF.
Expand its details to inspect both actual queries.

Open **Results & charts** (`/#results`) for paired original/wrong-decade charts,
Success@5, MRR@10, latency and coverage diagnostics. CLI equivalent:

```powershell
cd backend
uv run script/evaluate_experiment.py
```

Results save to `data/processed/experiment_results.json`. All 150 original dev
queries are used. Wrong-decade pairs require known release years for every
relevant movie; exclusions are recorded. The test split has no distributed labels.
This repeatedly inspected dev split is not an untouched final test set.

## Data

See [data/README.md](data/README.md) for storage and the proposed application
field mapping. Large datasets, virtual environments, and build outputs are
excluded from Git. Dependency lockfiles are included.
