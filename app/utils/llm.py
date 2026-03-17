from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from typing import List
from app.agent. state import ConversationMessage

DEBUG = False

# Initialize local Ollama model
llm = ChatOllama(
    model="mistral",
    base_url="http://localhost:11434",
    temperature=0,
)

def format_messages(messages):
    return "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

def llm_interaction(prompt: str) -> str:
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        return f"Error connecting to chatbot: {e}"
    
def classify_intent(message: str) -> str:
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

Follow these rules STRICTLY:

1. Extract numeric values directly from the data.
2. When comparing scenarios:
   - compute delta = scenario_2 - scenario_1
   - delta > 0 → "increased"
   - delta < 0 → "decreased"
   - delta = 0 → "unchanged"
3. NEVER infer increase/decrease without numeric calculation.
4. If index_diffs exist, explicitly connect them to KPI changes.
5. Do not rely on labels like "critical constraint" — use numeric values.
6. Use minimal text.
7. Round all numbers to 2 decimal places.
8. Do not add speculative impacts unless explicitly requested.

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

def extract_problem_data(messages: List[ConversationMessage], problem_info_to_extract: dict, extracted_problem_info: dict) -> str:
    #TODO: might need to revise to add the possiblity to change/integrate/remove a field

    all_keys = list(problem_info_to_extract.keys())

    prompt = f"""
SYSTEM ROLE:

You are a deterministic structured data extractor.

Your output is parsed automatically by a machine.
If the output is not valid JSON, the system will fail.

--------------------------------------------------

TASK:

Extract structured information about a REAL-WORLD problem
from the conversation.

--------------------------------------------------

STRICT OUTPUT CONTRACT:

- Output MUST be valid JSON.
- Output ONLY ONE JSON object.
- NEVER output markdown.
- NEVER output explanations or extra text.
- NEVER output role prefixes like "ASSISTANT:".
- The response MUST start with "{{" and end with "}}".
- The JSON must be directly parsable with json.loads().
- All fields must contain textual values except for available_subsystems.
- Remove empty fields entirely.

--------------------------------------------------

SCHEMA (STRICT):

A dictionary with pairs (key, value)

Allowed index keys:
{', '.join(list(all_keys))}

--------------------------------------------------

DEFINITION OF A VALID PROBLEM:

A valid problem MUST include explicit real-world content such as:

- a described situation
- an issue, constraint, difficulty, or goal
- concrete context

--------------------------------------------------

META-INTENT IS NOT A PROBLEM:

Statements about creating, defining, planning,
or wanting to make a problem are NOT problems.

Examples that MUST produce empty output:

- "I want to create a new problem."
- "Let's define a problem."
- "Add a problem."

If ONLY meta-intent exists, treat it as NO DATA.

--------------------------------------------------

EMPTY RESULT RULE (VERY IMPORTANT):

If no valid real-world problem exists in the conversation

Do NOT invent placeholder titles or descriptions.
Do NOT summarize meta-intent.
Remove all empty keys from the output dictionary.

--------------------------------------------------

EXTRACTION RULES:

- Extract ONLY explicit information.
- NEVER infer missing details.
- NEVER fabricate content.
- Field 'problem_title' should be short (2-3 words) when present.

--------------------------------------------------

SELF-CHECK (MANDATORY BEFORE OUTPUT):

Before producing the final answer:

1) Verify the output is valid JSON.
2) Verify there is NO text outside the JSON.
3) Verify no empty fields exist.
4) If no valid problem exists, output {{}}.

Only after validation, output the JSON.

--------------------------------------------------

MESSAGE HISTORY:

{format_messages(messages)}
"""

    
    return llm_interaction(prompt)

def assess_scenario_strategy(messages: List[ConversationMessage]) -> str:
    prompt = f"""You are an intent classifier that determines whether the user wants to create scenarios based on the conversation history.
The conversation may include steps to define a problem, so do not confuse confirations about proceeding with problem creation with the user wanting to create scenarios yet.
A scenario is a modification of currect indexes that could possibly solve a problem; consequently problems are typically created before scenarios.
Scenario creation can be either user-driven, where the user specifies which indexes to change and how, or agent-driven, where the user asks the system to generate scenarios based on general information or preferences.

Possible actions:
- GENERATE_SCENARIOS: The user wants to create scenarios and knows what indexes he wants to change.
- GENERATE_AGENTIC_SCENARIOS: The user wants to create scenarios, but would like the system to generate them based on some general information provided.
- ASK_USER_PREFERENCE: It is unclear/unkown if the user wants to create scenarios or if he prefers to specify them or to let the system generate them.
- NO_SCENARIOS: The user does not want to create scenarios for the current problem.


Rules:
- If the user was asked about creating scenarios and the latest user message is a clear "No" → NO_SCENARIOS.
- If the user was asked about creating scenarios, try to decide between GENERATE_SCENARIOS and GENERATE_AGENTIC_SCENARIOS based on whether the user provided specific information about scenario changes or just general preferences or indications. Use ASK_USER_PREFERENCE if the intent is unclear.
- If the user explicitly mentioned wanting to create scenarios before and provides specific information about them → GENERATE_SCENARIOS.
- If the user explicitly asked the assistant about scenario suggestions, possible modifications, or solutions → GENERATE_AGENTIC_SCENARIOS.
- Generic affirmations without scenario-related context → ASK_USER_PREFERENCE.
- If the user explicitly stated that they do not want to create scenarios → NO_SCENARIOS.
- If the user only mentions a problem, without talking about scenarios or specific changes to solve it → ASK_USER_PREFERENCE.
- If the user's intent is unclear or cannot be determined → ASK_USER_PREFERENCE.

Message history:
{format_messages(messages)}

Return only the action name.
"""
    
    return llm_interaction(prompt)

def extract_scenario_data(messages: List[ConversationMessage], editable_indexes: dict) -> str:
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
{', '.join(list(editable_indexes.keys()))}

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


def llm_classify_confirmation(message: str):
    prompt = f"""
You are an intent classifier inside an AI workflow.

Your task:
Classify the user's message into ONE of the following labels:

- CONFIRM
User clearly agrees, confirms, or wants to proceed.

- EDIT
User wants to modify, change, or adjust something before proceeding.

- CANCEL
User wants to stop, cancel, or quit the process.

- WAIT_CONFIRMATION
User intent is unclear, unrelated, ambiguous, or not a confirmation.

IMPORTANT RULES:

1. Return ONLY the label name.
2. Do NOT explain your reasoning.
3. Do NOT add extra text.
4. If uncertain, choose WAIT_CONFIRMATION.
5. Support multiple languages.

User message:
\"\"\"{message}\"\"\"
"""

    result = llm_interaction(prompt)

    allowed = {
        "CONFIRM",
        "EDIT",
        "CANCEL",
        "WAIT_CONFIRMATION",
    }

    return result if result in allowed else "WAIT_CONFIRMATION_PROBLEM"

translate_prompt = ChatPromptTemplate.from_template(
    "Translate the following text from {input_language} to {target_language}. "
    "Return ONLY the translated text. Do not explain.\n\n{text}"
)

def translate(text, input_language, target_language):
    chain = translate_prompt | llm
    return chain.invoke({
        "text": text,
        "input_language": input_language,
        "target_language": target_language
    }).content