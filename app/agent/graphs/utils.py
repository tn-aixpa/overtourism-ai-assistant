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

def human_gate(interrupt_type, output_key, payload_builder):
    def _node(state: AgentState):

        payload = {
            "type": interrupt_type,
            **payload_builder(state),
        }

        result = interrupt(payload)

        return {output_key: result}

    return _node
