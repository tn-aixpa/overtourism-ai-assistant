"""
Integration example for the tool registry.

Demonstrates:
1. Initializing the registry
2. Registering tools
3. Inspecting registered tools
4. Producing the LLM tool schema
"""

from app.tools.tool_registry import get_tool_registry
from app.tools.agent_tools import get_all_agent_tools


def setup_tool_system():
    """Initialize the global tool registry."""
    registry = get_tool_registry()

    if not registry.list_tool_names():
        registry.register_tools(get_all_agent_tools())

    print(f"Registered {len(registry.list_tool_names())} tools")
    return registry


def demonstrate_registered_tools():
    """Print all registered tools."""
    print("\n" + "=" * 60)
    print("REGISTERED TOOLS")
    print("=" * 60)

    registry = get_tool_registry()

    for tool in registry.get_all_known_tools().values():
        print(f"\n{tool.name}")
        print(f"  Description : {tool.description}")
        print(f"  Category    : {tool.category.value}")
        print(f"  Enabled     : {tool.enabled}")
        print(f"  Confirmation: {tool.requires_confirmation}")
        print(f"  Tags        : {tool.tags}")


def demonstrate_tool_lookup():
    """Show lookup of a single tool."""
    print("\n" + "=" * 60)
    print("TOOL LOOKUP")
    print("=" * 60)

    registry = get_tool_registry()

    tool_name = registry.list_tool_names()[0]
    tool = registry.get_tool(tool_name)

    print(f"Name: {tool.name}")
    print(f"Category: {tool.category.value}")
    print(f"Parameters:")

    if tool.parameters:
        for param in tool.parameters:
            print(
                f"  - {param.name} ({param.type})"
                f"{' [required]' if param.required else ''}"
            )
            print(f"      {param.description}")
    else:
        print("  None")


def demonstrate_llm_schema():
    """Show the schema passed to the LLM."""
    print("\n" + "=" * 60)
    print("LLM TOOL SCHEMA")
    print("=" * 60)

    registry = get_tool_registry()

    llm_tools = registry.get_tools_for_llm()

    print(f"Generated schemas: {len(llm_tools)}")

    if llm_tools:
        schema = llm_tools[0]
        print("\nExample schema:")
        print(schema)


def run_all_demonstrations():
    setup_tool_system()
    demonstrate_registered_tools()
    demonstrate_tool_lookup()
    demonstrate_llm_schema()

    print("\n" + "=" * 60)
    print("ALL DEMONSTRATIONS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_demonstrations()
