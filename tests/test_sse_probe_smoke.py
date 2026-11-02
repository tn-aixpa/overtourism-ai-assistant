"""Keeps scripts/sse_probe.py honest: it must run end-to-end against the app and
classify outcomes correctly (including a lost-`done` / still-running turn)."""

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if not (_SCRIPTS / "sse_probe.py").exists():
    pytest.skip(
        "scripts/sse_probe.py is not part of this checkout", allow_module_level=True
    )
sys.path.insert(0, str(_SCRIPTS))

import sse_probe  # noqa: E402

from sse_harness import action, sleep  # noqa: E402


def test_probe_reports_all_ok_for_healthy_turns(live, capsys):
    live.agent.script_for = lambda sid, m: [action("a", delay=0.05), action("b", delay=0.05)]
    rc = sse_probe.main(
        [
            "--base",
            live.base,
            "--token",
            "t",
            "--sessions",
            "4",
            "--turns",
            "2",
            "--timeout",
            "10",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "8 ok, 0 not ok" in out
    assert "last->done" in out


def test_probe_distinguishes_a_still_running_turn_from_a_lost_done(live, capsys):
    live.agent.script_for = lambda sid, m: [sleep(3.0)]
    rc = sse_probe.main(
        [
            "--base",
            live.base,
            "--token",
            "t",
            "--sessions",
            "1",
            "--turns",
            "1",
            "--timeout",
            "1",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "no-done(still-running)" in out, out
