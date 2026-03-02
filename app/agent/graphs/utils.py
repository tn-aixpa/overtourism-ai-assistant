from datetime import datetime
from langgraph.types import interrupt
from langgraph.types import Command

from ..state import AgentState, ConversationMessage
from ...utils.common import translate_to_eng, translate_from_eng
from ...utils.error_codes import ErrorCode, GraphError

# ─────────────────────────────────────────────
# Safe wrappers
# ─────────────────────────────────────────────

def add_safe_node(graph, name, fn):
    graph.add_node(name, safe(fn, name))

def safe(node_fn, node_name):
    def _safe(state):
        try:
            return node_fn(state)

        except GraphError as ge:
            state.error_code = ge.code
            state.error_details = f"Node {node_name}, error: {ge.details}"

            return Command(
                update=state,
                goto="error",
                graph=Command.PARENT
            )

        except Exception as e:
            state.error_code = ErrorCode.REQUEST_ERROR
            state.error_details = f"Node {node_name}, error: {e}"

            return Command(
                update=state,
                goto="error",
                graph=Command.PARENT
            )

    return _safe

# ─────────────────────────────────────────────
# HUMAN GATE NODES (Interrupt-based)
# ─────────────────────────────────────────────

def human_gate(interrupt_type, payload_builder):
    def _node(state: AgentState):

        payload = {
            "type": interrupt_type,
            **payload_builder(state),
        }

        if "instructions" in payload:
            state.add_assistant_message(
                localized=translate_from_eng(payload["instructions"], state.user_lang),
                translated_en=payload["instructions"]
            )

        response = interrupt(payload)
        if response:
            state.add_user_message(
                localized=response,
                translated_en=translate_to_eng(response, state.user_lang)
            )

        return state

    return _node
