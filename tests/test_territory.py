from app.prompts.answer_generation import _capitalize_territory_names
from app.utils.territory import display_territory, territory_question


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
