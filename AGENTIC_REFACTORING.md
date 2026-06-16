# Agentic Refactoring Guide

## Overview

Your agent has been refactored from a **workflow state machine** to a **true agentic system** where the LLM decides which tools to use instead of following hardcoded workflows.

## Architecture Changes

### Before: Workflow-Based
```
User Input → Intent Node → Router (hardcoded) → Problem/Proposal/Scenario/Interaction Graph → Output
```

The routing was predefined in the intent node based on user message patterns.

### After: Tool-Based (Agentic)
```
User Input → Initialize Tools → Tool Selection (LLM decides) → Tool Executor → Output
```

The LLM selects which tool to use based on its reasoning about the user's intent.

## Key Components

### 1. Tool Schema System (`app/tools/tool_schema.py`)
Defines the interface for all tools:
- `ToolDefinition`: Describes a tool with name, description, parameters, executor
- `ToolParameter`: Describes input parameters with types and validation
- `ToolExecutionResult`: Standardized result format

### 2. Tool Registry (`app/tools/tool_registry.py`)
Central catalog of available tools with features:
- **Tool Discovery**: `get_tool()`, `list_tool_names()`, `get_tools_by_category()`
- **Access Control**: `restrict_user_tools()`, `get_user_allowed_tools()`
- **Context Filtering**: `get_context_tools()` - tools available in current context
- **LLM Format**: `get_tools_for_llm()` - tools in Claude/OpenAI format

### 3. Tool Definitions (`app/tools/agent_tools.py`)
All available tools:
- `list_problems` - List all available problems/proposals/scenarios
- `get_context_details` - Get details for specific items
- `set_active_context` - Switch working context
- `extract_problem_details` - Extract & structure problem info
- `create_problem` - Create problem instance
- `extract_proposal_details` - Extract & structure proposal info
- `create_proposal` - Create proposal instance
- `extract_scenario_details` - Extract & structure scenario info
- `create_scenario` - Create scenario instance
- `interact_with_context` - View/edit/analyze current context

### 4. Tool Configuration (`app/tools/tool_config.py`)
Setup and access control:
- `ToolConfiguration` class for user-level configuration
- Pre-built roles: `configure_viewer_user()`, `configure_creator_user()`, `configure_power_user()`
- Fine-grained control: enable/disable tools per user

### 5. Tool Selector Node (`app/agent/nodes/tool_selector.py`)
- `initialize_tools()`: Load available tools based on user/context
- `tool_selector_node()`: LLM decides which tool to call
- Uses existing LLM reasoning infrastructure

### 6. Tool Executor Node (`app/agent/nodes/tool_executor.py`)
- `tool_executor_node()`: Main execution orchestrator
- `execute_selected_tool()`: Dispatcher and executor
- Tool-specific implementations for each tool
- Error handling and tracing

### 7. Simplified Graph (`app/agent/graph_agentic.py`)
New streamlined graph:
- Much simpler than original with fewer hardcoded nodes
- Pure tool-based execution path
- Extensible: add new tools without modifying graph

## Usage Examples

### Basic Usage

```python
from app.tools.tool_config import initialize_tools

# Initialize the tool system (call once during app startup)
initialize_tools()

# In your agent state/setup
state = AgentState(session_id="session_123")

# The agent will now use tools for decision making
# instead of hardcoded workflows
result = app.invoke(state)
```

### Future: Configure User Access (Infrastructure Ready)

Tool access control infrastructure is built and ready for when you need it. Currently all users have access to all tools. To implement restrictions later:

```python
from app.tools.tool_config import get_tool_configuration

config = get_tool_configuration()

# Read-only viewer (when implemented)
# config.configure_viewer_user("viewer@company.com")

# Creator with limited permissions (when implemented)
# config.configure_creator_user("creator@company.com")

# Power user with full access (when implemented)
# config.configure_power_user("admin@company.com")

# Custom permissions (when implemented)
# config.configure_user_tools(
#     user_id="special@company.com",
#     tool_names=[
#         "list_problems",
#         "get_context_details",
#         "extract_problem_details",
#         # ... only these tools
#     ]
# )
```

### Get Available Tools

