import json
from langgraph.graph import StateGraph, END
from langgraph.types import Command

from ..state import AgentState
#from ...utils.llm import extract_scenario_data
from .utils import human_gate, safe

# ---- Nodes

def extract_scenario(state: AgentState) -> AgentState:
    pass
    # answer = extract_scenario_data(state.messages[-1]["content"] if state.messages else "",
    #                               state.scenario_info_to_extract,
    #                               state.extracted_scenario_info)
    

    # if "Error connecting to Ollama" not in answer:

    #     try:
    #         # The LLM output should be JSON, so we load it
    #         parsed_data = json.loads(answer)
    #     except json.JSONDecodeError:
    #         return {}

    #     for key, value in parsed_data.items():
    #         if value:
    #             state.extracted_scenario_info[key] = value
        
    #     extracted_all_scenario = True
    #     for key, info in state.scenario_info_to_extract.items():
    #         if info["required"] and key not in state.extracted_scenario_info:
    #             # If any required info is missing, we consider the extraction incomplete
    #             extracted_all_scenario = False
    #             break
    #     state.extracted_all_scenario = extracted_all_scenario

    # else:
    #   #TODO: impement
    #   pass
    # return state


def create_scenario_instance_node(state: AgentState) -> AgentState:
    #TODO: call tool
    pass
    #TODO: go to scenario runner subgraph

# ---- Human gates

wait_scenario_input = human_gate(
    "WAIT_SCENARIO_INPUT",
    lambda s: {"instructions": f"To create correctly create the new scenario, please provide the missing information: {chr(10)} - {chr(10).join(k for k in s.scenario_info_to_extract if k not in s.extracted_scenario_info)}. {chr(10)}"},
)

wait_scenario_confirmation = human_gate(
    "WAIT_SCENARIO_CONFIRMATION",
    lambda s: {"instructions": "Do you confirm the extracted scenario information?", "scenario_info_to_extract": s.extracted_scenario_info},
)



# ---- Command wrappers

def extract_scenario_node(state: AgentState):
    with open("logs/debugger.log", "w") as f:
        f.write(f"Extracting scenario\n")
        try:
            state = safe(extract_scenario)(state)
            f.write(f"State after extraction: {state}\n")
            f.write(f"Extracted scenario info: {state.extracted_scenario_info}\n")
            if state.extracted_all_scenario:
                f.write("All scenario info extracted successfully.")
                return Command(update=state, goto="WAIT_SCENARIO_CONFIRMATION")
            f.write("Problem info extraction incomplete.")
            return Command(update=state, goto="WAIT_SCENARIO_INPUT")
        except Exception as e:
            f.write(f"Error during scenario extraction: {e}")

def parse_confirmation_node(state: AgentState):
    message = state.messages[-1]["content"].lower() if state.messages else ""
    if any(word in message for word in ["yes", "confirm", "ok"]):
        state.next_action = "CONFIRM_SCENARIO"
    elif any(word in message for word in ["edit", "change", "modify"]):
        state.next_action = "EDIT_SCENARIO"
    elif any(word in message for word in ["cancel", "interrut", "quit"]) or message == "no":
        state.next_action = "CANCEL_SCENARIO"
    else:
        state.next_action = "WAIT_SCENARIO_CONFIRMATION"
    #TODO: add also llm fallback

    routes = {
        "CONFIRM_SCENARIO": "run_scenario",
        "EDIT_SCENARIO": "extract_scenario",
        "CANCEL_SCENARIO": END,
        "WAIT_SCENARIO_CONFIRMATION": "WAIT_SCENARIO_CONFIRMATION",
    }
    return Command(update=state, goto=routes[state.next_action])


# ---- Build subgraph

graph = StateGraph(AgentState)

graph.add_node("extract_scenario", extract_scenario_node)
graph.add_node("WAIT_SCENARIO_INPUT", wait_scenario_input)
graph.add_node("WAIT_SCENARIO_CONFIRMATION", wait_scenario_confirmation)
graph.add_node("parse_scenario_confirmation", parse_confirmation_node)
graph.add_node("create_scenario_instance", create_scenario_instance_node)

graph.set_entry_point("extract_scenario")

graph.add_edge("WAIT_SCENARIO_CONFIRMATION", "parse_scenario_confirmation")
graph.add_edge("WAIT_SCENARIO_INPUT", "extract_scenario")

scenario_extraction_subgraph = graph.compile()
