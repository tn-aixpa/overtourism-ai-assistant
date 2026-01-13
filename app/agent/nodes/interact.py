from ollama import Client

from ..state import AgentState

# TODO: consider moving to config
OLLAMA_HOST = "http://localhost:11434"
MODEL_NAME = "mistral"

def interact_simulation(state: AgentState) -> AgentState:

    # check state
    if state.sim1_id is None:
        state.response = "Something went wrong. No simulation is available to interact with."
        return state
    

    # load data if needed
    if state.simulation_data is None:
        # TODO: implement fallback to try to load data
        state.response = f"Simulation data for id {state.sim1_id} is not available right now. Please try again later."
        return state

    role="data analyst"

    # answer user question
    state.response = answer_question(
        question=state.user_message,
        data=state.simulation_data,
        role=role,
    )

    return state


def answer_question(question: str, data: dict, role: str) -> str:
    """
    Calls a local Ollama instance with Mistral to answer questions over simulation data.
    """

    prompt = f"""
You are a {role}. Your task is to answer the user's question based strictly on the provided simulation data.

Follow these rules:
- Answer with the minimum amount of text necessary.
- Do not add explanations, interpretations, or conclusions unless explicitly requested in the question.
- Include only the information needed to directly answer the question.
- When numerical values are included, round them to 2 decimal places.

Simulation Data: {data}
Question: {question}
"""

    try:
        client = Client(host=OLLAMA_HOST)
        messages = [
            {"role": "system", "content": f"You are a {role}."},
            {"role": "user", "content": prompt}
        ]
        response = client.chat(model=MODEL_NAME, messages=messages)
        return response["message"]["content"]
    except Exception as e:
        return f"Error connecting to Ollama: {e}"