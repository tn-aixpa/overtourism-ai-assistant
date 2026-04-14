from app.agent.state import AgentState
import re
import json

from app.config import ALLOWED_ROLES
from app.utils.state_variables import VALID_INTENTS
from app.utils.llm import llm_interaction, format_messages

# ---------------------------------------------------------------------------
# INTENT CLASSIFICATION
# ---------------------------------------------------------------------------

def classify_intent(state: AgentState, message: str | None = None, history: list | None = None) -> str:
    """
    Classify the user's intent given the current message and optional
    conversation history.  Returns one of:
        LIST_AVAILABLE | INTERACT_CONTEXT | CREATE_NEW_PROBLEM |
        CREATE_NEW_PROPOSAL | CREATE_NEW_SCENARIO | CONTEXT_MANAGEMENT |
        ASSISTANT_CAPABILITIES | INVALID
    """
    message = message if message is not None else state.get_last_user_message().content
    history = history if history is not None else state.get_reasoning_context()
    
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

3. ASSISTANT_CAPABILITIES
   → User is greeting the assistant, or asking what the assistant can do, what features are
     available, how to use it, or what its current state/context is.
   Signals: "hi", "hello", "hey", "good morning", "what can you do", "what are your capabilities",
            "how does this work", "help", "what can I ask you", "what is your current context",
            "what are you able to do", "how can you help me", "what commands do you support".

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

7. INTERACT_CONTEXT
   → User wants to analyse, explore, compare or get information about EXISTING scenarios, proposals
     that are already on the platform.
     Questions related to indexes, constraints belong to this action.
   Signals: "explain scenario", "what does scenario X show", "compare scenario A and B",
            "interpret the results", "what is the most critical index", "what is this problem about".

8. INVALID
   → Anything unrelated to {context}, or too vague to classify into 1-7.

DECISION RULES:
- ASSISTANT_CAPABILITIES vs INTERACT_CONTEXT: "What can you do?" or "How does this work?" → ASSISTANT_CAPABILITIES.
  "What does scenario X show?" → INTERACT_CONTEXT.
- ASSISTANT_CAPABILITIES vs INVALID: greetings ("hi", "hello") and capability questions always → ASSISTANT_CAPABILITIES,
  never INVALID, even without prior context.
- CONTEXT_MANAGEMENT vs INTERACT_CONTEXT: CONTEXT_MANAGEMENT is about selecting/focusing on an item as context.
  INTERACT_CONTEXT is about asking analytical questions about it. "Let's work on problem X" → CONTEXT_MANAGEMENT.
  "What does scenario X show?" → INTERACT_CONTEXT.
- CONTEXT_MANAGEMENT vs LIST_AVAILABLE: "Show me the problems, then let's focus on the first one" → CONTEXT_MANAGEMENT
  (the selection intent dominates). A pure listing request with no selection intent → LIST_AVAILABLE.
- CREATE_NEW_SCENARIO vs INTERACT_CONTEXT: if the scenario does NOT exist yet → CREATE.
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
User: "Hi" → ASSISTANT_CAPABILITIES
User: "Hello! What can you do?" → ASSISTANT_CAPABILITIES
User: "What are your capabilities?" → ASSISTANT_CAPABILITIES
User: "How can you help me?" → ASSISTANT_CAPABILITIES
User: "Help" → ASSISTANT_CAPABILITIES
User: "We have an overtourism problem in the historic centre" → CREATE_NEW_PROBLEM
User: "I want to create a problem about traffic congestion" → CREATE_NEW_PROBLEM
User: "I want to create a new proposal to solve the problem" → CREATE_NEW_PROPOSAL
User: "Let's define a new proposal" → CREATE_NEW_PROPOSAL
User: "Create a scenario where we reduce tourist bus permits by 20%" → CREATE_NEW_SCENARIO
User: "Run a new scenario with stricter entry limits" → CREATE_NEW_SCENARIO
User: "What does scenario S3 show about hotel occupancy?" → INTERACT_CONTEXT
User: "Compare scenario A and scenario B" → INTERACT_CONTEXT
User: "Tell me a joke" → INVALID
User: "Yes" (no history) → INVALID

Return ONLY the action name. No explanation, no punctuation.
"""

    raw = llm_interaction(state, prompt).strip().upper()

    # Normalise: strip punctuation, take first token
    first_token = re.split(r'[\s\.,;]', raw)[0]

    if first_token in VALID_INTENTS:
        return first_token

    # Fallback: substring match in case the model added a prefix/suffix
    for intent in VALID_INTENTS:
        if intent in raw:
            return intent

    return "INVALID"

def extract_action_plan(state: AgentState, message: str | None = None) -> list[str]:
    """
    Single LLM call that both classifies intent and extracts multi-step plans.
    Always returns an ordered list of 1+ valid intents.
    """
    message = message or (state.get_last_user_message() or "").content
    if not message:
        return ["INVALID"]

    history = state.get_reasoning_context()
    history_block = format_messages(history) if history else "None"
    active_context = state.get_active_context_string() or "None"

    prompt = f"""You are an intent classifier for a digital-twin assistant about city management and overtourism.

Active context: {active_context}

Conversation so far:
{history_block}

New user message: "{message}"

Your task: decompose the user message into an ORDERED list of atomic actions.
Each action must be exactly one of:
  CONTEXT_MANAGEMENT | LIST_AVAILABLE | ASSISTANT_CAPABILITIES |
  CREATE_NEW_PROBLEM | CREATE_NEW_PROPOSAL | CREATE_NEW_SCENARIO |
  INTERACT_CONTEXT | INVALID

CLASSIFICATION RULES (single intent):

