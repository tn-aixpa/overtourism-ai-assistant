from enum import Enum
from typing import Optional

# consider using gettext for i18n support

class ErrorCode(Enum):
    INVALID_REQUEST = "E001"
    INVALID_REQUEST_STATE = "E002"
    REQUEST_ERROR = "E003"
    NOTHING_TO_LIST = "E004"

class GraphError(Exception):
    def __init__(self, code: ErrorCode, details: Optional[str] = None):
        self.code = code
        self.details = details
        super().__init__(str(code))

ERROR_TRANSLATIONS = {
    "English": {
        ErrorCode.INVALID_REQUEST: "I'm sorry, I can't answer this type of request.",
        ErrorCode.INVALID_REQUEST_STATE: "Invalid request in current state.",
        ErrorCode.REQUEST_ERROR: "Something went wrong while processing your request.",
        ErrorCode.NOTHING_TO_LIST: "Sorry, I didn't underestand your request, I can list problems, proposals and scenarios."
    },
    "Italian": {
        ErrorCode.INVALID_REQUEST: "Mi dispiace, non posso rispondere a questo tipo di richiesta.",
        ErrorCode.INVALID_REQUEST_STATE: "Richiesta non valida nello stato corrente.",
        ErrorCode.REQUEST_ERROR: "Errore durante l'elaborazione della richiesta.",
        ErrorCode.NOTHING_TO_LIST: "Scusa, non ho capito la tua richiesta, Posso darti la lista di problemi, porposte o scenari."
    },
}

def get_error_message(code: ErrorCode, lang="English", **kwargs):
    template = ERROR_TRANSLATIONS[lang][code]
    return template.format(**kwargs)