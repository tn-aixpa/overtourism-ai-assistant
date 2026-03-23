from langgraph.graph import StateGraph
from langgraph.types import Command

from app.agent.nodes.problem import extract_problem_node, parse_confirmation_node, CREATE_NEW_PROBLEM_instance_node, decide_strategy_node, generate_scenario_candidates
from app.agent.state import AgentState
from app.agent.graphs.utils import add_safe_node

# ---- Build subgraph

def problem_entry_router(state: AgentState):
    """
    Resume into the correct internal node based on `state.waiting_for`.
    """
    if state.waiting_for == AgentState.WaitingFor.PROBLEM_CONFIRMATION:
        return "parse_problem_confirmation"
    if state.waiting_for == AgentState.WaitingFor.SCENARIO_PREFERENCE:
        return "decide_scenario_strategy"
    # Default (including PROBLEM_INPUT and first entry)
    return "extract_problem"

graph = StateGraph(AgentState)

graph.add_node("problem_entry_router", lambda s: s)
add_safe_node(graph, "extract_problem", extract_problem_node)
add_safe_node(graph, "parse_problem_confirmation", parse_confirmation_node)
add_safe_node(graph, "CREATE_NEW_PROBLEM_instance", CREATE_NEW_PROBLEM_instance_node)
add_safe_node(graph, "decide_scenario_strategy", decide_strategy_node)
add_safe_node(graph, "generate_scenario_candidates", generate_scenario_candidates)

graph.set_entry_point("problem_entry_router")
graph.add_conditional_edges(
    "problem_entry_router",
    problem_entry_router,
    {
        "extract_problem": "extract_problem",
        "parse_problem_confirmation": "parse_problem_confirmation",
        "decide_scenario_strategy": "decide_scenario_strategy",
    }
)
graph.add_edge("CREATE_NEW_PROBLEM_instance", "decide_scenario_strategy")

problem_subgraph = graph.compile()
