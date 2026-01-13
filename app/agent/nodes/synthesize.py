from ollama import Client

from ..state import AgentState

from app.config import OLLAMA_HOST, MODEL_NAME

def synthesize_answers(state: AgentState) -> AgentState:
    # Safety check
    if len(state.expert_answers) <= 1:
        return state

    prompt = f"""
You are a policy synthesizer.

Rules:
- Do NOT invent new facts
- Preserve disagreements
- Be concise
- Do NOT add recommendations unless explicitly present

Question:
{state.user_message}

Expert answers:
"""

    for role, answer in state.expert_answers.items():
        prompt += f"\n[{role}]\n{answer}\n"

    try:
        client = Client(host=OLLAMA_HOST)
        response = client.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You synthesize expert perspectives."},
                {"role": "user", "content": prompt},
            ],
        )
        state.response = response["message"]["content"]
    except Exception as e:
        state.response = f"Error during synthesis: {e}"

    return state
