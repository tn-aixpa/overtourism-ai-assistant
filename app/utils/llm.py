import os
import logging
from typing import Any
from time import sleep
import anthropic
import openai

from app.agent.state import AgentState
from app.utils.common import RequestHandlingException, enforce_prompt_budget
from app.utils.token_tacking import _log_costs

logger = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================

# Which primary provider to use: "anthropic" (default) or "azure"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()

SMARTLAB_BASE_URL = "https://owu.smartcommunitylab.it/api/chat/completions"
SMARTLAB_MODELS = {
    "light": os.environ.get("SMARTLAB_LIGHT_MODEL", "llama31"),
    "heavy": os.environ.get("SMARTLAB_HEAVY_MODEL", "llama31"),
}

ANTHROPIC_MODELS = {
    "light": "claude-haiku-4-5",
    "heavy": "claude-sonnet-4-5",
}

# Azure OpenAI (or Azure AI Foundry "OpenAI-compatible") deployments.
# Overridable via env in case deployment names differ between environments.
AZURE_MODELS = {
    "light": os.environ.get("AZURE_LIGHT_MODEL", "model-router"),
    "heavy": os.environ.get("AZURE_HEAVY_MODEL", "gpt-5.6-sol"),
}

AZURE_ENDPOINT = os.environ.get(
    "AZURE_ENDPOINT",
    "https://oai-tndigit-gdst-test-resource.services.ai.azure.com/openai/v1",
)

LLM_TIMEOUT = 20  # seconds


# =========================
# CLIENT INITIALIZATION
# =========================
_llm_client = None  # Anthropic client cache
_azure_client = None  # Azure/OpenAI client cache


def init_anthropic():
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        timeout=LLM_TIMEOUT,
    )


def init_azure():
    api_key = os.environ.get("AZURE_API_KEY")
    if not api_key:
        raise RequestHandlingException("AZURE_API_KEY environment variable is not set")

    return openai.OpenAI(
        base_url=AZURE_ENDPOINT,
        api_key=api_key,
        timeout=LLM_TIMEOUT,
    )


def get_llm_client():
    global _llm_client

    if _llm_client is None or not isinstance(_llm_client, anthropic.Anthropic):
        _llm_client = init_anthropic()

    return _llm_client


def get_azure_client():
    global _azure_client

    if _azure_client is None or not isinstance(_azure_client, openai.OpenAI):
        _azure_client = init_azure()

    return _azure_client


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
# AZURE (OPENAI-COMPATIBLE) CALL WITH RETRY
# =========================
def call_azure_with_retry(
    llm_client, model: str, prompt: str, max_tokens: int, max_retries: int = 5
):
    # Retryable statuses: 429 (rate limited) and 5xx (transient server issues),
    # mirroring the "overloaded" handling used for Anthropic above.
    retryable_statuses = {429, 500, 502, 503, 504}

    for attempt in range(max_retries):
        try:
            return llm_client.chat.completions.create(
                model=model,
                max_completion_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.APIStatusError as e:
            if e.status_code in retryable_statuses:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2**attempt + 1
                logger.warning(
                    f"Azure GPT throttled/unavailable (status {e.status_code}, "
                    f"attempt {attempt+1}), retrying in {wait_time}s"
                )
                sleep(wait_time)
            else:
                raise


# =========================
# PROVIDER-SPECIFIC "PRIMARY" CALLS
# =========================
def _call_primary_anthropic(
    prompt: str, max_tokens: int, lightweight_llm: bool, state: AgentState
):
    llm_client = get_llm_client()
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
    return result, model_name


def _call_primary_azure(
    prompt: str, max_tokens: int, lightweight_llm: bool, state: AgentState
):
    llm_client = get_azure_client()
    model_name = AZURE_MODELS["light" if lightweight_llm else "heavy"]

    response = call_azure_with_retry(
        llm_client=llm_client,
        model=model_name,
        prompt=prompt,
        max_tokens=max_tokens,
    )

    result = (response.choices[0].message.content or "").strip()
    if not result:
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        raise RequestHandlingException(
            f"LLM returned an empty completion (finish_reason={finish_reason!r})"
        )
    _log_costs(
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        model_name,
        state.user_id,
    )
    return result, model_name


def _source(title: str | None, url: str | None) -> dict[str, str] | None:
    if not url:
        return None
    source = {"url": url}
    if title:
        source["title"] = title
    return source


def _anthropic_web_search(query: str, state: AgentState) -> dict[str, Any]:
    model_name = ANTHROPIC_MODELS["heavy"]
    response = get_llm_client().messages.create(
        model=model_name,
        max_tokens=1200,
        messages=[{"role": "user", "content": query}],
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 5,
            }
        ],
    )

    answer_parts = []
    sources = []
    for block in response.content:
        block_type = getattr(block, "type", "")
        if block_type == "text":
            text = getattr(block, "text", "").strip()
            if text:
                answer_parts.append(text)
            for citation in getattr(block, "citations", None) or []:
                source = _source(
                    getattr(citation, "title", None),
                    getattr(citation, "url", None),
                )
                if source:
                    sources.append(source)
        elif block_type == "web_search_tool_result":
            for result in getattr(block, "content", None) or []:
                source = _source(
                    getattr(result, "title", None),
                    getattr(result, "url", None),
                )
                if source:
                    sources.append(source)

    answer = "\n".join(answer_parts)
    if not answer:
        raise RequestHandlingException(
            "The configured LLM provider returned no answer for the web search."
        )

    _log_costs(
        response.usage.input_tokens,
        response.usage.output_tokens,
        model_name,
        state.user_id,
    )
    state.cognitive.generation_pipeline.append(model_name)
    return {"query": query, "answer": answer, "sources": _unique_sources(sources)}


