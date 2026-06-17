import logging
from langgraph.types import Command

from app.utils.common import RequestHandlingException
from app.utils.error_codes import GraphError

logger = logging.getLogger(__name__)
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

        except GraphInterrupt as gi:
            raise gi

        except RequestHandlingException as rhe:
            # Custom behaviour: no errors.txt logging, just surface to user
            logger.warning(f"Request handling error in node {node_name}: {rhe}")
            state.cognitive.error_details = str(rhe)
            state.cognitive.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

        except GraphError as ge:
            logger.warning(f"GraphError in node {node_name}: {rhe}")
            state.cognitive.error_details = ge.details
            state.cognitive.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

        except Exception as e:
            logger.error(f"Unexpected error in node {node_name}: {str(e)}")
            state.cognitive.error_details = str(e)
            state.cognitive.error_node = node_name
            return Command(update=state, goto="error", graph=Command.PARENT)

    return _safe
