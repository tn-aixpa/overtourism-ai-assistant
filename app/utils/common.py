from __future__ import annotations
import ast
import os
from contextvars import ContextVar
from typing import Optional, Dict, Any, Tuple, List
import json
import requests
import logging

logger = logging.getLogger(__name__)

# Never let a backend call hang a turn forever (a hung turn never sends
# "__done__").
BACKEND_TIMEOUT = 30  # seconds

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() == "true"
BACKEND_URL = os.environ.get("BACKEND_URL")


def _merge_auth_headers(headers: dict | None) -> dict:
    """Ensure Authorization is present, without overriding an explicitly-provided one."""

    merged = dict(headers) if headers else {}

    if AUTH_ENABLED and "Authorization" not in merged:
        merged["Authorization"] = f"Bearer {get_token()}"

    return merged


def get_data(url, headers=None, params=None):
    logger.info(f"Fetching data from URL: {url}")
    response = requests.get(
        url,
        headers=_merge_auth_headers(headers),
        params=params,
        timeout=BACKEND_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


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
# (territory data, scenario lists, ...), so the generic cap above is the right
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
    # Fixed, bounded catalog of territorial indexes (id/label/description/
    # years). Measured ~3.1k chars for the current 5 indexes with full
    # descriptions — the generic 1200-char default was cutting it off after
    # ~1.5 items, which is exactly what produced hallucinated/invented
    # extra indexes in practice. Same reasoning as
    # get_configuration_parameters above.
    "get_territorial_index_list": 8000,
    # Up to _MAX_LISTED_MUNICIPALITIES (120) {area_name, index_value} entries
    # (~50 chars each) plus a small header: cutting this at the 1200-char
    # default would drop most of a "which municipalities are above X" list.
    "query_territorial_index_values": 9000,
}


# Keys that carry UI-only payloads (widget dispatch data, map GeoJSON, raw plot
# arrays). They are meant to be consumed programmatically by the frontend and
# must NEVER reach an LLM prompt or long-lived state, at ANY nesting depth.
# Kept deliberately separate from _HEAVY_FIELDS below: _HEAVY_FIELDS only
# applies to list items when condensing for matching, whereas these are
# stripped recursively everywhere.
ASSISTANT_ACTION_KEY = "assistant_action_data"
_UI_ONLY_FIELDS = {
    ASSISTANT_ACTION_KEY,
    "geojsonStr",
    "plot_data",
}


def strip_plot_data(eval_data: Any) -> Any:
    """Drop the heavy 'plot_data' field from a clean_scenario()-shaped
    evaluation dict (see app/tools/executor_backend_tools.py) before it is
    written into any LONG-LIVED state — state.cognitive.context_cache,
    pending_temp_scenario, tool_results, etc.

    plot_data holds raw per-sample arrays (constraint curves, per-sample
    uncertainty/usage, capacity thresholds — potentially hundreds of
    points) that exist solely to feed the load/capacity plot widgets. Those
    widget tools are currently disabled (see
    app/tools/executors/analysis_widgets.py, entirely commented out), so
    nothing reads plot_data once it's cached: it just sits in
    context_cache for the rest of the session (context_cache is only
    pruned by topic change, not by size — see
    CognitiveState.prune_context_cache), gets duplicated by reference into
    tool_results / retrieved_context whenever get_context_details runs,
    and gets fully re-serialized (independently, once per place it's
    referenced) every time AgentState.dump_to_file runs. This is the
    single biggest source of avoidable memory growth in this app.

    Call this at the point data is WRITTEN into long-lived state, not at
    fetch time — a caller that genuinely needs plot_data for one immediate,
    transient use (e.g. building a widget payload right after fetching) can
    still read it off the raw dict returned by get_evaluation_data /
    get_temp_evaluation_data before this strips it. If the plot widgets are
    ever re-enabled, they should fetch plot_data fresh for that one call
    rather than expect it to have survived in context_cache.
    """
    if not isinstance(eval_data, dict) or "plot_data" not in eval_data:
        return eval_data
    return {k: v for k, v in eval_data.items() if k != "plot_data"}


