from langgraph.graph import StateGraph

from ..nodes.problem import extract_problem_node, parse_confirmation_node, create_problem_instance_node, decide_strategy_node, generate_scenario_candidates
from ..state import AgentState
from .utils import human_gate, add_safe_node

# ---- Human gates

wait_problem_input = human_gate(
    "WAIT_PROBLEM_INPUT",
        lambda s: {"instructions": f"To correctly create the new problem, please provide the missing information:\n- {'\n- '.join(f'{k}' for k, v in s.cognitive.problem_info_to_extract.items() if k not in s.cognitive.extracted_problem_info and v["required"])}"},
)

wait_problem_confirmation = human_gate(
    "WAIT_CONFIRMATION_PROBLEM",
    lambda s: {"instructions": f"These are the information I extracted:\n- {'\n- '.join(f'{k}: {v}' for k, v in s.cognitive.extracted_problem_info.items())}.\n\nDo you want to proceed?"}
)

wait_scenario_preference = human_gate(
    "WAIT_SCENARIO_PREFERENCE",
    lambda s: {"instructions": "Do you want to create scenarios for this problem? If so, do you have specific scenarios in mind or would you like the system to generate some based on the problem information?"},
)

# ---- Build subgraph

def problem_resume_router(state: AgentState):
    if state.last_node and state.last_node.startswith("WAIT_"):
        return state.last_node  # jump to the right node
    return "extract_problem"

graph = StateGraph(AgentState)

graph.add_node("problem_resume_router", lambda s: s)
add_safe_node(graph, "extract_problem", extract_problem_node)
add_safe_node(graph, "WAIT_PROBLEM_INPUT", wait_problem_input)
add_safe_node(graph, "WAIT_CONFIRMATION_PROBLEM", wait_problem_confirmation)
add_safe_node(graph, "parse_problem_confirmation", parse_confirmation_node)
add_safe_node(graph, "create_problem_instance", create_problem_instance_node)
add_safe_node(graph, "decide_scenario_strategy", decide_strategy_node)
add_safe_node(graph, "WAIT_SCENARIO_PREFERENCE", wait_scenario_preference)
add_safe_node(graph, "generate_scenario_candidates", generate_scenario_candidates)

graph.set_entry_point("problem_resume_router")
graph.add_conditional_edges(
    "problem_resume_router",
    problem_resume_router,
    {
        "extract_problem": "extract_problem",
        "WAIT_PROBLEM_INPUT": "extract_problem",
        "WAIT_CONFIRMATION_PROBLEM": "parse_problem_confirmation",
        "WAIT_SCENARIO_PREFERENCE": "decide_scenario_strategy",
    }
)
graph.add_edge("create_problem_instance", "decide_scenario_strategy")

problem_subgraph = graph.compile()
