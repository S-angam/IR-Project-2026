"""Standalone, in-memory BM25 plot search; no API or model server required."""

import argparse
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import heapq
import html
import json
from pathlib import Path
import re
import sys
import tomllib
import unicodedata

from rank_bm25 import BM25Okapi
import snowballstemmer


DEFAULT_CONFIG = Path(__file__).with_name("config.toml")
STOPWORDS = frozenset("""a an the and or of to in on at for from with by as is are was were be been being
i me my we our you your he him his she her it its they them their this that these
those who which what where when while how do does did have has had will would
can could should up out into than then there here s
""".split())


@dataclass(frozen=True)
class Movie:
    movie_id: str
    title: str
    plot: str
    plot_section: str
    year: int | None = None
    cast: str | None = None


def extract_cast(record):
    for box in record.get("infoboxes") or []:
        value = (box.get("params") or {}).get("starring")
        if value:
            # Retain source markup rather than guessing a complete cast list.
            return str(value)[:4000]
    return None


def extract_year(record):
    """Use release metadata first; never infer a release year from plot events."""
    for box in record.get("infoboxes") or []:
        if "film" not in box.get("name", "").casefold():
            continue
        released = str((box.get("params") or {}).get("released", ""))
        released = re.sub(r"<!--.*?-->|<ref\b[^>]*>.*?</ref>", "", released,
                          flags=re.DOTALL | re.IGNORECASE)
        match = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", released)
        if match:
            return int(match.group(1))
    match = re.search(r"\((18\d{2}|19\d{2}|20\d{2})\s+film\)", record.get("page_title", ""))
    return int(match.group(1)) if match else None


class Tokenizer:
    def __init__(self, stemming=True, remove_stopwords=True):
        self.remove_stopwords = remove_stopwords
        stemmer = snowballstemmer.stemmer("english")
        self.stem = lru_cache(maxsize=100_000)(stemmer.stemWord) if stemming else str

    def __call__(self, text):
        text = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
        words = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
        return [self.stem(word) for word in words
                if not self.remove_stopwords or word not in STOPWORDS]


def extract_plot(record, section_names):
    sections = record.get("sections") or {}
    normalized = {key.casefold().strip().replace("_", " ").strip(): value
                  for key, value in sections.items()}
    for name in section_names:
        text = normalized.get(name)
        if isinstance(text, str) and text.strip():
            # Parsed sections include a heading such as 'Plot.\n'.
            text = re.sub(r"^" + re.escape(name) + r"\s*\.?\s*\n", "", text,
                          count=1, flags=re.IGNORECASE).strip()
            if text:
                return name, text
    return None, None


def records(path):
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON in {path}, line {line_number}") from error


class MovieIndex:
    def __init__(self, movies, tokens, tokenizer, k1=1.5, b=0.75):
        if not movies:
            raise ValueError("No usable plots found; check corpus_path and plot_sections.")
        self.movies = movies
        self.tokenizer = tokenizer
        self.bm25 = BM25Okapi(tokens, k1=k1, b=b)

    def search(self, query, top_k=5):
        query_tokens = list(dict.fromkeys(self.tokenizer(query)))
        scores = self.bm25.get_scores(query_tokens)
        # Do not return arbitrary zero-match documents for an unknown query.
        matches = (i for i, frequencies in enumerate(self.bm25.doc_freqs)
                   if any(token in frequencies for token in query_tokens))
        order = heapq.nsmallest(top_k, matches, key=lambda i: (-scores[i], i))
        return query_tokens, scores, order


def build_index(path, config, on_progress=None):
    tokenizer = Tokenizer(config["stemming"], config["remove_stopwords"])
    movies, tokens = [], []
    stats = Counter()
    if on_progress:
        on_progress("reading", 0, 0)
    for record in records(path):
        stats["scanned"] += 1
        if on_progress and stats["scanned"] % 100 == 0:
            on_progress("reading", len(movies), stats["scanned"])
        section, plot = extract_plot(record, config["plot_sections"])
        if not plot:
            stats["missing_plot"] += 1
            continue
        if not record.get("doc_id") or not record.get("page_title"):
            stats["missing_identity"] += 1
            continue
        terms = tokenizer(plot)
        if not terms:
            stats["empty_after_preprocessing"] += 1
            continue
        movies.append(Movie(str(record["doc_id"]), record["page_title"], plot, section,
                            extract_year(record), extract_cast(record)))
        tokens.append(terms)
        stats[f"section:{section}"] += 1
        if config["max_movies"] and len(movies) >= config["max_movies"]:
            break
    print(f"Scanned {stats['scanned']:,} records; indexed {len(movies):,} plots; "
          f"missing plots {stats['missing_plot']:,}; "
          f"empty after preprocessing {stats['empty_after_preprocessing']:,}; "
          f"missing identity {stats['missing_identity']:,}.", flush=True)
    print("Plot sources:", {key[8:]: value for key, value in stats.items()
                            if key.startswith("section:")}, flush=True)
    if on_progress:
        on_progress("building", len(movies), stats["scanned"])
    index = MovieIndex(movies, tokens, tokenizer, config["k1"], config["b"])
    index.stats = dict(stats)
    return index


