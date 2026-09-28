"""
Reads the app's curated domain knowledge — everything under
`knowledge/glossary/`, in Open Knowledge Format (OKF, see
knowledge/index.md) — and adapts it into the shape the rest of the app
expects.

One bundle, one concern: every concept is a `GlossaryTerm` markdown file in
`knowledge/glossary/`, read the same way regardless of subject — platform
concepts (Problem, Proposal, Scenario, ...) and the territorial-indices
framework's own vocabulary (currently just Territorial Index) are all just
entries in GLOSSARY that link to each other via `related_terms`. Terms
belonging to the territorial-indices framework are tagged
`territorial-index` in their frontmatter if you need to filter to just
those.

The concrete, individual indexes (e.g. "Indice di ricettività") are NOT
glossary entries: they are not static domain vocabulary, they're backend
data (their list, descriptions, and available years can change), so they
are fetched live via the `get_territorial_index_list` tool
(app.tools.backend_tools.get_territorial_index_list) instead of being
hardcoded here. Do not add one GlossaryTerm file per index — that would
just go stale the next time the backend's index list changes.

Backs the `lookup_glossary` tool
(app.agent.nodes.tool_executor.execute_lookup_glossary) and
build_terminology_block, which keeps generated Italian text
terminologically consistent — see its docstring below for why.

The bundle is parsed at runtime, so editing a markdown file under
`knowledge/glossary/` (fixing a formula, adding a term) takes effect on
the next process start — no code change needed. Do not reintroduce a
hardcoded Python list/dict for this kind of content; add a markdown
concept file under `knowledge/glossary/` instead (see AGENTS.md).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import re
import logging

from app.utils.okf import load_bundle

logger = logging.getLogger(__name__)

# app/utils/knowledge.py -> app/utils -> app -> repo root -> knowledge/
_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"
_GLOSSARY_DIR = _KNOWLEDGE_ROOT / "glossary"


# =============================================================================
# GLOSSARY (platform terminology + territorial-indices framework, EN/IT)
# =============================================================================


def _build_glossary() -> List[Dict[str, Any]]:
    docs = load_bundle(_GLOSSARY_DIR, okf_type="GlossaryTerm")
    if not docs:
        logger.error(f"Glossary OKF bundle not found or empty: {_GLOSSARY_DIR}")

    glossary = []
    for doc in docs:
        term = doc.frontmatter.get("term") or doc.title.lower()
        glossary.append(
            {
                "term": term,
                "title": doc.title,
                "definition": doc.first_paragraph(),
                "aliases": doc.frontmatter.get("aliases", []),
                "related_terms": doc.frontmatter.get("related_terms", []),
                "examples": doc.bullet_section("Examples"),
                "it": doc.frontmatter.get("it", []),
                "tags": doc.frontmatter.get("tags", []),
            }
        )
    return glossary


# Loaded once at import time, same as the old hardcoded list — restart the
# process (or add a reload hook, if that's ever needed) to pick up bundle
# edits, exactly as before with the single-file doc.
GLOSSARY: list = _build_glossary()


def find_glossary_term(query: str) -> Optional[Dict[str, Any]]:
    """
    Look up a single GLOSSARY entry by term or alias (case-insensitive,
    exact match). Returns None if nothing matches. This is the read path
    for the `lookup_glossary` tool: it returns the term's own definition
    plus its declared `related_terms` — not a fuzzy full-text search across
    unrelated entries, so asking about "phenomenon" doesn't also surface
    every index that happens to link back to it.
    """
    q = query.strip().lower()
    if not q:
        return None
    for entry in GLOSSARY:
        candidates = [entry["term"]] + list(entry.get("aliases", []))
        if q in (c.lower() for c in candidates):
            return entry
    return None


def _find_glossary_matches(text: str) -> dict:
    """
    Scan `text` for GLOSSARY terms/aliases (English side only — matching is
    meant to catch English source text before it gets rendered in Italian).

    Returns {canonical_english_term: canonical_italian_translation}, deduped
    and in GLOSSARY order (stable output, easier to eyeball in logs). The
    canonical Italian translation is always entry["it"][0] — later items in
    "it" are recognized variants (useful for matching Italian input back to
    an entry) but are never what we instruct the model to output, precisely
    to avoid the "same concept, three different translations" problem.
    """
    if not text:
        return {}

    matches: dict[str, str] = {}

    for entry in GLOSSARY:
        term = entry["term"]
        it_translations = entry.get("it") or []
        if not it_translations:
            continue
        canonical_it = it_translations[0]

        candidates = [term] + list(entry.get("aliases", []))

        for candidate in candidates:
            pattern = r"\b" + re.escape(candidate) + r"\b"
            if re.search(pattern, text, flags=re.IGNORECASE):
                matches[term] = canonical_it
                break

    return matches


def build_terminology_block(*texts: str) -> str:
    """
    Build a prompt-ready terminology block from one or more source texts.

    Problem this solves: prompts that translate/rephrase content into the
    user's language are only told the *target language*, not the *target
    vocabulary*. Left to its own devices, an LLM will render the same
    English domain concept differently across turns (e.g. "problema" vs
    "problematica" vs "criticità" for "problem"), which reads as
    inconsistent/unprofessional once a user notices it. Rather than
    dumping the entire GLOSSARY into every prompt, we scan the source text
    for known terms/aliases and only surface the Italian translation for
    terms actually present — short and directly relevant every time.

    Returns "" if no glossary terms were found (so callers can safely
    concatenate this into a prompt without an extra blank-section check).
    """
    combined = "\n".join(t for t in texts if t)
    matches = _find_glossary_matches(combined)

    if not matches:
        return ""

    lines = "\n".join(f'- "{en}" → "{it}"' for en, it in matches.items())

    return (
        "## Terminology\n"
        "The following domain terms appear in the source content below. "
        "When your answer refers to these concepts, you MUST use exactly "
        "the Italian translation given here — do not substitute a synonym "
        "or an alternate translation, even if it sounds more natural:\n"
        f"{lines}\n"
    )