1. LIST_AVAILABLE
   → User asks to see/list existing problems, proposals or scenarios.
   Signals: "show me", "list", "what problems are there", "available scenarios".

2. CONTEXT_MANAGEMENT
   → User wants to activate, switch, or remove an item from their active context.
   Signals: "activate X", "focus on", "let's work on", "select", "open", "use problem X",
            "remove X", "deselect", "clear context", relative refs like "the last one".

3. ASSISTANT_CAPABILITIES
   → User is greeting the assistant or asking what it can do.
   Signals: "hi", "hello", "what can you do", "help", "how does this work".

4. CREATE_NEW_PROBLEM
   → User wants to register a new real-world problem.
   Signals: "I have a problem", "new problem", "add a problem", "we need to address".
   Priority: if the user mentions both a problem and scenarios, prefer CREATE_NEW_PROBLEM.

5. CREATE_NEW_PROPOSAL
   → User wants to create a new proposal.
   Signals: "create a proposal", "new proposal", "let's define a proposal".

6. CREATE_NEW_SCENARIO
   → User wants to create, run, or modify a scenario.
   Signals: "create a scenario", "run scenario", "new scenario", "what if we changed".

7. INTERACT_CONTEXT
   → User wants to analyse or get information about existing items on the platform.
   Signals: "explain", "compare", "what does X show", "interpret results", "what is this about".

8. INVALID
   → Unrelated to city management / overtourism, or too vague to classify.

MULTI-STEP RULES:

9. Split on ANY sequential signal — "and", "then", "also", "after that", commas
   implying sequence, or simply two distinct intents joined by "and" — regardless
   of language ("e poi", "und dann", "ensuite", "y luego", "e depois", etc.).

10. IMPLICIT CONTEXT ACTIVATION: if the user refers to a specific entity by name
    or id that is NOT currently active, prepend CONTEXT_MANAGEMENT before any
    action that operates on it.
    Example: active context is None, user says "show me results for scenario_1"
    → ["CONTEXT_MANAGEMENT", "INTERACT_CONTEXT"]
    Example: active context has problem_1, user says "what about scenario_1?"
    → ["CONTEXT_MANAGEMENT", "INTERACT_CONTEXT"]

DECISION RULES:
- "What can you do?" → ASSISTANT_CAPABILITIES. "What does scenario X show?" → INTERACT_CONTEXT.
- Greetings always → ASSISTANT_CAPABILITIES, never INVALID.
- CONTEXT_MANAGEMENT = selecting an item. INTERACT_CONTEXT = analysing an item.
- Scenario not yet existing → CREATE_NEW_SCENARIO. Already exists → INTERACT_CONTEXT.
- Generic one-word replies ("yes", "ok") with no prior context → INVALID.


EXAMPLES:
"List all the available problems" → ["LIST_AVAILABLE"]
"activate problem_1 and tell me how to create a new proposal for it" → ["CONTEXT_MANAGEMENT", "ASSISTANT_CAPABILITIES"]
"show me the scenarios, then let's work on the first one" → ["LIST_AVAILABLE", "CONTEXT_MANAGEMENT"]
"what are the results for scenario_1" (not active) → ["CONTEXT_MANAGEMENT", "INTERACT_CONTEXT"]
"what are the results for scenario_1" (already active) → ["INTERACT_CONTEXT"]
"Hi" → ["ASSISTANT_CAPABILITIES"]
"Tell me a joke" → ["INVALID"]
"Show me the results of scenario_1 and then create a new scenario" → ["CONTEXT_MANAGEMENT", "INTERACT_CONTEXT", "CREATE_NEW_SCENARIO"]

Return ONLY a JSON array of strings. No explanation, no markdown fences.
"""

    raw = llm_interaction(state, prompt).strip()
    raw = re.sub(r"^```[a-z]*\n?|```$", "", raw, flags=re.MULTILINE).strip()

    try:
        candidates = json.loads(raw)
        if isinstance(candidates, list):
            result = [c for c in candidates if c in VALID_INTENTS]
            if result:
                return result
    except json.JSONDecodeError:
        tokens = re.findall(r'\b([A-Z_]+)\b', raw)
        result = [t for t in tokens if t in VALID_INTENTS]
        if result:
            return result

    return ["INVALID"]

# ---------------------------------------------------------------------------
# SELECT ROLE
# ---------------------------------------------------------------------------

def select_role_llm(state: AgentState) -> str:
    
    question = state.get_last_user_message().content

    available_roles = "Available roles:"
    for role in ALLOWED_ROLES:
        available_roles += f"\n- {role}: {ALLOWED_ROLES[role]}"

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

    answer = llm_interaction(state, prompt)

    return answer

# ---------------------------------------------------------------------------
# ASSESS SCENARIO STRATEGY
# ---------------------------------------------------------------------------

def assess_scenario_strategy(state: AgentState) -> str:
    messages = state.get_reasoning_context()

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
    
    return llm_interaction(state, prompt)

# ---------------------------------------------------------------------------
# CONFIRMATION PARSING
# ---------------------------------------------------------------------------

def llm_classify_confirmation(state: AgentState):
    
    messages = state.get_reasoning_context()
    
    prompt = f"""
You are an intent classifier inside an AI workflow.

Your task:
Classify the last user's message into ONE of the following labels:

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

Conversation history:
\"\"\"{format_messages(messages)}\"\"\"
"""

    result = llm_interaction(state, prompt)

    allowed = {
        "CONFIRM",
        "EDIT",
        "CANCEL",
        "WAIT_CONFIRMATION",
    }

    return result if result in allowed else "WAIT_CONFIRMATION_PROBLEM"

