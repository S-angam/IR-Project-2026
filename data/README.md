# TREC Tip-of-the-Tongue 2023

Source: [official 2023 guidelines](https://trec-tot.github.io/guidelines-2023).
Download URLs, published counts, and MD5 checksums are in `sources.json`.
`inspection.json` records local archive verification and observed record counts.

All five downloads match the published MD5 checksums. The corpus contains
**231,852 records**, counted from the downloaded JSONL. The guidelines' download
table says 231,618, while its corpus description says 231,852; use the observed
count for this archive. Train, dev, and test each contain 150 queries. The IMDb
mapping contains 190,370 keys.

## Local storage

The original ZIP archives and extracted files are stored in `data/raw/` and
excluded from Git. From `backend/`, run
`uv run script/download_dataset.py` to download and extract anything missing.
The script reuses valid archives and skips extracted files with the expected
byte sizes. All paths are resolved from the script location, independent of the
working directory.

After preparation, the layout is:

```text
data/raw/
  corpus.jsonl
  train/
    queries.jsonl
    qrel.txt
  dev/
    queries.jsonl
    qrel.txt
  test/
    queries.jsonl
  wikipage_id_to_imdb.json
  (original ZIP archives)
```

The corpus alone is approximately 4.27 GB uncompressed. The archives are retained
so missing extracted files can be restored without downloading again.
JSONL means one JSON object per line; stream records instead of loading the entire
corpus into memory. JSON strings contain escaped newlines within each record.

| Archive | Payload |
| --- | --- |
| `corpus.jsonl.zip` | `corpus.jsonl`: candidate Wikipedia documents |
| `train.zip` | `train/queries.jsonl`, `train/qrel.txt` |
| `dev.zip` | `dev/queries.jsonl`, `dev/qrel.txt` |
| `test.zip` | `test/queries.jsonl`; no answers or qrels in this archive |
| `wikipage_id_to_imdb.json.zip` | Optional Wikipedia-to-IMDb mapping |

Ignore `__MACOSX/` ZIP entries; these are archive metadata, not dataset records.

## Corpus schema observed in the downloaded file

| Field | Meaning |
| --- | --- |
| `doc_id` | Wikipedia page identifier, stored as a string |
| `page_title` | Page title |
| `text` | Parsed page text |
| `sections` | Object mapping section headings to text |
| `infoboxes` | List of objects with `name` and `params` |
| `page_source` | Original wikitext |
| `wikidata_id` | Linked Wikidata identifier |
| `wikidata_classes` | Entity classification pairs |

## Mapping to our future movie records

The source does not directly provide a uniform `movie_id`, `title`, `plot`,
`year`, `cast` schema. The BM25 loader now maps IDs, titles, a selected plot
section, and an optional release year in memory. The remaining fields below
describe future normalization; no separate normalized corpus has been written.

| Application field | Proposed source and handling |
| --- | --- |
| `movie_id` | Preserve `doc_id` as a string, so query answers and qrels still join correctly |
| `title` | Use `page_title`; optionally keep the film infobox's `params.name` as an alternate title |
| `plot` | Prefer a `plot` section, then `synopsis`; leave missing values null. Keep the abstract separately |
| `year` | Parse the film infobox's `params.released`; allow null and preserve the original date text |
| `cast` | Parse film infobox `params.starring`, or a cast section if present; use an array of names |
| `text` | Preserve the full parsed text for retrieval |
| `wikidata_id` | Preserve the source identifier |
| `imdb_ids` | Join the optional mapping using `doc_id`; allow multiple IDs or no match |

For example, the first corpus record has `doc_id = "330"`,
`page_title = "Actrius"`, and `wikidata_id = "Q2823770"`. Its film infobox has
the alternate name `Actresses`, a release template encoding 1997-01-17, and a
`starring` list containing Nuria Espert, Rosa Maria Sarda, Anna Lizaran, and
Merce Pons (the original values retain their accents). Its plot is under
`sections.synopsis`.

Infobox values still contain markup such as `[[Ventura Pons]]`, list templates,
date templates, and comments. They need proper parsing before serving clean
application fields. Do not assume every document is a feature film or has every
field. Preserve raw records and write future normalized output separately under
`data/processed/`.

The IMDb mapping values are lists, and not all identifiers are movie title IDs:
the inspected mapping includes `"330": ["tt0115462"]` and
`"324": ["ev0000003"]`. Validate the `tt` prefix before treating an entry as an
IMDb movie/title link.

## Queries and answers

Queries describe a movie someone is trying to remember. Their `title` is the
request title, not the movie title. Train/dev records include `id`, `text`,
`title`, `domain`, source URLs, answer identifiers, and `sentence_annotations`.
The inspected test record only contains `id`, `domain`, `title`, `text`, and
`sentence_annotations`.

Each qrel row is `query_id 0 document_id relevance`. For example,
`763 0 16742289 1` associates query `763` with relevant corpus document
`16742289`. Join on `doc_id`, not page title. Keep train, dev, and test separate
when building and evaluating retrieval.

## Read the first extracted corpus record

Run this Python snippet from the repository root using the backend environment:

```python
import json

with open("data/raw/corpus.jsonl", encoding="utf-8") as lines:
    record = json.loads(next(lines))
    print(record["doc_id"], record["page_title"])
    print(record["sections"].keys())
```

For ingestion, iterate over `lines` and decode each line with `json.loads`.
