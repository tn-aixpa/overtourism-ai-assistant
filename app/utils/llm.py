import os
import re
import json
import logging
from time import time, sleep
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import anthropic
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage


from app.agent.events import publish
from app.agent.state import AgentState
from app.utils.common import RequestHandlingException

_llm_client = None
logger = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================
USE_LOCAL_LLM = True

LOCAL_MODEL = "mistral" #qwen2.5:14b "gpt-oss:20b"

ANTHROPIC_MODELS = {
    "light": "claude-haiku-4-5",
    "heavy": "claude-sonnet-4-5",
}

ANTHROPIC_PRICING = {
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-5": {"input": 15.00, "output": 75.00},
}


# =========================
# TIMEOUT
# =========================
EXECUTOR = ThreadPoolExecutor(max_workers=4)
LLM_TIMEOUT = 20  # seconds

def _local_call(prompt, llm_client):
    return llm_local_interaction(prompt, llm_client)

# =========================
# CLIENT INITIALIZATION
# =========================
def init_local_llm():
    return ChatOllama(
        model=LOCAL_MODEL,
        base_url="http://localhost:11434",
        temperature=0,
        keep_alive=-1,
    )

def init_anthropic():
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        timeout=LLM_TIMEOUT
    )

def get_llm_client():
    global _llm_client

    desired_type = ChatOllama if USE_LOCAL_LLM else anthropic.Anthropic

    if _llm_client is None or not isinstance(_llm_client, desired_type):
        _llm_client = init_local_llm() if USE_LOCAL_LLM else init_anthropic()

    return _llm_client

# =========================
# HELPERS
# =========================
def ensure_logs_dir():
    os.makedirs("logs", exist_ok=True)


def log_time(model_name: str, elapsed: float):
    ensure_logs_dir()
    filename = f"logs/times_{re.sub(r'\\W+', '', model_name)}.txt"
    with open(filename, "a+") as f:
        f.write(f"{elapsed:.2f}\n")


def log_cost(model_name: str, input_tokens: int, output_tokens: int):
    ensure_logs_dir()
    pricing = ANTHROPIC_PRICING.get(model_name)

    if not pricing:
        return

    cost = (
        input_tokens / 1_000_000 * pricing["input"] +
        output_tokens / 1_000_000 * pricing["output"]
    )

    with open("logs/costs.csv", "a+") as f:
        f.write(f"{model_name};{input_tokens};{output_tokens};{cost}\n")


# =========================
# ANTHROPIC CALL WITH RETRY
# =========================
def call_anthropic_with_retry(llm_client, model: str, prompt: str, max_tokens: int, max_retries: int = 5):
    for attempt in range(max_retries):
        try:
            return llm_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

        except anthropic.APIStatusError as e:
            if e.status_code == 529:
                if attempt == max_retries - 1:
                    raise

                wait_time = 2 ** attempt + 1
                logger.warning(
                    f"Anthropic overloaded (attempt {attempt+1}), retrying in {wait_time}s"
                )
                sleep(wait_time)
            else:
                raise


# =========================
# MAIN LLM INTERFACE
# =========================
def llm_local_interaction(prompt: str, llm_client: ChatOllama) -> str:
    model_name = LOCAL_MODEL
    response = llm_client.invoke([
        HumanMessage(content=prompt)
    ])
    return response.content.strip(), model_name

def llm_interaction(state: AgentState, prompt: str, max_tokens: int = 1024, lightweight_llm: bool = True) -> str:
    try:
        start = time()

        llm_client = get_llm_client()
        if USE_LOCAL_LLM:
            future = EXECUTOR.submit(_local_call, prompt, llm_client)
            try:
                result, model_name = future.result(timeout=LLM_TIMEOUT)
            except FuturesTimeoutError:
                future.cancel()
                raise TimeoutError("Local LLM timed out after 60 seconds")
        else:
            try:
                model_name = ANTHROPIC_MODELS["light" if lightweight_llm else "heavy"]

                response = call_anthropic_with_retry(
                    llm_client=llm_client,
                    model=model_name,
                    prompt=prompt,
                    max_tokens=max_tokens,
                )

                result = response.content[0].text.strip()

                # Logging usage
                log_cost(
                    model_name,
                    response.usage.input_tokens,
                    response.usage.output_tokens
                )
            except Exception as e:
                publish(state.session_id, "Unable to connect to Anthropic's API, switching to local LLM (answer might take longer to generate and be less accurate)", force_print=True)
                logger.error(f"Error during Anthropic interaction: {e}, falling back to local LLM")
                llm_client = init_local_llm()  # Re-initialize local client
                future = EXECUTOR.submit(_local_call, prompt, llm_client)
                try:
                    result, model_name = future.result(timeout=LLM_TIMEOUT)
                except FuturesTimeoutError:
                    future.cancel()
                    raise RequestHandlingException(f"Local LLM timed out after {LLM_TIMEOUT} seconds")

        elapsed = time() - start
        log_time(model_name, elapsed)
        state.cognitive.generation_pipeline.append(model_name)

        return result

    except Exception as e:
        error = f"Error connecting to chatbot: {e}"
        logger.error(error)
        raise RequestHandlingException(error)


# =========================
# UTILITIES
# =========================
def format_messages(messages):
    return "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

def parse_llm_json(raw: str):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    # Fix Python literals that are invalid JSON
    cleaned = re.sub(r'\bNone\b', 'null', cleaned)
    cleaned = re.sub(r'\bTrue\b', 'true', cleaned)
    cleaned = re.sub(r'\bFalse\b', 'false', cleaned)
    return json.loads(cleaned)