"""
Reads and searches "indici territoriali.md" — the reference documentation
for the platform's territorial indices framework: what a *Fenomeno*,
*Indice*, *combinatore*, and *macro area* are, and the full list of
currently available indices with their formulas and source data.

The document is parsed at runtime rather than hardcoded, so any edit to
the .md file (a new index added, a formula corrected, ...) is picked up
automatically without a code change. Backs the `lookup_territorial_index`
tool (see app.agent.nodes.tool_executor.execute_lookup_territorial_index).
"""

from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

_DOC_PATH = Path(__file__).parent / "indici territoriali.md"

# English -> Italian keyword expansions, so a query phrased in English
# ("what is an index", "phenomenon", "combinator") still matches this
# Italian-only document. Doc content matching itself is a plain substring
# search, so Italian queries need no expansion — this only helps the
# English side.
_ALIASES: dict = {
    "index": ["indice"],
    "indices": ["indici"],
    "indexes": ["indici"],
    "indicator": ["indice", "indicatore"],
    "indicators": ["indici", "indicatori"],
    "territorial index": ["indice territoriale"],
    "territorial indices": ["indici territoriali"],
    "phenomenon": ["fenomeno"],
    "phenomena": ["fenomeni"],
    "combinator": ["combinatore"],
    "combiner": ["combinatore"],
    "macro area": ["macro area"],
    "macro-area": ["macro area"],
    "region": ["macro area"],
    "province": ["macro area", "provincia"],
    "formula": ["formula"],
    "glossary": ["glossario"],
}


def _load_raw_document() -> str:
    try:
        return _DOC_PATH.read_text(encoding="utf-8")
    except OSError as e:
        logger.error(f"Could not read territorial indices doc at {_DOC_PATH}: {e}")
        return ""


def get_full_document() -> str:
    """Return the full raw markdown documentation, or "" if it can't be read."""
    return _load_raw_document()


def _split_sections(raw: str) -> List[dict]:
    """
    Split the markdown into sections on "## " headers.

    Section 0 ("Introduzione e Glossario") is everything before the first
    "## " — the framework overview, the Fenomeno/Indice/combinatore/macro
    area glossary table, and the index list. Every subsequent entry is one
    "## <title>" block, i.e. one territorial index.
    """
    if not raw:
        return []

    parts = raw.split("\n## ")
    sections = []

    intro = parts[0].strip()
    if intro:
        sections.append({"title": "Introduzione e Glossario", "content": intro})

    for part in parts[1:]:
        title = part.split("\n", 1)[0].strip()
        content = ("## " + part).strip()
        sections.append({"title": title, "content": content})

    return sections


def list_index_titles() -> List[str]:
    """Titles of every documented index — every '## Indice ...' section, excluding the intro and the 'Glossario' section."""
    sections = _split_sections(_load_raw_document())
    return [s["title"] for s in sections if s["title"].startswith("Indice")]


def _expand_query_tokens(query: str) -> List[str]:
    tokens = [t.strip().lower() for t in query.split() if t.strip()]
    expanded = set(tokens)
    lowered_query = query.lower()
    for en_term, it_terms in _ALIASES.items():
        if en_term in lowered_query:
            expanded.update(it_terms)
    return list(expanded)


def search_territorial_indices(query: str) -> List[dict]:
    """
    Case-insensitive fuzzy search over the territorial indices doc.

    Matches expanded query tokens (see _ALIASES) against each section's
    title and content. Returns full matching sections ({"title", "content"})
    verbatim — including the exact formula and source columns/aggregation/
    resolution — so nothing about a calculation is paraphrased away.
    """
    raw = _load_raw_document()
    sections = _split_sections(raw)
    if not sections:
        return []

    tokens = _expand_query_tokens(query)
    if not tokens:
        return []

    matches = []
    for section in sections:
        haystack = (section["title"] + "\n" + section["content"]).lower()
        if any(tok in haystack for tok in tokens):
            matches.append(section)

    return matches