def strip_ui_only_fields(obj: Any) -> Any:
    """Recursively drop UI-only keys (assistant_action_data, geojsonStr,
    plot_data) at ANY depth, through dicts, lists and tuples.

    This is the deep counterpart of the shallow, per-item stripping done by
    _condense_object. It exists because widget payloads such as
    {"assistant_action_data": [{"type": "SHOW_WIDGET", "payload":
    {"data": {"geojsonStr": "..."}}}]} sit several levels down, where the
    shallow strip never reaches them. Returns a new structure; the input is
    never mutated (so a caller can still dispatch the original payload).
    """
    if isinstance(obj, dict):
        return {
            k: strip_ui_only_fields(v)
            for k, v in obj.items()
            if k not in _UI_ONLY_FIELDS
        }
    if isinstance(obj, (list, tuple)):
        return [strip_ui_only_fields(item) for item in obj]
    return obj


def split_assistant_actions(result: Any) -> Tuple[Any, List[Any]]:
    """WRITE-TIME helper: separate a tool result into (clean_result, actions).

    `actions` is the list stored under 'assistant_action_data' (empty if
    absent) and must be dispatched to the frontend BEFORE the clean result is
    stored in tool_results / context_cache / any long-lived state. The clean
    result has the widget payload removed at every depth (including heavy
    leftovers like geojsonStr), but keeps small, LLM-relevant fields such as
    'success', 'response' and 'map_summary'.

    Typical use in the tool executor:

        clean, actions = split_assistant_actions(raw_result)
        dispatch_to_frontend(actions)          # widget payload goes out here
        state.cognitive.tool_results[key] = clean   # only the slim version stored
    """
    if not isinstance(result, dict):
        return strip_ui_only_fields(result), []

    actions = result.get(ASSISTANT_ACTION_KEY) or []
    if not isinstance(actions, list):
        actions = [actions]
    return strip_ui_only_fields(result), actions


def strip_assistant_action_data(result: Any) -> Any:
    """Convenience wrapper around split_assistant_actions for callers that
    only want the slim result and have already dispatched (or don't need) the
    widget actions."""
    clean, _ = split_assistant_actions(result)
    return clean


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
# known. Dropped (at the top level of each list item) when condensing
# list-shaped data for prompt injection.
# "plot_data" holds the raw per-sample arrays (curves, uncertainty, usage,
# ...) that back the load/capacity plot widgets — see clean_scenario in
# app/tools/backend_tools.py. It's only ever meant to be consumed
# programmatically to build a SHOW_WIDGET payload, never shown to the LLM.
# Note: the UI-only fields are additionally stripped recursively at any depth
# by strip_ui_only_fields before condensing runs.
_HEAVY_FIELDS = {
    "extras",
    "evaluation_data",
    "related_scenario_ids",
    "plot_data",
    "geojsonStr",
    ASSISTANT_ACTION_KEY,
}

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


