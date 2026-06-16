"""
Integration example and validation for the agentic refactoring.

This module shows how to:
1. Initialize the tool system
2. Configure users with different access levels
3. Use the new agentic graph
4. Monitor tool selection and execution
"""

from app.agent.state import AgentState
from app.tools.tool_config import initialize_tools, get_tool_configuration, reset_tools
from app.tools.tool_registry import get_tool_registry

def setup_tool_system():
    """Initialize tool system with example configurations."""
    print("Setting up tool system...")
    
    # Initialize
    initialize_tools()
    config = get_tool_configuration()
    
    # Show registration
    registry = get_tool_registry()
    stats = registry.get_stats()
    print(f"Registered tools: {stats['total_tools']}")
    print(f"Tools by category: {stats['tools_by_category']}")
    
    # Configure example users
    config.configure_viewer_user("viewer@example.com")
    print("Configured: viewer@example.com (read-only)")
    
    config.configure_creator_user("creator@example.com")
    print("Configured: creator@example.com (can create)")
    
    config.configure_power_user("admin@example.com")
    print("Configured: admin@example.com (full access)")
    
    return config


def demonstrate_tool_selection():
    """Show how tool selection works."""
    print("\n" + "="*60)
    print("TOOL SELECTION DEMONSTRATION")
    print("="*60)
    
    registry = get_tool_registry()
    
    # Get tools for different contexts
    all_tools = registry.get_all_enabled_tools()
    print(f"\nAll enabled tools: {list(all_tools.keys())}")
    
    # Get tools for viewer
    viewer_tools = registry.get_user_allowed_tools("viewer@example.com")
    print(f"\nViewer can access: {list(viewer_tools.keys())}")
    
    # Get tools for creator
    creator_tools = registry.get_user_allowed_tools("creator@example.com")
    print(f"\nCreator can access: {list(creator_tools.keys())}")
    
    # Get tools in context
    problem_context_tools = registry.get_context_tools(
        user_id="creator@example.com",
        active_context="problem"
    )
    print(f"\nIn problem context, creator can use: {list(problem_context_tools.keys())}")
    
    proposal_context_tools = registry.get_context_tools(
        user_id="creator@example.com",
        active_context="proposal"
    )
    print(f"\nIn proposal context, creator can use: {list(proposal_context_tools.keys())}")


def demonstrate_state_setup():
    """Show how to setup agent state for tool usage."""
    print("\n" + "="*60)
    print("STATE SETUP DEMONSTRATION")
    print("="*60)
    
    state = AgentState(
        session_id="demo_session_001",
        user_id="creator@example.com",
        user_lang="English",
    )
    
    print(f"\nCreated state:")
    print(f"  Session ID: {state.session_id}")
    print(f"  User ID: {state.user_id}")
    print(f"  Language: {state.user_lang}")
    
    # Add user message
    state.add_user_message("I want to create a new problem about traffic congestion")
    print(f"\nAdded user message: {state.get_last_user_message().content}")
    
    # Check tool state fields
    print(f"\nTool execution state:")
    print(f"  Available tools: {state.cognitive.available_tools}")
    print(f"  Selected tool: {state.cognitive.selected_tool}")
    print(f"  Tool confirmation needed: {state.cognitive.tool_confirmation_needed}")
    
    return state


def demonstrate_tool_discovery():
    """Show tool discovery and metadata."""
    print("\n" + "="*60)
    print("TOOL DISCOVERY DEMONSTRATION")
    print("="*60)
    
    registry = get_tool_registry()
    
    # Get a specific tool
    tool = registry.get_tool("list_problems")
    print(f"\nTool: {tool.name}")
    print(f"  Description: {tool.description}")
    print(f"  Category: {tool.category.value}")
    print(f"  Requires context: {tool.requires_context}")
    print(f"  Requires confirmation: {tool.requires_confirmation}")
    print(f"  Version: {tool.version}")
    print(f"  Tags: {tool.tags}")
    
    # Get tools by category
    from app.tools.tool_schema import ToolCategory
    
    problem_tools = registry.get_tools_by_category(ToolCategory.PROBLEM_MANAGEMENT)
    print(f"\nProblem management tools: {list(problem_tools.keys())}")
    
    # Get tool descriptions for LLM
    llm_tools = registry.get_tools_for_llm("creator@example.com", "problem")
    print(f"\nTools formatted for LLM in problem context ({len(llm_tools)} tools)")
    if llm_tools:
        first_tool = llm_tools[0]['function']
        print(f"  Example: {first_tool['name']}")
        print(f"           {first_tool['description']}")
    
    # Get text description
    description = registry.get_tools_description("creator@example.com", "proposal")
    print(f"\nTools description for prompt (in proposal context):")
    for line in description.split('\n')[:5]:  # First 5 lines
        print(f"  {line}")


def demonstrate_access_control():
    """Show access control patterns."""
    print("\n" + "="*60)
    print("ACCESS CONTROL DEMONSTRATION")
    print("="*60)
    
    config = get_tool_configuration()
    registry = get_tool_registry()
    
    # Restricted user
    print("\nRestricting user to specific tools...")
    config.configure_user_tools(
        user_id="restricted@example.com",
        tool_names=["list_problems", "get_context_details"]
    )
    
    restricted_tools = registry.get_user_allowed_tools("restricted@example.com")
    print(f"Restricted user tools: {list(restricted_tools.keys())}")
    
    # Check if a specific tool is available
    has_create = "create_problem" in restricted_tools
    print(f"Can create problem? {has_create}")
    
    # Enable/disable tools
    print("\nDisabling 'create_problem' tool globally...")
    registry.set_tool_enabled("create_problem", False)
    
    admin_tools = registry.get_user_allowed_tools("admin@example.com")
    can_create = "create_problem" in admin_tools
    print(f"Admin can create problem (after disable)? {can_create}")
    
    # Re-enable
    registry.set_tool_enabled("create_problem", True)
    print("Re-enabled 'create_problem' tool")


def run_all_demonstrations():
    """Run all demonstrations."""
    print(f'(levelname)s: %(message)s')
    
    try:
        # Reset to clean state
        reset_tools()
        
        # Run demos
        setup_tool_system()
        demonstrate_tool_selection()
        demonstrate_state_setup()
        demonstrate_tool_discovery()
        demonstrate_access_control()
        
        print("\n" + "="*60)
        print("ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Error in demonstrations: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_all_demonstrations()
