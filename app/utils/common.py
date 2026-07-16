from __future__ import annotations
from contextvars import ContextVar
from typing import Optional, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

# =========================
# PROMPT-SIZE GUARDS
# =========================
# Tool results (raw backend payloads) are the single biggest source of
# uncontrolled prompt growth in this codebase: they accumulate in
# CognitiveState.tool_results for the entire session and used to be
# JSON-dumped in full into every tool-selection prompt. These helpers keep
# that injection bounded regardless of how long the session runs, while
# still telling the LLM which tools already ran (so it can skip re-fetching).

DEFAULT_MAX_RESULT_ENTRIES = 6
DEFAULT_MAX_CHARS_PER_ENTRY = 1200


def build_prior_results_block(
    tool_results: Dict[str, Any],
    max_entries: int = DEFAULT_MAX_RESULT_ENTRIES,
    max_chars_per_entry: int = DEFAULT_MAX_CHARS_PER_ENTRY,
) -> str:
    """Render `tool_results` for prompt injection with a hard size cap.

    Only the most recent `max_entries` results are shown in full (each
    truncated to `max_chars_per_entry`). Older entries are referenced by key
    only, so the LLM still knows a tool already ran this session (and can
    decide to skip re-running it) without the full payload bloating every
    subsequent prompt forever.
    """
    if not tool_results:
        return "None"

    keys = list(tool_results.keys())
    shown_keys = keys[-max_entries:]
    omitted_keys = keys[:-max_entries] if len(keys) > max_entries else []

    lines = []
    if omitted_keys:
        lines.append(
            f"[{len(omitted_keys)} older result(s) omitted for brevity: "
            f"{', '.join(omitted_keys)}. These tools already ran successfully "
            "earlier in this session — only re-run them if you need fresh data.]"
        )

    for key in shown_keys:
        lines.append(f"### {key}\n{_truncate_json(tool_results[key], max_chars_per_entry)}")

    return "\n\n".join(lines)


def _truncate_json(obj: Any, max_chars: int) -> str:
    try:
        text = json.dumps(obj, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(obj)
    if len(text) > max_chars:
        omitted = len(text) - max_chars
        text = text[:max_chars] + f"\n... [truncated, {omitted} more characters omitted]"
    return text
_current_token: ContextVar[str | None] = ContextVar("_current_token", default=None)


def set_token(token: str) -> None:
    logger.debug(f"Setting auth token in current context: {token}")
    _current_token.set(token)

def get_token() -> str:
    token = _current_token.get()
    if token is None:
        raise RuntimeError("No auth token set in current context")
    return token
class GraphError(Exception):
    def __init__(self, details: Optional[str] = None):
        self.details = details
        super().__init__(self.details)

class RequestHandlingException(GraphError):
    """Exception raised when request handling fails."""
    def __init__(self, message: str):
        super().__init__(
            details=str(message)
        )
