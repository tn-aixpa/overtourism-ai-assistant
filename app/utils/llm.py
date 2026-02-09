from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

DEBUG = False

# Initialize local Ollama model
llm = ChatOllama(
    model="mistral",
    base_url="http://localhost:11434",
    temperature=0,
)

def llm_interaction(prompt: str) -> str:
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        return f"Error connecting to Ollama: {e}"
    
def classify_intent(active_sims: list, user_message: str) -> str:
    context = "City management and overtourism" #TODO: move it somewhere else
    prompt = f"""
You are an intent classifier.
Your task is to determine the user's intended action.

Possible actions:
- INTERACT_SCENARIO: Analyze, explain, interpret, or explore existing scenarios.
- CREATE_PROBLEM: Create a new problem starting from it's description. When creating a new problem the user might want to include also scenarios generation.
  parameters of an existing scenario.
- RUN_NEW_SCENARIO: Create, run, start, or re-run a scenario, including modifying
  parameters of an existing scenario.
- INVALID: The request is totally unclear and the intent cannot be determined or the request is clear but unrelated to scenarios or system capabilities.

Decision rules:

1. If the user request is clear and refers to a scenario → INTERACT_SCENARIO.
2. If the user mentions a new problem or the focus of the request is a specific problem description → CREATE_PROBLEM.
3. If the user request asks to run, create, start, or modify a scenario → RUN_NEW_SCENARIO.
4. If the request is unrelated to problems or scenarios in the related to {context} → INVALID.
5. If the request is totally unclear or vague → INVALID.

Context: {context}.
The Context provides background but does not override the intent rules.

User request: {user_message}
Active scenarios: {active_sims or "none"}

Return only the action name.

"""
       
    return llm_interaction(prompt)

def select_role_llm(question: str, allowed_roles: dict) -> str:

    available_roles = "Available roles:"
    for role in allowed_roles:
        available_roles += f"\n- {role}: {allowed_roles[role]}"

    prompt = f"""
You are selecting expert roles for answering a question about a digital twin scenario.

{available_roles}


Rules:
- Return a comma-separated list of roles.
- Prefer ONE role unless the question asks for solutions, policies, tradeoffs, or impacts.
- If the question does not refer to scenario data directly, but more on reasoning or cause/effect prefer an expert in the domain, otherwise return Data Analyst.
- Do NOT explain your choice.
- Return ONLY role names.

Question:
{question}
"""

    answer = llm_interaction(prompt)

    if DEBUG:
        with open("logs/debug_select_role.txt", "a") as f:
            f.write(f"Q: {question}\nA: {answer}\n")

    return answer



def answer_question_comparison(question: str, data: dict, role: str) -> str:
    """
    Calls a local Ollama instance with Mistral to answer questions over scenario data.
    """

    prompt = f"""
You are a {role}. Your task is to answer the user's question based strictly on the provided scenarios data.
Answers can refer to one or more scenarios.

Follow these rules:
1. **Compute numerically** whenever the question asks about differences, changes, rankings, or comparisons.
2. Do not rely on labels like "critical constraint" — use the actual numeric values in the data.
3. Answer with the minimum amount of text necessary.
4. Do not add explanations, interpretations, or conclusions unless explicitly requested.
5. Include only the information needed to directly answer the question.
6. Round all numerical values to 2 decimal places.d

Scenario Data: {data}
Question: {question}
"""

    if DEBUG:
        with open("logs/last_prompt.txt", "w") as f:
            f.write(prompt)

    return llm_interaction(prompt)
    

def answer_question(question: str, data: dict, role: str) -> str:
    """
    Calls a local Ollama instance with Mistral to answer questions over scenario data.
    """

    prompt = f"""
You are a {role}. Your task is to answer the user's question based strictly on the provided scenario data.

Follow these rules:
- Answer with the minimum amount of text necessary.
- Do not add explanations, interpretations, or conclusions unless explicitly requested in the question.
- Include only the information needed to directly answer the question.
- When numerical values are included, round them to 2 decimal places.

Scenario Data: {data}
Question: {question}
"""

    return llm_interaction(prompt)

def synthesize_llm(user_message: str, expert_answers: dict) -> str:
    prompt = f"""
You are a policy synthesizer.

Rules:
- Do NOT invent new facts
- Preserve disagreements
- Be concise
- Do NOT add recommendations unless explicitly present

Question:
{user_message}

Expert answers:
"""

    for role, answer in expert_answers.items():
        prompt += f"\n[{role}]\n{answer}\n"

    return llm_interaction(prompt)

def extract_problem_data(user_message: str, problem_info: dict, extracted_problem_info: dict) -> str:
    all_keys = list(problem_info.keys())
    keys_to_extract = {k for k in all_keys if k not in extracted_problem_info}

    prompt = f"""You are a problem information extractor for a city management digital twin focused on overtourism.
Your task is to extract structured information about a problem from the user's message.
The information to extract is:
{', '.join(keys_to_extract)}
Rules:
- Return your answer in JSON format with the following structure:
{{
{', '.join([f'  "{field}": "extracted content"' for field in keys_to_extract])}
}}
- Fill each field with corresponding information from the user's message, if present.
- If a field is about the tile, please limit the length to maximum 3 words.
- You can reuse information to fill more than one field if applicable.
- Do NOT invent information that is not present in the user's message.
- If no information is found for a field do not include it in the output.
{user_message}
"""
    
    return llm_interaction(prompt)