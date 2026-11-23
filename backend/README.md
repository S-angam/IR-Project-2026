# Backend

Python 3.13 and FastAPI, managed by uv.

## Clue relaxation and paired evaluation

`POST /search` additionally accepts `methods: ["hybrid", "hybrid_relaxed"]`,
`uncertain_clues: ["Maybe Jim Carrey was in it"]`, and `auto_relax: true/false`.
Manual phrases must occur exactly in the query. Automatic detection stops at
sentence/clause punctuation. Marked phrases are removed together for a second
query; full and relaxed Hybrid rankings are fused with RRF. Without a removable
clue, the result equals Hybrid. Responses expose actual variants. Direct
`hybrid_relaxed.search(string, top_k)` enables the automatic heuristic; API requests
explicitly control it. `POST /clues/detect` previews detected phrases.

`GET/POST /experiments` reads or starts the expanded retrieval benchmark. POST
requires no request body. The CLI uses the same services:
`uv run script/evaluate_experiment.py`.

JSON records original dev queries, a matched original subset, automatic wrong-detail
queries, and manually marked wrong-detail queries. A wrong decade is appended only
when every known relevant movie has a verified, incompatible release decade.
Mutations and exclusions are saved. Manual marking is an oracle diagnostic for
clue location; automatic detection receives no gold labels. All-query relevance
includes missing indexed targets; covered-only relevance is an extra diagnostic.
Warm latency includes ranking/query embedding/snippets and excludes queueing,
preparation/network. Method order rotates. Unchanged manual-condition methods
reuse identical-input automatic measurements, explicitly marked in JSON. The
manual original baseline has no marked clue, so relaxed Hybrid reuses Hybrid's
identical measurement.

Results save to `data/processed/experiment_results_covered50.json`. Originals also
update `results_covered50.json`. The API prevents concurrent benchmark runs. Use one CLI runner
at a time. Dev has already been inspected; final claims need a fresh labelled split.

## Starting the service

```powershell
uv sync
uv run script/download_dataset.py
uv run script/prepare_index.py
uv run script/evaluate.py
uv run main.py
```

`main.py` starts the API at http://127.0.0.1:8000. It builds the lexical indexes at
startup and opens the existing persistent ChromaDB collection. The embedding model
loads from its local cache. Startup never downloads models or embeds movie plots.
If vectors are missing, BM25 and TF-IDF stay available while dense/hybrid are marked unavailable.
Prepare missing dataset files separately with:

```powershell
uv run script/download_dataset.py
```

It resolves paths relative to the project, reuses valid archives, and extracts
missing or incomplete files into `data/raw/`. Complete extracted datasets are
skipped without downloading or extracting again, even if their ZIPs were removed.
Existing extracted files are checked by expected byte size; archives are checked
against the published MD5 before extraction. Same-size manual edits to extracted
files are not detected; remove an edited file to restore it from the archive.
Downloads and extraction use temporary `.part` files so an interrupted operation
can be safely rerun. Only listed dataset members are extracted; `__MACOSX`
metadata is ignored.

Dataset storage and the proposed movie schema are documented in
[`../data/README.md`](../data/README.md).

## API

API routes are grouped by feature in `routers/`. Request and response schemas
are in `models/`, ranking and corpus code in `retrieval/`, and index management
and answer generation in `services/`. Benchmark code lives in `benchmarks/`.

`POST /search` accepts:

```json
{"query": "A reporter relives the same day in a small town", "methods": ["bm25", "tfidf", "dense", "hybrid"], "top_k": 5}
```

The response contains `query`, `indexed_movies`, and
`methods.<name> = {elapsed_ms, score_type, results}`, plus the index fingerprint.
Each result includes `movie_id`, `title`,
`year`, `rank`, `snippet`, `score`, and `wikipedia_url`. Years are extracted from
film release metadata or a year explicitly present in the page title; unknown
years are null. Each method's timing covers ranking (including query embedding)
and snippets, excluding queueing, index building, network transport, and posters.
Methods run independently in request order; hybrid includes both component
searches in its own latency. Invalid methods, blank queries, and top_k outside
1–50 return 422. Unprepared dense/hybrid requests return 409 with a preparation hint.
Repeated method names are deduplicated.

