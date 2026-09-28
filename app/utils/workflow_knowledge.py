"""
Reads the app's workflow reference document — `knowledge/workflow.md` — and
exposes it as a single block of text.

This is deliberately NOT an OKF bundle (see app.utils.okf / app.utils.knowledge
and knowledge/index.md): the glossary is a graph of small, independently
addressable concept entries meant to be looked up one term at a time, while
`workflow.md` is one continuous document describing the end-to-end
methodology (identifying elements, modelling the territory, defining
Problems/Proposals/Scenarios, evaluating results). Splitting it into
per-concept entries and matching by term/alias — like lookup_glossary does —
would break the narrative and make it impossible to answer questions that
span sections (e.g. "what's the overall procedure?", "how does a Proposal
relate to a Scenario?"). So instead of parsing it, we just read it whole and
let the (methodological-tier) answer-generation step reason over the full
text — see the `explain_workflow` tool
(app.tools.executors.system_utility.execute_explain_workflow).

The file is read at import time, same as GLOSSARY in app.utils.knowledge —
editing knowledge/workflow.md takes effect on the next process start, no
code change needed.
"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# app/utils/workflow_knowledge.py -> app/utils -> app -> repo root -> knowledge/
_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"
_WORKFLOW_PATH = _KNOWLEDGE_ROOT / "workflow.md"


def _load_workflow_document() -> str:
    if not _WORKFLOW_PATH.exists():
        logger.error(f"Workflow document not found: {_WORKFLOW_PATH}")
        return ""
    return _WORKFLOW_PATH.read_text(encoding="utf-8").strip()


# Loaded once at import time, same pattern as GLOSSARY in app.utils.knowledge.
WORKFLOW_DOCUMENT: str = _load_workflow_document()

__all__ = ["WORKFLOW_DOCUMENT"]
