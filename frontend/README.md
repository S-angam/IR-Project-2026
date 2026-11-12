# IRSangam frontend

Simple React + Vite movie search UI. Start the backend in another terminal with
`uv run main.py` from `backend/`, then run:

```powershell
npm install
npm run dev
```

Open http://127.0.0.1:5173. Vite forwards `/api/search`, `/api/config`,
`/api/index/progress`, `/api/index/prepare`, `/api/evaluation` and `/api/posters`
to the backend on port 8000. The actual FastAPI endpoint is
`POST /search`.

Enter a description or select an example, choose a result count (1–50), and search.
Choose BM25, TF-IDF, Dense, Hybrid or Hybrid + clue relaxation, or click **Compare all** for side-by-side
rankings of the same query and movie collection. Compact cards show an image,
title, available release year, prominent method-specific score,
rank, ID, an expandable plot excerpt, and a Wikipedia source link.
Missing images have a placeholder.
Elapsed time is reported by the ranking method, separately from image loading.
Score scales differ between rankers, so compare ordering rather than raw scores.

The **Benchmark** table shows Success@5, MRR@10, mean latency and p95 latency
from the backend's saved `data/processed/results.json`. Coverage is explicit and
missing target movies count as misses. Expand metric details for definitions,
timestamp and covered-only diagnostics. **Run benchmark / Run again** evaluates
all five methods and updates the table and charts. Old metrics are marked when settings change.

Expand **Browse benchmark queries** to read all 150 dev descriptions and see the
expected IDs and whether their movies are indexed. **Use this description** copies
the exact benchmark query and expected IDs into the search form.

To evaluate your own description, expand **Test against a known movie**, enter its
expected Wikipedia movie ID, and click **Test description**. The page shows each
method's rank in the first ten, Success@5, RR@10 and latency above the result cards.
The **A day on repeat** example fills Groundhog Day's ID (`142327`) for a quick try.
This checks one query and leaves the saved overall benchmark unchanged.

Use the right-hand **Search settings** panel to change the indexed movie limit, BM25 parameters,
word-form matching, common-word removal, and image display. **Save settings**
persists these preferences and the current result count on the backend. Collection
or ranking changes rebuild the index. The page displays loading, error, and empty
states and disables conflicting actions while a settings change is running.
Index preparation streams live counts and stages from `/index/progress`. A known
movie limit shows a progress bar; the full collection shows counts without an
invented total. The sidebar stacks below the content on narrow screens.

**Prepare dense index** computes and caches new movie embeddings, with live counts.
Dense/Hybrid and Compare all remain unavailable until every selected movie has a
saved embedding. Existing lexical searches remain available during preparation.

```powershell
npm run build
```

After building, restart the backend to serve the UI and API together at
http://127.0.0.1:8000. The production build uses same-origin API paths by default.
For a separately hosted frontend, set `VITE_API_BASE_URL` at build time and update
the backend's CORS origins accordingly. `npm run preview` only previews static
assets; use the backend or `npm run dev` for the connected application.

Select a phrase in the description, then click **Mark selection uncertain**.
An optional checkbox detects “maybe”/“I think” clauses automatically. Expand the
relaxed method's details to see the full and reduced queries.

**Results & charts** opens `/#results`. Grouped bars compare Success@5, MRR@10 and
mean latency on identical original/wrong-detail query subsets. Exact values and
p95 remain available in a table. Covered-only relevance is an optional diagnostic;
latency always covers the whole paired subset. Switch between automatic detection
and manually marked clues. No chart library or external API key is required.

Test-case files are intentionally not retained; behavior is verified through
temporary API checks and browser interactions.
