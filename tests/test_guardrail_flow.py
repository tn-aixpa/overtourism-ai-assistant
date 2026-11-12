"""
End-to-end guardrail flows through the REAL compiled graph
(initialize_tools -> top_level_router -> react_reasoner -> tool_executor ->
WAIT_USER_INPUT -> generate_output_message), with only the LLM scripted:

  * router classification  -> `classify_route`   (scripted verdict per turn)
  * reasoning step         -> `react_step`       (scripted JSON per step)
  * answer generation      -> `llm_interaction`  (records every prompt and
                                                  tags it with WHO is speaking)

Recording who speaks is the point: the original bug was an off-topic recipe
coming out of the EXECUTOR persona, whose contract is "restate tool data
only". These tests pin that:

  off-topic          -> a decline, no tool, no reasoning, no tier persona
  on-topic, no data  -> exploitative tier, only after consent, never executor
  on-topic, grounded -> executor/operative relays tool output, and is told it
                        may not use its own knowledge
"""

import json
from collections import deque

import pytest

from app.agent.graph_agentic import build_agentic_graph
from app.agent.nodes import reasoner as reasoner_module
from app.agent.nodes import router as router_module
from app.agent.state import AgentState, AgentTier
from app.prompts import answer_generation as ag

RECIPE = "Pizza: mix 500g flour, 300ml water, yeast; bake 10 minutes at 250C."


def finish(message="", finish_type=None, thought="t"):
    body = {"thought": thought, "action": "finish", "message": message}
    if finish_type:
        body["finish_type"] = finish_type
    return json.dumps(body)


def use(tool, **args):
    return json.dumps(
        {"thought": f"need {tool}", "action": "tool", "tool_name": tool, "arguments": args}
    )


def speaker(prompt: str) -> str:
    """Who produced this LLM call?"""
    if "outside what you can help with" in prompt and "tourism-management digital twin" in prompt:
        return "decline"
    for tier in AgentTier:
        if ag._role_intro(tier)[:60] in prompt:
            return tier.value
    return "control"  # consent question, clarification menus, ...


class Flow:
    """One conversation: scripted collaborators + helpers to take turns."""

    def __init__(self, monkeypatch, tmp_path, **state_kw):
        (tmp_path / "logs").mkdir(exist_ok=True)
        monkeypatch.chdir(tmp_path)
        self.verdicts: deque = deque()
        self.steps: deque = deque()
        self.speakers: list[str] = []
        self.prompts: list[str] = []
        self.react_calls = 0
        self.graph = build_agentic_graph()
        self.state = AgentState(
            session_id="s", territory="molveno", allowed_territories=["molveno"],
            user_role=state_kw.pop("user_role", "editor"),
            session_mode=state_kw.pop("session_mode", "standalone"),
            **state_kw,
        )

        def classify(state, current_top, current_second):
            top, *rest = self.verdicts.popleft()
            return {"top_level": top, "topic_changed": True,
                    "second_level": rest[0] if rest else None}

        def react_step(state, tools, mode_unavailable, role_unavailable):
            self.react_calls += 1
            return self.steps.popleft()

        def llm(state, prompt, *a, **k):
            who = speaker(prompt)
            self.speakers.append(who)
            self.prompts.append(prompt)
            return f"<{who}>"

        monkeypatch.setattr(router_module, "classify_route", classify)
        monkeypatch.setattr(reasoner_module, "react_step", react_step)
        monkeypatch.setattr(ag, "llm_interaction", llm)

    def say(self, text, route=("general",), steps=()):
        """Take one user turn. `route` is the router's verdict for it."""
        if route is not None:
            self.verdicts.append(route)
        self.steps.extend(steps)
        waiting = self.state.waiting_for
        self.state.add_user_message(text)
        self.state.user_input = text if waiting else None
        out = self.graph.invoke(self.state)
        self.state = AgentState(**{k: v for k, v in out.items() if k != "__interrupt__"})
        return self.state.get_last_message().content

    @property
    def tools_run(self):
        return list(self.state.cognitive.tool_results)


@pytest.fixture
def flow(monkeypatch, tmp_path):
    return Flow(monkeypatch, tmp_path)


# ---------------------------------------------------------------------------
# Off-topic: declined by the router
# ---------------------------------------------------------------------------


