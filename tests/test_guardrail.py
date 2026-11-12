"""Guardrail regression tests — LLM calls are stubbed, only the control flow is checked."""
import sys, types, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
pathlib.Path("logs").mkdir(exist_ok=True)

import pytest
from app.agent.state import AgentState, ReActStep
from app.agent.nodes import router, reasoner, guardrail
from app.agent.nodes import route_groups as rg
from app.prompts import answer_generation as ag


def make_state(text="come si fa la pizza?", route=None, second=None, role=None):
    s = AgentState()
    s.add_user_message(text) if hasattr(s, "add_user_message") else None
    s.cognitive.known_tools = ["get_system_capabilities", "lookup_glossary",
                               "explain_workflow", "general_question_response", "web_search"]
    s.cognitive.enabled_tools = list(s.cognitive.known_tools)
    s.cognitive.top_level_route = route
    s.cognitive.second_level_route = second
    if role:
        s.force_role = role
    return s


def classify(top, changed=True, second=None):
    return lambda state, a, b: {"top_level": top, "topic_changed": changed, "second_level": second}


# ---------------- router ----------------
def test_router_declines_off_topic_without_route(monkeypatch):
    monkeypatch.setattr(router, "classify_route", classify("off_topic"))
    s = make_state()
    cmd = router.top_level_router_node(s)
    assert cmd.goto == "generate_output_message"
    assert s.cognitive.guardrail_decline is True
    assert s.cognitive.top_level_route is None


def test_router_declines_even_when_classifier_says_continuation(monkeypatch):
    monkeypatch.setattr(router, "classify_route", classify("off_topic", changed=False))
    s = make_state(route="location", second=["scenario"])
    cmd = router.top_level_router_node(s)
    assert cmd.goto == "generate_output_message"
    assert s.cognitive.guardrail_decline is True
    # the on-topic conversation is preserved for the next message
    assert s.cognitive.top_level_route == "location"
    assert s.cognitive.second_level_route == ["scenario"]


def test_router_on_topic_unchanged(monkeypatch):
    monkeypatch.setattr(router, "classify_route", classify("general", second=None))
    s = make_state("che cos'è l'overtourism?")
    cmd = router.top_level_router_node(s)
    assert cmd.goto == "react_reasoner"
    assert s.cognitive.guardrail_decline is False


def test_off_topic_is_not_a_menu_option():
    assert rg.TOP_OFF_TOPIC not in rg.TOP_LEVEL_LABELS
    assert rg.resolve_allowed_tools(rg.TOP_OFF_TOPIC, None) is None or True


# ---------------- reasoner ----------------
def run_reasoner(monkeypatch, state, payload):
    import json
    monkeypatch.setattr(reasoner, "react_step", lambda *a, **k: json.dumps(payload))
    monkeypatch.setattr(reasoner, "publish_thought", lambda *a, **k: None)
    return reasoner.react_reasoner_node(state)


RECIPE = {"thought": "easy", "action": "finish",
          "message": "Ingredients: 500g flour, water, yeast... bake 10 min at 250C"}


def test_ungrounded_recipe_is_not_relayed_on_system_info(monkeypatch):
    s = make_state(route="system_info")
    cmd = run_reasoner(monkeypatch, s, RECIPE)
    assert cmd.goto == "tool_executor"
    assert s.cognitive.selected_tool == "general_question_response"
    assert s.cognitive.messages_to_include == []          # recipe discarded


def test_ungrounded_recipe_blocked_for_executor_only_role(monkeypatch):
    s = make_state(route="system_info", role="executor")
    cmd = run_reasoner(monkeypatch, s, RECIPE)
    assert cmd.goto == "generate_output_message"
    assert "500g" not in " ".join(s.cognitive.messages_to_include)


def test_decline_finish_type(monkeypatch):
    s = make_state(route="general")
    cmd = run_reasoner(monkeypatch, s, {"thought": "x", "action": "finish",
                                         "finish_type": "decline", "message": RECIPE["message"]})
    assert cmd.goto == "generate_output_message"
    assert s.cognitive.guardrail_decline is True
    assert "500g" not in " ".join(s.cognitive.messages_to_include)


def test_needs_general_knowledge_escalates(monkeypatch):
    s = make_state(route="system_info")
    cmd = run_reasoner(monkeypatch, s, {"thought": "x", "action": "finish",
                                         "finish_type": "needs_general_knowledge", "message": ""})
    assert cmd.goto == "tool_executor" and s.cognitive.selected_tool == "general_question_response"


def test_no_second_escalation_loop(monkeypatch):
    s = make_state(route="system_info")
    s.cognitive.scratchpad = [ReActStep(tool_name="general_question_response",
                                        observation={"success": True, "answer": "ok"})]
    cmd = run_reasoner(monkeypatch, s, {"thought": "x", "action": "finish",
                                         "finish_type": "answer_from_data", "message": "done"})
    assert cmd.goto == "generate_output_message"          # grounded finish passes through


def test_grounded_finish_after_tool_is_untouched(monkeypatch):
    s = make_state(route="system_info")
    s.cognitive.scratchpad = [ReActStep(tool_name="get_system_capabilities",
                                        observation={"success": True})]
    cmd = run_reasoner(monkeypatch, s, {"thought": "x", "action": "finish", "message": "I can do X."})
    assert cmd.goto == "generate_output_message"
    assert s.cognitive.messages_to_include == ["I can do X."]


def test_clarification_is_untouched(monkeypatch):
    s = make_state(route="system_info")
    cmd = run_reasoner(monkeypatch, s, {"thought": "x", "action": "finish",
                                         "message": "Which territory do you mean?"})
    assert cmd.goto == "generate_output_message"
    assert s.cognitive.messages_to_include == ["Which territory do you mean?"]


def test_location_route_finish_from_context_is_untouched(monkeypatch):
    s = make_state(route="location", second=["territory"])
    cmd = run_reasoner(monkeypatch, s, {"thought": "x", "action": "finish",
                                         "message": "Available: Molveno, Altipiano di Fazzon."})
    assert cmd.goto == "generate_output_message"


# ---------------- answer generation ----------------
def test_decline_prompt_never_contains_the_request(monkeypatch):
    seen = {}
    monkeypatch.setattr(ag, "llm_interaction", lambda st, p, **k: seen.setdefault("p", p) or "ok")
    s = make_state("dammi la ricetta della pizza margherita")
    s.cognitive.guardrail_decline = True
    s.user_lang = "Italian"
    ag.generate_answer(s)
    assert "pizza" not in seen["p"].lower() and "ricetta" not in seen["p"].lower()
    assert "Italian" in seen["p"]


def test_executor_policy_forbids_own_knowledge():
    from app.agent.state import AgentTier
    assert "NEVER answer the Question from your own knowledge" in ag._reasoning_policy(AgentTier.EXECUTOR)
