"""Utility tool definitions."""

from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory


def create_lookup_glossary_tool() -> ToolDefinition:
    return ToolDefinition(
        name="lookup_glossary",
        description=(
            "Look up definitions, aliases, and relationships for domain terms "
            "(e.g. 'problem', 'proposal', 'scenario', 'overtourism', 'digital twin', "
            "'territorial index'). Use this to answer user questions about terminology "
            "or to clarify ambiguous intent before selecting another tool. To list the "
            "concrete, individual territorial indexes that actually exist (e.g. 'what "
            "indices are there?', 'which territorial indices exist?'), use "
            "get_territorial_index_list instead — that data comes from the backend, not "
            "the glossary."
        ),
        category=ToolCategory.UTILITY,
        long_description=(
            "Searches the platform glossary for one or more terms. "
            "Matching is fuzzy: it checks the query against term names, aliases, and "
            "related_terms fields. "
            "Returns definitions, aliases, and related concepts for all matching entries. "
            "Call this whenever: (a) the user asks what a term means, "
            "(b) the user uses unfamiliar vocabulary that might map to a platform concept, "
            "or (c) you need to clarify whether the user is referring to a Problem, "
            "Proposal, or Scenario before proceeding. "
            "This tool does NOT enumerate the concrete territorial indexes available on "
            "the platform (e.g. 'Indice di ricettività') — those are backend data, not "
            "glossary vocabulary; call get_territorial_index_list for that instead."
        ),
        parameters=[
            ToolParameter(
                name="query",
                description=(
                    "One or more space-separated keywords to look up in the glossary. "
                    "Example: 'scenario simulation' or 'overtourism carrying capacity'."
                ),
                type="string",
                required=True,
            ),
        ],
        output_description=(
            "List of matching glossary entries with their definitions, aliases, "
            "related terms, and examples."
        ),
        tags=["data", "read-only", "glossary", "utility"],
        agent_tier="executor",
    )


def create_get_system_capabilities_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_system_capabilities",
        description="Retrieve a description of the system and its capabilities",
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Returns a description of the system, its core concepts (problems, proposals, scenarios), "
            "allowed operations per context level, and which tools are available in each context. "
            "Call this at startup or whenever clarification about system capabilities is needed."
        ),
        parameters=[],
        output_description="System description, context rules, and available tools per context",
        tags=["data", "read-only", "system", "navigation"],
        agent_tier="operative",
    )


def create_general_question_response_tool() -> ToolDefinition:
    return ToolDefinition(
        name="general_question_response",
        description=(
            "Answer an on-topic question (tourism management, overtourism, mobility, or the platform's "
            "subject matter) that isn't covered by platform data, the glossary, or any other tool. "
            "Do NOT use this for questions outside that domain (e.g. weather, movies, general trivia) — "
            "those should be declined per the on-topic check, not delegated here."
        ),
        category=ToolCategory.INTERACTION,
        long_description=(
            "Answers the current question with an unguarded, free-form reply that is not "
            "checked against platform data, the glossary, or any other grounded source. Use "
            "this only once other guidelines and tools don't apply — e.g. the user asks a "
            "general-knowledge question with no connection to problems, proposals, scenarios, "
            "or territorial indexes, and clearly expects a direct answer rather than a "
            "refusal. This tool's agent_tier is 'exploitative' (see AgentTier), an unguarded "
            "tier that requires explicit, one-time user consent before a session may use it "
            "at all — the first use each session pauses for that consent automatically (see "
            "TIERS_REQUIRING_CONSENT / tool_executor_node's tier-consent gate). Do not use "
            "this to bypass a grounded tool that could answer the question instead."
        ),
        parameters=[
            ToolParameter(
                name="query",
                description="The user's general question, restated if helpful for clarity.",
                type="string",
                required=True,
            ),
        ],
        output_description=(
            "A free-form answer to the general question, not grounded in platform "
            "data, the glossary, or any other verified source."
        ),
        agent_tier="exploitative",
        tags=["general", "ungrounded", "exploitative-tier"],
    )


def create_get_data_from_link_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_data_from_link",
        description=(
            "Fetch data from a URL, following links found in problem or proposal fields, "
            "and return the content or an error summary if the link cannot be retrieved."
        ),
        category=ToolCategory.DATA_RETRIEVAL,
        long_description=(
            "Fetch the content at the provided URL. If the URL points to a web page, return a text snippet and extracted title where available. "
            "If the link is broken, blocked, or otherwise unavailable, return a clear error message."
        ),
        parameters=[
            ToolParameter(
                name="url",
                description="The link to fetch data from.",
                type="string",
                required=True,
            ),
        ],
        output_description="URL fetch result with content summary or error details",
        tags=["data", "read-only", "link", "web"],
        agent_tier="operative",
    )


__all__ = [
    "create_get_system_capabilities_tool",
    "create_lookup_glossary_tool",
    "create_get_data_from_link_tool",
    "create_general_question_response_tool",
]
