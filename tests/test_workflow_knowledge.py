from pathlib import Path

import pytest

from app.agent.nodes import route_groups
from app.agent.state import AgentState
from app.tools.definitions.system_utility import create_explain_workflow_tool
from app.tools.executors.system_utility import execute_explain_workflow
from app.utils import workflow_knowledge
from app.utils.workflow_knowledge import WORKFLOW_DOCUMENTS, get_workflow_document

_KNOWLEDGE = Path(__file__).resolve().parent.parent / "knowledge"
requires_knowledge = pytest.mark.skipif(
    not (
        (_KNOWLEDGE / "workflow_modeling.md").exists()
        and (_KNOWLEDGE / "workflow_territorial_indexes.md").exists()
    ),
    reason="knowledge/workflow_*.md are not part of this checkout",
)

FAKE_DOCS = {
    "modeling": "MODELING DOC",
    "territorial_indexes": "INDEXES DOC",
}


@pytest.fixture
def fake_workflow_docs(monkeypatch):
    """execute_explain_workflow resolves documents through
    get_workflow_document at call time, so the executor logic can be tested
    without the markdown files."""
    monkeypatch.setattr(
        "app.utils.workflow_knowledge.get_workflow_document",
        lambda workflow_type: FAKE_DOCS.get(workflow_type, ""),
    )


# --------------------------------------------------------------------------- #
# Loading (depends on the real markdown files)
# --------------------------------------------------------------------------- #
@requires_knowledge
def test_both_workflow_documents_are_loaded_from_renamed_paths():
    assert "Workflow for the Analysis of Territorial Critical Situations" in (
        WORKFLOW_DOCUMENTS["modeling"]
    )
    assert "Workflow for the Methodological Design of Territorial Indices" in (
        WORKFLOW_DOCUMENTS["territorial_indexes"]
    )
    assert get_workflow_document("unknown") == ""


@requires_knowledge
def test_explain_workflow_returns_the_real_documents(fresh_state: AgentState):
    modeling = execute_explain_workflow(fresh_state, workflow_type="modeling")
    indexes = execute_explain_workflow(fresh_state, workflow_type="territorial_indexes")

    assert modeling["workflow_type"] == "modeling"
    assert "A **Problem** is a critical situation" in modeling["workflow_document"]
    assert indexes["workflow_type"] == "territorial_indexes"
    assert "Define the Territorial Phenomenon" in indexes["workflow_document"]


def test_unknown_workflow_type_yields_empty_document():
    assert get_workflow_document("does-not-exist") == ""


def test_legacy_alias_points_at_the_modeling_document():
    assert workflow_knowledge.WORKFLOW_DOCUMENT == WORKFLOW_DOCUMENTS["modeling"]


def test_missing_workflow_file_loads_as_empty_string(tmp_path):
    assert workflow_knowledge._load_workflow_document(tmp_path / "nope.md") == ""


def test_workflow_file_is_read_and_stripped(tmp_path):
    f = tmp_path / "wf.md"
    f.write_text("\n\n  # Title\nbody\n\n", encoding="utf-8")

    assert workflow_knowledge._load_workflow_document(f) == "# Title\nbody"


# --------------------------------------------------------------------------- #
# execute_explain_workflow (document-independent logic)
# --------------------------------------------------------------------------- #
def test_explain_workflow_selects_requested_document(
    fresh_state: AgentState, fake_workflow_docs
):
    modeling = execute_explain_workflow(fresh_state, workflow_type="modeling")
    indexes = execute_explain_workflow(fresh_state, workflow_type="territorial_indexes")

    assert modeling == {
        "success": True,
        "workflow_type": "modeling",
        "workflow_document": "MODELING DOC",
    }
    assert indexes["workflow_type"] == "territorial_indexes"
    assert indexes["workflow_document"] == "INDEXES DOC"


def test_auto_selection_defaults_to_modeling(fresh_state: AgentState, fake_workflow_docs):
    result = execute_explain_workflow(fresh_state)

    assert result["workflow_type"] == "modeling"


def test_auto_selection_uses_index_methodology_route(
    fresh_state: AgentState, fake_workflow_docs
):
    fresh_state.cognitive.second_level_route = ["index_methodology"]

    result = execute_explain_workflow(fresh_state)

    assert result["workflow_type"] == "territorial_indexes"
    assert result["workflow_document"] == "INDEXES DOC"


def test_explicit_selection_beats_the_route(fresh_state: AgentState, fake_workflow_docs):
    fresh_state.cognitive.second_level_route = ["index_methodology"]

    result = execute_explain_workflow(fresh_state, workflow_type="modeling")

    assert result["workflow_type"] == "modeling"


def test_unknown_workflow_type_is_rejected(fresh_state: AgentState, fake_workflow_docs):
    result = execute_explain_workflow(fresh_state, workflow_type="astrology")

    assert result["success"] is False
    assert "astrology" in result["error"]


def test_unavailable_document_is_reported_not_returned_empty(
    fresh_state: AgentState, monkeypatch
):
    monkeypatch.setattr(
        "app.utils.workflow_knowledge.get_workflow_document", lambda workflow_type: ""
    )

    result = execute_explain_workflow(fresh_state, workflow_type="modeling")

    assert result["success"] is False
    assert "unavailable" in result["error"]


# --------------------------------------------------------------------------- #
# Routing + tool schema
# --------------------------------------------------------------------------- #
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
