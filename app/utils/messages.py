from enum import Enum

# consider using gettext for i18n support

class MessageCode(Enum):
    ANYTHING_ELSE = "M000"
    GENERAL_EXIT_MESSAGE = "M001"  # fixed typo
    SUCCESS_PROBLEM = "M002"
    SUCCESS_PROPOSAL = "M003"
    SUCCESS_SCENARIO = "M004"
    CHANGED_CONTEXT = "M005"

# Only English messages now
MSG_TRANSLATIONS = {
    MessageCode.ANYTHING_ELSE: "Is there any other way in which I can help?",
    MessageCode.SUCCESS_PROBLEM: "The problem was successfully created.",
    MessageCode.SUCCESS_PROPOSAL: "The proposal was successfully created.",
    MessageCode.SUCCESS_SCENARIO: "The scenarios were successfully created.",
    MessageCode.GENERAL_EXIT_MESSAGE: "Okay, let me know if you need anything else!",
    MessageCode.CHANGED_CONTEXT: "I changed the active context to {new_context}."
}

def get_message(code: MessageCode, **kwargs):
    """
    Retrieve the message for a given code and optionally format it with kwargs.
    """
    template = MSG_TRANSLATIONS[code]
    return template.format(**kwargs)