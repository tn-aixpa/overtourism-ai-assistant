from enum import Enum
from typing import Optional

# consider using gettext for i18n support

class ErrorCode(Enum):
    REQUEST_ERROR = "E001"


class GraphError(Exception):
    def __init__(self, details: Optional[str] = None):
        self.details = details
        super().__init__(self.details)

ERRORS_TEMPLATES = {
        ErrorCode.REQUEST_ERROR: "Error: something went wrong while processing your request.",
}

def get_error_message(code: ErrorCode, **kwargs):
    """
    Retrieve the message for a given code and optionally format it with kwargs.
    """
    template = ERRORS_TEMPLATES[code]
    return template.format(**kwargs)
