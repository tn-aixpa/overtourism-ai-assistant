from langgraph.types import Command

from app.utils.error_codes import ErrorCode, GraphError

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
            state.cognitive.error_code = ge.code
            state.cognitive.error_details = ge.details
            state.cognitive.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

        except GraphInterrupt as gi:
            raise gi  

        except Exception as e:
            state.cognitive.error_code = ErrorCode.REQUEST_ERROR
            state.cognitive.error_details = str(e)
            state.cognitive.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

    return _safe
