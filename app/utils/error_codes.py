from enum import Enum
from typing import Optional

# consider using gettext for i18n support

class ErrorCode(Enum):
    REQUEST_ERROR = "E001"
    INVALID_REQUEST = "E002"
    INVALID_CONTEXT = "E003"
    INVALID_REQUEST_STATE = "E004"
    NOTHING_TO_LIST = "E005"


class GraphError(Exception):
    def __init__(self, code: ErrorCode, details: Optional[str] = None):
        self.code = code
        self.details = details
        super().__init__(str(code))

ERROR_TRANSLATIONS = {
        ErrorCode.REQUEST_ERROR: "Errror: something went wrong while processing your request.",
        ErrorCode.INVALID_REQUEST: "Error: I can't answer this type of request.",
        ErrorCode.INVALID_CONTEXT: "Error: the current context does not support the requested operation.",
        ErrorCode.INVALID_REQUEST_STATE: "Error: Invalid request in current state.",
        ErrorCode.NOTHING_TO_LIST: "Error: I didn't underestand your request, I can list problems, proposals and scenarios.",
}

def get_error_message(code: ErrorCode, **kwargs):
    """
    Retrieve the message for a given code and optionally format it with kwargs.
    """
    template = ERROR_TRANSLATIONS[code]
    return template.format(**kwargs)