class TestOffTopicIsDeclined:
    def test_pizza_recipe_gets_a_decline_and_nothing_else(self, flow):
        reply = flow.say("come si fa la pizza?", route=("off_topic",))
        assert reply == "<decline>"
        assert flow.speakers == ["decline"]          # nobody else spoke
        assert flow.react_calls == 0                  # the reasoner never ran
        assert flow.tools_run == []
        assert "500g" not in reply

    def test_the_request_text_never_reaches_the_decline_prompt(self, flow):
        flow.say("dammi la ricetta della pizza margherita", route=("off_topic",))
        decline_prompt = flow.prompts[0]
        assert "pizza" not in decline_prompt.lower() and "ricetta" not in decline_prompt.lower()

    def test_decline_in_the_middle_of_an_on_topic_conversation(self, flow):
        flow.state.cognitive.top_level_route = "location"
        flow.state.cognitive.second_level_route = ["scenario"]
        reply = flow.say("e per la pizza quanti minuti?", route=("off_topic",))
        assert reply == "<decline>" and flow.react_calls == 0
        # the on-topic conversation is still there to pick up
        assert flow.state.cognitive.top_level_route == "location"
        assert flow.state.cognitive.second_level_route == ["scenario"]

    def test_consent_to_general_knowledge_does_not_open_the_door_to_off_topic(self, flow):
        flow.state.cognitive.grant_tier_consent("exploitative")
        reply = flow.say("scrivimi una poesia sul mare", route=("off_topic",))
        assert reply == "<decline>"
        assert flow.speakers == ["decline"] and flow.tools_run == []

    def test_a_later_on_topic_message_works_normally(self, flow):
        flow.say("barzelletta?", route=("off_topic",))
        reply = flow.say(
            "ciao", route=("system_info",),
            steps=[use("get_system_capabilities"), finish("Posso aiutarti con X.", "answer_from_data")],
        )
        assert flow.tools_run == ["get_system_capabilities"]
        assert flow.state.cognitive.guardrail_decline is False
        assert reply != "<decline>"


# ---------------------------------------------------------------------------
# Second line of defence: the classifier let it through, the reasoner drafts it
# ---------------------------------------------------------------------------


class TestReasonerCannotSmuggleAnAnswer:
    def test_recipe_in_a_finish_message_is_never_relayed(self, flow):
        # classifier mislabels it as small talk; the reasoner "helpfully" answers
        reply = flow.say(
            "come si fa la pizza?", route=("system_info",),
            steps=[finish(RECIPE)],
        )
        assert "500g" not in reply
        # blocked at the consent gate: nothing from the executor persona either
        assert "executor" not in flow.speakers
        assert flow.state.waiting_for == AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION
        assert all("500g" not in p for p in flow.prompts)

    def test_declared_decline_from_the_reasoner_is_content_free(self, flow):
        reply = flow.say(
            "come si fa la pizza?", route=("general",),
            steps=[finish(RECIPE, "decline")],
        )
        assert reply == "<decline>"
        assert all("500g" not in p for p in flow.prompts)

    def test_declined_consent_ends_with_no_answer_and_no_loop(self, flow):
        flow.say("come si fa la pizza?", route=("system_info",), steps=[finish(RECIPE)])
        reply = flow.say(
            "no", route=None,
            steps=[finish(RECIPE)],   # the reasoner tries the same thing again
        )
        assert "500g" not in reply and all("500g" not in p for p in flow.prompts)
        assert "exploitative" not in flow.speakers
        assert flow.state.waiting_for is None

    def test_viewer_gets_no_general_knowledge_fallback(self, monkeypatch, tmp_path):
        flow = Flow(monkeypatch, tmp_path, user_role="viewer")
        reply = flow.say("spiegami la capacità di carico", route=("general",),
                         steps=[finish("Carrying capacity is ...", "needs_general_knowledge")])
        assert flow.state.waiting_for is None            # no consent prompt: not allowed at all
        assert "exploitative" not in flow.speakers
        assert "Carrying capacity is" not in reply

    def test_forced_executor_role_gets_no_general_knowledge_fallback(self, monkeypatch, tmp_path):
        flow = Flow(monkeypatch, tmp_path, force_role="executor")
        flow.say("spiegami la capacità di carico", route=("general",),
                 steps=[finish("", "needs_general_knowledge")])
        assert flow.state.waiting_for is None
        assert "exploitative" not in flow.speakers and flow.tools_run == []


