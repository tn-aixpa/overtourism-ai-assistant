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
    # Which AgentTier this tool's response is generated under once selected
    # (see AgentState.active_agent / _reasoning_policy in
    # answer_generation.py). This is orthogonal to routing: the top-level
    # router (app.agent.nodes.router) decides which SUBSET of tools the
    # ReAct reasoner may pick from this turn; agent_tier instead decides
    # the RESPONSE STYLE/POLICY once a tool from that subset is actually
    # used, and — for tiers in TIERS_REQUIRING_CONSENT (see
    # app.agent.state) — whether tool_executor_node must pause for
    # one-time user consent before running it at all. A turn that calls
    # several tools takes the highest tier reached across all of them (see
    # tool_executor_node._bump_active_agent). Plain string rather than an
    # import of app.agent.state.AgentTier to avoid a tools -> agent
    # dependency; must be kept in sync with AgentTier's values
    # ("executor", "operative", "methodological", "exploitative").
    #
    # NOTE: this used to also be filtered on for tool *selectability* via a
    # separate `visible_to` field (checked in
    # ToolRegistry.get_context_tools against AgentState.active_agent). That
    # was removed: it created a chicken-and-egg problem where a tool tagged
    # for a higher tier could never be selected in the first place, because
    # active_agent only ever reaches that tier as a RESULT of selecting
    # such a tool. Which tools are selectable this turn is now governed
    # entirely by routing (app.agent.nodes.router /
    # CognitiveState.enabled_tools); agent_tier only affects the response
    # once a tool has actually run.
    agent_tier: str = "executor"

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
