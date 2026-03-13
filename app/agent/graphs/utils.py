from langgraph.types import Command

from ..state import AgentState
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
