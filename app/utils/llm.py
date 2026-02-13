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
    
def classify_intent(active_sims: list, message: str) -> str:
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

User request: {message}
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

def synthesize_llm(message: str, expert_answers: dict) -> str:
    prompt = f"""
You are a policy synthesizer.

Rules:
- Do NOT invent new facts
- Preserve disagreements
- Be concise
- Do NOT add recommendations unless explicitly present

Question:
{message}

Expert answers:
"""

    for role, answer in expert_answers.items():
        prompt += f"\n[{role}]\n{answer}\n"

    return llm_interaction(prompt)

def extract_problem_data(message: str, problem_info_to_extract: dict, extracted_problem_info: dict) -> str:
    #TODO: might need to revise to add the possiblity to change/integrate/remove a field

    all_keys = list(problem_info_to_extract.keys())
    keys_to_extract = {k for k in all_keys if k not in extracted_problem_info}

    prompt = f"""You are a problem information extractor for a city management digital twin focused on overtourism.

Your task is to extract structured information about a problem from the user's message.

Fields that MAY be extracted:
{', '.join(keys_to_extract)}

This is what each field means:
{', '.join([f'{k}: {problem_info_to_extract[k]["description"]}' for k in all_keys if k not in extracted_problem_info])}

IMPORTANT RULES:

- Return ONLY a JSON object.
- Extract ONLY concrete problem content (real-world issues, constraints, descriptions, goals, systems).
- DO NOT extract meta-intent about creating or defining a problem.
  Example of meta-intent that must be ignored:
    - "I want to create a new problem"
    - "Let's define a problem"
    - "Add a problem"
- The user must describe an actual problem situation for any field to be included.
- If the message only expresses intent to create or manage a problem but provides no actual problem details, return exactly ''.
- NEVER infer, summarize, reinterpret, or expand the message.
- NEVER generate generic summaries.
- Remove from the output any fields that are empty strings or empty arrays.

Special rule for "problem_title": maximum 3 words.

User message:
{message}
"""
    
    return llm_interaction(prompt)

def format_messages(messages):
    return "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in messages
    )

def assess_scenario_strategy(messages: list) -> str:
    prompt = f"""You are an intent classfier that need to decide if and how the user wants to create scenarios based on the conversation history.
Possible actions:
- GENERATE_SCENARIOS: The user wants to create scenarios and has or will provided enough information.
- GENERATE_AGENTIC_SCENARIOS: The user wants to create scenarios, but would like the system to generate them based on some general information provided.
- ASK_USER_PREFERENCE: It is unclear/unkown if the user wants to create scenarios or if he prefers atuomatic or manual geneartion of scenarios.
- NO_SCENARIOS: The user does not want to create scenarios for the current problem.
Rules:
- If the user explicitly mentions wanting to create scenarios and provides specific information about them → GENERATE_SCENARIOS.
- If the user asks for suggestions/solutions for the problem or explicitly mentions wanting the system to generate appropirate scenarios → GENERATE_AGENTIC_SCENARIOS.
- If scenarios are mentioned try to make a decision between GENERATE_SCENARIOS and GENERATE_AGENTIC_SCENARIOS based on the level of detail provided by the user.
- If the user says that they do not want to create scenarios, or answered no upon system request → NO_SCENARIOS.
- If the user only mentions a problem, without talking about modifications or solutions → ASK_USER_PREFERENCE.
- If the user's intent is unclear or cannot be determined → ASK_USER_PREFERENCE.

Message history:
{format_messages(messages)}

Return only the action name.
"""
    return llm_interaction(prompt)

def extract_scenario_data(messages: dict, scenario_info_to_extract: dict, editable_idexes: dict) -> str:
    all_keys = list(scenario_info_to_extract.keys())

    prompt = f"""
SYSTEM ROLE:

You are a deterministic structured data extractor.

Your output is parsed automatically by a machine.
If the output is not valid JSON, the system will fail.

--------------------------------------------------

TASK:

Extract structured information about proposed solutions
from the conversation.

--------------------------------------------------

STRICT OUTPUT CONTRACT:

- Output MUST be valid JSON.
- Output MUST be a JSON ARRAY.
- Each item = ONE solution.
- NEVER output multiple JSON objects concatenated.
- NEVER output markdown (no ```).
- NEVER output explanations or extra text.
- The response MUST start with "[" and end with "]".
- The JSON must be directly parsable with json.loads().

--------------------------------------------------

SCHEMA (STRICT):

[
  {{
    "title": string (max 3 words),

    "context_conditions": string (optional),

    "indexes_to_change": {{
        "<index_name>": {{
            "type": "increase" | "decrease" | "range",
            "value": number OR [lower_number, upper_number]
        }}
    }},

    "potential_impact": string (optional),
    "description": string (optional),
    "additional_data": string (optional)
  }}
]

Allowed index keys:
{', '.join(list(editable_idexes.keys()))}

--------------------------------------------------

EXTRA RULES:

- Extract ONLY explicit information.
- NEVER infer missing details.
- Remove empty fields entirely.
- If no solutions exist, return [].
- Inside "indexes_to_change" NEVER put a list as 'value' if type is "increase" or "decrease".
- Inside "indexes_to_change" NEVER put a single number as 'value' if type is "range".

--------------------------------------------------

SELF-CHECK (MANDATORY BEFORE OUTPUT):

Before producing the final answer:

1) Verify the output is valid JSON.
2) Verify the output is a list.
3) Verify it begins with "[" and ends with "]".
4) Verify there is NO text outside the JSON.
5) Verify no empty fields exist.

Only after validation, output the JSON.

--------------------------------------------------

MESSAGE HISTORY:

{format_messages(messages)}
"""
    
    return llm_interaction(prompt)