def _condense(data: Any, max_items: int, max_field_chars: int) -> Any:
    """Internal recursive worker for condense_for_matching. Assumes UI-only
    fields were already stripped at every depth by the public wrapper, so it
    does not re-walk the structure for them."""
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
        return {k: _condense(v, max_items, max_field_chars) for k, v in data.items()}
    return data


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

    UI-only payloads (assistant_action_data, geojsonStr, plot_data) are
    removed first, recursively, at any depth — so a widget payload nested in
    a tool-result envelope never survives, regardless of where it sits.

    This is intentionally lossy: if the caller genuinely needs full detail
    on a specific object, the right move is another call to
    get_context_details for that one id, not carrying full payloads for
    every object across every prompt.
    """
    return _condense(strip_ui_only_fields(data), max_items, max_field_chars)


def truncate_for_prompt(obj: Any, max_chars: int = DEFAULT_MAX_CHARS_PER_ENTRY) -> str:
    """Public wrapper around the JSON-truncation used for prompt injection.
    Use this (not raw json.dumps/f-string interpolation) anywhere a tool
    result or other backend payload is about to be embedded in an LLM
    prompt, so growth is bounded consistently across the codebase."""
    return _truncate_json(obj, max_chars)


def render_agent_message(msg: Any, max_chars: int = 4000) -> str:
    """Render ONE agent message for the synthesis ("Agent Messages") prompt.

    Use this wherever that list is built, instead of str(msg) / f-string
    interpolation, which dumps Python reprs (single quotes, True/False) of the
    full payload — including widget data like geojsonStr — straight into the
    prompt.

    - Plain text messages pass through unchanged (only length-capped).
    - Dicts/lists are stripped of UI-only fields at any depth, then
      serialized with boundary-aware truncation.
    - Strings that are really the repr/JSON of a dict/list (e.g. someone
      already did str(result)) are parsed back, stripped, then rendered. If
      they can't be parsed (e.g. already truncated), they fall back to a
      plain length cap.
    """
    if isinstance(msg, str):
        text = msg.strip()
        if text[:1] in ("{", "["):
            parsed: Any = None
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                try:
                    parsed = ast.literal_eval(text)
                except (ValueError, SyntaxError, MemoryError, RecursionError):
                    parsed = None
            if isinstance(parsed, (dict, list)):
                return _truncate_json(strip_ui_only_fields(parsed), max_chars)
        if len(msg) <= max_chars:
            return msg
        omitted = len(msg) - max_chars
        return msg[:max_chars] + f"... [truncated, {omitted} more characters omitted]"

    return _truncate_json(strip_ui_only_fields(msg), max_chars)


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

    # TODO remove
    with open("logs/too_long_debug.txt", "w+") as fout:
        fout.write(prompt)

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

    IMPORTANT: a tool_results entry can be a FAILURE (result["success"] is
    False — see tool_executor_node, which stores failed attempts here too,
    not just successful ones). The omitted-keys note below must never tell
    the model a failed call "already ran successfully", or the reasoner
    reads that as "don't call it again" and silently refuses to retry a
    failed operation even when the user explicitly asks it to try again —
    that was a real bug: failed and successful prior results were described
    identically, so retry requests were being treated as already-satisfied.
    Failed keys are called out separately and explicitly marked retryable.
    """
    if not tool_results:
        return "None"

    keys = list(tool_results.keys())
    shown_keys = keys[-max_entries:]
    omitted_keys = keys[:-max_entries] if len(keys) > max_entries else []

    lines = []
    if omitted_keys:
        succeeded = [
            k for k in omitted_keys if (tool_results.get(k) or {}).get("success", True)
        ]
        failed = [k for k in omitted_keys if k not in succeeded]
        if succeeded:
            lines.append(
                f"[{len(succeeded)} older SUCCESSFUL result(s) omitted for brevity: "
                f"{', '.join(succeeded)}. These tools already ran successfully "
                "earlier in this session — only re-run them if you need fresh data.]"
            )
        if failed:
            lines.append(
                f"[{len(failed)} older FAILED result(s) omitted for brevity: "
                f"{', '.join(failed)}. These tools did NOT succeed earlier — "
                "do not treat them as already done. If the user is asking to "
                "retry/try again, call the same tool again with the same "
                "(or corrected) arguments.]"
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
        entry = tool_results[key]
        status = (
            "FAILED — do not treat as already done; retry if the user asks"
            if isinstance(entry, dict) and entry.get("success") is False
            else "succeeded"
        )
        condensed = condense_for_matching(entry)
        entry_max_chars = _max_chars_for_tool(key, max_chars_per_entry)
        lines.append(
            f"### {key} [{status}]\n{_truncate_json(condensed, entry_max_chars)}"
        )

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
                continue
            # This key doesn't fit whole. Rather than dropping it outright —
            # which silently discards the actual payload in envelopes like
            # {"success": ..., "output": {...}, "error": ...} whenever the
            # trivial sibling keys already fit — recurse into it so it can
            # still contribute a partial (but real) value. Only if even a
            # single-key rendering of it can't fit at all do we fall back to
            # omitting it.
            remaining_budget = max(budget - len(_dump(kept)), _note_reserve)
            inner = _truncate_json(value, remaining_budget, _note_reserve=0)
            try:
                # Clean case: the recursed truncation stayed valid JSON
                # (nothing inside it needed its own omission note), so it
                # nests in as real structure.
                kept[key] = json.loads(inner)
            except (TypeError, ValueError):
                # inner carries an appended non-JSON note (e.g. "... [N
                # more items omitted]") — build this key's entry as raw
                # text rather than JSON-string-encoding it, so the note and
                # partial structure stay human/model-readable instead of
                # turning into an escaped blob.
                prefix = _dump(kept)[:-1] if kept else "{"
                sep = ",\n" if kept else "\n"
                result = f'{prefix}{sep}  "{key}": {inner}\n}}'
                if len(result) <= budget + _note_reserve:
                    if omitted_keys:
                        result += (
                            f"\n... [{len(omitted_keys)} more key(s) omitted "
                            f"for space: {omitted_keys}. Data was NOT lost — "
                            "say so if you summarize this, rather than "
                            "presenting it as complete.]"
                        )
                    return result
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