`GET /config` returns settings, index size, corpus counters, rebuild status, method
availability and the current index fingerprint. `dense_index` reports the ChromaDB
collection name, stored vectors and missing vectors for the selected plots.

`POST /answer` takes `query`, optional `uncertain_clues`, and optional `auto_relax`.
It retrieves up to five candidates with Hybrid or relaxed Hybrid. When dense search
is unavailable, it uses BM25. The backend sends plot excerpts to the configured
Gemini model via LangChain and verifies that the selected ID is a candidate and its evidence quote
appears in that candidate's excerpt. The response includes `status`, `method`, `model`,
`explanation`, and retrieved `sources` with Wikipedia links. `unavailable` responses
include the evidence so it remains inspectable. The default model is `gemini-4-hydrogen`.
Set `GOOGLE_API_KEY` in the ignored `backend/.env` or in the backend process environment.
`PUT /config` accepts the complete settings object and saves it to `config.toml`.
Collection/ranking changes prepare a replacement index before swapping it in;
existing requests can use the old index during preparation. A concurrent update
gets 409. Result-count and image preferences do not rebuild the index. Use a
single backend process; multiple workers would maintain separate indexes.

`GET /index/progress` streams server-sent events every 300 ms during a UI update.
It reports the preparation/build/save phase, actual accepted movie count, scanned
record count, and requested limit (null for all movies). `GET /config` also includes
this progress snapshot. The progress bar counts plot preparation, then switches
to an indeterminate bar for lexical construction, loading and saving. Embedding
preparation reports completed/cached vectors against the exact plot count;
completion is reported
only after the replacement index and settings are active.

`POST /index/prepare` starts explicit embedding preparation in a background job
(202). It reuses completed vectors and streams counts via `/index/progress`.
Searches continue using the active snapshot. Concurrent settings/preparation jobs
get 409. A failed job preserves the old rankers and completed cache batches.

## Rankers and offline embeddings

`retrieval/rankers.py` defines the `Ranker` protocol `search(query, top_k) -> list[Hit]`.
A hit carries a corpus position and score. The service adds shared movie metadata,
one-based ranks and snippets, so every method has the same API result format.

- **BM25:** the existing stemmed full-plot baseline.
- **TF-IDF:** full-plot term counts from the same tokenizer, smoothed IDF, L2
  normalization, cosine similarity. Unknown vocabulary gives no results.
