"""
Tool schema and interface definitions for the agentic system.

This module defines the structure and interface for all tools that the agent can execute.
Tools are dynamically discoverable, have clear interfaces, and can be restricted based on context.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict, List
from enum import Enum


class ToolCategory(str, Enum):
    """Categories for organizing tools."""
    DATA_RETRIEVAL = "data_retrieval"
    PROBLEM_MANAGEMENT = "problem_management"
    PROPOSAL_MANAGEMENT = "proposal_management"
    SCENARIO_MANAGEMENT = "scenario_management"
    INTERACTION = "interaction"
    UTILITY = "utility"


@dataclass
class ToolParameter:
    """Represents a parameter for a tool."""
    name: str
    description: str
    type: str  # "string", "integer", "number", "boolean", "object", "array"
    required: bool = True
    default: Optional[Any] = None
    enum_values: Optional[List[Any]] = None  # For restricted values
    schema: Optional[Dict[str, Any]] = None  # For complex types


@dataclass
class ToolDefinition:
    """Defines a tool that the agent can execute."""
    
    # Identity & Documentation
    name: str
    description: str
    category: ToolCategory
    long_description: Optional[str] = None
    
    # Interface
    parameters: List[ToolParameter] = field(default_factory=list)
    output_description: str = "Result of tool execution"
    
    # Implementation
    executor: Optional[Callable] = None  # Function that executes the tool
    
    # Configuration
    enabled: bool = True
    requires_confirmation: bool = False
    streaming: bool = False  # If true, tool can provide streaming output
    
    # Metadata
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_tool_description(self) -> Dict[str, Any]:
        """Convert to format suitable for LLM tool calling."""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum_values:
                prop["enum"] = param.enum_values
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
                }
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize tool definition to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "long_description": self.long_description,
            "parameters": [
                {
                    "name": p.name,
                    "description": p.description,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "enum_values": p.enum_values,
                }
                for p in self.parameters
            ],
            "output_description": self.output_description,
            "enabled": self.enabled,
            "requires_confirmation": self.requires_confirmation,
            "version": self.version,
            "tags": self.tags,
        }

