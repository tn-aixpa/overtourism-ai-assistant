from dataclasses import fields, is_dataclass
from typing import get_type_hints

from app.agent.state import AgentState

def invoke_state(app, state: AgentState) -> AgentState:
    """
    Invoke the LangGraph app and convert the resulting dict back into AgentState recursively.
    """
    result = app.invoke(state)

    def from_dict(cls, data):
        """
        Recursively convert a nested dict to dataclass.
        Safe: if data is already a dataclass, return it as-is.
        """
        # If data is already the correct dataclass, just return it
        if is_dataclass(data):
            return data

        # If cls itself is not a dataclass, just return the value
        if not is_dataclass(cls):
            return data

        if not isinstance(data, dict):
            # Unexpected type, return as-is
            return data

        fieldtypes = get_type_hints(cls)
        init_values = {}

        for f in fields(cls):
            if f.name not in data:
                continue
            val = data[f.name]
            ftype = fieldtypes[f.name]

            # Nested dataclass
            if is_dataclass(ftype):
                init_values[f.name] = from_dict(ftype, val)

            # List of dataclasses
            elif getattr(ftype, "__origin__", None) is list:
                inner_type = ftype.__args__[0]
                if is_dataclass(inner_type):
                    init_values[f.name] = [from_dict(inner_type, x) for x in val]
                else:
                    init_values[f.name] = val

            # Dict with dataclass values
            elif getattr(ftype, "__origin__", None) is dict:
                key_type, val_type = ftype.__args__
                if is_dataclass(val_type):
                    init_values[f.name] = {k: from_dict(val_type, v) for k, v in val.items()}
                else:
                    init_values[f.name] = val

            else:
                init_values[f.name] = val

        return cls(**init_values)

    return from_dict(AgentState, result)

class AgentTestResult:
    def __init__(self, state: AgentState):
        self.state = state

    @property
    def messages(self):
        return self.state.conversation.messages

    def print_conversation(self):
        for m in self.messages:
            print(f"{m.role}: {m.content}")

    def trace(self):
        return self.state.cognitive.trace.steps


class AgentTestRunner:
    def __init__(self, app, initial_state: AgentState):
        self.app = app
        self.state = initial_state
        self.pending_user_inputs = []

    def start(self, message: str):
        self.state.add_user_message(message)
        return self

    def reply(self, message: str):
        self.pending_user_inputs.append(message)
        return self

    def step(self):
        self.state = invoke_state(self.app, self.state)

        if self.state.waiting_for:
            if not self.pending_user_inputs:
                raise RuntimeError(
                    f"Agent waiting for {self.state.waiting_for} but no test reply provided"
                )
            user_reply = self.pending_user_inputs.pop(0)
            self.state.add_user_message(user_reply)
            self.state.user_input = user_reply

        return self.state

    def run(self, max_steps=50):
        steps = 0
        # Run the first message
        self.state = invoke_state(self.app, self.state)
        
        while self.pending_user_inputs and steps < max_steps:
            steps += 1
            
            if self.state.waiting_for:
                # Agent explicitly waiting — pop and inject as before
                user_reply = self.pending_user_inputs.pop(0)
            else:
                # Normal conversational turn — just pop next message
                user_reply = self.pending_user_inputs.pop(0)

            self.state.add_user_message(user_reply)
            self.state.user_input = user_reply if self.state.waiting_for else None
            self.state = invoke_state(self.app, self.state)

        return AgentTestResult(self.state)
    