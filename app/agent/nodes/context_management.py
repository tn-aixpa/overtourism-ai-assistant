import logging

from app.agent.state import AgentState
from app.tools.backend_tools import get_data_from_context


logger = logging.getLogger(__name__)

def handle_context(state: AgentState) -> AgentState:
    logger.info("Entering handle_context node")
    if state.cognitive.active_context == state.cognitive.previous_context:
        return state
    
    extract_editable = (
        not isinstance(state.cognitive.editable_indexes, dict)
        or len(state.cognitive.editable_indexes) == 0
    )

    # TODO: fix or remove
    extracted_data = get_data_from_context.invoke({
        "context_type": state.cognitive.active_context_type,
        "context": list(state.cognitive.active_context),
        "relations": {},
        "extract_editable": extract_editable
    })
    retrieved = extracted_data["retrieved"]
    editable_indexes = extracted_data["editable_indexes"]
    state.add_trace("node_execution", node="handle_context", data={"extracted": str(retrieved)})

    state.cognitive.context_data = retrieved

    if extract_editable:
        state.cognitive.editable_indexes = editable_indexes

    return state
