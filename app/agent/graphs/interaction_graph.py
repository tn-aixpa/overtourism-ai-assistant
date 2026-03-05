from langgraph.graph import StateGraph, END
from langgraph.types import Command

from app.agent.state import AgentState
from app.agent.nodes.iteraction import select_role, interact_scenario, compare_scenarios, synthesize_answers
from app.agent.graphs.utils import add_safe_node


# ---- Command wrappers

def select_role_router(state: AgentState):
    result = select_role(state)

    state.add_trace("node_execution", node="select_role_router", data={"selected_roles": state.cognitive.selected_roles})

    mapping = {
        "INTERACT_SCENARIO": "interact_scenario",
        "COMPARE_SCENARIOS": "compare_scenarios",
    }

    return Command(
        update=result,
        goto=mapping[state.cognitive.next_action],
    )


def interact_router(state: AgentState):
    state.add_trace("node_execution", node="interact_router")
    result = interact_scenario(state)

    if len(state.cognitive.selected_roles) > 1:
        return Command(update=result, goto="synthesize")

    return Command(update=result, goto=END)


def compare_router(state: AgentState):
    state.add_trace("node_execution", node="compare_router")
    result = compare_scenarios(state)

    if len(state.cognitive.selected_roles) > 1:
        return Command(update=result, goto="synthesize")

    return Command(update=result, goto=END)


# ---- Build subgraph

graph = StateGraph(AgentState)

add_safe_node(graph, "select_role", select_role_router)
add_safe_node(graph, "interact_scenario", interact_router)
add_safe_node(graph, "compare_scenarios", compare_router)
add_safe_node(graph, "synthesize", synthesize_answers)

graph.set_entry_point("select_role")
graph.add_edge("synthesize", END)

interaction_subgraph = graph.compile()
