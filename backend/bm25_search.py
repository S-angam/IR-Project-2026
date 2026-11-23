"""Standalone, in-memory BM25 plot search; no API or model server required."""

import argparse
import sys
import tomllib
from pathlib import Path

from retrieval.bm25 import DEFAULT_CONFIG, build_index
from retrieval.corpus import excerpt, extract_plot, records


def show_results(index, query, top_k, inspect_record=None, section_names=()):
    query_tokens, scores, order = index.search(query, top_k)
    print(f"\nQuery: {query}\nTokens: {query_tokens}")
    print(
        "Not in index vocabulary:", [t for t in query_tokens if t not in index.bm25.idf]
    )
    if not order:
        print("No matching plot terms. Try different words or increase max_movies.")
    for rank, position in enumerate(order, 1):
        movie = index.movies[position]
        matched = [t for t in query_tokens if t in index.bm25.doc_freqs[position]]
        print(
            f"{rank}. {movie.movie_id} | {movie.title} | score={scores[position]:.4f}"
        )
        print(
            f"   section={movie.plot_section}; tokens={index.bm25.doc_len[position]}; "
            f"matched={matched}"
        )
        print(f"   {excerpt(movie, query_tokens, index.tokenizer)}")
    if inspect_record is not None:
        section, plot = extract_plot(inspect_record, section_names)
        position = next(
            (
                i
                for i, movie in enumerate(index.movies)
                if movie.movie_id == str(inspect_record["doc_id"])
            ),
            None,
        )
        print(f"\nInspect: {inspect_record['doc_id']} | {inspect_record['page_title']}")
        print(
            f"Available sections: {list((inspect_record.get('sections') or {}).keys())}"
        )
        if not plot:
            print("No usable configured plot section: data coverage/extraction issue.")
        elif position is None:
            print(
                "Plot exists but was not indexed: check the movie limit or preprocessing."
            )
        else:
            matched = [t for t in query_tokens if t in index.bm25.doc_freqs[position]]
            missing = [
                t for t in query_tokens if t not in index.bm25.doc_freqs[position]
            ]
            rank = 1 + sum(
                1
                for i, score in enumerate(scores)
                if (
                    score > scores[position]
                    or (score == scores[position] and i < position)
                )
                and any(t in index.bm25.doc_freqs[i] for t in query_tokens)
            )
            print(
                f"section={section}; rank={rank if matched else 'no match'}; "
                f"score={scores[position]:.4f}; tokens={index.bm25.doc_len[position]}"
            )
            print(f"Matched terms: {matched}\nAbsent terms: {missing}")


def main():
    # Preserve accented movie titles in Windows terminals and redirected output.
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--query", help="Search once; omit to enter queries interactively"
    )
    parser.add_argument(
        "--limit", type=int, help="Override max_movies; 0 indexes all usable plots"
    )
    parser.add_argument(
        "--no-stemming",
        action="store_true",
        help="Compare preprocessing without stemming",
    )
    parser.add_argument(
        "--inspect-id",
        help="Diagnose one Wikipedia movie ID, including outside the index",
    )
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
        parser.error(
            f"Corpus missing: {path}. Run 'uv run script/download_dataset.py' in backend first."
        )
    print(
        f"Corpus: {path}\nMovie limit: {config['max_movies']} (0 = all); "
        f"stemming: {config['stemming']}",
        flush=True,
    )
    index = build_index(path, config)
    inspect_record = None
    if args.inspect_id:
        inspect_record = next(
            (r for r in records(path) if str(r.get("doc_id")) == args.inspect_id), None
        )
        if inspect_record is None:
            print(f"ID {args.inspect_id} is absent from the corpus.")
    if args.query is not None:
        show_results(
            index, args.query, config["top_k"], inspect_record, config["plot_sections"]
        )
    else:
        print("Enter a movie description. Empty input or Ctrl+C exits.")
        try:
            while query := input("\nQuery> ").strip():
                show_results(
                    index,
                    query,
                    config["top_k"],
                    inspect_record,
                    config["plot_sections"],
                )
        except (EOFError, KeyboardInterrupt):
            print()


if __name__ == "__main__":
    main()
