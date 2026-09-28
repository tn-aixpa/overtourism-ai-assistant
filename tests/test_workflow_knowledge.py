from app.agent.nodes import route_groups
from app.agent.state import AgentState
from app.tools.definitions.system_utility import create_explain_workflow_tool
from app.tools.executors.system_utility import execute_explain_workflow
from app.utils.workflow_knowledge import WORKFLOW_DOCUMENTS, get_workflow_document


def test_both_workflow_documents_are_loaded_from_renamed_paths():
    assert "Workflow for the Analysis of Territorial Critical Situations" in (
        WORKFLOW_DOCUMENTS["modeling"]
    )
    assert "Workflow for the Methodological Design of Territorial Indices" in (
        WORKFLOW_DOCUMENTS["territorial_indexes"]
    )
    assert get_workflow_document("unknown") == ""


def test_explain_workflow_selects_requested_document(fresh_state: AgentState):
    modeling = execute_explain_workflow(fresh_state, workflow_type="modeling")
    indexes = execute_explain_workflow(fresh_state, workflow_type="territorial_indexes")

    assert modeling["workflow_type"] == "modeling"
    assert "A **Problem** is a critical situation" in modeling["workflow_document"]
    assert indexes["workflow_type"] == "territorial_indexes"
    assert "Define the Territorial Phenomenon" in indexes["workflow_document"]


def test_auto_selection_uses_index_methodology_route(fresh_state: AgentState):
    fresh_state.cognitive.second_level_route = ["index_methodology"]

    result = execute_explain_workflow(fresh_state)

    assert result["workflow_type"] == "territorial_indexes"


def test_index_methodology_route_exposes_workflow_tool_only():
    allowed = route_groups.resolve_allowed_tools("indexes", "index_methodology")

    assert allowed == {"explain_workflow"}


def test_tool_schema_explains_available_workflow_types():
    tool = create_explain_workflow_tool()
    parameter = tool.parameters[0]

    assert parameter.name == "workflow_type"
    assert parameter.required is False
    assert parameter.schema["enum"] == [
        "auto",
        "modeling",
        "territorial_indexes",
    ]
