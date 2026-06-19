from __future__ import annotations
# import re
import logging

from app.utils.error_codes import GraphError

logger = logging.getLogger(__name__)


class RequestHandlingException(GraphError):
    """Exception raised when request handling fails."""
    def __init__(self, message: str):
        super().__init__(
            details=str(message)
        )