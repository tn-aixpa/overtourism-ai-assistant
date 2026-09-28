"""Load the workflow reference documents used to ground methodology answers.

The modeling workflow and territorial-index design workflow are separate
narratives, so the caller selects the relevant document rather than merging
both into every answer. Documents are loaded at import time; edits take effect
after the application process restarts.
"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# app/utils/workflow_knowledge.py -> app/utils -> app -> repo root -> knowledge/
_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"
_WORKFLOW_PATHS = {
    "modeling": _KNOWLEDGE_ROOT / "workflow_modeling.md",
    "territorial_indexes": _KNOWLEDGE_ROOT / "workflow_territorial_indexes.md",
}


def _load_workflow_document(path: Path) -> str:
    if not path.exists():
        logger.error(f"Workflow document not found: {path}")
        return ""
    return path.read_text(encoding="utf-8").strip()


WORKFLOW_DOCUMENTS: dict[str, str] = {
    workflow_type: _load_workflow_document(path)
    for workflow_type, path in _WORKFLOW_PATHS.items()
}
# Backward-compatible alias for callers that specifically mean the original
# modeling workflow.
WORKFLOW_DOCUMENT: str = WORKFLOW_DOCUMENTS["modeling"]


def get_workflow_document(workflow_type: str) -> str:
    """Return the requested workflow document, or an empty string if missing."""
    return WORKFLOW_DOCUMENTS.get(workflow_type, "")


__all__ = ["WORKFLOW_DOCUMENT", "WORKFLOW_DOCUMENTS", "get_workflow_document"]
