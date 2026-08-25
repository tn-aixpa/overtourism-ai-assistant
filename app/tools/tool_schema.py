"""
Tool schema and interface definitions for the agentic system.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List, Set
from enum import Enum


class ToolCategory(str, Enum):
    DATA_RETRIEVAL = "data_retrieval"
    PROBLEM_MANAGEMENT = "problem_management"
    PROPOSAL_MANAGEMENT = "proposal_management"
    SCENARIO_MANAGEMENT = "scenario_management"
    INTERACTION = "interaction"
    UTILITY = "utility"


@dataclass
class ToolParameter:
    name: str
    description: str
    type: str  # "string", "integer", "number", "boolean", "object", "array"
    required: bool = True
    default: Optional[Any] = None
    schema: Optional[Dict[str, Any]] = None  # For complex types


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: ToolCategory
    long_description: Optional[str] = None
    parameters: List[ToolParameter] = field(default_factory=list)
    output_description: str = "Result of tool execution"
    enabled: bool = True
    requires_confirmation: bool = False
    tags: List[str] = field(default_factory=list)
    # Set on delegate_to_<tier> tools (e.g. "exploitative") that require
    # one-time user consent before a session may use that tier at all.
    # Checked by tool_executor_node against
    # CognitiveState.has_valid_tier_consent before the tool is allowed to
    # run. None means no tier-level gate applies (the default for
    # everything except delegation tools into gated tiers).
    requires_tier_consent: Optional[str] = None
    # Which agent tiers may see/select this tool at all (filtered in
    # ToolRegistry.get_context_tools via the `tier` argument). Defaults to
    # all four tiers, i.e. no restriction, so existing tools need no
    # changes to keep working exactly as before. Values are plain strings
    # rather than an import of app.agent.state.AgentTier to avoid a
    # tools -> agent dependency; they must be kept in sync with
    # AgentTier's values ("executor", "operative", "methodological",
    # "exploitative").
    visible_to: Set[str] = field(
        default_factory=lambda: {
            "executor",
            "operative",
            "methodological",
            "exploitative",
        }
    )

    def to_tool_description(self) -> Dict[str, Any]:
        """Convert to format suitable for LLM tool calling."""
        properties = {}
        required = []

        for param in self.parameters:
            prop = {"type": param.type, "description": param.description}
            if param.schema:
                prop.update(param.schema)
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
