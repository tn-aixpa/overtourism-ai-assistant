from app.prompts.answer_generation import _capitalize_territory_names
from app.agent.state import AgentState
from app.utils.territory import (
    display_territory,
    switch_territory_if_requested,
    territory_question,
)


def test_display_territory_capitalizes_only_first_character():
    assert display_territory("molveno") == "Molveno"
    assert display_territory("fazzon") == "Fazzon"
    assert display_territory("altipiano di fazzon") == "Altipiano di fazzon"
    assert display_territory("") == ""


def test_territory_question_displays_capitalized_names():
    question = territory_question(["molveno", "fazzon"])

    assert "1. Molveno" in question
    assert "2. Fazzon" in question
    assert "molveno" not in question
    assert "fazzon" not in question


def test_generated_answer_capitalizes_known_territory_names_case_insensitively():
    answer = _capitalize_territory_names(
        "Le località sono molveno e FAZZON.", ["molveno", "fazzon"]
    )

    assert answer == "Le località sono Molveno e Fazzon."


def test_generated_answer_does_not_rewrite_territory_name_inside_other_words():
    answer = _capitalize_territory_names("molvenolandia", ["molveno"])

    assert answer == "molvenolandia"


def test_integrated_request_switches_to_an_explicit_allowed_territory():
    state = AgentState(
        integrated_mode=True,
        territory="Fazzon",
        allowed_territories=["Fazzon", "Molveno"],
    )
    state.cognitive.current_context["scenarios"] = ["fazzon-scenario"]
    state.cognitive.tool_results = {"old": {"scenarios": ["fazzon-scenario"]}}
    state.add_user_message("Vorrei vedere lo scenario base di Molveno ora")

    previous = switch_territory_if_requested(state)

    assert previous == "Fazzon"
    assert state.territory == "Molveno"
    assert state.cognitive.current_context == {
        "problems": [],
        "proposals": [],
        "scenarios": [],
    }
    assert state.cognitive.tool_results == {}


def test_integrated_request_does_not_switch_to_an_unallowed_territory():
    state = AgentState(
        integrated_mode=True,
        territory="Fazzon",
        allowed_territories=["Fazzon"],
    )
    state.add_user_message("Vorrei vedere lo scenario base di Molveno ora")

    assert switch_territory_if_requested(state) is None
    assert state.territory == "Fazzon"


def test_integrated_index_request_does_not_switch_modelling_territory():
    state = AgentState(
        integrated_mode=True,
        territory="Fazzon",
        allowed_territories=["Fazzon", "Molveno"],
    )
    state.add_user_message("Qual è l'indice di ricettività di Molveno?")

    assert switch_territory_if_requested(state) is None
    assert state.territory == "Fazzon"
