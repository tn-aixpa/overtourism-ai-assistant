from langgraph.graph import StateGraph

from ..nodes.problem import extract_problem_node, parse_confirmation_node, create_problem_instance_node, decide_strategy_node, generate_scenario_candidates
from ..state import AgentState
from .utils import human_gate, add_safe_node

# ---- Human gates

wait_problem_input = human_gate(
    "WAIT_PROBLEM_INPUT",
        lambda s: {"instructions": f"To correctly create the new problem, please provide the missing information:\n- {'\n- '.join(f'{k}' for k, v in s.problem_info_to_extract.items() if k not in s.extracted_problem_info and v["required"])}"},
)

wait_problem_confirmation = human_gate(
    "WAIT_PROBLEM_CONFIRMATION",
    lambda s: {"instructions": f"These are the information I extracted:\n- {'\n- '.join(f'{k}: {v}' for k, v in s.extracted_problem_info.items())}.\nDo you want to proceed?"}
)

wait_scenario_preference = human_gate(
    "WAIT_SCENARIO_PREFERENCE",
    lambda s: {"instructions": "Do you want to create scenarios for this problem? If so, do you have specific scenarios in mind or would you like the system to generate some based on the problem information?"},
)

# ---- Build subgraph

graph = StateGraph(AgentState)

add_safe_node(graph, "extract_problem", extract_problem_node)
add_safe_node(graph, "WAIT_PROBLEM_INPUT", wait_problem_input)
add_safe_node(graph, "WAIT_PROBLEM_CONFIRMATION", wait_problem_confirmation)
add_safe_node(graph, "parse_problem_confirmation", parse_confirmation_node)
add_safe_node(graph, "create_problem_instance", create_problem_instance_node)
add_safe_node(graph, "decide_scenario_strategy", decide_strategy_node)
add_safe_node(graph, "WAIT_SCENARIO_PREFERENCE", wait_scenario_preference)
add_safe_node(graph, "generate_scenario_candidates", generate_scenario_candidates)

graph.set_entry_point("extract_problem")

graph.add_edge("WAIT_PROBLEM_INPUT", "extract_problem")
graph.add_edge("WAIT_PROBLEM_CONFIRMATION", "parse_problem_confirmation")
graph.add_edge("create_problem_instance", "decide_scenario_strategy")
graph.add_edge("WAIT_SCENARIO_PREFERENCE", "decide_scenario_strategy")

problem_subgraph = graph.compile()
