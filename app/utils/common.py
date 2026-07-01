from __future__ import annotations
from contextvars import ContextVar
from typing import Optional
import logging

logger = logging.getLogger(__name__)
_current_token: ContextVar[str | None] = ContextVar("_current_token", default=None)


def set_token(token: str) -> None:
    logger.debug(f"Setting auth token in current context: {token}")
    _current_token.set(token)

def get_token() -> str:
    token = _current_token.get()
    if token is None:
        raise RuntimeError("No auth token set in current context")
    return token
class GraphError(Exception):
    def __init__(self, details: Optional[str] = None):
        self.details = details
        super().__init__(self.details)

class RequestHandlingException(GraphError):
    """Exception raised when request handling fails."""
    def __init__(self, message: str):
        super().__init__(
            details=str(message)
        )
