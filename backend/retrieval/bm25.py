"""Build and search the lexical movie index."""

import html
import re
import unicodedata
from array import array
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np
import snowballstemmer
from rank_bm25 import BM25Okapi

from models.movie import Movie

from .corpus import extract_cast, extract_plot, extract_year, records

DEFAULT_CONFIG = Path(__file__).parent.parent / "config.toml"


STOPWORDS = frozenset(
    """a an the and or of to in on at for from with by as is are was were be been being
i me my we our you your he him his she her it its they them their this that these
those who which what where when while how do does did have has had will would
can could should up out into than then there here s
""".split()
)


class Tokenizer:
    def __init__(self, stemming=True, remove_stopwords=True):
        self.remove_stopwords = remove_stopwords
        stemmer = snowballstemmer.stemmer("english")
        self.stem = lru_cache(maxsize=100_000)(stemmer.stemWord) if stemming else str

    def __call__(self, text):
        text = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
        words = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
        return [
            self.stem(word)
            for word in words
            if not self.remove_stopwords or word not in STOPWORDS
        ]


class MovieIndex:
    def __init__(self, movies, tokens, tokenizer, k1=1.5, b=0.75):
        if not movies:
            raise ValueError(
                "No usable plots found; check corpus_path and plot_sections."
            )
        self.movies = movies
        self.tokenizer = tokenizer
        self.bm25 = BM25Okapi(tokens, k1=k1, b=b)
        self._postings = self._build_postings()

    def _build_postings(self):
        postings = defaultdict(lambda: (array("i"), array("i")))
        for position, frequencies in enumerate(self.bm25.doc_freqs):
            for term, frequency in frequencies.items():
                positions, counts = postings[term]
                positions.append(position)
                counts.append(frequency)

        bm25 = self.bm25
        length_penalty = bm25.k1 * (
            1 - bm25.b + bm25.b * np.asarray(bm25.doc_len) / bm25.avgdl
        )
        for term, (positions, counts) in postings.items():
            positions = np.asarray(positions)
            counts = np.asarray(counts)

            # Precompute the BM25Okapi contribution for this term in each matching plot.
            weights = bm25.idf[term] * (
                counts * (bm25.k1 + 1) / (counts + length_penalty[positions])
            )
            postings[term] = positions, weights
        return postings

    def search(self, query, top_k=5):
        query_tokens = list(dict.fromkeys(self.tokenizer(query)))
        scores = np.zeros(len(self.movies))
        matched = np.zeros(len(self.movies), dtype=bool)
        for term in query_tokens:
            posting = self._postings.get(term)
            if posting is not None:
                positions, weights = posting
                scores[positions] += weights
                matched[positions] = True

        # Keep matching zero/negative scores and break ties by corpus position.
        positions = np.flatnonzero(matched)
        order = np.argsort(-scores[positions], kind="stable")[:top_k]
        return query_tokens, scores, positions[order].tolist()


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
        movies.append(
            Movie(
                str(record["doc_id"]),
                record["page_title"],
                plot,
                section,
                extract_year(record),
                extract_cast(record),
            )
        )
        tokens.append(terms)
        stats[f"section:{section}"] += 1
        if config["max_movies"] and len(movies) >= config["max_movies"]:
            break
    print(
        f"Scanned {stats['scanned']:,} records; indexed {len(movies):,} plots; "
        f"missing plots {stats['missing_plot']:,}; "
        f"empty after preprocessing {stats['empty_after_preprocessing']:,}; "
        f"missing identity {stats['missing_identity']:,}.",
        flush=True,
    )
    print(
        "Plot sources:",
        {key[8:]: value for key, value in stats.items() if key.startswith("section:")},
        flush=True,
    )
    if on_progress:
        on_progress("building", len(movies), stats["scanned"])
    index = MovieIndex(movies, tokens, tokenizer, config["k1"], config["b"])
    index.stats = dict(stats)
    return index
