from ollama import Client

from ..state import AgentState
from app.config import OLLAMA_HOST, MODEL_NAME

def interact_simulation(state: AgentState) -> AgentState:

    # check state
    if len(state.sim_ids) == 0:
        state.response = "Something went wrong. No simulation is available to interact with."
        return state
    
    if len(state.sim_ids) > 1:
        state.response = "Something went wrong. More than one active simulation"
        return state
    

    # load data if needed
    if state.sim_ids[0] not in state.simulation_data:
        # TODO: implement fallback to try to load data
        state.response = f"Simulation data for id {state.sim_ids[0]} is not available right now. Please try again later."
        return state

    state.expert_answers = {}

    # answer user question
    for role in state.selected_roles:

        answer = answer_question(
            question=state.user_message,
            data=state.simulation_data,
            role=role,
        )
        state.expert_answers[role] = answer
    
    if len(state.selected_roles) == 1:
        state.response = next(iter(state.expert_answers.values()))

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