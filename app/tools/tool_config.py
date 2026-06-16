"""
Tool configuration and initialization for the agentic system.

This module handles setup of the tool registry with proper user/context-based restrictions.
It provides high-level APIs for configuring which tools are available to different users.
"""

import logging
from typing import List, Optional, Set

from app.tools.tool_registry import get_tool_registry, reset_tool_registry
from app.tools.agent_tools import get_all_agent_tools
from app.tools.tool_schema import ToolCategory

logger = logging.getLogger(__name__)


class ToolConfiguration:
    """Manages tool configuration and access control."""
    
    def __init__(self):
        self.registry = get_tool_registry()
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize the tool registry with all available tools."""
        if self._initialized:
            logger.info("Tool registry already initialized")
            return
        
        logger.info("Initializing tool registry")
        
        # Register all tools
        all_tools = get_all_agent_tools()
        self.registry.register_tools(all_tools)
        
        logger.info(f"Registered {len(all_tools)} tools")
        logger.debug(f"Tool names: {self.registry.list_tool_names()}")
        
        self._initialized = True
    
    def configure_user_tools(
        self,
        user_id: str,
        tool_names: Optional[List[str]] = None,
        allow_problem_tools: bool = True,
        allow_proposal_tools: bool = True,
        allow_scenario_tools: bool = True,
        allow_interaction_tools: bool = True,
        allow_data_retrieval: bool = True,
    ) -> None:
        """
        Configure which tools a user can access.
        
        Can specify either explicit tool names or use boolean flags for categories.
        
        Args:
            user_id: User identifier
            tool_names: Explicit list of allowed tool names. If provided, other params are ignored.
            allow_problem_tools: Allow problem creation/extraction
            allow_proposal_tools: Allow proposal creation/extraction
            allow_scenario_tools: Allow scenario creation/extraction
            allow_interaction_tools: Allow interaction with context
            allow_data_retrieval: Allow listing/getting data
        """
        self.initialize()
        
        if tool_names:
            # Use explicit tool names
            self.registry.restrict_user_tools(user_id, tool_names)
            logger.info(f"Restricted user {user_id} to tools: {tool_names}")
        else:
            # Build list based on categories
            allowed_tools = []
            all_tools = self.registry.get_all_tools()
            
            for tool_name, tool_def in all_tools.items():
                include = False
                
                if allow_problem_tools and tool_def.category == ToolCategory.PROBLEM_MANAGEMENT:
                    include = True
                elif allow_proposal_tools and tool_def.category == ToolCategory.PROPOSAL_MANAGEMENT:
                    include = True
                elif allow_scenario_tools and tool_def.category == ToolCategory.SCENARIO_MANAGEMENT:
                    include = True
                elif allow_interaction_tools and tool_def.category == ToolCategory.INTERACTION:
                    include = True
                elif allow_data_retrieval and tool_def.category == ToolCategory.DATA_RETRIEVAL:
                    include = True
                elif tool_def.category == ToolCategory.CONTEXT_MANAGEMENT:
                    # Context management is always included
                    include = True
                
                if include:
                    allowed_tools.append(tool_name)
            
            self.registry.restrict_user_tools(user_id, allowed_tools)
            logger.info(f"Configured user {user_id} with tools: {allowed_tools}")
    
    def configure_viewer_user(self, user_id: str) -> None:
        """Configure a read-only viewer user (can only view data)."""
        self.initialize()
        self.registry.restrict_user_tools(user_id, [
            "list_problems",
            "get_context_details",
            "set_active_context",
        ])
        logger.info(f"Configured user {user_id} as viewer (read-only)")
    
    def configure_creator_user(self, user_id: str) -> None:
        """Configure a creator user (can create but not delete/modify)."""
        self.initialize()
        self.registry.restrict_user_tools(user_id, [
            "list_problems",
            "get_context_details",
            "set_active_context",
            "extract_problem_details",
            "create_problem",
            "extract_proposal_details",
            "create_proposal",
            "extract_scenario_details",
            "create_scenario",
        ])
        logger.info(f"Configured user {user_id} as creator")
    
    def configure_power_user(self, user_id: str) -> None:
        """Configure a power user (full access to all tools)."""
        self.initialize()
        # Don't restrict - all tools available
        if user_id in self.registry._user_tool_restrictions:
            del self.registry._user_tool_restrictions[user_id]
        logger.info(f"Configured user {user_id} as power user (full access)")
    
    def enable_tool(self, tool_name: str, enabled: bool = True) -> None:
        """Enable or disable a tool globally."""
        self.initialize()
        self.registry.set_tool_enabled(tool_name, enabled)
        logger.info(f"Tool '{tool_name}' set to enabled={enabled}")
    
    def disable_tool(self, tool_name: str) -> None:
        """Disable a tool globally."""
        self.enable_tool(tool_name, False)
    
    def get_user_tools(self, user_id: Optional[str] = None) -> List[str]:
        """Get list of tools available to a user."""
        self.initialize()
        tools = self.registry.get_user_allowed_tools(user_id)
        return list(tools.keys())
    
    def get_stats(self) -> dict:
        """Get registry statistics."""
        self.initialize()
        return self.registry.get_stats()


# Global configuration instance
_tool_config: Optional[ToolConfiguration] = None


def get_tool_configuration() -> ToolConfiguration:
    """Get or create the global tool configuration."""
    global _tool_config
    if _tool_config is None:
        _tool_config = ToolConfiguration()
    return _tool_config


def initialize_tools() -> None:
    """Initialize the tool system with default configuration."""
    config = get_tool_configuration()
    config.initialize()
    logger.info("Tool system initialized")


def reset_tools() -> None:
    """Reset the tool system (for testing)."""
    global _tool_config
    reset_tool_registry()
    _tool_config = None
    logger.info("Tool system reset")
