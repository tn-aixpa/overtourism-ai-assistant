from typing import List
from app.agent. state import ConversationMessage

from app.utils.llm import llm_interaction, format_messages, DEBUG

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