def excerpt(movie, query_tokens, tokenizer):
    sentences = re.split(r"(?<=[.!?])\s+|\n+", movie.plot)
    best = max(sentences, key=lambda sentence:
               len(set(tokenizer(sentence)).intersection(query_tokens)))
    return " ".join(html.unescape(best).split())[:350]


def show_results(index, query, top_k, inspect_record=None, section_names=()):
    query_tokens, scores, order = index.search(query, top_k)
    print(f"\nQuery: {query}\nTokens: {query_tokens}")
    print("Not in index vocabulary:", [t for t in query_tokens if t not in index.bm25.idf])
    if not order:
        print("No matching plot terms. Try different words or increase max_movies.")
    for rank, position in enumerate(order, 1):
        movie = index.movies[position]
        matched = [t for t in query_tokens if t in index.bm25.doc_freqs[position]]
        print(f"{rank}. {movie.movie_id} | {movie.title} | score={scores[position]:.4f}")
        print(f"   section={movie.plot_section}; tokens={index.bm25.doc_len[position]}; "
              f"matched={matched}")
        print(f"   {excerpt(movie, query_tokens, index.tokenizer)}")
    if inspect_record is not None:
        section, plot = extract_plot(inspect_record, section_names)
        position = next((i for i, movie in enumerate(index.movies)
                         if movie.movie_id == str(inspect_record['doc_id'])), None)
        print(f"\nInspect: {inspect_record['doc_id']} | {inspect_record['page_title']}")
        print(f"Available sections: {list((inspect_record.get('sections') or {}).keys())}")
        if not plot:
            print("No usable configured plot section: data coverage/extraction issue.")
        elif position is None:
            print("Plot exists but was not indexed: check the movie limit or preprocessing.")
        else:
            matched = [t for t in query_tokens if t in index.bm25.doc_freqs[position]]
            missing = [t for t in query_tokens if t not in index.bm25.doc_freqs[position]]
            rank = 1 + sum(1 for i, score in enumerate(scores)
                           if (score > scores[position] or (score == scores[position] and i < position))
                           and any(t in index.bm25.doc_freqs[i] for t in query_tokens))
            print(f"section={section}; rank={rank if matched else 'no match'}; "
                  f"score={scores[position]:.4f}; tokens={index.bm25.doc_len[position]}")
            print(f"Matched terms: {matched}\nAbsent terms: {missing}")


def main():
    # Preserve accented movie titles in Windows terminals and redirected output.
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--query", help="Search once; omit to enter queries interactively")
    parser.add_argument("--limit", type=int, help="Override max_movies; 0 indexes all usable plots")
    parser.add_argument("--no-stemming", action="store_true", help="Compare preprocessing without stemming")
    parser.add_argument("--inspect-id", help="Diagnose one Wikipedia movie ID, including outside the index")
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))["bm25"]
    if args.limit is not None:
        config["max_movies"] = args.limit
    if args.no_stemming:
        config["stemming"] = False
    if type(config["max_movies"]) is not int or config["max_movies"] < 0:
        parser.error("max_movies must be a nonnegative integer (0 = all)")
    if type(config["top_k"]) is not int or config["top_k"] < 1:
        parser.error("top_k must be a positive integer")
    if config["k1"] <= 0 or not 0 <= config["b"] <= 1:
        parser.error("k1 must be positive and b must be between 0 and 1")
    path = (config_path.parent / config["corpus_path"]).resolve()
    if not path.is_file():
        parser.error(f"Corpus missing: {path}. Run 'uv run script/download_dataset.py' in backend first.")
    print(f"Corpus: {path}\nMovie limit: {config['max_movies']} (0 = all); "
          f"stemming: {config['stemming']}", flush=True)
    index = build_index(path, config)
    inspect_record = None
    if args.inspect_id:
        inspect_record = next((r for r in records(path) if str(r.get("doc_id")) == args.inspect_id), None)
        if inspect_record is None:
            print(f"ID {args.inspect_id} is absent from the corpus.")
    if args.query is not None:
        show_results(index, args.query, config["top_k"], inspect_record, config["plot_sections"])
    else:
        print("Enter a movie description. Empty input or Ctrl+C exits.")
        try:
            while query := input("\nQuery> ").strip():
                show_results(index, query, config["top_k"], inspect_record, config["plot_sections"])
        except (EOFError, KeyboardInterrupt):
            print()


if __name__ == "__main__":
    main()
