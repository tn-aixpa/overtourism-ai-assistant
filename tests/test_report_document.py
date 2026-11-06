from app.utils.report_document import build_report_document


def test_scenario_report_includes_a_repeated_scenario_only_once():
    document = build_report_document(
        territory="test",
        territory_label="Test",
        current_context={"scenarios": ["s1", "s1"]},
        problems=[],
        proposals=[],
        scenarios=[{"scenario_id": "s1", "name": "Scenario 1"}],
        base_scenario_id=None,
    )

    assert [scenario["id"] for scenario in document["sections"]] == ["s1"]
