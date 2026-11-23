"""Read Wikipedia records and extract plot evidence."""

import html
import json
import re
from heapq import nlargest


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
        released = re.sub(
            r"<!--.*?-->|<ref\b[^>]*>.*?</ref>",
            "",
            released,
            flags=re.DOTALL | re.IGNORECASE,
        )
        match = re.search(r"\b(18\d{2}|19\d{2}|20\d{2})\b", released)
        if match:
            return int(match.group(1))
    match = re.search(
        r"\((18\d{2}|19\d{2}|20\d{2})\s+film\)", record.get("page_title", "")
    )
    return int(match.group(1)) if match else None


def extract_plot(record, section_names):
    sections = record.get("sections") or {}
    normalized = {
        key.casefold().strip().replace("_", " ").strip(): value
        for key, value in sections.items()
    }
    for name in section_names:
        text = normalized.get(name)
        if isinstance(text, str) and text.strip():
            # Parsed sections include a heading such as 'Plot.\n'.
            text = re.sub(
                r"^" + re.escape(name) + r"\s*\.?\s*\n",
                "",
                text,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
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
                raise ValueError(
                    f"Invalid JSON in {path}, line {line_number}"
                ) from error


def excerpt(movie, query_tokens, tokenizer, *, limit=350, sentence_count=1):
    sentences = re.split(r"(?<=[.!?])\s+|\n+", movie.plot)
    best = nlargest(
        sentence_count,
        enumerate(sentences),
        key=lambda item: len(set(tokenizer(item[1])).intersection(query_tokens)),
    )
    text = " … ".join(sentence for _, sentence in sorted(best) if sentence)
    return " ".join(html.unescape(text).split())[:limit]
