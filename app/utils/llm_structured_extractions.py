from typing import List
from app.agent. state import ConversationMessage

from app.utils.llm import llm_interaction, format_messages
from app.utils.backend_integration_classes import ProposalInfoSchema, ProblemInfoSchema

# ---------------------------------------------------------------------------
# PROBLEM DATA EXTRACTION
# ---------------------------------------------------------------------------

def extract_problem_data(messages: List[ConversationMessage], schema: ProblemInfoSchema, attachment_list) -> str:
    #TODO: might need to revise to add the possiblity to change/integrate/remove a field


    field_specs = schema.format_structure()
    attachments = "\n".join(f"- {p}" for p in attachment_list) if attachment_list else "No attachments provided."

    prompt = f"""

SYSTEM ROLE:

You are an expert analyst helping to extract structured information about a problem from a conversation.

--------------------------------------------------

TASK:

Analyze the conversation history and extract the fields listed below. 
Only extract information that is clearly stated or strongly implied by the conversation — do not invent or hallucinate details.

## Fields to extract

{field_specs}


## Attachments

The user has provided the following attachments (file paths or URLs). Include relevant ones in `additional_data`:

{attachments}

## Available subsystems
Available subsystems that are allowed in 'available_subsystems' are: parking, beach, restaurants, hotels

## Output format

Respond ONLY with a valid JSON object. Do not include any explanation or markdown fences. Example structure:

{{
  "problem_title": "string",
  "objectives": "string",
  "problem_description": "string",
  "available_subsystems": ["string", "..."],
  "additional_data": ["path/or/url", ...]
}}

If a field cannot be determined from the conversation, set it to null (or [] for list fields).

--------------------------------------------------

SELF-CHECK (MANDATORY BEFORE OUTPUT):

Before producing the final answer:

1) Verify the output is valid JSON.
2) Verify the output is a list.
3) Verify it begins with "[" and ends with "]".
4) Verify there is NO text outside the JSON — nothing before "[", nothing after "]".
5) Verify no empty fields, empty objects, or empty arrays exist.
6) Verify every solution has at least one entry in "indexes_to_change".
7) Verify the output does NOT contain backticks, ```json, or any markdown formatting.

Only after passing ALL checks, output the JSON and then STOP.

--------------------------------------------------

MESSAGE HISTORY:

{format_messages(messages)}
"""

    
    return llm_interaction(prompt, lightweight_llm=False)

# ---------------------------------------------------------------------------
# PROPOSAL DATA EXTRACTION
# ---------------------------------------------------------------------------
def extract_proposal_data(messages: List[ConversationMessage], schema: ProposalInfoSchema, available_scenarios, attachment_list) -> str:

    field_specs = schema.format_structure()
    attachments = "\n".join(f"- {p}" for p in attachment_list) if attachment_list else "No attachments provided."

    prompt = f"""

SYSTEM ROLE:

You are an expert analyst helping to extract structured information about a proposal from a conversation.

--------------------------------------------------

TASK:

Analyze the conversation history and extract the fields listed below. 
Only extract information that is clearly stated or strongly implied by the conversation — do not invent or hallucinate details.

## Fields to extract

{field_specs}

## Available scenarios

The `connected_scenarios` field must only reference IDs from this list:

{available_scenarios}

## Attachments

The user has provided the following attachments (file paths or URLs). Include relevant ones in `related_data`:

{attachments}

## Output format

Respond ONLY with a valid JSON object. Do not include any explanation or markdown fences. Example structure:

{{
  "title": "string or null",
  "description": "string or null",
  "related_data": ["path/or/url", ...],
  "context_conditions": "string or null",
  "potential_impact": "string or null",
  "connected_scenarios": ["scenario_id", ...]
}}

If a field cannot be determined from the conversation, set it to null (or [] for list fields).

--------------------------------------------------

SELF-CHECK (MANDATORY BEFORE OUTPUT):

Before producing the final answer:

1) Verify the output is valid JSON.
2) Verify the output is a list.
3) Verify it begins with "[" and ends with "]".
4) Verify there is NO text outside the JSON — nothing before "[", nothing after "]".
5) Verify no empty fields, empty objects, or empty arrays exist.
6) Verify every solution has at least one entry in "indexes_to_change".
7) Verify the output does NOT contain backticks, ```json, or any markdown formatting.

Only after passing ALL checks, output the JSON and then STOP.

--------------------------------------------------

MESSAGE HISTORY:

{format_messages(messages)}
"""

    return llm_interaction(prompt, lightweight_llm=False)


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
- NEVER output explanations or extra text — BEFORE or AFTER the JSON.
- The response MUST start with "[" and end with "]".
- The JSON must be directly parsable with json.loads().
- OUTPUT NOTHING AFTER THE CLOSING "]". No comments, no questions, no follow-ups.

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
- Remove empty fields entirely — including empty objects {{}} and empty arrays [].
- A solution with no entries in "indexes_to_change" is NOT a valid solution. Omit it entirely.
- If no valid solutions exist, return [].
- Inside "indexes_to_change" NEVER put a list as 'value' if type is "increase" or "decrease".
- Inside "indexes_to_change" NEVER put a single number as 'value' if type is "range".

