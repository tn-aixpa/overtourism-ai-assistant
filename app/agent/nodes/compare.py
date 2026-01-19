from ollama import Client

from app.config import OLLAMA_HOST, MODEL_NAME
from ..state import AgentState

def compare_simulations(state: AgentState) -> AgentState:
    # check state
    if len(state.sim_ids) < 2:
        state.response = f"Something went wrong. There are {len(state.sim_ids)} simulations."
        return state
    

    # load data if needed
    unavailable = [sim for sim in state.sim_ids if sim not in state.simulation_data]
    if len(unavailable):
        # TODO: implement fallback to try to load data
        state.response = f"Simulation data for id {unavailable} is not available right now. Please try again later."
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
You are a {role}. Your task is to answer the user's question based strictly on the provided simulations data.
Answers can refer to one or more simulations.

Follow these rules:
1. **Compute numerically** whenever the question asks about differences, changes, rankings, or comparisons.
2. Do not rely on labels like "critical constraint" — use the actual numeric values in the data.
3. Answer with the minimum amount of text necessary.
4. Do not add explanations, interpretations, or conclusions unless explicitly requested.
5. Include only the information needed to directly answer the question.
6. Round all numerical values to 2 decimal places.d

Simulation Data: {data}
Question: {question}
"""

    with open("logs/last_prompt.txt", "w") as f:
        f.write(prompt)

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