- **Dense:** pretrained [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
  384-dimensional vectors via FastEmbed/ONNX on CPU with mean pooling and cosine
  similarity. ChromaDB's HNSW index retrieves approximate nearest neighbors. The
  pinned ONNX model revision is in `[dense]` in `config.toml`.
- **Hybrid:** BM25 + dense, equal-weight Reciprocal Rank Fusion:
  `sum(1 / (rrf_k + rank))`, ranks start at 1. Defaults: `rrf_k=60`,
  `candidate_k=100` per component (or top_k if larger). Missing component hits
  contribute zero. Ties use corpus order. Raw score scales are never added.

Dense inputs are HTML-decoded plots with collapsed whitespace. **Only the first
256 model tokens of each plot/query are encoded** (MiniLM's standard limit).
This initial baseline may miss scenes late in long plots; lexical rankers read
the full plot. Dense cosine values and RRF scores are ranking values, not
confidence percentages, and are not numerically comparable to BM25 scores.

`uv run script/prepare_index.py` stores vectors, plot text and metadata in batches
in `data/processed/chroma`. It skips completed records and resumes interrupted work.
Records are keyed by movie ID and normalized plot content within a collection tied
to the model revision, preprocessing recipe and HNSW settings. A lower plot limit
restricts Chroma search to active IDs. The model cache is under `data/processed/models`.
If upgrading, use `--import-sqlite ../data/processed/embeddings.sqlite3` to import
compatible vectors from the old cache as part of preparation. Restart the API after
CLI preparation. Search encodes the query and submits that vector to ChromaDB.

The current prepared collection has 20,000 usable plots. Index statistics tell
you how many source records were skipped for missing plots. Reducing the movie
limit is not a random sample, so relevance metrics depend strongly on coverage.

## Evaluation

Run `uv run script/evaluate.py` or click **Run benchmark / Run again** in React.
`POST /evaluation` starts a background evaluation (202); `GET /evaluation`
returns progress, the saved summary and whether its index fingerprint is stale.
All five rankers must be ready. Evaluation uses one immutable index snapshot.

The default is a **fixed set of 50 labelled dev queries** listed in
`data/benchmark_cohort.json`. Of the 150 labelled development queries, 63 had a
relevant movie in the 20,000-plot baseline. A fixed hash of the query IDs selected
50 of those 63 without using ranking scores. The same IDs apply to future runs.
Only `title` and `text` form the query. Relevance labels join by `id` for grading.
For a different labelled split, use a matching cohort file or omit `cohort_path`
to evaluate the full split. The supplied test set has no relevance labels.

- **Success@5:** fraction of queries with any relevant movie in the top five.
- **MRR@10:** mean reciprocal rank of the first relevant movie in the top ten;
  zero if there is no relevant hit.
- **Latency:** mean, median and p95 milliseconds per method, including ranking,
  query embedding and top-10 snippets. One warmup is excluded; method order is
  rotated across queries. No query-result caching is used. Latency depends on
  hardware and concurrent load, and excludes queueing/network/images/preparation.

The denominator includes **every query in the configured benchmark**. If index
settings remove a target, it counts as a miss. The report shows current coverage
and relevance among covered queries separately.

The complete report is written atomically to `data/processed/results_covered50.json`, with
timestamp, split, corpus fingerprint, model revision, settings, aggregate metrics,
and per-query top-10 IDs/scores. React displays the summary and warns when it is
from an earlier index. An interrupted evaluation leaves the previous report intact.
Use a single CLI or API evaluation writer at a time.

### Browse and test individual descriptions

`GET /evaluation/queries` returns the configured benchmark queries,
their exact `title + text` search input, relevant movie IDs, and current index
coverage. React exposes this under **Browse benchmark queries**. **Use this
description** fills the search box and expected IDs without running a search.

`POST /evaluation/query` accepts normal search fields plus `expected_movie_ids`:

```json
{"query":"A reporter keeps waking up on the same day while covering a small-town festival.","methods":["bm25","tfidf","dense","hybrid"],"top_k":5,"expected_movie_ids":["142327"]}
```

It searches at least 10 results per method, grades the first 10, and returns the
requested number of cards plus `evaluation`: expected-movie coverage, rank within
the top 10, Success@5 (yes/no), reciprocal rank at 10 and measured latency. For
multiple acceptable IDs, the first relevant hit determines the rank. RR@10 is
for one query; MRR@10 averages reciprocal ranks across a query set. Missing
targets count as misses and are labelled as outside the current index.

Expected IDs are never passed to the rankers. This diagnostic does not overwrite
the saved report or change the overall benchmark. Both search routes accept up to
20,000 characters so full benchmark descriptions can be tested through the UI.

Measured before the ChromaDB migration on 2026-11-11 with 20,000 plots and all 150 dev queries (63 targets
covered by the selected corpus):

| Method | Success@5 | MRR@10 | Mean latency (ms) | P95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 2.67% | 0.0244 | 433.7 | 825.5 |
| TF-IDF | 2.67% | 0.0121 | 19.8 | 25.5 |
| Dense | 2.00% | 0.0132 | 21.9 | 34.1 |
| Hybrid | 3.33% | 0.0287 | 447.7 | 847.8 |

These are initial baselines, not tuned relevance results. On the detailed festival
example, BM25 puts Groundhog Day first and hybrid second; TF-IDF and dense miss it
in the top five. The target's cached dense vector matched a fresh embedding with
cosine 1.0. Its time-loop explanation occurs later in the plot, illustrating the
limits of truncation and the pretrained model. Increasing corpus coverage and
embedding plot chunks are possible next retrieval improvements.

`GET /posters?movie_ids=142327,52371` returns optional images from the
[Wikipedia PageImages API](https://www.mediawiki.org/wiki/API:Pageimages), with
no API key. The lookup uses Wikipedia IDs, not title guessing. Images are cached
in memory for 24 hours; missing images and errors are briefly cached. Unavailable
images return null and never prevent search. These are page thumbnails, not
guaranteed film posters; source links are shown on every card. Images retain
their original rights and come from Wikipedia/Wikimedia.

Open http://127.0.0.1:8000/docs, expand `POST /search`, click **Try it out**, then
**Execute**. The supplied example was verified there with HTTP 200 before React
was connected. Its shorter wording gives different rankings from the detailed
festival query below; the API does not force a target movie into results.

## BM25 plot search

```powershell
uv run bm25_search.py --query "a reporter keeps waking up on the same day while covering a small-town festival." --inspect-id 142327
```

Run `uv run bm25_search.py` to build the index once and enter multiple queries
interactively. Empty input exits. The CLI remains available independently of the
FastAPI service.

Edit `config.toml` to set `max_movies` (default 10,000 usable plots, 0 for all),
`top_k` (default 5), the corpus path, plot section priority, stemming, stopwords,
and BM25 parameters. `--limit 1000` overrides the limit for one run. Paths in the
configuration are relative to the configuration file, not the working directory.
The limit selects the first N usable records in corpus order, not a random sample.
The raw JSONL is streamed; selected plots and the index are held in memory and
rebuilt for each invocation. Using all records requires more memory and time.

Only plot sections are indexed. Missing plots are counted and skipped; abstracts,
titles, cast, and full-page text are not silently substituted. The TREC candidate
corpus includes TV episodes and other audiovisual works, so results are not
restricted to feature films. `Movie` is a small dataclass holding the Wikipedia
ID, title, plot, and selected section. IDs and titles are metadata, not search terms.

The implementation uses [rank-bm25's BM25Okapi](https://github.com/dorianbrown/rank_bm25).
Both plots and queries use the same Unicode normalization, HTML entity decoding,
case folding, word tokenization, small explicit stopword list, and optional
[English Snowball stemming](https://pypi.org/project/snowballstemmer/). Negation
and `same` are retained. Repeated query tokens are counted once. Scores are
ranking values, not probabilities, and change with the indexed corpus.

Diagnostics print counts of missing/empty plots, query tokens, terms absent from
the index vocabulary, and each result's plot section, length, matched terms, and
an excerpt. Unknown queries return no matches rather than arbitrary zero-score
documents. `--inspect-id ID` checks the source record even if it falls outside
the configured limit, and reports its rank and absent query terms if indexed.

## Inspected example

With the default 10,000-plot limit, 14,525 records were scanned and 4,525 had no
usable configured plot section; no selected plots became empty after preprocessing.
These counts describe the scanned subset, not the entire corpus.

| Rank | Wikipedia ID | Title | Score |
| --- | --- | --- | --- |
| 1 | 142327 | Groundhog Day (film) | 20.5175 |
| 2 | 2256919 | Chef's Chocolate Salty Balls | 17.7966 |
| 3 | 1526741 | Ánimas Trujano (film) | 16.5214 |
| 4 | 2082558 | Danny Deckchair | 14.8767 |
| 5 | 1998991 | The Gathering (2003 film) | 14.1197 |

`Groundhog Day` has a real `plot` section (413 tokens after preprocessing), so
missing data is not the issue for this query. Disabling stemming with
`--no-stemming` moves it to rank 12 (11.7521); `Danny Deckchair` becomes rank 1.
Stemming connects `reporter` with `reports`, `festival` with `festivities`, and
`waking` with `wakes`. It does not match every related word: `covering` and
`coverage` still differ. The default target matches seven of nine query stems.

Other top results overlap on festival/town vocabulary; BM25 does not understand
the time-loop relationship. The TV episode at rank 2 also demonstrates candidate
corpus scope. This separates data availability, preprocessing differences, and
lexical ranking limitations without adding semantic search or hand-tuned boosts.
One successful query is a smoke check, not a relevance evaluation across the dataset.

The full default-query output is saved in [bm25_example.txt](bm25_example.txt).
With `--limit 100`, the target is outside the index; `--inspect-id 142327` correctly
reports that its plot exists but was not indexed.

Verification was performed using temporary checks and browser interactions;
test-case files are intentionally not kept in the project.
