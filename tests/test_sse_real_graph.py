"""
SSE tests that drive the REAL ReAct nodes (react_reasoner_node,
tool_executor_node, error_recovery_node, generate_output_message_node and the
`safe()` wrapper) through the real HTTP/SSE layer.

Only the two external dependencies are scripted:
  * the LLM  -> `react_step` (the reasoning call) and `generate_answer`
  * the tools -> `execute_selected_tool`

So the thoughts / actions that reach the stream are published by your actual
node code, and every branch that leaves the reasoner (tool, finish, hallucinated
tool, malformed JSON, LLM exception, tool failure, max-steps, answer-generation
failure) must still end with a `done` event and a retrievable result.

(initialize_tools / top_level_router are skipped: they need the backend and an
LLM routing call, and are not part of the SSE contract.)
"""

from __future__ import annotations

import json
import random
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

import pytest
from langgraph.graph import END, StateGraph

import sse_harness as h
from app.agent.nodes import general as general_module
from app.agent.nodes import reasoner as reasoner_module
from app.agent.nodes import tool_executor as tool_executor_module
from app.agent.nodes.general import (
    add_safe_node,
    error_recovery_node,
    generate_output_message_node,
)
from app.agent.nodes.reasoner import react_reasoner_node
from app.agent.nodes.tool_executor import tool_executor_node
from app.agent.state import AgentState
from app.tools.tool_registry import get_tool_registry
from app.tools.tool_schema import ToolCategory, ToolDefinition

TOOLS = ["tool_a", "tool_b", "tool_c"]


def finish(msg="all done", thought="wrapping up"):
    return json.dumps({"thought": thought, "action": "finish", "message": msg})


def use_tool(name, thought=None, **args):
    return json.dumps(
        {
            "thought": thought if thought is not None else f"I need {name}",
            "action": "tool",
            "tool_name": name,
            "arguments": args,
        }
    )


class RealGraphAgent:
    """Replaces routes.agent_app with a mini graph made of the real nodes."""

    def __init__(self):
        self.llm: dict[str, deque] = defaultdict(deque)  # per-session scripted LLM
        self.tool_behaviour: dict[str, object] = {}  # tool -> callable | Exception
        self.answer_behaviour = None  # callable(state) | Exception | None
        self.llm_calls = defaultdict(int)
        graph = StateGraph(AgentState)
        add_safe_node(graph, "react_reasoner", react_reasoner_node)
        add_safe_node(graph, "tool_executor", tool_executor_node)
        add_safe_node(graph, "error", error_recovery_node)
        add_safe_node(graph, "generate_output_message", generate_output_message_node)
        graph.set_entry_point("react_reasoner")
        graph.add_edge("error", "generate_output_message")
        graph.add_edge("generate_output_message", END)
        self.graph = graph.compile()

    # ---- scripted collaborators -------------------------------------------
    def react_step(self, state, tools, mode_unavailable, role_unavailable):
        sid = state.session_id
        self.llm_calls[sid] += 1
        item = self.llm[sid].popleft()
        if isinstance(item, tuple) and item[0] == "sleep":
            time.sleep(item[1])
            item = self.llm[sid].popleft()
        if isinstance(item, BaseException):
            raise item
        return item

    def execute_selected_tool(self, tool_name, args, state, allow_disabled=False):
        behaviour = self.tool_behaviour.get(tool_name)
        if isinstance(behaviour, BaseException):
            raise behaviour
        if callable(behaviour):
            behaviour()
        return {"success": True, "output": {"message": f"{tool_name} ok"}, "error": None}

    def generate_answer(self, state):
        if isinstance(self.answer_behaviour, BaseException):
            raise self.answer_behaviour
        n_tools = len(state.cognitive.scratchpad)
        return f"final(tools={n_tools}):{'|'.join(state.cognitive.messages_to_include)[:60]}"

    # ---- agent_app interface ----------------------------------------------
    def invoke(self, state, config=None):
        registry = get_tool_registry()
        for name in TOOLS:
            registry.register_tool(
                ToolDefinition(
                    name=name, description="d", category=ToolCategory.UTILITY, parameters=[]
                )
            )
        state.cognitive.enabled_tools = list(TOOLS)
        state.cognitive.known_tools = list(TOOLS)
        state.cognitive.scratchpad = []
        return self.graph.invoke(state, config=config)


@pytest.fixture
def real(live, monkeypatch):
    agent = RealGraphAgent()
    monkeypatch.setattr(reasoner_module, "react_step", agent.react_step)
    monkeypatch.setattr(
        tool_executor_module, "execute_selected_tool", agent.execute_selected_tool
    )
    monkeypatch.setattr(general_module, "generate_answer", agent.generate_answer)
    monkeypatch.setattr(live.routes, "agent_app", agent)
    live.real = agent
    return live


def kinds(rec):
    return [(s["type"], s.get("tool") or s.get("content")) for s in rec.statuses]


