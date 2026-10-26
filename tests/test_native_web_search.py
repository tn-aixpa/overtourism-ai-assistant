from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.agent.state import AgentState
from app.utils import llm


def test_anthropic_native_search_returns_answer_and_citations(monkeypatch):
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="text",
                text="A current finding.",
                citations=[
                    SimpleNamespace(title="Source", url="https://example.test/page")
                ],
            ),
            SimpleNamespace(
                type="web_search_tool_result",
                content=[
                    SimpleNamespace(
                        type="web_search_result",
                        title="Source",
                        url="https://example.test/page",
                    )
                ],
            ),
        ],
        usage=SimpleNamespace(input_tokens=12, output_tokens=24),
    )
    create = Mock(return_value=response)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(
        llm,
        "get_llm_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    monkeypatch.setattr(llm, "_log_costs", Mock())
    state = AgentState(session_id="search-session")

    result = llm.native_web_search(state, "current tourism data")

    assert result == {
        "query": "current tourism data",
        "answer": "A current finding.",
        "sources": [
            {"title": "Source", "url": "https://example.test/page"}
        ],
    }
    assert create.call_args.kwargs["tools"] == [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5,
        }
    ]
    assert state.cognitive.generation_pipeline == [llm.ANTHROPIC_MODELS["heavy"]]


def test_azure_native_search_returns_answer_and_citations(monkeypatch):
    response = SimpleNamespace(
        output_text="A current finding.",
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                title="Source",
                                url="https://example.test/page",
                            )
                        ]
                    )
                ],
            )
        ],
        usage=SimpleNamespace(input_tokens=12, output_tokens=24),
    )
    create = Mock(return_value=response)
    monkeypatch.setattr(llm, "LLM_PROVIDER", "azure")
    monkeypatch.setattr(
        llm,
        "get_azure_client",
        lambda: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    monkeypatch.setattr(llm, "_log_costs", Mock())
    state = AgentState(session_id="search-session")

    result = llm.native_web_search(state, "current tourism data")

    assert result["answer"] == "A current finding."
    assert result["sources"] == [
        {"title": "Source", "url": "https://example.test/page"}
    ]
    assert create.call_args.kwargs["tools"] == [{"type": "web_search_preview"}]
    assert state.cognitive.generation_pipeline == [llm.AZURE_MODELS["heavy"]]


def test_native_search_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "unknown")
    with pytest.raises(llm.RequestHandlingException, match="not supported"):
        llm.native_web_search(AgentState(session_id="search-session"), "query")
