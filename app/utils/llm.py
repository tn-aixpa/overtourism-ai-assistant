import os
import re
import logging
import requests
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
USE_ANTHROPIC = True

# Backup LLM provider when USE_ANTHROPIC is False (or Anthropic fails)
# Options: "ollama" | "smartlab"
BACKUP_PROVIDER = "smartlab"

LOCAL_MODEL = "mistral"  # used when BACKUP_PROVIDER = "ollama"

SMARTLAB_BASE_URL = "https://owu.smartcommunitylab.it/api/chat/completions"
SMARTLAB_MODEL = "llama31"  # used when BACKUP_PROVIDER = "smartlab"

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
def init_ollama_llm():
    return ChatOllama(
        model=LOCAL_MODEL,
        base_url="http://localhost:11434",
        temperature=0,
        keep_alive=-1,
    )

def init_anthropic():
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        timeout=LLM_TIMEOUT,
    )

def get_llm_client():
    global _llm_client

    if USE_ANTHROPIC:
        if _llm_client is None or not isinstance(_llm_client, anthropic.Anthropic):
            _llm_client = init_anthropic()
    else:
        if BACKUP_PROVIDER == "ollama":
            if _llm_client is None or not isinstance(_llm_client, ChatOllama):
                _llm_client = init_ollama_llm()
        else:
            # SmartLab is stateless (plain HTTP), no client object needed
            _llm_client = None

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
# BACKUP LLM CALLS
# =========================
def llm_local_interaction(prompt: str, llm_client: ChatOllama) -> tuple[str, str]:
    """Call the local Ollama model."""
    logger.info(f"Using ollama ({LOCAL_MODEL})")
    response = llm_client.invoke([HumanMessage(content=prompt)])
    return response.content.strip(), LOCAL_MODEL


def llm_smartlab_interaction(prompt: str) -> tuple[str, str]:
    """Call the SmartLab OpenAI-compatible API."""
    logger.info(f"Using smartlab ({SMARTLAB_MODEL})")
    api_key = os.environ.get("SMARTLAB_API_KEY")
    if not api_key:
        raise RequestHandlingException("SMARTLAB_API_KEY environment variable is not set")

    response = requests.post(
        SMARTLAB_BASE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": SMARTLAB_MODEL,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=LLM_TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    text = result["choices"][0]["message"]["content"].strip()
    return text, SMARTLAB_MODEL


def call_backup_llm(prompt: str) -> tuple[str, str]:
    """Dispatch to the configured backup provider."""
    if BACKUP_PROVIDER == "ollama":
        llm_client = init_ollama_llm()
        future = EXECUTOR.submit(_local_call, prompt, llm_client)
        try:
            return future.result(timeout=LLM_TIMEOUT)
        except FuturesTimeoutError:
            future.cancel()
            raise RequestHandlingException(f"Ollama LLM timed out after {LLM_TIMEOUT} seconds")

    elif BACKUP_PROVIDER == "smartlab":
        return llm_smartlab_interaction(prompt)

    else:
        raise RequestHandlingException(f"Unknown BACKUP_PROVIDER: '{BACKUP_PROVIDER}'")


# =========================
# MAIN LLM INTERFACE
# =========================
def llm_interaction(state: AgentState, prompt: str, max_tokens: int = 1024, lightweight_llm: bool = True) -> str:
    try:
        start = time()

        if USE_ANTHROPIC:
            llm_client = get_llm_client()
            try:
                model_name = ANTHROPIC_MODELS["light" if lightweight_llm else "heavy"]
                response = call_anthropic_with_retry(
                    llm_client=llm_client,
                    model=model_name,
                    prompt=prompt,
                    max_tokens=max_tokens,
                )
                result = response.content[0].text.strip()
                log_cost(model_name, response.usage.input_tokens, response.usage.output_tokens)

            except Exception as e:
                publish(
                    state.session_id,
                    f"Unable to connect to Anthropic's API, switching to backup LLM ({BACKUP_PROVIDER}) — answer may take longer and be less accurate.",
                    force_print=True,
                )
                logger.error(f"Anthropic error: {e}, falling back to {BACKUP_PROVIDER}")
                result, model_name = call_backup_llm(prompt)
        else:
            result, model_name = call_backup_llm(prompt)

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