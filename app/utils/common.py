from __future__ import annotations
import os
from contextvars import ContextVar
from typing import Optional, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() == "true"


def _merge_auth_headers(headers: dict | None) -> dict:
    """Ensure Authorization is present, without overriding an explicitly-provided one."""

    merged = dict(headers) if headers else {}

    if AUTH_ENABLED and "Authorization" not in merged:
        merged["Authorization"] = f"Bearer {get_token()}"

    return merged


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

# Most tool results are raw backend payloads that can grow without bound
# (tenant data, scenario lists, ...), so the generic cap above is the right
# default. A few tools instead return a fixed, small, bounded payload
# (e.g. the full catalog of tunable simulation parameters, or a single
# scenario's evaluation summary) — capping those at the generic size cuts
# them off mid-structure (e.g. only the first one or two parameter groups
# survive), which the reasoning/answer-generation LLM then has no way to
# distinguish from "that's everything", and results in incomplete or
# invented answers. Give these a larger, still-bounded budget instead.
_LARGE_BUDGET_TOOLS = {
    # get_configuration_parameters' full catalog is ~9.9k chars as of the
    # current 5 groups / 23 parameters (measured, not guessed). 6000 was
    # silently dropping the last 2 groups. 14000 gives ~40% headroom for
    # the catalog to grow before this needs revisiting; the boundary-aware
    # truncation in _truncate_json is the real backstop if it ever does.
    "get_configuration_parameters": 14000,
    "create_new_temp_scenario": 4000,
}


def _max_chars_for_tool(tool_name: str | None, default: int) -> int:
    """Look up the prompt-injection char budget for a given tool/result key,
    stripping any '__N' collision suffix (see tool_executor's result_key)."""
    if not tool_name:
        return default
    base_name = tool_name.split("__", 1)[0]
    return _LARGE_BUDGET_TOOLS.get(base_name, default)


# Fields that regularly hold large/nested payloads (simulation output,
# free-form extras, etc.) and are almost never needed to *match* an object
# by name/description — only to inspect it once a specific id is already
# known. Dropped when condensing list-shaped data for prompt injection.
# "plot_data" holds the raw per-sample arrays (curves, uncertainty, usage,
# ...) that back the load/capacity plot widgets — see clean_scenario in
# app/tools/backend_tools.py. It's only ever meant to be consumed
# programmatically to build a SHOW_WIDGET payload, never shown to the LLM.
_HEAVY_FIELDS = {"extras", "evaluation_data", "related_scenario_ids", "plot_data"}

# Any single object's textual fields (name/description/...) get truncated to
# this many characters when condensing a list for name/intent matching.
DEFAULT_MAX_FIELD_CHARS = 300
# Hard cap on how many objects are shown in full when condensing a list.
DEFAULT_MAX_ITEMS_FOR_MATCHING = 40

# Absolute last-resort ceiling on any single prompt sent to the LLM. This is
# a safety net on top of the targeted truncation below: if something still
# slips through uncapped, the prompt gets shrunk here (with a warning)
# instead of failing outright against Anthropic's request-size limits.
MAX_PROMPT_CHARS = 60_000


def _condense_object(obj: Any, max_field_chars: int = DEFAULT_MAX_FIELD_CHARS) -> Any:
    """Strip heavy/nested fields from a single backend object and truncate
    its remaining string fields, so it stays cheap to include in a prompt
    while keeping enough (id, name, description, tags...) for matching."""
    if not isinstance(obj, dict):
        return obj
    condensed = {}
    for key, value in obj.items():
        if key in _HEAVY_FIELDS:
            continue
        if isinstance(value, str) and len(value) > max_field_chars:
            omitted = len(value) - max_field_chars
            value = value[:max_field_chars] + f"...[{omitted} chars omitted]"
        condensed[key] = value
    return condensed


def condense_for_matching(
    data: Any,
    max_items: int = DEFAULT_MAX_ITEMS_FOR_MATCHING,
    max_field_chars: int = DEFAULT_MAX_FIELD_CHARS,
) -> Any:
    """Shrink a raw backend list/detail payload down to only what's needed to
    match a user's intent to an id: id/name/description-type fields, with
    heavy nested payloads (extras, evaluation_data, ...) stripped and long
    text truncated. Never drops *which items exist* silently — if there are
    more than max_items, the extras are summarized by id/name only so the
    LLM still knows they exist and can ask to narrow the search instead of
    guessing.

    This is intentionally lossy: if the caller genuinely needs full detail
    on a specific object, the right move is another call to
    get_context_details for that one id, not carrying full payloads for
    every object across every prompt.
    """
    if isinstance(data, list):
        shown = [_condense_object(item, max_field_chars) for item in data[:max_items]]
        if len(data) > max_items:
            overflow = data[max_items:]
            overflow_ids = [
                item.get("id", item.get("name", "?")) if isinstance(item, dict) else "?"
                for item in overflow
            ]
            return {
                "items": shown,
                "note": (
                    f"{len(overflow)} additional item(s) not shown in full "
                    f"(ids/names only): {overflow_ids}. Narrow the query if one "
                    "of these is the intended match."
                ),
            }
        return shown
    if isinstance(data, dict):
        return {
            k: condense_for_matching(v, max_items, max_field_chars)
            for k, v in data.items()
        }
    return data


