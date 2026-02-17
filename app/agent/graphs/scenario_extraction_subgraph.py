from langgraph.graph import StateGraph, END

from ..nodes.scenario import extract_scenario_node, parse_confirmation_node
from ..state import AgentState
from .utils import human_gate, add_safe_node

# ---- Human gates

wait_scenario_input = human_gate(
    "WAIT_SCENARIO_INPUT",
    lambda s: {"instructions": s.error_message + f"\nPlease, provide all required details to create a scenario"},
)

wait_scenario_confirmation = human_gate(
    "WAIT_SCENARIO_CONFIRMATION",
    lambda s: {
        "instructions": f"Do you want to proceed with the following scenarios?\n- "
                        f"{'\n- '.join(str(x) for x in s.scenarios_to_generate)}"
    },)

# ---- Build subgraph

graph = StateGraph(AgentState)

add_safe_node(graph, "extract_scenario", extract_scenario_node)
add_safe_node(graph, "WAIT_SCENARIO_INPUT", wait_scenario_input)
add_safe_node(graph, "WAIT_SCENARIO_CONFIRMATION", wait_scenario_confirmation)
add_safe_node(graph, "parse_scenario_confirmation", parse_confirmation_node)

graph.set_entry_point("extract_scenario")

graph.add_edge("WAIT_SCENARIO_CONFIRMATION", "parse_scenario_confirmation")
graph.add_edge("WAIT_SCENARIO_INPUT", "extract_scenario")

scenario_extraction_subgraph = graph.compile()
