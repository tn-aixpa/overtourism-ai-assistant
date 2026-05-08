from enum import Enum

class MessageCode(Enum):
    GENERAL_EXIT_MESSAGE = "M001"
    SUCCESSFUL_INSTANCE_CREATION = "M002"
    CHANGED_CONTEXT = "M003"
    INVALID_REQUEST = "M004"
    INVALID_CONTEXT = "M005"
    NOTHING_TO_LIST = "M006"

MSG_TEMPLATES = {
    MessageCode.GENERAL_EXIT_MESSAGE: "Let me know if you need anything else!",
    MessageCode.SUCCESSFUL_INSTANCE_CREATION: "The {instance} was successfully created. Do you want to activate it now?",
    MessageCode.CHANGED_CONTEXT: "I changed the active context to {new_context}.",
    MessageCode.INVALID_REQUEST: "I'm sorry, but I can't answer this type of request.",
    MessageCode.INVALID_CONTEXT: "The current context does not support the requested operation.",
    MessageCode.NOTHING_TO_LIST: "Sorry, I didn't understand your request, I can list problems, proposals and scenarios.",

}

def get_message(code: MessageCode, **kwargs):
    """
    Retrieve the message for a given code and optionally format it with kwargs.
    """
    template = MSG_TEMPLATES[code]
    return template.format(**kwargs)