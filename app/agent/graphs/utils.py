from datetime import datetime
from langgraph.types import interrupt
from ..state import AgentState, ConversationMessage
from ..nodes.error_recovery import error_recovery_node

# ─────────────────────────────────────────────
# Safe wrappers
# ─────────────────────────────────────────────

def add_safe_node(graph, name, fn):
    graph.add_node(name, safe(fn))

def safe(node_fn):
    def _safe(state):
        try:
            return node_fn(state)
        except Exception as e:
            return error_recovery_node(state, str(e))

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
            state.conversation.append(
                ConversationMessage(
                    role="assistant",
                    content=payload["instructions"],
                    timestamp=datetime.now()
            ))

        response = interrupt(payload)
        if response:
            state.conversation.append(
                ConversationMessage(
                    role="user",
                    content=response,
                    timestamp=datetime.now()
            ))
            state.last_user_en = response

        return state

    return _node