def truncate_for_prompt(obj: Any, max_chars: int = DEFAULT_MAX_CHARS_PER_ENTRY) -> str:
    """Public wrapper around the JSON-truncation used for prompt injection.
    Use this (not raw json.dumps/f-string interpolation) anywhere a tool
    result or other backend payload is about to be embedded in an LLM
    prompt, so growth is bounded consistently across the codebase."""
    return _truncate_json(obj, max_chars)


def enforce_prompt_budget(prompt: str, max_chars: int = MAX_PROMPT_CHARS) -> str:
    """Last line of defense: if a fully-built prompt is still over budget
    (e.g. a new injection point forgets to truncate), cut the middle down to
    size rather than letting the request fail against the provider's limit.
    Keeps the head (instructions) and tail (the actual question/output
    format) intact, since the bulky part is almost always the injected
    context in the middle."""
    if len(prompt) <= max_chars:
        return prompt

    logger.warning(
        f"Prompt exceeded {max_chars} chars ({len(prompt)} chars) — truncating "
        "the middle before sending. Consider tightening the source of this "
        "prompt so this doesn't need to trigger."
    )
    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars
    omitted = len(prompt) - max_chars
    return (
        prompt[:head_chars]
        + f"\n\n... [{omitted} characters truncated to fit the prompt budget] ...\n\n"
        + prompt[-tail_chars:]
    )


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
        # Condense (item-aware) BEFORE the char-level safety cut below. Doing
        # this the other way around — as this used to — truncates the raw
        # JSON string blindly, which can slice a list mid-object and drop
        # trailing items (e.g. the 2nd of 2 problems) with no indication
        # anything was cut. The model then treats the partial list as
        # complete and undercounts/hallucinates. condense_for_matching keeps
        # items whole and, if it does need to drop any, says so explicitly
        # via a "note" field instead of silently truncating mid-structure.
        condensed = condense_for_matching(tool_results[key])
        entry_max_chars = _max_chars_for_tool(key, max_chars_per_entry)
        lines.append(f"### {key}\n{_truncate_json(condensed, entry_max_chars)}")

    return "\n\n".join(lines)


def _dump(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)


def _truncate_json(obj: Any, max_chars: int, _note_reserve: int = 200) -> str:
    """JSON-serialize obj for prompt injection, capped at max_chars.

    Boundary-aware: for dicts and lists, whole top-level keys/items are kept
    or dropped as a unit — never sliced mid-object — and any drop is always
    called out with an explicit note (mirroring condense_for_matching's
    philosophy, but applied at the final serialization step too, since a
    structure like {"widgets": {"GroupA": [...], "GroupB": [...]}} can still
    exceed budget after condensing and needs the same treatment one level
    deeper). If a single key/item is itself too big to fit even alone, we
    recurse into it rather than dropping it outright, so partial content
    from a large group still beats no content from it.
    """
    text = _dump(obj)
    if len(text) <= max_chars:
        return text

    budget = max(max_chars - _note_reserve, max_chars // 2)

    if isinstance(obj, dict) and obj:
        kept: Dict[Any, Any] = {}
        omitted_keys = []
        for key, value in obj.items():
            candidate_text = _dump({**kept, key: value})
            if len(candidate_text) <= budget:
                kept[key] = value
            else:
                omitted_keys.append(key)
        if not kept:
            # Not even the first key fits whole: recurse into it so we still
            # return *something* structurally sound instead of nothing.
            first_key, first_val = next(iter(obj.items()))
            inner = _truncate_json(first_val, budget, _note_reserve=0)
            try:
                kept = {first_key: json.loads(inner)}
                result = _dump(kept)
            except (TypeError, ValueError):
                result = f'{{\n  "{first_key}": {inner}\n}}'
            omitted_keys = [k for k in obj if k != first_key]
        else:
            result = _dump(kept)
        if omitted_keys:
            result += (
                f"\n... [{len(omitted_keys)} more key(s) omitted for space: "
                f"{list(omitted_keys)}. Data was NOT lost — say so if you "
                "summarize this, rather than presenting it as complete.]"
            )
        return result

    if isinstance(obj, list) and obj:
        kept_items = []
        for item in obj:
            candidate_text = _dump(kept_items + [item])
            if len(candidate_text) <= budget:
                kept_items.append(item)
            else:
                break
        omitted_count = len(obj) - len(kept_items)
        result = _dump(kept_items) if kept_items else "[]"
        if omitted_count:
            result += (
                f"\n... [{omitted_count} more item(s) omitted for space. "
                "Data was NOT lost — say so if you summarize this, rather "
                "than presenting it as complete.]"
            )
        return result

    # Not a dict/list we can reason about structurally (e.g. a long string) —
    # this is the only case where a raw character slice is safe.
    omitted = len(text) - max_chars
    return text[:max_chars] + f"\n... [truncated, {omitted} more characters omitted]"


_current_token: ContextVar[str | None] = ContextVar("_current_token", default=None)


def set_token(token: str) -> None:
    logger.debug("Setting auth token in current context")
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
        super().__init__(details=str(message))
