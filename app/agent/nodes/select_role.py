from ollama import Client
from ..state import AgentState
from app.config import OLLAMA_HOST, MODEL_NAME, ALLOWED_ROLES

def select_role(state: AgentState) -> AgentState:
    question = state.user_message

    available_roles = "Available roles:"
    for role in ALLOWED_ROLES:
        available_roles += f"\n- {role}: {ALLOWED_ROLES[role]}"

    prompt = f"""
You are selecting expert roles for answering a question about a digital twin simulation.

{available_roles}


Rules:
- Return a comma-separated list of roles.
- Prefer ONE role unless the question asks for solutions, policies, tradeoffs, or impacts.
- If the question does not refer to simulation data directly, but more on reasoning or cause/effect prefer an expert in the domain, otherwise return Data Analyst.
- Do NOT explain your choice.
- Return ONLY role names.

Question:
{question}
"""

    try:
        client = Client(host=OLLAMA_HOST)
        response = client.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You select expert roles."},
                {"role": "user", "content": prompt},
            ],
        )

        raw = response["message"]["content"]
        with open("logs/debug_select_role.txt", "a") as f:
            f.write(f"Q: {question}\nA: {raw}\n")

            # ---- Parse & normalize ----
            roles = []
            for r in raw.split(","):
                key = r.strip()
                roles.append(key)
            f.write(f"Roles: {roles}\n\n")

        # ---- Fallback (important) ----
        if not roles:
            roles = ["UNK"]

        state.selected_roles = roles

    except Exception as e:
        # Hard fallback: never break the graph
        state.selected_roles = ["BBB"]

    return state
