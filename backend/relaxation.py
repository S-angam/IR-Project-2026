"""Deterministic, inspectable uncertainty handling; no answer labels are consulted."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    uncertain_clues: tuple[str, ...] = ()
    auto_relax: bool = False


def detect_uncertain(text):
    # Keep the scope to a clause. Commas, sentence punctuation and line breaks stop it.
    pattern = r"\b(?:maybe|perhaps|possibly|I\s+think|I\s+guess|I\s+believe)\b[^.!?;,\n]*"
    return list(dict.fromkeys(m.group().strip() for m in re.finditer(pattern, text, re.I)))[:5]


def relaxation_details(query):
    if isinstance(query, str):
        query = RetrievalQuery(query, auto_relax=True)
    phrases = list(dict.fromkeys(query.uncertain_clues))
    if query.auto_relax:
        phrases = list(dict.fromkeys(phrases + detect_uncertain(query.text)))[:5]
    relaxed = query.text
    for phrase in sorted(phrases, key=len, reverse=True):
        if not phrase.strip() or phrase not in query.text:
            raise ValueError("Each uncertain clue must be an exact phrase from the current description.")
        relaxed = relaxed.replace(phrase, "")
    relaxed = re.sub(r"\s+", " ", relaxed).strip(" .!?;,\t\n")
    variants = [query.text]
    if relaxed and relaxed != query.text and phrases:
        variants.append(relaxed)
    return {"uncertain_clues": phrases, "variants": variants,
            "mode": "automatic" if query.auto_relax else "manual",
            "applied": len(variants) > 1}

