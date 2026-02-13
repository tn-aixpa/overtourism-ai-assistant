from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState

def run_scenario_node(state: AgentState) -> AgentState:
    if state.scenarios_to_generate:
        scenario_title, scanario_parameters = state.scenarios_to_generate.popitem()
        #TODO: run tool
        return Command(update=state, goto="run_scenario")
    else:
        return Command(update=state, goto="END")

graph = StateGraph(AgentState)

graph.add_node("run_scenario", run_scenario_node)

graph.set_entry_point("run_scenario")

scenario_runner_subgraph = graph.compile()