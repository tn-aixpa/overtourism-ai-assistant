"""Typed handling of the tunable parameters exposed by the backend's
``/configuration`` endpoint (its ``"indexes"`` list).

Each entry has a ``kind`` that decides what a value for it looks like:

    scalar        a number                         e.g. parking price -> 15
    categorical   one of ``support`` (or no filter) e.g. weather       -> "rainy"
    distribution  a [low, high] range              e.g. parking capacity -> [400, 500]

This module is deliberately free of I/O and of any agent/LLM imports so it can
be unit-tested against sample ``/configuration`` payloads. It provides:

* ``build_catalog_view`` — what ``get_configuration_parameters`` returns: a
  compact, uniform description of the parameters (optionally filtered by
  name / category / keyword), instead of a dump of the raw payload.
* ``resolve_overrides`` — what ``create_new_temp_scenario`` uses to turn the
  model's requested changes into the exact ``params_overrides`` payload,
  validating every value against the parameter's kind, bounds, step and
  allowed values, and doing relative arithmetic ("double", "+20%") itself so
  the model never has to.

Value grammar accepted by ``resolve_overrides`` (per parameter):

    plain value       scalar: 15 | categorical: "rainy" / null | distribution: [400, 500]
    {"set": v}        same as the plain value
    {"add": d}        current + d              (scalar; both ends of a distribution)
    {"multiply": f}   current * f              (scalar; both ends of a distribution)
    {"percent": p}    current * (1 + p/100)    (scalar; both ends of a distribution)
    {"low": a, "high": b}   distribution only; either end may be omitted to keep it
    a bare number for a distribution = its new central value (width is kept)
"""

from __future__ import annotations

import difflib
import math
import re
import unicodedata
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

KIND_SCALAR = "scalar"
KIND_CATEGORICAL = "categorical"
KIND_DISTRIBUTION = "distribution"

# Strings a user/model may use to mean "no filter / all" for a categorical
# parameter (the UI shows "(tutte)"). Only consulted when the text is not one
# of the parameter's own allowed values.
_NO_FILTER_TOKENS = {"all", "any", "none", "null", "tutte", "tutti", "tutto"}

_RELATIVE_OPS = ("add", "multiply", "percent")
_OPS = ("set",) + _RELATIVE_OPS
_RANGE_KEYS = ("low", "high")

_EPS = 1e-9


class ParameterError(ValueError):
    """A requested value is not valid for its parameter. The message is
    written to be shown to the model (and, through it, to the user)."""


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _norm(text: Any) -> str:
    """Case-, accent- and punctuation-insensitive form used for matching."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _num(value: Any, what: str = "value") -> float:
    """Coerce a model-supplied number (int/float, or a numeric string such as
    "0.5" / "0,5") into a finite float."""
    if isinstance(value, bool):
        raise ParameterError(f"{what} must be a number, got {value!r}")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(" ", "")
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        try:
            number = float(text)
        except ValueError:
            raise ParameterError(f"{what} must be a number, got {value!r}") from None
    else:
        raise ParameterError(f"{what} must be a number, got {value!r}")
    if not math.isfinite(number):
        raise ParameterError(f"{what} must be a finite number")
    return number


def _decimals(*numbers: Any) -> int:
    """How many decimal places are needed to represent all `numbers` exactly
    (used to round away float noise such as 0.30000000000000004)."""
    places = 0
    for n in numbers:
        if n is None:
            continue
        exponent = Decimal(str(n)).as_tuple().exponent
        if isinstance(exponent, int) and exponent < 0:
            places = max(places, -exponent)
    return places


def _clean(number: float) -> Any:
    """12.0 -> 12 so payloads/messages don't carry spurious '.0'."""
    return int(number) if float(number).is_integer() else number


def _is_range(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    )


