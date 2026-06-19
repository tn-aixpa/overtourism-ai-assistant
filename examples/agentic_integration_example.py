"""
Integration example and validation for the agentic refactoring.

This module shows how to:
1. Initialize the tool system
2. Demonstrate available tools (all users have access)
3. Use the new agentic graph
4. Monitor tool selection and execution
"""

from app.agent.state import AgentState
from app.tools.tool_registry import get_tool_registry
from app.tools.agent_tools import get_all_agent_tools


def setup_tool_system():
    """Initialize and register the tool system."""
    print("Setting up tool system...")

    registry = get_tool_registry()

    # Register tools before inspecting stats
    if not registry.list_tool_names():
        all_tools = get_all_agent_tools()
        registry.register_tools(all_tools)

    stats = registry.get_stats()
    print(f"Registered tools: {stats['total_tools']}")
    print(f"Enabled tools: {stats['enabled_tools']}")
    print(f"Tools by category: {stats['tools_by_category']}")

    return registry


def demonstrate_tool_selection():
    """Show available tools across different contexts."""
    print("\n" + "="*60)
    print("AVAILABLE TOOLS DEMONSTRATION")
    print("="*60)

    registry = get_tool_registry()

    # Get all enabled tools
    all_tools = registry.get_all_enabled_tools()
    print(f"\nAll available tools ({len(all_tools)}):")
    for tool_name, tool_def in sorted(all_tools.items()):
        print(f"  - {tool_name}: {tool_def.description}")

def demonstrate_state_setup():
    """Show how to setup agent state for tool usage."""
    print("\n" + "="*60)
    print("STATE SETUP DEMONSTRATION")
    print("="*60)

    state = AgentState(
        session_id="demo_session_001",
        user_lang="English",
    )

    print(f"\nCreated state:")
    print(f"  Session ID: {state.session_id}")
    print(f"  Language: {state.user_lang}")

    state.add_user_message("I want to create a new problem about traffic congestion")
    print(f"\nAdded user message: {state.get_last_user_message().content}")

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
    tool = registry.get_tool("list_available_problems")
    print(f"\nTool: {tool.name}")
    print(f"  Description: {tool.description}")
    print(f"  Category: {tool.category.value}")
    print(f"  Requires confirmation: {tool.requires_confirmation}")
    print(f"  Version: {tool.version}")
    print(f"  Tags: {tool.tags}")

    # Get tools by category
    from app.tools.tool_schema import ToolCategory

    problem_tools = registry.get_tools_by_category(ToolCategory.PROBLEM_MANAGEMENT)
    print(f"\nProblem management tools: {list(problem_tools.keys())}")


def run_all_demonstrations():
    """Run all demonstrations."""
    try:
        setup_tool_system()
        demonstrate_tool_selection()
        demonstrate_state_setup()
        demonstrate_tool_discovery()

        print("\n" + "="*60)
        print("ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY")
        print("="*60)

    except Exception as e:
        print(f"Error in demonstrations: {e}")
        raise


if __name__ == "__main__":
    run_all_demonstrations()