--------------------------------------------------

SELF-CHECK (MANDATORY BEFORE OUTPUT):

Before producing the final answer:

1) Verify the output is valid JSON.
2) Verify the output is a list.
3) Verify it begins with "[" and ends with "]".
4) Verify there is NO text outside the JSON — nothing before "[", nothing after "]".
5) Verify no empty fields, empty objects, or empty arrays exist.
6) Verify every solution has at least one entry in "indexes_to_change".
7) Verify the output does NOT contain backticks, ```json, or any markdown formatting.

Only after passing ALL checks, output the JSON and then STOP.

--------------------------------------------------

MESSAGE HISTORY:

{format_messages(messages)}
"""
    
    return llm_interaction(prompt, lightweight_llm=False)

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

    return llm_interaction(prompt, lightweight_llm=False)

# ---------------------------------------------------------------------------
# DECIDE WHAT NEEDS TO BE LISTED
# ---------------------------------------------------------------------------

def assess_what_to_list(message, conversation_history=None, active_context=None):
    """
    conversation_history: optional list of dicts with 'role' and 'content' keys,
                          e.g. [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    active_context: optional string describing the currently active item in the agent state,
                    e.g. "problem: Flooding in sector 4"
    """

    context_block = ""
    if active_context:
        context_block = f"""
ACTIVE CONTEXT:
The agent currently has this item selected/active: {active_context}
Use this to resolve implicit references when appropriate.
"""

    history_block = ""
    if conversation_history:
        formatted = "\n".join(
            f"{turn['role'].upper()}: {turn['content']}"
            for turn in conversation_history
        )
        history_block = f"""
CONVERSATION HISTORY (for resolving references only):
{formatted}
"""

    prompt = f"""
SYSTEM ROLE:
You are a deterministic structured data extractor.
Your output is parsed automatically by a machine. Any deviation from the format will cause a system failure.

TASK:
Extract two things from the user message:
1. What the user wants to LIST (the target).
2. What specific item they want to filter by (the subject), if any.

STRICT OUTPUT CONTRACT (MANDATORY):
- Output ONLY a valid Python dict literal. Nothing else.
- The response MUST start with "{{" and end with "}}".
- No prose, no explanation, no markdown, no code fences.
- Keys must be exactly: "to_list" and "subject"
- "to_list": a list of strings. Allowed values ONLY: "problems", "proposals", "scenarios". Max 3 items.
- "subject": one of:
    - A string with the name/identifier of the item, either:
        · Explicitly named by the user (e.g. "Alpha", "problem X"), OR
        · Resolved from ACTIVE CONTEXT or CONVERSATION HISTORY when the user uses an
          implicit reference (e.g. "this", "that", "it", "the current", "last", "latest",
          "previous", "the one", "this one", "that one")
      Resolution priority: ACTIVE CONTEXT first, then CONVERSATION HISTORY.
    - None if no subject is referenced, OR if an implicit reference exists but
      cannot be resolved from either ACTIVE CONTEXT or CONVERSATION HISTORY.

DECISION RULES:
- Include an item in "to_list" ONLY if the user EXPLICITLY asks to list or retrieve it.
- Set "subject" to the user's explicitly named item if they name one directly.
- If the user uses an implicit reference, attempt to resolve it:
    1. Check ACTIVE CONTEXT — if it matches the reference, extract and use its name.
    2. Check CONVERSATION HISTORY — if a recent specific item was mentioned, use its name.
    3. If unresolvable → None.
- If nothing is explicitly requested → {{"to_list": [], "subject": None}}
- NEVER infer, assume, or guess beyond these rules. NEVER explain.

EXAMPLES:

User: "List the problems"
Output: {{"to_list": ["problems"], "subject": None}}

User: "What proposals are there for problem X?"
Output: {{"to_list": ["proposals"], "subject": "X"}}

User: "Give me scenarios for proposal Alpha"
Output: {{"to_list": ["scenarios"], "subject": "Alpha"}}

User: "Give me problems and scenarios"
Output: {{"to_list": ["problems", "scenarios"], "subject": None}}

--- With active_context = "problem_1" ---

User: "What proposals have been made for this problem?"
Output: {{"to_list": ["proposals"], "subject": "problem_1"}}

User: "Show me scenarios for it"
Output: {{"to_list": ["scenarios"], "subject": "problem_1"}}

--- With no active_context, but history mentions "proposal Beta" ---

User: "Give me scenarios for the last one"
Output: {{"to_list": ["scenarios"], "subject": "Beta"}}

--- With no active_context and no relevant history ---

User: "What proposals have been made for this problem?"
Output: {{"to_list": ["proposals"], "subject": None}}

User: "What do you think?"
Output: {{"to_list": [], "subject": None}}

{context_block}{history_block}
USER MESSAGE:
{message}
"""
    return llm_interaction(prompt, lightweight_llm=False)