from langgraph.graph import StateGraph, END

from ..nodes.scenario import extract_scenario_node, parse_confirmation_node
from ..state import AgentState
from .utils import human_gate, add_safe_node

# ---- Human gates

wait_scenario_input = human_gate(
    "WAIT_SCENARIO_INPUT",
    lambda s: {"instructions": s.cognitive.validation_errors + f"\nPlease, provide all required details to create a scenario"},
)

wait_scenario_confirmation = human_gate(
    "WAIT_CONFIRMATION_SCENARIO",
    lambda s: {
        "instructions": f"Do you want to proceed with the following scenarios?\n- "
                        f"{'\n- '.join(str(x) for x in s.cognitive.scenarios_to_generate)}"
    },)

def scenario_resume_router(state: AgentState):
    if state.last_node and state.last_node.startswith("WAIT_"):
        return state.last_node  # jump to the right node
    return "extract_scenario"

# ---- Build subgraph

graph = StateGraph(AgentState)

graph.add_node("scenario_resume_router", lambda s: s)
add_safe_node(graph, "extract_scenario", extract_scenario_node)
add_safe_node(graph, "WAIT_SCENARIO_INPUT", wait_scenario_input)
add_safe_node(graph, "WAIT_CONFIRMATION_SCENARIO", wait_scenario_confirmation)
add_safe_node(graph, "parse_scenario_confirmation", parse_confirmation_node)

graph.set_entry_point("scenario_resume_router")

graph.add_conditional_edges(
    "scenario_resume_router",
    scenario_resume_router,
    {
        "WAIT_CONFIRMATION_SCENARIO", "parse_scenario_confirmation",
        "WAIT_SCENARIO_INPUT", "extract_scenario"
    }
)

scenario_extraction_subgraph = graph.compile()
