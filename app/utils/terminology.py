"""
Terminology consistency helper for Italian (or any other) user-facing output.

Problem this solves:
    Prompts that translate/rephrase content into the user's language (see
    app.prompts.answer_generation.generate_answer and
    app.prompts.scanarios.generate_summary) are only told the *target
    language*, not the *target vocabulary*. Left to its own devices, an LLM
    will render the same English domain concept differently across turns
    (e.g. "problema" vs "problematica" vs "criticità" for "problem"),
    which reads as inconsistent/unprofessional once a user notices it.

Approach:
    Rather than dumping the entire GLOSSARY into every prompt (wasteful, and
    dilutes the instruction the more the glossary grows), we scan the
    *source* text that is about to be translated/rephrased for known English
    glossary terms (and their aliases) and only surface the Italian
    translation for terms that are actually present. This keeps the
    instruction short and directly relevant every time.

    This is intentionally a simple whole-word/phrase substring matcher, not
    a fuzzy or embedding-based one: exact terminology enforcement wants
    precision, not recall. If a concept is phrased in a way this doesn't
    catch, the model still falls back to its own translation for that
    instance — this is a floor, not a full constrained-decoding system.
"""

import re

# ---------------------------------------------------------------------------
# GLOSSARY
# ---------------------------------------------------------------------------
# A list of entries: {term, definition, aliases, related_terms, examples, it}
# The agent can query this via the `lookup_glossary` tool.
#
# - "term": canonical English name for the concept (used as the stable ID
#   elsewhere in the code, e.g. app.utils.terminology).
# - "aliases": English-only synonyms/variants used for fuzzy matching
#   (e.g. matching "issue" or "challenge" back to "problem").
# - "it": list of Italian terms for this concept. The FIRST item is the
#   canonical translation — the one prompts should actually generate (see
#   app.utils.terminology.build_terminology_block). Additional items are
#   accepted variants, useful for matching Italian user input back to this
#   entry (via lookup_glossary) even if they're not what we want the model
#   to output.
#
# Keep "it" as the single source of truth for output terminology: if you
# want the model to start saying "criticità" instead of "problema", change
# it here — don't rely on the model improvising, or different prompts will
# drift apart again.

