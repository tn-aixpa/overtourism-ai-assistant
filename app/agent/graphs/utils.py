from langgraph.types import interrupt
from ..state import AgentState
from ..nodes.error_recovery import error_recovery_node

# ─────────────────────────────────────────────
# Safe wrappers
# ─────────────────────────────────────────────

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
            state.messages.append({
                "role": "assistant",
                "content": payload["instructions"]
            })

        response = interrupt(payload)
        if response:
            state.messages.append({
                "role": "user",
                "content": response
            })

        return state

    return _node
