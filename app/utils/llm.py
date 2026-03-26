import anthropic
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from time import time
import re
import os
import logging

logger = logging.getLogger(__name__)

DEBUG = False
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
    llm = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def format_messages(messages):
    return "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )


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

            response = llm.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            result = response.content[0].text.strip()
            el = time() - t1

            #compute pricing
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
    