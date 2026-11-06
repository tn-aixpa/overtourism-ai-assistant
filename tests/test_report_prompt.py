import json

from app.agent.state import AgentState
from app.prompts import report
from app.tools.executors import analysis


def test_report_generation_localizes_nodes_and_keeps_plot_payload_out_of_prompt(
    monkeypatch,
):
    state = AgentState(user_lang="English")
    state.cognitive.context_cache["scenarios s1"] = {
        "evaluation_data": {
            "sustainability_index": 0.8,
            "plot_data": {"private_plot_marker": "do-not-send"},
        }
    }
    document = {
        "report_type": "scenarios",
        "title": "Scenario report",
        "territory": "test-territory",
        "territory_label": "Test territory",
        "sections": [
            {
                "type": "scenario",
                "id": "s1",
                "title": "Scenario originale",
                "description": "Descrizione originale",
                "changes": ["Posti auto: da 10 a 5"],
                "plots": [
                    {
                        "widgetName": "loadPlot",
                        "data": {"private_plot_marker": "do-not-send"},
                    }
                ],
            }
        ],
        "base_scenario": None,
        "unassigned_scenarios": [],
    }
    response = {
        "title": "Scenario report",
        "territory_label": "Test territory",
        "introduction": "Introduction.",
        "nodes": [
            {
                "id": "s1",
                "title": "Localized scenario",
                "narrative": "Localized scenario description.",
            }
        ],
        "conclusion": "Conclusion.",
    }
    prompts = []

    def fake_llm(_state, prompt, **_kwargs):
        prompts.append(prompt)
        return json.dumps(response)

    monkeypatch.setattr(report, "llm_interaction", fake_llm)

    result = report.generate_report(state, document)

    assert result["nodes"]["s1"] == {
        "title": "Localized scenario",
        "narrative": "Localized scenario description.",
    }
    assert "in English" in prompts[0]
    assert "Descrizione originale" in prompts[0]
    assert "private_plot_marker" not in prompts[0]


def test_report_executor_returns_assistant_text_and_preserves_plot_payload(
    monkeypatch,
):
    plot_payload = {
        "widgetName": "loadPlot",
        "data": {"type": "mono", "data": {"points": [1, 2, 3]}},
    }
    document = {
        "report_type": "scenarios",
        "title": "Raw title",
        "territory": "test-territory",
        "territory_label": "Raw territory",
        "sections": [
            {
                "type": "scenario",
                "id": "s1",
                "title": "Raw scenario",
                "description": "Untranslated description",
                "changes": ["Raw change"],
                "is_base_scenario": False,
            }
        ],
        "base_scenario": None,
        "unassigned_scenarios": [],
        "warnings": [],
    }

    monkeypatch.setattr(analysis, "_ensure_data_cached", lambda *_args: None)
    monkeypatch.setattr(
        analysis,
        "execute_lookup_glossary",
        lambda *_args, **_kwargs: {"success": True, "matches": []},
    )
    monkeypatch.setattr(
        analysis,
        "generate_report",
        lambda *_args, **_kwargs: {
            "title": "Localized report",
            "territory_label": "Localized territory",
            "introduction": "Introduction.",
            "nodes": {"s1": {"title": "Localized scenario", "narrative": "Narrative."}},
            "conclusion": "Conclusion.",
        },
    )
    monkeypatch.setattr(
        analysis,
        "_scenario_plots",
        lambda *_args: {
            "per_scenario": {"s1": [plot_payload]},
            "comparisons": [],
            "unavailable": [],
        },
    )

    analysis._add_report_content(AgentState(), document)

    assert document["title"] == "Localized report"
    assert document["territory_label"] == "Localized territory"
    assert document["sections"][0] == {
        "type": "scenario",
        "id": "s1",
        "title": "Localized scenario",
        "is_base_scenario": False,
        "narrative": "Narrative.",
        "plots": [plot_payload],
    }