class TestUnavailableIsNotADecline:
    """A permission / mode limit on an ON-topic request must not be shown to
    the user as 'outside the scope of tourism management'."""

    def test_viewer_refused_a_write_gets_the_specific_reason(self, monkeypatch, tmp_path):
        flow = Flow(monkeypatch, tmp_path, user_role="viewer")
        reply = flow.say(
            "cancella il problema sul traffico", route=("location", "problem"),
            steps=[finish("Il tuo ruolo non può eliminare problemi.", "unavailable")],
        )
        assert "decline" not in flow.speakers
        assert flow.state.cognitive.guardrail_decline is False
        assert any("non può eliminare" in p for p in flow.prompts)  # relayed, not replaced
        assert flow.tools_run == [] and reply

    def test_unavailable_on_a_tool_only_route_is_not_escalated_to_free_knowledge(self, flow):
        flow.say(
            "cerca sul web le ultime notizie", route=("general",),
            steps=[finish("La ricerca web non è disponibile in questa modalità.", "unavailable")],
        )
        assert flow.state.waiting_for is None          # no consent prompt
        assert "exploitative" not in flow.speakers and flow.tools_run == []


# ---------------------------------------------------------------------------
# On-topic but not covered by any tool -> exploitative tier, with consent
# ---------------------------------------------------------------------------


class TestOnTopicGeneralKnowledge:
    QUESTION = "che cos'è la capacità di carico turistica?"

    def test_first_time_asks_consent_then_answers_as_the_exploitative_tier(self, flow):
        first = flow.say(self.QUESTION, route=("general",),
                         steps=[finish("", "needs_general_knowledge")])
        assert flow.state.waiting_for == AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION
        assert flow.tools_run == []                       # nothing ran before consent
        assert "exploitative" not in flow.speakers        # nor was anything answered

        second = flow.say("sì", route=None, steps=[finish("ok", "answer_from_data")])
        assert flow.tools_run == ["general_question_response"]
        assert "exploitative" in flow.speakers
        assert flow.state.active_agent == AgentTier.EXPLOITATIVE
        assert flow.state.waiting_for is None
        assert second.startswith("<")

    def test_consent_is_remembered_so_the_next_question_is_not_gated(self, flow):
        flow.say(self.QUESTION, route=("general",), steps=[finish("", "needs_general_knowledge")])
        flow.say("sì", route=None, steps=[finish("ok", "answer_from_data")])
        flow.speakers.clear()
        flow.say("e la resilienza di una destinazione?", route=("general",),
                 steps=[finish("", "needs_general_knowledge"), finish("ok", "answer_from_data")])
        assert flow.state.waiting_for is None             # no second consent prompt
        assert "exploitative" in flow.speakers

    def test_reasoner_may_call_the_general_tool_directly_too(self, flow):
        flow.say(self.QUESTION, route=("general",),
                 steps=[use("general_question_response", query=self.QUESTION)])
        assert flow.state.waiting_for == AgentState.WaitingFor.TIER_ACCESS_CONFIRMATION

    def test_methodology_questions_use_the_workflow_document_not_free_knowledge(
        self, flow, monkeypatch
    ):
        from app.utils import workflow_knowledge as wk

        monkeypatch.setattr(wk, "get_workflow_document", lambda kind: "WORKFLOW-DOC")
        flow.say(
            "come funziona il processo di analisi?", route=("system_info",),
            steps=[use("explain_workflow"), finish("Segue il processo.", "answer_from_data")],
        )
        assert flow.tools_run == ["explain_workflow"]
        assert flow.state.waiting_for is None             # methodological tier: no consent
        assert "exploitative" not in flow.speakers


# ---------------------------------------------------------------------------
# On-topic and grounded: executor relays data and is forbidden its own knowledge
# ---------------------------------------------------------------------------


