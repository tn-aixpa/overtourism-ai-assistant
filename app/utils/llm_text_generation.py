from langchain_core.prompts import ChatPromptTemplate
from app.utils.llm import llm, llm_interaction, DEBUG


# ---------------------------------------------------------------------------
# ANSWER QUESTION COMPARISON
# ---------------------------------------------------------------------------

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
    
# ---------------------------------------------------------------------------
# ANSWER QUESTION
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# SYNTESIZE MULTIPLE EXPERTS ANSWERS
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# LISTING AVAILABLE MESSAGE
# ---------------------------------------------------------------------------

def get_list_message(partial_lists):
    prompt = f"""
SYSTEM ROLE:
You are a deterministic text generator.

--------------------------------------------------

TASK:

Generate a sentence or a short text that summarizes the content of a dictionary.

The dictionary contains up to three keys:
- "problems"
- "proposals"
- "scenarios"

Each key maps to a list of strings.

--------------------------------------------------

STRICT RULES:

- Do NOT add explanations or extra text.
- Respect this order: problems → proposals → scenarios.
- Only include keys that exist AND have at least one element.
- Use correct singular/plural grammar:
    - 1 → "one problem"
    - 2+ → "two problems", etc.
- Start the sentence with a something like: "On the platform there is", "I have found", "There is". Use plural forms (e.g. "there are") if needed.
- If there are many elments prefer bullet points, otherwise try to build a single sentence.

--------------------------------------------------

EXAMPLES:

Input:
{{"problems": ["P1"]}}
Output:
On the platform there is one problem: P1.

Input:
{{"problems": ["P1"], "scenarios": ["s0", "s1"]}}
Output:
On the platform there are one problem (P1) and two scenarios (s0 and s1).

Input:
{{"proposals": ["p0"]}}
Output:
On the platform there is one proposal: p0.

Input:
{{"problems": ["P1"], "proposals": ["p0"], "scenarios": ["s0", "s1"]}}
Output:
On the platform there are one problem (P1), one proposal (p0) and two scenarios (s0 and s1).

Input:
{{"problems": ["P1"], "proposals": ["p0", "p1"], "scenarios": ["s0", "s1", "s2", "s3","s4"]}}
Output:
On the platform there are:\n-one problem: P1,\n-two proposals: p0, p1,\n-5 scenarios: s0, s1, s2, s3, s4.

--------------------------------------------------

INPUT:
{partial_lists}
"""
    return llm_interaction(prompt)

# ---------------------------------------------------------------------------
# TRANSLATION
# ---------------------------------------------------------------------------

translate_prompt = ChatPromptTemplate.from_template(
    "Translate the following text from {input_language} to {target_language}. "
    "Return ONLY the translated text. Do not explain.\n\n{text}"
)

def translate(text, input_language, target_language):
    # chain = translate_prompt | llm
    # return chain.invoke({
    #     "text": text,
    #     "input_language": input_language,
    #     "target_language": target_language
    # }).content
    return text
