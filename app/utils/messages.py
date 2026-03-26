from enum import Enum

# consider using gettext for i18n support

class MessageCode(Enum):

    ANYTHING_ELSE = "M000"
    SUCCESS_PROBLEM = "M001"
    SUCCESS_SCENARIO = "M002"
    GENRAL_EXIT_MESSAGE = "M003"
    CHANGED_CONTEXT = "M004"


MSG_TRANSLATIONS = {
    "English": {
        MessageCode.ANYTHING_ELSE: "Is there any other way in which I can help?",
        MessageCode.SUCCESS_PROBLEM: "The problem was successfully created.",
        MessageCode.SUCCESS_SCENARIO: "The scenarios were successfully created.",
        MessageCode.GENRAL_EXIT_MESSAGE: "Okay, let me know if you need anything else!",
        MessageCode.CHANGED_CONTEXT: "I changed the active context to {new_context}."
    },
    "Italian": {
        MessageCode.ANYTHING_ELSE: "Posso aiutarti in qualche altro modo?",
        MessageCode.SUCCESS_PROBLEM: "Problema creato con successo.",
        MessageCode.SUCCESS_SCENARIO: "Scenari creati con successo",
        MessageCode.GENRAL_EXIT_MESSAGE: "Okay, fammi sapere se hai bisogno di qualcosa altro!",
        MessageCode.CHANGED_CONTEXT: "Ora il contesto attivo è il seguent: {new_context}."
    },
}

def get_message(code: MessageCode, lang="English", **kwargs):
    template = MSG_TRANSLATIONS[lang][code]
    return template.format(**kwargs)