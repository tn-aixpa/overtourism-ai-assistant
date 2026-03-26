from typing import List
from app.agent. state import ConversationMessage
import re

from app.utils.state_variables import VALID_INTENTS
from app.utils.llm import llm_interaction, format_messages, DEBUG

# ---------------------------------------------------------------------------
# INTENT CLASSIFICATION
# ---------------------------------------------------------------------------

def classify_intent(message: str, history: List[ConversationMessage] = None) -> str:
    """
    Classify the user's intent given the current message and optional
    conversation history.  Returns one of:
        LIST_AVAILABLE | INTERACT_SCENARIO | CREATE_NEW_PROBLEM |
        CREATE_NEW_PROPOSAL | CREATE_NEW_SCENARIO | CONTEXT_MANAGEMENT | INVALID
    """
    context = "City management and overtourism"

    history_block = ""
    if history:
        history_block = f"""
Conversation so far
{format_messages(history)}\n\n
"""
    prompt = f"""You are an intent classifier for a digital-twin platform about {context}.

{history_block}New user message: "{message}"

Your job: classify the NEW user message into exactly ONE of these actions.

ACTIONS:

1. LIST_AVAILABLE
   → User asks to see / list existing problems, proposals or scenarios on the platform.
   Signals: "show me", "list", "what problems are there", "available scenarios".

2. CONTEXT_MANAGEMENT
   → User wants to set their active context to a specific problem, proposal, or scenario,
     so that subsequent actions apply to it. The target may be named explicitly (by id or
     title), or referred to relatively ("the last one", "the first one", "the third").
     Often follows a LIST_AVAILABLE response.
     OR the user wants to remove a problem, proposal, or scenario from their active context.
     OR the user wants to change the context to a given problem/proposal/scenario to another.
   Signals: "activate X", "I want to focus on", "let's work on", "let's explore", "I am interested in",
            "set the context to", "select", "open", "use problem X", "the last one",
            "the first one", "that one", "I'm no longer interested in","remove X from context",
            "deselect", "close", "stop working on", "forget about X", "clear the context"..
   Note: resolving WHICH item the user means is handled downstream — classify as CONTEXT_MANAGEMENT
         even when the reference is vague or relative.

4. CREATE_NEW_PROBLEM
   → User wants to register a NEW real-world problem, OR is in the middle of describing
     one, even if they also hint at solutions or scenarios.
   Priority: if the user mentions creating a problem AND creating scenarios, prefer CREATE_NEW_PROBLEM.
   Signals: "I have a problem", "new problem", "add a problem", "we need to address", "the issue is".

5. CREATE_NEW_PROPOSAL
   → User wants to create a new proposal (and is NOT primarily describing a new problem).
   Signals: "create a proposal", "new proposal".

6. CREATE_NEW_SCENARIO
   → User wants to create, run, start or modify a scenario (and is NOT primarily describing
     a new problem).
   Signals: "create a scenario", "run scenario", "modify scenario", "new scenario",
            "let's simulate", "what if we changed".

7. INTERACT_SCENARIO
   → User wants to analyse, explore, compare or get information about EXISTING scenarios
     that are already on the platform.
     Questions related to indexes, constraints belong to this action.
   Signals: "explain scenario", "what does scenario X show", "compare scenario A and B",
            "interpret the results", "what is the most critical index".

8. INVALID
   → Anything unrelated to {context}, or too vague to classify into 1-7.

DECISION RULES:
- CONTEXT_MANAGEMENT vs INTERACT_SCENARIO: CONTEXT_MANAGEMENT is about selecting/focusing on an item as context.
  INTERACT_SCENARIO is about asking analytical questions about it. "Let's work on problem X" → CONTEXT_MANAGEMENT.
  "What does scenario X show?" → INTERACT_SCENARIO.
- CONTEXT_MANAGEMENT vs LIST_AVAILABLE: "Show me the problems, then let's focus on the first one" → CONTEXT_MANAGEMENT
  (the selection intent dominates). A pure listing request with no selection intent → LIST_AVAILABLE.
- CREATE_NEW_SCENARIO vs INTERACT_SCENARIO: if the scenario does NOT exist yet → CREATE.
  If the scenario already exists and the user just wants to discuss/analyse it → INTERACT.
- Generic one-word replies ("yes", "ok", "sure") with no prior context → INVALID.
- Generic one-word replies that follow a CREATE_NEW_PROBLEM or CREATE_NEW_SCENARIO assistant prompt
  should be inferred from the conversation history above.

EXAMPLES:
User: "List all the available problems" → LIST_AVAILABLE
User: "I want to focus on problem P1" → CONTEXT_MANAGEMENT
User: "Let's explore the last scenario" → CONTEXT_MANAGEMENT
User: "Set the context to the third proposal" → CONTEXT_MANAGEMENT
User: "That one" (after a list was shown) → CONTEXT_MANAGEMENT
User: "I'm no longer interested in problem P1" → CONTEXT_MANAGEMENT
User: "Remove scenario S2 from context" → CONTEXT_MANAGEMENT
User: "Clear the active problem" → CONTEXT_MANAGEMENT
User: "We have an overtourism problem in the historic centre" → CREATE_NEW_PROBLEM
User: "I want to create a problem about traffic congestion" → CREATE_NEW_PROBLEM
User: "I want to create a new proposal to solve the problem" → CREATE_NEW_PROPOSAL
User: "Let's define a new proposal" → CREATE_NEW_PROPOSAL
User: "Create a scenario where we reduce tourist bus permits by 20%" → CREATE_NEW_SCENARIO
User: "Run a new scenario with stricter entry limits" → CREATE_NEW_SCENARIO
User: "What does scenario S3 show about hotel occupancy?" → INTERACT_SCENARIO
User: "Compare scenario A and scenario B" → INTERACT_SCENARIO
User: "Tell me a joke" → INVALID
User: "Yes" (no history) → INVALID

Return ONLY the action name. No explanation, no punctuation.
"""

    raw = llm_interaction(prompt).strip().upper()

    # Normalise: strip punctuation, take first token
    first_token = re.split(r'[\s\.,;]', raw)[0]

    if first_token in VALID_INTENTS:
        return first_token

    # Fallback: substring match in case the model added a prefix/suffix
    for intent in VALID_INTENTS:
        if intent in raw:
            return intent

    return "INVALID"

