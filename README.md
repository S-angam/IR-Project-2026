# IRSangam

Movie identification from remembered details, with BM25, TF-IDF, ChromaDB vector search,
and hybrid ranking behind FastAPI. The React app compares ranking methods, shows benchmark
charts, and uses Gemini via LangChain to generate answers from retrieved plot excerpts.

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
The **Benchmark** section evaluates a fixed set of 50 labelled development queries.
Their correct movies were present in the 20,000-plot baseline. The panel displays
Success@5, MRR@10, retrieval latency and target coverage from
`data/processed/results_covered50.json`. **Run again** evaluates the same queries
against the active index.

Movie embeddings, plot text and metadata are stored in a persistent ChromaDB collection
under `data/processed/chroma`. After increasing the movie limit, click **Prepare dense
index** or rerun the preparation script and restart the backend. Lower limits reuse
stored vectors. Search settings and `GET /config` show the ChromaDB collection status.
If you have the previous local embedding cache, import it from `backend/` with
`uv run script/prepare_index.py --import-sqlite ../data/processed/embeddings.sqlite3`.

## Generate a RAG answer

Copy `backend/.env.example` to `backend/.env` and set `GOOGLE_API_KEY`. The `.env`
file is ignored by Git. Start the backend, select **A day on repeat** in the app,
and click **Generate answer**.

The backend retrieves candidate movies and sends the description and their plot
excerpts to Gemini 4 Hydrogen through LangChain. A named match requires a quote
that appears in the selected movie's excerpt. The app shows the source link and
keeps the retrieved evidence visible when generation is unavailable. Set the
Gemini model under `[answer]` in `backend/config.toml`.

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

Results save to `data/processed/experiment_results_covered50.json`. The experiment
starts with the same 50 original queries. It creates wrong-decade pairs for the
queries whose relevant movies all have a known release year and records each
exclusion. The scores describe the selected development subset.

## Data

See [data/README.md](data/README.md) for storage and the proposed application
field mapping. Large datasets, virtual environments, and build outputs are
excluded from Git. Dependency lockfiles are included.
