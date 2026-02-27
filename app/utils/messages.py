from enum import Enum

# consider using gettext for i18n support

class MessageCode(Enum):

    SUCCESS_PROBLEM = "M001"
    SUCCESS_SCENARIO = "M002"

MSG_TRANSLATIONS = {
    "English": {
        MessageCode.SUCCESS_PROBLEM: "The problem was successfully created.",
        MessageCode.SUCCESS_SCENARIO: "The scenarios were successfully created.",
    },
    "Italian": {
        MessageCode.SUCCESS_PROBLEM: "Problema creato con successo.",
        MessageCode.SUCCESS_SCENARIO: "Scenari creati con successo",
    },
}

def get_message(code: MessageCode, lang="English", **kwargs):
    template = MSG_TRANSLATIONS[lang][code]
    return template.format(**kwargs)