GLOSSARY: list = [
    {
        "term": "problem",
        "definition": (
            "A critical situation or phenomenon to be analyzed or managed within the platform "
            "(e.g., overtourism, extreme weather events, unregistered tourism). "
            "A Problem is the top-level concept: it owns one or more Proposals."
        ),
        "aliases": ["issue", "challenge", "problematic", "ambit"],
        "related_terms": ["proposal", "scenario"],
        "examples": [
            "Overtourism in the historic centre",
            "Mobility congestion during peak season",
        ],
        "it": ["problema", "ambito"],
    },
    {
        "term": "proposal",
        "definition": (
            "A possible strategy or intervention designed to address a specific Problem. "
            "A Proposal groups one or more Scenarios that explore different parameter configurations "
            "for that strategy. Each Proposal belongs to exactly one Problem."
        ),
        "aliases": ["strategy", "intervention", "solution"],
        "related_terms": ["problem", "scenario"],
        "examples": ["Introduce visitor caps", "Promote off-peak mobility incentives"],
        "it": ["proposta", "soluzione"],
    },
    {
        "term": "scenario",
        "definition": (
            "A simulation run that explores the consequences of a specific set of parameter changes "
            "within a Proposal. Scenarios are used to evaluate and compare alternative configurations "
            "of the same strategy. Each Scenario belongs to exactly one Proposal."
        ),
        "aliases": ["simulation", "run", "configuration"],
        "related_terms": ["proposal", "problem", "evaluation"],
        "examples": [
            "Visitor cap at 500/day",
            "Visitor cap at 1000/day with shuttle service",
        ],
        "it": ["scenario"],
    },
    {
        "term": "evaluation",
        "definition": (
            "The computed output data associated with a Scenario after a simulation run. "
            "Contains KPIs, metrics, and model outputs that allow comparing Scenarios."
        ),
        "aliases": ["result", "output", "kpi", "metrics"],
        "related_terms": ["scenario"],
        "examples": ["Congestion index reduction by 30%", "Visitor satisfaction score"],
        "it": ["valutazione"],
    },
    {
        "term": "overtourism",
        "definition": (
            "A phenomenon where the number of tourists visiting a destination exceeds one or more of it's "
            "constraint capacities, causing negative impacts on residents, infrastructure, or the environment."
        ),
        "aliases": ["over-tourism", "mass tourism"],
        "related_terms": ["problem", "mobility", "visitor cap"],
        "examples": [],
        # "overtourism" (used as a loanword) is what Italian tourism-policy
        # literature and domain experts actually say; "turismo eccessivo"
        # reads as a gloss, kept only as a recognized variant.
        "it": ["overtourism", "mancanza di equilibrio turistico"],
    },
    {
        "term": "digital twin",
        "definition": (
            "A virtual replica of a physical destination (city, region, attraction) used to simulate "
            "the effects of management decisions before implementing them in the real world. "
            "This platform is built around the digital twin concept."
        ),
        "aliases": ["DT", "digital model"],
        "related_terms": ["scenario", "simulation"],
        "examples": [],
        "it": ["gemello digitale"],
    },
    {
        "term": "tenant",
        "definition": (
            "An isolated organisational unit within the platform, typically representing a destination "
            "or municipality (e.g., 'molveno'). All data (problems, proposals, scenarios) is scoped "
            "to a tenant."
        ),
        "aliases": ["destination", "municipality", "organisation"],
        "related_terms": ["problem", "proposal", "scenario"],
        "examples": ["molveno"],
        # Deliberately left untranslated: "tenant" is used as-is in Italian
        # SaaS/platform contexts and a literal translation ("inquilino")
        # would be actively confusing here.
        "it": ["tenant"],
    },
    {
        "term": "constraint capacity",
        "definition": (
            "The maximum acceptable value for a specific constraint before it is considered "
            "violated. A constraint capacity may refer to the number of visitors, parked cars, "
            "accommodation occupancy, restaurant demand, beach attendance, or any other resource "
            "or indicator used in the simulation."
        ),
        "aliases": ["capacity", "constraint threshold", "limit", "maximum capacity"],
        "related_terms": ["constraint", "sustainability", "overtourism"],
        "examples": [
            "Maximum number of visitors in the historic centre.",
            "Maximum parking occupancy.",
            "Maximum beach attendance.",
        ],
        "it": ["capacità di carico"],
    },
    {
        "term": "sustainability",
        "definition": (
            "A measure of how often one or more constraints remain within their respective "
            "capacity limits during a simulation. It is expressed as the proportion of time "
            "or simulation outcomes in which the selected constraint (or all selected constraints) "
            "are not exceeded. A higher sustainability value indicates that capacity limits are "
            "respected more consistently."
        ),
        "aliases": [
            "sustainability index",
            "constraint compliance",
            "capacity compliance",
            "sustainability score",
        ],
        "related_terms": [
            "constraint capacity",
            "evaluation",
            "scenario",
            "uncertainty",
        ],
        "examples": [
            "A parking sustainability of 0.92 means the parking capacity is respected in 92% of the simulation.",
            "An overall sustainability of 0.81 means all considered constraints are simultaneously respected in 81% of the simulation.",
        ],
        "it": ["sostenibilità"],
    },
    {
        "term": "uncertainty",
        "definition": (
            "A measure of the confidence associated with a prediction or simulation result. "
            "Uncertainty reflects the expected reliability of the model output and arises from "
            "(i) assumptions about people behaviour and other tourism-related processes, and "
            "(ii) approximations introduced by the statistical and computational models. "
        ),
        "aliases": [
            "confidence",
            "confidence level",
            "prediction uncertainty",
            "model uncertainty",
            "forecast uncertainty",
            "uncertainty band",
        ],
        "related_terms": [
            "evaluation",
            "scenario",
            "prediction",
            "simulation",
        ],
        "examples": [],
        "it": ["incertezza"],
    },
]


def _find_matches(text: str) -> dict:
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

    Returns "" if no glossary terms were found (so callers can safely
    concatenate this into a prompt without an extra blank-section check).
    """
    combined = "\n".join(t for t in texts if t)
    matches = _find_matches(combined)

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