def _bounds(idx: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    lo, hi = idx.get("min_value"), idx.get("max_value")
    return (
        float(lo) if lo is not None else None,
        float(hi) if hi is not None else None,
    )


def _label(idx: Dict[str, Any]) -> str:
    return idx.get("label") or idx["name"]


def _unit(idx: Dict[str, Any]) -> str:
    return idx.get("unit") or ""


# --------------------------------------------------------------------------
# Reading the /configuration payload
# --------------------------------------------------------------------------


def load_indexes(raw: Any) -> List[Dict[str, Any]]:
    """The usable entries of a /configuration ``indexes`` list (dicts with a
    ``name``). Accepts the list itself or the whole payload."""
    if isinstance(raw, dict):
        raw = raw.get("indexes", [])
    if not isinstance(raw, list):
        return []
    return [idx for idx in raw if isinstance(idx, dict) and idx.get("name")]


def current_value(idx: Dict[str, Any]) -> Any:
    """The parameter's baseline value, in the same shape a new value takes:
    a number (scalar), a string or None for "no filter" (categorical), or
    [low, high] (distribution)."""
    kind = idx.get("kind")
    if kind == KIND_DISTRIBUTION:
        rng = idx.get("default_range")
        return list(rng) if _is_range(rng) else None
    if kind == KIND_CATEGORICAL:
        category = idx.get("default_category")
        return category if category is not None else idx.get("default")
    return idx.get("default")


def allowed_values(idx: Dict[str, Any]) -> Dict[str, Any]:
    """Compact statement of what is acceptable for this parameter."""
    kind = idx.get("kind")
    if kind == KIND_CATEGORICAL:
        return {"values": list(idx.get("support") or []), "null_means": "no filter (all)"}

    lo, hi = idx.get("min_value"), idx.get("max_value")
    allowed = {"min": lo, "max": hi, "step": idx.get("step")}
    if kind == KIND_DISTRIBUTION:
        allowed["value_is"] = "a [low, high] range within min..max"
    return {k: v for k, v in allowed.items() if v is not None}


def find_index(
    indexes: List[Dict[str, Any]], key: Any
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Resolve `key` (a parameter's ``name`` or its human ``label``,
    case/accent/punctuation-insensitive) to its entry.

    Returns ``(entry, [])`` on success, ``(None, suggestions)`` otherwise,
    where suggestions are the closest parameter names."""
    if not isinstance(key, str) or not key.strip():
        return None, []
    wanted = _norm(key)

    for idx in indexes:
        if idx["name"] == key:
            return idx, []
    for field in ("name", "label"):
        for idx in indexes:
            if idx.get(field) and _norm(idx[field]) == wanted:
                return idx, []

    candidates: Dict[str, str] = {}
    for idx in indexes:
        candidates.setdefault(_norm(idx["name"]), idx["name"])
        if idx.get("label"):
            candidates.setdefault(_norm(idx["label"]), idx["name"])
    close = difflib.get_close_matches(wanted, list(candidates), n=3, cutoff=0.5)
    suggestions: List[str] = []
    for match in close:
        if candidates[match] not in suggestions:
            suggestions.append(candidates[match])
    return None, suggestions


# --------------------------------------------------------------------------
# Catalog view (what get_configuration_parameters returns)
# --------------------------------------------------------------------------


def parameter_record(idx: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    """Uniform description of one parameter, whatever its kind."""
    record: Dict[str, Any] = {
        "name": idx["name"],
        "label": _label(idx),
        "kind": idx.get("kind"),
    }
    if _unit(idx):
        record["unit"] = _unit(idx)
    record["current"] = current_value(idx)
    record["allowed"] = allowed_values(idx)
    if full:
        if idx.get("description"):
            record["description"] = idx["description"]
        if idx.get("kind") == KIND_DISTRIBUTION and idx.get("distribution_family"):
            record["distribution"] = {
                "family": idx["distribution_family"],
                "fixed_params": idx.get("distribution_fixed_params") or {},
            }
    return record


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str) and v.strip()]


def _match_category(indexes: List[Dict[str, Any]], requested: List[str]):
    """Indexes whose category matches any requested one (equal, or one
    contains the other once normalised); plus the requested names that
    matched nothing."""
    selected, unmatched = [], []
    for wanted in requested:
        w = _norm(wanted)
        hits = [
            idx
            for idx in indexes
            if (c := _norm(idx.get("category") or "")) and (w == c or w in c or c in w)
        ]
        if hits:
            selected.extend(i for i in hits if i not in selected)
        else:
            unmatched.append(wanted)
    return selected, unmatched


def _match_search(indexes: List[Dict[str, Any]], query: str):
    """Indexes matching any keyword of `query` in name/label/category/
    description, best match (most keywords) first."""
    tokens = [t for t in _norm(query).split() if len(t) >= 3]
    if not tokens:
        return []
    scored = []
    for position, idx in enumerate(indexes):
        haystack = _norm(
            " ".join(
                str(idx.get(f) or "")
                for f in ("name", "label", "category", "description")
            )
        )
        score = sum(1 for t in tokens if t in haystack)
        if score:
            scored.append((-score, position, idx))
    return [idx for _, _, idx in sorted(scored, key=lambda s: (s[0], s[1]))]


def build_catalog_view(
    indexes: List[Dict[str, Any]],
    names: Any = None,
    category: Any = None,
    search: Optional[str] = None,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    """The payload of get_configuration_parameters.

    * no filter            -> every parameter, compact (no descriptions)
    * ``names``            -> exactly those parameters (by name or label)
    * ``category`` / ``search`` -> narrow the catalog (ANDed); ``names``
      takes precedence over both
    * ``detail``           -> "summary" | "full"; default is "summary" with
      no filter and "full" (descriptions, distribution shape) with one.
    """
    names_list = _as_list(names)
    categories = _as_list(category)
    query = search.strip() if isinstance(search, str) and search.strip() else None
    filtered = bool(names_list or categories or query)

    full = (detail == "full") or (detail != "summary" and filtered)

    unmatched: List[Dict[str, Any]] = []
    selected = list(indexes)

    if names_list:
        selected = []
        for requested in names_list:
            idx, suggestions = find_index(indexes, requested)
            if idx is None:
                unmatched.append({"requested": requested, "did_you_mean": suggestions})
            elif idx not in selected:
                selected.append(idx)
    else:
        if categories:
            selected, bad = _match_category(selected, categories)
            for requested in bad:
                unmatched.append({"requested_category": requested})
        if query:
            ranked = _match_search(selected, query)
            selected = ranked

    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for idx in selected:
        by_category.setdefault(idx.get("category") or "Other", []).append(
            parameter_record(idx, full=full)
        )

    view: Dict[str, Any] = {
        "total_parameters": len(indexes),
        "categories": list(dict.fromkeys(i.get("category") or "Other" for i in indexes)),
        "matched": len(selected),
        "parameters_by_category": by_category,
    }
    if unmatched:
        view["unmatched"] = unmatched
    if filtered and not selected:
        view["note"] = (
            "Nothing matched. Call again without filters to see every parameter, "
            "or use one of the listed categories."
        )
    return view


# --------------------------------------------------------------------------
# Resolving requested changes (what create_new_temp_scenario uses)
# --------------------------------------------------------------------------


def _parse_spec(idx: Dict[str, Any], spec: Any) -> Tuple[str, Any]:
    """Split a requested value into (operation, argument).

    Plain values become ("set", value). For a dict, exactly one of the
    operations set/add/multiply/percent, or (distribution only) low/high.
    """
    if not isinstance(spec, dict):
        return "set", spec

    keys = set(spec)
    ops = [k for k in _OPS if k in keys]
    range_keys = [k for k in _RANGE_KEYS if k in keys]
    unknown = keys - set(_OPS) - set(_RANGE_KEYS)
    is_distribution = idx.get("kind") == KIND_DISTRIBUTION

    if unknown or (ops and range_keys) or len(ops) > 1:
        raise ParameterError(
            f"unsupported value {spec!r}; use a plain value, or exactly one of "
            f"{list(_OPS)}" + (", or low/high" if is_distribution else "")
        )
    if range_keys:
        if not is_distribution:
            raise ParameterError("'low'/'high' only apply to range (distribution) parameters")
        return "bounds", {k: spec[k] for k in range_keys}
    if not ops:
        raise ParameterError(f"empty value {spec!r}")
    return ops[0], spec[ops[0]]


def _snap(value: float, idx: Dict[str, Any]) -> float:
    """Round to the parameter's step grid (anchored at min_value, like the
    UI slider) and keep the result inside [min, max]."""
    step = idx.get("step")
    if not step or step <= 0:
        return value
    lo, hi = _bounds(idx)
    anchor = lo if lo is not None else 0.0
    places = _decimals(step, lo)

    steps = math.floor((value - anchor) / step + 0.5)
    snapped = anchor + steps * step
    if hi is not None and snapped > hi + _EPS:
        snapped = anchor + math.floor((hi - anchor) / step + _EPS) * step
    if lo is not None and snapped < lo - _EPS:
        snapped = anchor
    return round(snapped, places)


def _check_bounds(value: float, idx: Dict[str, Any], what: str = "value") -> None:
    lo, hi = _bounds(idx)
    unit = f" {_unit(idx)}" if _unit(idx) else ""
    if (lo is not None and value < lo - _EPS) or (hi is not None and value > hi + _EPS):
        span = f"{_clean(lo) if lo is not None else '-inf'} to {_clean(hi) if hi is not None else 'inf'}"
        raise ParameterError(
            f"{what} {_clean(value)}{unit} is outside the allowed range ({span}{unit})"
        )


def _apply_relative(op: str, current: float, arg: Any) -> float:
    amount = _num(arg, f"'{op}' amount")
    if op == "add":
        return current + amount
    if op == "multiply":
        return current * amount
    return current * (1 + amount / 100.0)  # percent


def _resolve_scalar(idx: Dict[str, Any], spec: Any) -> Tuple[Any, str, List[str]]:
    op, arg = _parse_spec(idx, spec)
    notes: List[str] = []
    current = current_value(idx)

    if op == "set":
        if isinstance(arg, (list, tuple, dict)) or arg is None:
            raise ParameterError("needs a single number")
        target = _num(arg)
        how = "set"
    elif op in _RELATIVE_OPS:
        if current is None:
            raise ParameterError(
                f"has no current value to apply '{op}' to; give an absolute number"
            )
        target = _apply_relative(op, float(current), arg)
        how = f"{op} {_clean(_num(arg))}"
    else:
        raise ParameterError(f"unsupported operation '{op}' for a number")

    _check_bounds(target, idx, "resulting value" if op != "set" else "value")
    snapped = _snap(target, idx)
    if abs(snapped - target) > _EPS:
        notes.append(
            f"adjusted from {_clean(round(target, 6))} to {_clean(snapped)} "
            f"(allowed in steps of {_clean(idx['step'])})"
        )
    return _clean(snapped), how, notes


def _resolve_categorical(idx: Dict[str, Any], spec: Any) -> Tuple[Any, str, List[str]]:
    op, arg = _parse_spec(idx, spec)
    if op != "set":
        raise ParameterError(f"'{op}' does not apply to a choice parameter")
    if arg is None:
        return None, "set", []
    if not isinstance(arg, str):
        raise ParameterError(
            "needs a single text value (one choice only), or null for no filter"
        )

    support = [str(s) for s in (idx.get("support") or [])]
    wanted = _norm(arg)
    for option in support:
        if _norm(option) == wanted:
            return option, "set", []
    if wanted == "" or wanted in _NO_FILTER_TOKENS:
        return None, "set", []
    if not support:  # nothing to validate against: pass it through unchanged
        return arg, "set", []

    close = difflib.get_close_matches(wanted, [_norm(s) for s in support], n=2, cutoff=0.5)
    hint = [s for s in support if _norm(s) in close]
    raise ParameterError(
        f"{arg!r} is not an allowed choice; allowed: {support}"
        + (f" (did you mean {hint}?)" if hint else "")
        + ", or null for no filter"
    )


def _recenter(idx: Dict[str, Any], center: float, width: float) -> Tuple[float, float]:
    """New [low, high] of the given width whose centre — the mode for a
    triangular distribution, else the midpoint — is `center`, shifted back
    inside min..max if it would stick out."""
    params = idx.get("distribution_fixed_params") or {}
    anchor = 0.5
    if idx.get("distribution_family") == "triang" and isinstance(
        params.get("c"), (int, float)
    ):
        anchor = float(params["c"])

    low = center - anchor * width
    high = low + width
    lo_b, hi_b = _bounds(idx)
    if lo_b is not None and hi_b is not None and width >= hi_b - lo_b:
        return lo_b, hi_b
    if lo_b is not None and low < lo_b:
        low, high = lo_b, lo_b + width
    if hi_b is not None and high > hi_b:
        low, high = hi_b - width, hi_b
    return low, high


def _resolve_distribution(idx: Dict[str, Any], spec: Any) -> Tuple[Any, str, List[str]]:
    op, arg = _parse_spec(idx, spec)
    notes: List[str] = []
    current = current_value(idx)

    def need_current(why: str) -> Tuple[float, float]:
        if current is None:
            raise ParameterError(f"has no current range to {why}; give both [low, high]")
        return float(current[0]), float(current[1])

    if op == "set" and isinstance(arg, (list, tuple)):
        if len(arg) != 2:
            raise ParameterError("a range needs exactly two numbers: [low, high]")
        low, high = _num(arg[0], "low"), _num(arg[1], "high")
        how = "set"
    elif op == "set":
        if arg is None or isinstance(arg, dict):
            raise ParameterError("needs a [low, high] range, or one number for its centre")
        center = _num(arg)
        c_lo, c_hi = need_current("recentre")
        _check_bounds(center, idx, "central value")
        low, high = _recenter(idx, center, c_hi - c_lo)
        how = "recentred"
        notes.append(
            f"single number read as the central value; range width {_clean(c_hi - c_lo)} kept"
        )
    elif op == "bounds":
        if len(arg) == 2:
            low, high = _num(arg["low"], "low"), _num(arg["high"], "high")
        else:
            c_lo, c_hi = need_current("keep the other end of")
            low = _num(arg["low"], "low") if "low" in arg else c_lo
            high = _num(arg["high"], "high") if "high" in arg else c_hi
        how = "set " + "/".join(arg)
    elif op in _RELATIVE_OPS:
        c_lo, c_hi = need_current(f"apply '{op}' to")
        low, high = _apply_relative(op, c_lo, arg), _apply_relative(op, c_hi, arg)
        how = f"{op} {_clean(_num(arg))}"
    else:
        raise ParameterError(f"unsupported operation '{op}' for a range")

    if low >= high:
        raise ParameterError(
            f"the range must have low < high, got [{_clean(low)}, {_clean(high)}]"
        )
    _check_bounds(low, idx, "low end")
    _check_bounds(high, idx, "high end")

    snapped = [_snap(low, idx), _snap(high, idx)]
    if snapped[0] >= snapped[1]:
        raise ParameterError(
            f"the range [{_clean(low)}, {_clean(high)}] collapses to nothing once "
            f"rounded to steps of {_clean(idx.get('step'))}; widen it"
        )
    if abs(snapped[0] - low) > _EPS or abs(snapped[1] - high) > _EPS:
        notes.append(
            f"adjusted from [{_clean(round(low, 6))}, {_clean(round(high, 6))}] to "
            f"{[_clean(v) for v in snapped]} (allowed in steps of {_clean(idx['step'])})"
        )
    return [_clean(v) for v in snapped], how, notes


_RESOLVERS = {
    KIND_SCALAR: _resolve_scalar,
    KIND_CATEGORICAL: _resolve_categorical,
    KIND_DISTRIBUTION: _resolve_distribution,
}


def format_value(idx: Dict[str, Any], value: Any) -> str:
    """Human-readable value for recaps and messages."""
    unit = f" {_unit(idx)}" if _unit(idx) else ""
    if idx.get("kind") == KIND_CATEGORICAL:
        return "all (no filter)" if value is None else str(value)
    if _is_range(value):
        return f"{_clean(value[0])} – {_clean(value[1])}{unit}"
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{_clean(value)}{unit}"
    return str(value)


def resolve_overrides(indexes: List[Dict[str, Any]], values: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the requested changes and build the backend payload.

    Returns::

        {
          "payload":  {<parameter name>: <value sent to the backend>, ...},
          "changes":  [{"name", "label", "kind", "unit"?, "from", "to",
                        "summary", "how", "notes"?}, ...],
          "problems": [{"parameter", "reason", "name"?, "allowed"?,
                        "current"?, "did_you_mean"?}, ...],
        }

    Nothing is raised for a bad value: every problem is collected so the
    caller can report them all at once. When ``problems`` is non-empty the
    payload must not be used.
    """
    payload: Dict[str, Any] = {}
    changes: List[Dict[str, Any]] = []
    problems: List[Dict[str, Any]] = []
    seen: Dict[str, str] = {}

    for key, spec in values.items():
        idx, suggestions = find_index(indexes, key)
        if idx is None:
            problem = {"parameter": key, "reason": "unknown parameter"}
            if suggestions:
                problem["did_you_mean"] = suggestions
            problems.append(problem)
            continue

        name = idx["name"]
        if name in seen:
            problems.append(
                {
                    "parameter": key,
                    "name": name,
                    "reason": f"given twice (also as {seen[name]!r}); pass it once",
                }
            )
            continue
        seen[name] = key

        resolver = _RESOLVERS.get(idx.get("kind"))
        if resolver is None:
            problems.append(
                {
                    "parameter": key,
                    "name": name,
                    "reason": f"unsupported parameter kind {idx.get('kind')!r}",
                }
            )
            continue

        try:
            new_value, how, notes = resolver(idx, spec)
        except ParameterError as err:
            problems.append(
                {
                    "parameter": key,
                    "name": name,
                    "label": _label(idx),
                    "reason": str(err),
                    "current": current_value(idx),
                    "allowed": allowed_values(idx),
                }
            )
            continue

        before = current_value(idx)
        if new_value == before:
            notes = notes + ["same as the current value"]

        # A categorical filter that is already unset needs no override.
        if idx.get("kind") == KIND_CATEGORICAL and new_value is None and before is None:
            pass
        else:
            payload[name] = new_value

        change = {
            "name": name,
            "label": _label(idx),
            "kind": idx.get("kind"),
            "from": before,
            "to": new_value,
            "summary": f"{_label(idx)}: {format_value(idx, before)} → {format_value(idx, new_value)}",
            "how": how,
        }
        if _unit(idx):
            change["unit"] = _unit(idx)
        if notes:
            change["notes"] = notes
        changes.append(change)

    return {"payload": payload, "changes": changes, "problems": problems}