# --------------------------------------------------------------------------- #
# Every exit from the reasoner must end in `done` + a usable result
# --------------------------------------------------------------------------- #
class TestReasonerExits:
    def test_finish_without_tools(self, real):
        real.real.llm["s"].extend([finish("hello", thought="easy one")])
        rec = h.run_turn(real.base, "s", "hi")
        assert rec.got_done and rec.error is None
        assert kinds(rec) == [("thought", "easy one")]
        assert rec.result["response"].startswith("final(tools=0)")

    def test_three_tool_loop_publishes_thought_action_pairs_in_order(self, real):
        real.real.llm["s"].extend(
            [
                use_tool("tool_a", thought="t1"),
                use_tool("tool_b", thought="t2"),
                use_tool("tool_c", thought="t3"),
                finish("ok", thought="t4"),
            ]
        )
        rec = h.run_turn(real.base, "s", "go")
        assert kinds(rec) == [
            ("thought", "t1"),
            ("action", "tool_a"),
            ("thought", "t2"),
            ("action", "tool_b"),
            ("thought", "t3"),
            ("action", "tool_c"),
            ("thought", "t4"),
        ]
        assert rec.result["response"].startswith("final(tools=3)")

    def test_empty_thought_publishes_no_thought_event_but_turn_completes(self, real):
        real.real.llm["s"].extend([use_tool("tool_a", thought=""), finish(thought="")])
        rec = h.run_turn(real.base, "s", "go")
        assert kinds(rec) == [("action", "tool_a")]
        assert rec.got_done and rec.result

    def test_hallucinated_tool_finishes_cleanly(self, real):
        real.real.llm["s"].extend([use_tool("does_not_exist", thought="try it")])
        rec = h.run_turn(real.base, "s", "go")
        assert kinds(rec) == [("thought", "try it")]  # no action: tool was refused
        assert rec.got_done and rec.result["response"].startswith("final(")

    @pytest.mark.parametrize(
        "bad",
        ["not json at all", "", "```json\n{broken\n```"],
        ids=["prose", "empty", "fenced-broken"],
    )
    def test_malformed_llm_output_routes_to_error_and_still_completes(self, real, bad):
        real.real.llm["s"].extend([bad])
        rec = h.run_turn(real.base, "s", "go")
        assert rec.got_done, "malformed LLM output must not leave the stream hanging"
        assert rec.result is not None
        assert "technical error" in rec.result["response"].lower() or rec.result[
            "response"
        ].startswith("final(")

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: valid-but-not-an-object JSON ('[]', 'null') makes "
            "`response_json.get(...)` raise AttributeError OUTSIDE the try block in "
            "react_reasoner_node. safe() answers with Command(goto='error', "
            "graph=Command.PARENT); on a top-level graph that is raised out of "
            "agent_app.invoke() as ParentCommand, so error_recovery_node never runs "
            "and _run_agent falls back to the bare 'System error' result."
        ),
    )
    @pytest.mark.parametrize("bad", ["[]", "null", '"just a string"', "42"])
    def test_non_object_json_from_llm_is_recovered_by_error_node(self, real, bad):
        real.real.llm["s"].extend([bad])
        rec = h.run_turn(real.base, "s", "go")
        assert rec.got_done
        assert rec.result is not None
        assert "technical error" in rec.result["response"].lower() or rec.result[
            "response"
        ].startswith("final(")

    def test_llm_exception_in_reasoner_still_completes(self, real):
        real.real.llm["s"].extend([TimeoutError("LLM timed out")])
        rec = h.run_turn(real.base, "s", "go")
        assert rec.got_done and rec.result is not None

    def test_llm_failure_after_some_progress_keeps_earlier_events(self, real):
        real.real.llm["s"].extend(
            [use_tool("tool_a", thought="t1"), RuntimeError("boom on 2nd step")]
        )
        rec = h.run_turn(real.base, "s", "go")
        assert kinds(rec)[:2] == [("thought", "t1"), ("action", "tool_a")]
        assert rec.got_done and rec.result is not None

    def test_tool_failure_routes_to_error_and_completes(self, real):
        real.real.llm["s"].extend([use_tool("tool_b", thought="t1")])
        real.real.tool_behaviour["tool_b"] = RuntimeError("backend 500")
        rec = h.run_turn(real.base, "s", "go")
        assert ("action", "tool_b") in kinds(rec)
        assert rec.got_done and rec.result is not None

    def test_answer_generation_failure_still_sends_done(self, real):
        real.real.llm["s"].extend([finish()])
        real.real.answer_behaviour = RuntimeError("LLM down while writing answer")
        rec = h.run_turn(real.base, "s", "go")
        assert rec.got_done
        assert rec.result["response"] == "System error"

    def test_max_react_steps_safety_valve_ends_the_turn(self, real):
        limit = AgentState().cognitive.max_react_steps
        real.real.llm["s"].extend([use_tool("tool_a", thought=f"t{i}") for i in range(limit + 5)])
        rec = h.run_turn(real.base, "s", "loop forever", read_timeout=30)
        actions = [k for k in kinds(rec) if k[0] == "action"]
        assert len(actions) == limit
        assert rec.got_done and rec.result is not None
        assert real.real.llm_calls["s"] == limit  # no extra LLM call past the limit

    def test_error_recovery_node_failing_does_not_hang(self, real, monkeypatch):
        """`safe()` routes any node failure to "error". If error_recovery_node
        itself fails (e.g. logs/errors.txt not writable), safe() sends it back
        to "error" again - a loop that only the LangGraph recursion limit (and
        ultimately the watchdog) stops. The client must still get `done`."""
        import builtins

        real_open = builtins.open

        def failing_open(path, *a, **kw):
            if str(path).endswith("errors.txt"):
                raise PermissionError("read-only fs")
            return real_open(path, *a, **kw)

        monkeypatch.setattr(builtins, "open", failing_open)
        real.real.llm["s"].extend(["garbage"])
        t0 = time.monotonic()
        rec = h.run_turn(real.base, "s", "go", read_timeout=30)
        assert rec.got_done, rec.error
        assert time.monotonic() - t0 < 20