# ---------------------------------------------------------------------------
# SELECT ROLE
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# PROBLEM DATA EXTRACTION
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# ASSESS SCENARIO STRATEGY
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# SCENARIO DATA EXTRACTION
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# CONFIRMATION PARSING
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# DECIDE WHAT NEEDS TO BE LISTED
# ---------------------------------------------------------------------------

def assess_what_to_list(message):
    prompt = f"""
SYSTEM ROLE:
You are a deterministic structured data extractor.

Your output is parsed automatically by a machine.
If the format is violated, the system will fail.

--------------------------------------------------

TASK:
Extract what the user explicitly wants to list.

--------------------------------------------------

STRICT OUTPUT CONTRACT (MANDATORY):

- Output ONLY a valid Python list.
- Do NOT output any explanation, reasoning, text, or comments.
- Do NOT output anything before or after the list.
- The response MUST start with "[" and end with "]".
- Each item MUST be a string.
- Allowed values ONLY: "problems", "proposals", "scenarios".
- Maximum 3 items.

--------------------------------------------------

DECISION RULES:

- Include an item ONLY if the user EXPLICITLY asks to list it.
- If nothing is explicitly requested → return [].
- NEVER infer, assume, or guess.
- NEVER explain your decision.

--------------------------------------------------

EXAMPLES:

User: "List the problems"
Output: ["problems"]

User: "Give me problems and scenarios"
Output: ["problems", "scenarios"]

User: "What do you think?"
Output: []

--------------------------------------------------

USER MESSAGE:
{message}
"""
    
    return llm_interaction(prompt)

# ---------------------------------------------------------------------------
# UNDERSTAND IF THERE IS THE NEED TO ACTIVATE/DAECTIVATE THINGS FROM CONTEXT
# ---------------------------------------------------------------------------

def get_context_activation_deactivation_list(last_message, message_history, current_context, available_ids):
    prompt = f"""
You are a context management assistant. Your sole task is to analyze a user's message and return a JSON dictionary indicating which items should be activated or deactivated in the current context.

## Available IDs
These are the only valid IDs you may reference:
{available_ids}

## Current Context
The following IDs are currently active:
{current_context}

## Message History
{message_history}

## User's Last Message
{last_message}

## Your Task
Analyze the user's last message and return a JSON dictionary with exactly this format:
{{"activate": [], "deactivate": []}}

Follow these rules strictly:

1. **Explicit activation**: If the user explicitly asks to activate, enable, focus on, or select a problem, proposal, or solution, add its ID to "activate".

2. **Implicit activation**: If the user mentions or references one or more available IDs — whether asking for information, modifications, or comparisons — without explicitly activating them, still add those IDs to "activate".

3. **Relative references**: The user may refer to items indirectly (e.g. "the first one", "the last one", "the second option"). Use the message history to resolve what item they are referring to, then add the corresponding ID to "activate".

4. **Explicit deactivation**: If the user explicitly asks to remove, deactivate, or dismiss an item, or says they are no longer interested in it, add its ID to "deactivate".

5. **Strict ID validation**: Every ID in both "activate" and "deactivate" MUST be drawn from the available IDs list above. Never invent or infer IDs that are not in that list.

6. **No overlap**: An ID should not appear in both "activate" and "deactivate" in the same response.

7. **Empty lists are valid**: If the user's message does not warrant any activation or deactivation, return empty lists.

## Output
Return ONLY the JSON dictionary. No explanation, no preamble, no markdown formatting.
"""

    return llm_interaction(prompt)