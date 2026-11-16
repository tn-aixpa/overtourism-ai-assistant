"""Runtime switches read from the environment.

Each value comes from, in order of precedence:

1. the process environment (``docker run -e ...``, ``environment:`` in
   docker-compose, a Kubernetes env entry, ...);
2. ``run.sh`` / the ``.env`` file it sources (which end up in the process
   environment as well, so there is one lookup for all of them).

Switches
--------
``SAVE_CONVERSATION_LOGS``  (default: ``false``)
    When true, conversations are written to ``logs/`` (the per-session
    ``state_<session_id>.json`` dump).
    When false nothing about a conversation is written to disk.

``LOG_LEVEL``  (default: ``INFO``)
    Verbosity of the console log: ``DEBUG`` | ``INFO`` | ``WARNING`` |
    ``ERROR`` | ``CRITICAL`` (case-insensitive; ``WARN`` and ``FATAL`` are
    accepted as aliases). ``DEBUG`` adds the payload-level detail (backend
    response bodies, tool arguments, ...) that ``INFO`` leaves out.

This module has no dependency on the rest of the app, so it can be imported
from anywhere (including before logging is configured).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

SAVE_CONVERSATION_LOGS_ENV = "SAVE_CONVERSATION_LOGS"
LOG_LEVEL_ENV = "LOG_LEVEL"

DEFAULT_SAVE_CONVERSATION_LOGS = False
DEFAULT_LOG_LEVEL = "INFO"

_TRUE = frozenset({"1", "true", "t", "yes", "y", "on"})
_FALSE = frozenset({"0", "false", "f", "no", "n", "off"})

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
    "FATAL": logging.CRITICAL,
}

# Names accepted for LOG_LEVEL, for error messages and run.sh validation.
VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def parse_bool(raw: Optional[str]) -> Optional[bool]:
    """True/False for a recognised spelling, None for unset/empty/unknown."""
    if raw is None:
        return None
    text = raw.strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def parse_log_level(raw: Optional[str]) -> int:
    """The ``logging`` level for a LOG_LEVEL value.

    Raises ValueError for an unrecognised name, so a typo is reported
    instead of silently changing the verbosity.
    """
    name = (raw or "").strip().upper()
    if name in _LOG_LEVELS:
        return _LOG_LEVELS[name]
    raise ValueError(
        f"Invalid {LOG_LEVEL_ENV} {raw!r}; expected one of "
        f"{', '.join(VALID_LOG_LEVELS)}"
    )


def save_conversation_logs_enabled() -> bool:
    """Whether conversations may be written to ``logs/``.

    Read on every call (an environment lookup, negligible next to the file
    write it guards), so the switch is never stale and is easy to test.
    An unset, empty or unrecognised value means the default: disabled.
    """
    value = parse_bool(os.environ.get(SAVE_CONVERSATION_LOGS_ENV))
    return DEFAULT_SAVE_CONVERSATION_LOGS if value is None else value


def configured_log_level() -> Optional[int]:
    """The level requested through LOG_LEVEL, or None when it is unset/empty.

    Raises ValueError for an invalid value (see ``parse_log_level``).
    """
    raw = os.environ.get(LOG_LEVEL_ENV)
    if raw is None or not raw.strip():
        return None
    return parse_log_level(raw)