def _azure_web_search(query: str, state: AgentState) -> dict[str, Any]:
    model_name = AZURE_MODELS["heavy"]
    response = get_azure_client().responses.create(
        model=model_name,
        input=query,
        tools=[{"type": "web_search_preview"}],
        max_output_tokens=1200,
    )

    sources = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", None) or []:
            for annotation in getattr(content, "annotations", None) or []:
                if getattr(annotation, "type", None) == "url_citation":
                    source = _source(
                        getattr(annotation, "title", None),
                        getattr(annotation, "url", None),
                    )
                    if source:
                        sources.append(source)

    answer = (getattr(response, "output_text", None) or "").strip()
    if not answer:
        raise RequestHandlingException(
            "The configured LLM provider returned no answer for the web search."
        )

    usage = response.usage
    _log_costs(
        usage.input_tokens,
        usage.output_tokens,
        model_name,
        state.user_id,
    )
    state.cognitive.generation_pipeline.append(model_name)
    return {"query": query, "answer": answer, "sources": _unique_sources(sources)}


def _unique_sources(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    unique = {}
    for source in sources:
        unique.setdefault(source["url"], source)
    return list(unique.values())


def native_web_search(state: AgentState, query: str) -> dict[str, Any]:
    """Run a provider-native web search and return its answer and citations."""
    query = query.strip()
    if not query:
        raise ValueError("Web search query cannot be empty")

    if LLM_PROVIDER == "anthropic":
        return _anthropic_web_search(query, state)
    if LLM_PROVIDER == "azure":
        return _azure_web_search(query, state)
    raise RequestHandlingException(
        f"Native web search is not supported for LLM_PROVIDER={LLM_PROVIDER!r}."
    )


# =========================
# MAIN LLM INTERFACE
# =========================
def llm_interaction(
    state: AgentState, prompt: str, max_tokens: int = 2024, lightweight_llm: bool = True
) -> str:
    # Last line of defense: every individual injection point (tool results,
    # matching data, retrieved context, ...) is already truncated at the
    # source, but if something new slips through uncapped, shrink the
    # assembled prompt here rather than letting the call fail against the
    # provider's request-size limit. See app.utils.common.enforce_prompt_budget.
    prompt = enforce_prompt_budget(prompt)

    with open("logs/temp.txt", "w+") as fout:
        fout.write(prompt)

    try:
        try:
            if LLM_PROVIDER == "azure":
                result, model_name = _call_primary_azure(
                    prompt, max_tokens, lightweight_llm, state
                )
            else:
                result, model_name = _call_primary_anthropic(
                    prompt, max_tokens, lightweight_llm, state
                )

        except Exception as e:
            logger.error(f"{LLM_PROVIDER} error: {e}")
            return (
                "Al momento no nè possibile contattare l'Assistente, riprova più tardi"
            )

        state.cognitive.generation_pipeline.append(model_name)
        return result

    except Exception as e:
        error = f"Error connecting to chatbot: {e}"
        logger.error(error)
        raise RequestHandlingException(error)


# =========================
# UTILITIES
# =========================
# Conversation history is re-sent in full on every LLM call of a turn (router,
# each ReAct step, ...). Final answers are normally short, but nothing else
# bounds them, so one very long earlier message would be repeated in every call.
MAX_HISTORY_MESSAGE_CHARS = 1500


def _cap_history_message(content: str, max_chars: int) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + f"... [{len(content) - max_chars} chars omitted]"


def format_messages(messages, max_chars_per_message: int = MAX_HISTORY_MESSAGE_CHARS):
    return "\n".join(
        f"{m['role'].upper()}: {_cap_history_message(str(m['content']), max_chars_per_message)}"
        for m in messages
    )
