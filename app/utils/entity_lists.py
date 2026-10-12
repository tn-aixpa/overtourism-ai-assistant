"""Helpers shared by everything that deals with the "list of problems /
proposals / scenarios" tool results.

Problems, proposals and scenarios used to be listed by three separate tools
(list_available_problems / _proposals / _scenarios). They are now served by a
single tool, list_available_entities, whose output is keyed by entity type:

    {"problems": [...], "proposals": [...], "scenarios": [...]}

(only the requested types are present). This module is the one place that
knows how to read those results back out of ``state.cognitive.tool_results``
— it also understands the legacy per-entity result keys, so sessions that
were persisted before the merge keep working.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Union

ENTITY_TYPES: tuple[str, ...] = ("problems", "proposals", "scenarios")
LIST_TOOL_NAME = "list_available_entities"

# Result keys used before the three list tools were merged.
_LEGACY_LIST_TOOLS: Dict[str, str] = {
    "list_available_problems": "problems",
    "list_available_proposals": "proposals",
    "list_available_scenarios": "scenarios",
}


def _entity_type_from_token(token: Any) -> Optional[str]:
    """Map 'problem', 'Problems', 'list_available_problems', ... to the
    canonical plural entity type, or None if it isn't recognised."""
    if not isinstance(token, str):
        return None
    text = token.strip().lower()
    if text in _LEGACY_LIST_TOOLS:
        return _LEGACY_LIST_TOOLS[text]
    if text in ENTITY_TYPES:
        return text
    if text + "s" in ENTITY_TYPES:
        return text + "s"
    return None


def normalize_entity_types(
    value: Union[None, str, Iterable[str]], default_all: bool = True
) -> List[str]:
    """Normalize an ``entity_types`` argument into an ordered, de-duplicated
    list of canonical types.

    Accepts None, a single string or an iterable of strings, tolerating
    singular/plural and the legacy tool names. ``None`` / empty means "all
    three" when ``default_all`` is true. Raises ValueError for anything
    unrecognised, naming the valid values so the model can correct itself.
    """
    if value is None or value == [] or value == "":
        return list(ENTITY_TYPES) if default_all else []
    if isinstance(value, str):
        value = [value]

    resolved: List[str] = []
    unknown: List[Any] = []
    for token in value:
        entity_type = _entity_type_from_token(token)
        if entity_type is None:
            unknown.append(token)
        elif entity_type not in resolved:
            resolved.append(entity_type)

    if unknown:
        raise ValueError(
            f"Unknown entity type(s) {unknown}; valid values are {list(ENTITY_TYPES)}"
        )
    # Keep a stable, canonical order regardless of how the caller listed them.
    return [t for t in ENTITY_TYPES if t in resolved]


def collect_listed_entities(
    tool_results: Dict[str, Any],
    entity_types: Optional[Iterable[str]] = None,
) -> Dict[str, List[Any]]:
    """Latest known list for each entity type, gathered from every successful
    listing result stored in ``tool_results``.

    Newest result wins per type (``tool_results`` preserves insertion order),
    so a list fetched after creating/deleting something supersedes an older
    one — while a type that was only listed earlier is still available. Types
    that were never listed are simply absent from the returned dict.
    """
    wanted = set(normalize_entity_types(entity_types))
    found: Dict[str, List[Any]] = {}

    for key in reversed(list(tool_results)):
        entry = tool_results[key]
        if isinstance(entry, dict) and entry.get("success") is False:
            continue
        output = entry.get("output", entry) if isinstance(entry, dict) else entry
        base_name = key.split("__", 1)[0]

        if base_name == LIST_TOOL_NAME and isinstance(output, dict):
            for entity_type in ENTITY_TYPES:
                items = output.get(entity_type)
                if (
                    entity_type in wanted
                    and entity_type not in found
                    and isinstance(items, list)
                ):
                    found[entity_type] = items
        elif base_name in _LEGACY_LIST_TOOLS and isinstance(output, list):
            entity_type = _LEGACY_LIST_TOOLS[base_name]
            if entity_type in wanted and entity_type not in found:
                found[entity_type] = output

    return found