```python
from app.tools.tool_registry import get_tool_registry

registry = get_tool_registry()

# All available tools
tools = registry.list_tool_names()

# Get registry stats
stats = registry.get_stats()
print(f"Total tools: {stats['total_tools']}")
print(f"Enabled: {stats['enabled_tools']}")
```

### Add Custom Tool

```python
from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory
from app.tools.tool_registry import get_tool_registry

# Define the tool
my_tool = ToolDefinition(
    name="my_custom_tool",
    description="Does something useful",
    category=ToolCategory.UTILITY,
    parameters=[
        ToolParameter(
            name="input_value",
            description="Some input",
            type="string",
            required=True,
        )
    ],
)

# Register it
registry = get_tool_registry()
registry.register_tool(my_tool)

# Implement executor in tool_executor.py:
# Add to get_tool_executor() dispatcher
# Add implementation function execute_my_custom_tool()
```

## State Changes

### New CognitiveState Fields
```python
# Tool execution state
available_tools: List[str]  # List of available tool names
selected_tool: Optional[str]  # Currently selected tool
tool_arguments: Dict[str, Any]  # Arguments for the selected tool
tool_result: Optional[Dict[str, Any]]  # Result from last tool execution
tool_confirmation_needed: bool  # Whether tool result needs user confirmation
pending_tools: List[str]  # Queue of tools to execute
```

### New AgentState Fields
```python
user_id: Optional[str]  # For tool access control
```

## Migration from Old System

### For Existing Workflows
The old workflow-based subgraphs are still present but now act as "tool implementations":
- Problem extraction → `execute_extract_problem_details()`
- Problem creation → `execute_create_problem()`
- Proposal extraction → `execute_extract_proposal_details()`
- Proposal creation → `execute_create_proposal()`
- Scenario extraction → `execute_extract_scenario_details()`
- Scenario creation → `execute_create_scenario()`

### Updating Your Code

**Before:**
```python
from app.agent.graph import app

# Agent followed hardcoded workflows
result = app.invoke(state)
```

**After:**
```python
from app.agent.graph_agentic import app
from app.tools.tool_config import initialize_tools

# Initialize tools once
initialize_tools()

# Agent now uses LLM-selected tools
result = app.invoke(state)
```

## Benefits of This Approach

1. **More Agentic**: LLM decides what to do, not hardcoded logic
2. **More Extensible**: Add new tools without modifying graph structure
3. **Cleaner Code**: No duplicate logic across workflow-specific nodes
4. **Better Access Control**: Easily restrict tools per user/context
5. **More Traceable**: Clear tool execution history in traces
6. **Composable**: Tools can call other tools
7. **Testable**: Tools can be tested independently

## Future Enhancements

1. **Tool Output Processing**: Format tool outputs for context/display
2. **Multi-Tool Execution**: Agent chains multiple tools together
3. **Tool Approval**: Human-in-the-loop for sensitive tools
4. **Dynamic Tool Discovery**: Load tools from plugins/external sources
5. **Tool Versioning**: Multiple versions of same tool with upgrades
6. **Tool Metrics**: Track which tools are used most, performance data
7. **Tool Dependencies**: Some tools require others to run first

## Troubleshooting

### No tools available
- Call `initialize_tools()` before using agent
- Check if tools are registered in registry

### Tool not executing
- Check tool is in available_tools list
- Verify tool executor implementation exists
- Check tool_executor logs for error details

### Tool selection issues
- Verify LLM reasoning is working
- Check available tools descriptions are clear
- Review tool selection trace for what LLM chose

## Files Changed

New files:
- `app/tools/tool_schema.py` - Tool interface definitions
- `app/tools/tool_registry.py` - Central tool registry
- `app/tools/agent_tools.py` - Tool definitions
- `app/tools/tool_config.py` - Configuration and setup
- `app/agent/nodes/tool_selector.py` - Tool selection node
- `app/agent/nodes/tool_executor.py` - Tool execution node
- `app/agent/graph_agentic.py` - Simplified agentic graph

Modified files:
- `app/agent/state.py` - Added tool execution state fields

Original files (kept for reference):
- `app/agent/graph.py` - Original workflow-based graph
- `app/agent/graphs/` - Original workflow subgraphs
- `app/agent/nodes/` - Original workflow nodes
