from datetime import datetime
from langgraph.graph import END
from langgraph.types import Command

from ..state import AgentState, ConversationMessage
from ...utils.llm import classify_intent

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
        state.cognitive.next_action = "INVALID"
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content="I'm not able to handle this request with the current system capabilities.",
                timestamp=datetime.now()
        ))

        return state

    # --- INTERACT_SCENARIO ---
    if intent == "INTERACT_SCENARIO":
        if not state.cognitive.scenario_ids:
            state.cognitive.next_action = "NOT_ALLOWED"
            state.conversation.append(
                ConversationMessage(
                    role="assistant",
                    content="I understand you want to interact with a scenario, but no scenario is currently selected.",
                    timestamp=datetime.now()
            ))
            return state

        if len(state.cognitive.scenario_ids) > 1:
            state.cognitive.next_action = "COMPARE_SCENARIOS"
            return state
        
    # --- CREATE_PROBLEM ---
    if intent == "RUN_NEW_SCENARIO" and not state.cognitive.problem_id:
        state.cognitive.next_action = "NOT_ALLOWED"
        state.conversation.append(
            ConversationMessage(
                role="assistant",
                content="No problem is defined. Please define a problem first.",
                timestamp=datetime.now()
        ))
        return state

    return state

def route_from_intent(state: AgentState):
    action = state.cognitive.next_action
    if action in ["INTERACT_SCENARIO", "COMPARE_SCENARIOS"]:
        return Command(update=state, goto="interaction", graph=Command.PARENT)

    # Scenario runner subgraph

    if action == "RUN_NEW_SCENARIO":
        return Command(update=state, goto="scenario_extraction", graph=Command.PARENT)

    if action == "CREATE_PROBLEM":
        return Command(update=state, goto="problem", graph=Command.PARENT)

    # END nodes
    if action in ["NOT_ALLOWED", "INVALID"]:
        return Command(update=state, goto=END)
    

    # Fallback safety
    return Command(update=state, goto="error", graph=Command.PARENT)