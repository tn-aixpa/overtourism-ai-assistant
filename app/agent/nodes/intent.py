from langgraph.types import Command

from ..state import AgentState
from ...utils.llm import classify_intent
from ...utils.error_codes import ErrorCode, GraphError

def intent_node(state: AgentState) -> AgentState:
    answer = classify_intent(state.cognitive.scenario_ids, state.last_user_en).strip()

    VALID_OUTPUTS = {
        "CREATE_PROBLEM",
        "RUN_NEW_SCENARIO",
        "INTERACT_SCENARIO",
        "INVALID",
    }

    assert answer in VALID_OUTPUTS
    state.cognitive.next_action = answer
    return state

def validate_intent_node(state: AgentState) -> AgentState:
    """
    Validate the intent determined in the intent_node.
    Adjust the next_action and response if needed based on the current state.
    """
    intent = state.cognitive.next_action

    # --- INVALID intent ---
    if intent == "INVALID":
        raise GraphError(ErrorCode.INVALID_REQUEST)

    # --- INTERACT_SCENARIO ---
    elif intent == "INTERACT_SCENARIO":
        if not state.cognitive.scenario_ids:
            state.cognitive.next_action = "NOT_ALLOWED"
            raise GraphError(ErrorCode.INVALID_REQUEST_STATE, "No active scenario")
        
        if len(state.cognitive.scenario_ids) > 1:
            state.cognitive.next_action = "COMPARE_SCENARIOS"

            # --- COMPARE_SCENARIOS ---
            if not len(state.cognitive.scenario_ids) > 1:
                state.cognitive.next_action = "NOT_ALLOWED"
                raise GraphError(ErrorCode.INVALID_REQUEST_STATE, "There should be at least two active scenarios")
        
    # --- CREATE_PROBLEM ---
    elif intent == "RUN_NEW_SCENARIO":
        if not state.cognitive.problem_id:
            state.cognitive.next_action = "NOT_ALLOWED"
            raise GraphError(ErrorCode.INVALID_REQUEST_STATE, "No problem selected")

    return state

def route_from_intent(state: AgentState):
    action = state.cognitive.next_action
    if action in ["INTERACT_SCENARIO", "COMPARE_SCENARIOS"]:
        return Command(update=state, goto="interaction", graph=Command.PARENT)

    if action == "RUN_NEW_SCENARIO":
        return Command(update=state, goto="scenario_extraction", graph=Command.PARENT)

    if action == "CREATE_PROBLEM":
        return Command(update=state, goto="problem", graph=Command.PARENT)   

    raise GraphError(ErrorCode.REQUEST_ERROR)
    