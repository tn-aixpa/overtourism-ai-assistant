import anthropic
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from time import time, sleep
import re
import os
import json
import logging

logger = logging.getLogger(__name__)

USE_LOCAL_LLM = False  # Toggle: True = Ollama, False = Anthropic

ANTHROPIC_PRICING = {
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-5": {"input": 15.00, "output": 75.00},
}

# Initialize the appropriate client
if USE_LOCAL_LLM:
    # Initialize local Ollama model
    # https://ollama.com/search
    # mistral, tinyllama, phi3:mini, gemma2:2b, llama3:8b, qwen3.5:2b, llama3.2:1b, gpt-oss:20b

    MODEL = "gpt-oss:20b"
    llm = ChatOllama(
        model=MODEL,
        base_url="http://localhost:11434",
        temperature=0,
        keep_alive=-1
    )
else:
    llm = anthropic.Anthropic(api_key="abc123")
    # llm = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def format_messages(messages):
    return "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )


def _call_anthropic_with_retry(model: str, max_tokens: int, prompt: str, max_retries: int = 5):
    """Call Anthropic API with exponential backoff retry on overload errors."""
    for attempt in range(max_retries):
        try:
            return llm.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                if attempt == max_retries - 1:
                    raise  # Exhausted retries, propagate the error
                wait_time = 2 ** attempt + 1  # 2, 3, 5, 9, 17 seconds...
                logger.warning(f"Anthropic overloaded (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                sleep(wait_time)
            else:
                raise  # Non-529 errors are not retried


def llm_interaction(prompt: str, max_tokens: int = 1024, lightweight_llm=True) -> str:
    try:
        t1 = time()

        if USE_LOCAL_LLM:
            response = llm.invoke([HumanMessage(content=prompt)])
            result = response.content.strip()
            el = time() - t1
        else:
            if lightweight_llm:
                MODEL = "claude-haiku-4-5"
            else:
                MODEL = "claude-sonnet-4-5"

            response = _call_anthropic_with_retry(MODEL, max_tokens, prompt)
            result = response.content[0].text.strip()
            el = time() - t1

            # Compute pricing
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            pricing = ANTHROPIC_PRICING.get(MODEL)
            call_cost = (
                input_tokens  / 1_000_000 * pricing["input"] +
                output_tokens / 1_000_000 * pricing["output"]
            )

            with open("logs/costs.csv", "a+") as f:
                f.write(f"{MODEL};{input_tokens};{output_tokens};{call_cost}\n")

        with open("logs/times_" + re.sub(r'\W+', '', MODEL) + "_.txt", "a+") as f:
            f.write(f"{el:.2f}\n")

        return result

    except Exception as e:
        logger.error(e)
        return f"Error connecting to chatbot: {e}"
    
def parse_llm_json(raw: str) -> list:
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    return json.loads(cleaned)