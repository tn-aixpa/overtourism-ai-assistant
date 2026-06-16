# Quick Start: Using the Agentic System

## 1. Initialize the Tool System

```python
from app.tools.tool_config import initialize_tools

# Call once during app startup
initialize_tools()
```

## 2. Configure Tools for Your Users

```python
from app.tools.tool_config import get_tool_configuration

config = get_tool_configuration()

# Example: Setup different user roles
config.configure_viewer_user("viewer@company.com")
config.configure_creator_user("creator@company.com")
config.configure_power_user("admin@company.com")
```

## 3. Update Your Agent Invocation

```python
from app.agent.graph_agentic import app
from app.agent.state import AgentState

# Create state
state = AgentState(
    session_id="session_123",
    user_id="user@company.com",  # Important: set user_id for access control
)

# Add user input
state.add_user_message("I want to create a new problem about traffic congestion")

# Run the agent (it will select and execute appropriate tools)
result = app.invoke(state)

# Get the agent's response
print(result.get_last_message())
```

## 4. Understanding Tool Selection

The agent will:
1. **Initialize** - Load tools available to this user
2. **Select** - Use LLM to decide which tool to call (e.g., "extract_problem_details")
3. **Execute** - Run the selected tool
4. **Handle Result** - Check if confirmation needed, handle errors
5. **Output** - Generate response for user

You can see which tool was selected in the trace:
```python
trace = state.cognitive.trace.steps
for step in trace:
    if step.step_type == "tool_selection":
        print(f"Selected tool: {step.data['selected_tool']}")
    if step.step_type == "tool_execution":
        print(f"Executed tool: {step.node}")
```

## 5. Restrict Tools for Specific Users

```python
config = get_tool_configuration()

# Only allow listing and viewing, no creation
config.configure_user_tools(
    user_id="readonly@company.com",
    tool_names=[
        "list_problems",
        "get_context_details",
        "set_active_context",
    ]
)
```

## 6. Check Available Tools

```python
from app.tools.tool_registry import get_tool_registry

registry = get_tool_registry()

# Get all available tools
all_tools = registry.list_tool_names()
print(f"Available tools: {all_tools}")

# Get tools for a specific user
user_tools = registry.get_user_allowed_tools("user@company.com")
print(f"User tools: {list(user_tools.keys())}")

# Get statistics
stats = registry.get_stats()
print(f"Total tools: {stats['total_tools']}")
print(f"Tools by category: {stats['tools_by_category']}")
```

## 7. Adding Custom Tools

Define your tool:
```python
from app.tools.tool_schema import ToolDefinition, ToolParameter, ToolCategory

custom_tool = ToolDefinition(
    name="my_analysis_tool",
    description="Analyzes problem data",
    category=ToolCategory.UTILITY,
    parameters=[
        ToolParameter(
            name="problem_id",
            description="ID of problem to analyze",
            type="string",
            required=True,
        )
    ],
)
```

Register it:
```python
from app.tools.tool_registry import get_tool_registry

registry = get_tool_registry()
registry.register_tool(custom_tool)
```

Implement the executor in `app/agent/nodes/tool_executor.py`:
```python
def execute_my_analysis_tool(state: AgentState, problem_id: str, **kwargs) -> dict:
    # Your implementation
    result = perform_analysis(problem_id)
    return result
```

Add to the dispatcher in `get_tool_executor()`:
```python
executors: Dict[str, Callable] = {
    # ...
    "my_analysis_tool": execute_my_analysis_tool,
}
```

## Common Patterns

### View Available Options
```python
# List all problems
state.cognitive.selected_tool = "list_problems"
result = app.invoke(state)
```

### Switch Context
```python
# Switch to working with a specific problem
state.cognitive.selected_tool = "set_active_context"
state.cognitive.tool_arguments = {
    "context_type": "problem",
    "context_id": "problem_123",
}
result = app.invoke(state)
```

### Create New Item
```python
# Extract information first
state.cognitive.selected_tool = "extract_problem_details"
state.cognitive.tool_arguments = {
    "user_input": "Traffic congestion in downtown area..."
}
result = app.invoke(state)

# Then create after user confirms
state.cognitive.selected_tool = "create_problem"
state.cognitive.tool_arguments = {
    "problem_title": "Urban Traffic Congestion",
    "problem_description": "...",
    "objectives": ["Reduce commute time", "Improve air quality"],
}
result = app.invoke(state)
```

## Monitoring and Debugging

### Check What Tool Was Selected
```python
print(f"Selected tool: {state.cognitive.selected_tool}")
print(f"Tool arguments: {state.cognitive.tool_arguments}")
print(f"Tool result: {state.cognitive.tool_result}")
```

### View Tool Execution Trace
```python
for step in state.cognitive.trace.steps:
    print(f"{step.timestamp} | {step.step_type} | {step.node} | {step.data}")
```

### Check Available Tools for User
```python
from app.tools.tool_config import get_tool_configuration

config = get_tool_configuration()
tools = config.get_user_tools("user@company.com")
print(f"User can access: {tools}")
```

## Differences from Old System

| Aspect | Old System | New System |
|--------|-----------|-----------|
| Routing | Hardcoded in intent node | LLM-driven tool selection |
| Workflows | Separate subgraphs | Tools with standardized interface |
| Extensibility | Add subgraph + node | Add tool definition + executor |
| Access Control | None | User-based restrictions |
| Code Reuse | Limited | High (shared tool framework) |
| Testing | Workflow-specific | Tool-specific |

## Troubleshooting

**Agent not selecting tools:**
- Verify `initialize_tools()` was called
- Check `state.user_id` is set
- Check logs for LLM reasoning

**Tool returns error:**
- Check tool arguments match schema
- Verify context requirements (e.g., active problem for proposals)
- Check backend/API connectivity

**Permission denied:**
- User may not have access to that tool
- Call `config.get_user_tools(user_id)` to check
- Use `config.configure_user_tools()` to grant access

For more details, see [AGENTIC_REFACTORING.md](./AGENTIC_REFACTORING.md)
