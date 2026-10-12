"""Aggregated domain tool definitions."""

from typing import List

from app.tools.tool_schema import ToolDefinition

from app.tools.definitions.analysis_widgets import *
from app.tools.definitions.analysis import *
from app.tools.definitions.indexes import *
from app.tools.definitions.problem import *
from app.tools.definitions.proposal import *
from app.tools.definitions.scenario import *
from app.tools.definitions.system_utility import *


def get_all_agent_tools() -> List[ToolDefinition]:
    return [
        create_lookup_glossary_tool(),
        create_get_system_capabilities_tool(),
        create_explain_workflow_tool(),
        create_general_question_response_tool(),
        create_list_available_problems_tool(),
        create_list_available_proposals_tool(),
        create_list_available_scenarios_tool(),
        create_get_context_ids_tool(),
        create_get_context_tool(),
        create_get_base_scenario_tool(),
        create_get_configuration_parameters_tool(),
        create_get_territorial_index_list_tool(),
        create_analyze_scenario_results_tool(),
        create_analysis_widget_tool(),
        create_explain_widget_tool(),
        create_show_territorial_index_map_tool(),
        create_show_territorial_index_plot_tool(),
        create_query_territorial_index_values_tool(),
        create_summary_generation_tool(),
        create_report_generation_tool(),
        create_new_problem_tool(),
        create_new_proposal_tool(),
        create_new_temp_scenario_tool(),
        create_new_scenario_tool(),
        edit_problem_tool(),
        edit_proposal_tool(),
        edit_scenario_tool(),
        delete_problem_tool(),
        delete_proposal_tool(),
        delete_scenario_tool(),
    ]


__all__ = [name for name in globals() if name.endswith("_tool")] + [
    "get_all_agent_tools"
]