class TestGroundedAnswers:
    def test_greeting_is_answered_from_a_tool_not_from_nothing(self, flow):
        reply = flow.say(
            "ciao", route=("system_info",),
            steps=[use("get_system_capabilities"), finish("Ecco cosa posso fare.", "answer_from_data")],
        )
        assert flow.tools_run == ["get_system_capabilities"]
        assert flow.state.waiting_for is None
        assert "exploitative" not in flow.speakers
        assert reply

    def test_glossary_question_runs_the_glossary_tool_without_consent(self, flow):
        flow.say(
            "cosa significa overtourism?", route=("system_info",),
            steps=[use("lookup_glossary", query="overtourism"), finish("Definizione.", "answer_from_data")],
        )
        assert flow.tools_run == ["lookup_glossary"]
        assert flow.state.waiting_for is None
        assert flow.state.active_agent in (AgentTier.EXECUTOR, AgentTier.OPERATIVE)

    def test_clarifying_question_is_allowed_without_a_tool(self, flow):
        reply = flow.say(
            "e quello?", route=("system_info",),
            steps=[finish("A cosa ti riferisci esattamente?", "clarification")],
        )
        assert flow.state.waiting_for is None and flow.tools_run == []
        assert "exploitative" not in flow.speakers
        assert reply

    def test_executor_prompt_forbids_answering_from_its_own_knowledge(self, flow):
        flow.say(
            "ciao", route=("system_info",),
            steps=[use("get_system_capabilities"), finish("ok", "answer_from_data")],
        )
        final_prompt = flow.prompts[-1]
        assert "never a source" in final_prompt or "NEVER answer the Question" in final_prompt


# ---------------------------------------------------------------------------
# The real classifier prompt + parser (only the model's raw JSON is faked)
# ---------------------------------------------------------------------------


class TestClassifierContract:
    """Every other test stubs classify_route. These run the real one, so a
    prompt that fails to render, or a parser that drops the 'off_topic'
    verdict, can't hide behind the stub."""

    @pytest.fixture
    def classify(self, monkeypatch, tmp_path):
        from app.prompts import routing

        (tmp_path / "logs").mkdir(exist_ok=True)
        monkeypatch.chdir(tmp_path)
        seen = {}

        def run(model_json, text="come si fa la pizza?"):
            seen.clear()

            def fake_llm(state, prompt, *a, **k):
                seen["prompt"] = prompt
                return model_json

            monkeypatch.setattr(routing, "llm_interaction", fake_llm)
            state = AgentState(session_id="s", territory="molveno")
            state.add_user_message(text)
            return routing.classify_route(state, None, None), seen

        return run

    def test_off_topic_verdict_survives_parsing(self, classify):
        result, _ = classify(
            '{"top_level": "off_topic", "topic_changed": true, "second_level": null}'
        )
        assert result["top_level"] == "off_topic"

    def test_verdict_in_a_json_code_fence_survives_too(self, classify):
        result, _ = classify(
            '```json\n{"top_level": "off_topic", "topic_changed": true, "second_level": null}\n```'
        )
        assert result["top_level"] == "off_topic"

    def test_prompt_renders_and_states_the_guardrail(self, classify):
        _, seen = classify('{"top_level": "general", "topic_changed": true, "second_level": null}')
        prompt = seen["prompt"]
        assert "off_topic" in prompt
        assert "tourism management" in prompt
        for domain in ("system_info", "location", "indexes", "general"):
            assert domain in prompt
        assert "{" in prompt and "{{" not in prompt  # f-string escapes rendered

    @pytest.mark.parametrize("garbage", ["", "not json", '{"top_level": ', "[]"])
    def test_unparseable_output_fails_safe_to_a_clarification_never_to_an_answer(
        self, classify, garbage
    ):
        result, _ = classify(garbage)
        assert result["top_level"] == "unclear"

    def test_real_classifier_into_real_router_declines(self, monkeypatch, tmp_path):
        from app.prompts import routing

        (tmp_path / "logs").mkdir(exist_ok=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            routing, "llm_interaction",
            lambda *a, **k: '{"top_level": "off_topic", "topic_changed": true, "second_level": null}',
        )
        state = AgentState(session_id="s", territory="molveno", user_role="editor")
        state.add_user_message("come si fa la pizza?")
        cmd = router_module.top_level_router_node(state)
        assert cmd.goto == "generate_output_message"
        assert state.cognitive.guardrail_decline is True
        assert state.cognitive.pending_route_clarification is None  # no menu shown
