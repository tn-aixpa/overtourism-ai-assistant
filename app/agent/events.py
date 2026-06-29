from queue import Queue
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

_queues: dict[str, Queue] = defaultdict(Queue)
_results: dict[str, dict] = {}          # store final results here

def get_queue(session_id: str) -> Queue:
    return _queues[session_id]

def publish(session_id: str, event: str):
    logger.info(f"Publishing event to session {session_id}: {event}")
    _queues[session_id].put(event)

def publish_done(session_id: str, result: dict):
    _results[session_id] = result        # store before signalling done
    _queues[session_id].put("__done__")

def get_result(session_id: str) -> dict | None:
    return _results.pop(session_id, None)