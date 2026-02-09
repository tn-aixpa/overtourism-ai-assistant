from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState
from ..nodes.select_role import select_role
from ..nodes.interact import interact_scenario
from ..nodes.compare import compare_scenarios
from ..nodes.synthesize import synthesize_answers


# ---- Command wrappers

def select_role_router(state: AgentState):
    result = select_role(state)

    mapping = {
        "INTERACT_SCENARIO": "interact_scenario",
        "COMPARE_SCENARIOS": "compare_scenarios",
    }

    return Command(
        update=result,
        goto=mapping[state.next_action],
    )


def interact_router(state: AgentState):

    result = interact_scenario(state)

    if len(state.selected_roles) > 1:
        return Command(update=result, goto="synthesize")

    return Command(update=result, goto=END)


def compare_router(state: AgentState):

    result = compare_scenarios(state)

    if len(state.selected_roles) > 1:
        return Command(update=result, goto="synthesize")

    return Command(update=result, goto=END)


# ---- Build subgraph

interaction_graph = StateGraph(AgentState)

interaction_graph.add_node("select_role", select_role_router)
interaction_graph.add_node("interact_scenario", interact_router)
interaction_graph.add_node("compare_scenarios", compare_router)
interaction_graph.add_node("synthesize", synthesize_answers)

interaction_graph.set_entry_point("select_role")
interaction_graph.add_edge("synthesize", END)

interaction_subgraph = interaction_graph.compile()
