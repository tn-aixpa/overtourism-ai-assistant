from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState
from ..nodes.run_scenario import extract_inputs, confirm, run_scenario
from ..graphs.utils import human_gate, safe

# ---- Human gates

wait_missing_inputs = human_gate(
    "WAIT_SCENARIO_INPUT",
    lambda s: {"missing_fields": s.missing_fields},
)

# ---- Command wrappers

def extract_cmd(state: AgentState):
    # Skip extraction if scenarios already exist
    if state.scenario_ids:
        return Command(update=state, goto="confirm")

    state = safe(extract_inputs)(state)
    if state.current_input:
        return Command(update=state, goto="confirm")
    return Command(update=state, goto="WAIT_SCENARIO_INPUT")


def confirm_cmd(state: AgentState):
    state = safe(confirm)(state)
    routes = {
        "RUN": "run_scenario",
        "EDIT": "extract",
        "CANCEL": END,
    }
    return Command(update=state, goto=routes[state.confirm_action])


def run_cmd(state: AgentState):
    state = safe(run_scenario)(state)

    # Set next_action for tests
    if len(state.scenario_ids) == 1:
        state.next_action = "INTERACT_SCENARIO"
    elif len(state.scenario_ids) > 1:
        state.next_action = "COMPARE_SCENARIOS"

    if state.has_pending_scenarios:
        return Command(update=state, goto="extract")

    return Command(update=state, goto=END)


# ---- Build subgraph

graph = StateGraph(AgentState)

graph.add_node("extract", extract_cmd)
graph.add_node("WAIT_SCENARIO_INPUT", wait_missing_inputs)
graph.add_node("confirm", confirm_cmd)
graph.add_node("run_scenario", run_cmd)

graph.set_entry_point("extract")

scenario_runner_subgraph = graph.compile()
