from datetime import datetime
import json
from langgraph.types import interrupt
from langgraph.types import Command
from langgraph.errors import Interrupt

from app.schemas import AgentResponse
from app.agent.memory import save_state

from ..state import AgentState
from ...utils.common import translate_to_eng, translate_from_eng
from ...utils.error_codes import ErrorCode, GraphError

# ─────────────────────────────────────────────
# Safe wrappers
# ─────────────────────────────────────────────

def add_safe_node(graph, name, fn):
    graph.add_node(name, safe(fn, name))

from langgraph.errors import GraphInterrupt

def safe(node_fn, node_name):
    def _safe(state):
        try:
            return node_fn(state)

        except GraphError as ge:
            state.error_code = ge.code
            state.error_details = ge.details
            state.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

        except GraphInterrupt as gi:
            raise gi  

        except Exception as e:
            state.error_code = ErrorCode.REQUEST_ERROR
            state.error_details = str(e)
            state.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

    return _safe

# ─────────────────────────────────────────────
# HUMAN GATE NODES (Interrupt-based)
# ─────────────────────────────────────────────

def human_gate(interrupt_type, payload_builder):
    def _node(state: AgentState):
        state.add_trace("human_gate", node=interrupt_type)

        payload = {
            "type": interrupt_type,
            **payload_builder(state),
        }

        if "instructions" in payload:
            state.add_assistant_message(
                localized=translate_from_eng(payload["instructions"], state.user_lang),
                translated_en=payload["instructions"]
            )

        # trigger interrupt
        response = interrupt(payload)
        if response:
            state.add_user_message(
                localized=response,
                translated_en=translate_to_eng(response, state.user_lang)
            )

        return state

    return _node
