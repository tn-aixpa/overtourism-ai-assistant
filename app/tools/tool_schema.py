"""
Tool schema and interface definitions for the agentic system.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List
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
