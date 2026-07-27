import os
import logging
import requests
from time import sleep
import anthropic

from app.agent.state import AgentState
from app.utils.common import RequestHandlingException, enforce_prompt_budget
from app.utils.token_tacking import _log_costs

_llm_client = None
logger = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================

SMARTLAB_BASE_URL = "https://owu.smartcommunitylab.it/api/chat/completions"
SMARTLAB_MODELS = {
    "light": os.environ.get("SMARTLAB_LIGHT_MODEL", "llama31"),
    "heavy": os.environ.get("SMARTLAB_HEAVY_MODEL", "llama31"),
}

ANTHROPIC_MODELS = {
    "light": "claude-haiku-4-5",
    "heavy": "claude-sonnet-4-5",
}

LLM_TIMEOUT = 20  # seconds


# =========================
# CLIENT INITIALIZATION
# =========================
def init_anthropic():
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        timeout=LLM_TIMEOUT,
    )


def get_llm_client():
    global _llm_client

    if _llm_client is None or not isinstance(_llm_client, anthropic.Anthropic):
        _llm_client = init_anthropic()

    return _llm_client


# =========================
# ANTHROPIC CALL WITH RETRY
# =========================
def call_anthropic_with_retry(
    llm_client, model: str, prompt: str, max_tokens: int, max_retries: int = 5
):
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
                wait_time = 2**attempt + 1
                logger.warning(
                    f"Anthropic overloaded (attempt {attempt+1}), retrying in {wait_time}s"
                )
                sleep(wait_time)
            else:
                raise


# =========================
# BACKUP LLM CALLS
# =========================
def llm_smartlab_interaction(prompt: str, model: str) -> tuple[str, str]:
    logger.info(f"Using smartlab ({model})")
    api_key = os.environ.get("SMARTLAB_API_KEY")
    if not api_key:
        raise RequestHandlingException(
            "SMARTLAB_API_KEY environment variable is not set"
        )

    response = requests.post(
        SMARTLAB_BASE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=LLM_TIMEOUT,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"].strip()
    return text, model


def call_backup_llm(prompt: str, lightweight_llm: bool = True) -> tuple[str, str]:
    """Fallback call. Now tier-aware: a light task still gets the backup
    provider's light model, a heavy task gets its heavy model, instead of both
    collapsing onto a single fixed backup model regardless of task weight."""
    tier = "light" if lightweight_llm else "heavy"

    model = SMARTLAB_MODELS[tier]
    return llm_smartlab_interaction(prompt, model)


# =========================
# MAIN LLM INTERFACE
# =========================
def llm_interaction(
    state: AgentState, prompt: str, max_tokens: int = 1024, lightweight_llm: bool = True
) -> str:
    # Last line of defense: every individual injection point (tool results,
    # matching data, retrieved context, ...) is already truncated at the
    # source, but if something new slips through uncapped, shrink the
    # assembled prompt here rather than letting the call fail against the
    # provider's request-size limit. See app.utils.common.enforce_prompt_budget.
    prompt = enforce_prompt_budget(prompt)

    try:

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
            _log_costs(
                response.usage.input_tokens,
                response.usage.output_tokens,
                model_name,
                state.user_id,
            )

        except Exception as e:
            logger.error(f"Anthropic error: {e}, falling back to backup llm")
            result, model_name = call_backup_llm(prompt)

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
    return "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