# --------------------------------------------------------------------------- #
# Many calls, different reasoning shapes, at the same time
# --------------------------------------------------------------------------- #
class TestRealGraphUnderLoad:
    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_random_reasoning_shapes_across_many_sessions(self, real, seed):
        rnd = random.Random(seed)
        n_sessions = 30
        plan: dict[str, tuple[str, list]] = {}

        for i in range(n_sessions):
            sid = f"s{i}"
            shape = rnd.choice(
                ["finish", "tools", "long", "bad-json", "llm-exc", "tool-fail", "hallucinate"]
            )
            q = real.real.llm[sid]
            expected_tools: list[str] = []
            if shape == "finish":
                q.append(finish(thought=f"{sid}-only"))
            elif shape in ("tools", "long"):
                limit = AgentState().cognitive.max_react_steps
                # "long" deliberately overshoots max_react_steps: the safety
                # valve must cut the loop at `limit` and still finish the turn.
                n = rnd.randint(1, 3) if shape == "tools" else rnd.randint(limit - 2, limit + 4)
                for k in range(n):
                    tool = rnd.choice(TOOLS)
                    if len(expected_tools) < limit:
                        expected_tools.append(tool)
                    if rnd.random() < 0.3:
                        q.append(("sleep", rnd.random() * 0.05))
                    q.append(use_tool(tool, thought=f"{sid}-t{k}"))
                q.append(finish(thought=f"{sid}-end"))
            elif shape == "bad-json":
                q.append("}{")
            elif shape == "llm-exc":
                q.append(use_tool("tool_a", thought=f"{sid}-t0"))
                q.append(ConnectionError("llm reset"))
                expected_tools.append("tool_a")
            elif shape == "tool-fail":
                q.append(use_tool("tool_c", thought=f"{sid}-t0"))
                expected_tools.append("tool_c")
            elif shape == "hallucinate":
                q.append(use_tool("nope", thought=f"{sid}-t0"))
            plan[sid] = (shape, expected_tools)

        # one tool misbehaves for everybody who calls it in "tool-fail" sessions
        real.real.tool_behaviour["tool_c"] = None  # default ok; patched below

        def exec_tool(tool_name, args, state, allow_disabled=False):
            shape = plan[state.session_id][0]
            if shape == "tool-fail" and tool_name == "tool_c":
                raise RuntimeError("backend 500")
            return {"success": True, "output": {"message": "ok"}, "error": None}

        real.real.execute_selected_tool = exec_tool
        tool_executor_module.execute_selected_tool = exec_tool

        with ThreadPoolExecutor(n_sessions) as ex:
            recs = list(
                ex.map(
                    lambda sid: h.run_turn(real.base, sid, f"msg-{sid}", read_timeout=30),
                    plan,
                )
            )

        problems = []
        for rec in recs:
            shape, tools = plan[rec.session]
            if not rec.got_done:
                problems.append(f"{rec.session}[{shape}] no done: {rec.error}")
                continue
            if rec.result is None:
                problems.append(f"{rec.session}[{shape}] no result (status {rec.result_status})")
                continue
            got_tools = [t for ty, t in kinds(rec) if ty == "action"]
            if got_tools != tools:
                problems.append(f"{rec.session}[{shape}] tools {got_tools} != {tools}")
            foreign = [
                c
                for ty, c in kinds(rec)
                if ty == "thought" and not str(c).startswith(rec.session + "-")
            ]
            if foreign:
                problems.append(f"{rec.session}[{shape}] foreign events {foreign}")
        assert not problems, f"seed={seed}\n" + "\n".join(problems)

    def test_follow_up_turns_on_same_session_do_not_see_previous_turns_events(self, real):
        for turn in range(8):
            real.real.llm["s"].extend(
                [use_tool("tool_a", thought=f"turn{turn}-a"), finish(thought=f"turn{turn}-b")]
            )
            rec = h.run_turn(real.base, "s", f"msg{turn}")
            assert rec.post_status == 202, rec.error
            assert kinds(rec) == [
                ("thought", f"turn{turn}-a"),
                ("action", "tool_a"),
                ("thought", f"turn{turn}-b"),
            ]
            assert rec.got_done and rec.result is not None
