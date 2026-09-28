"""
Tool schema and interface definitions for the agentic system.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List, Set, FrozenSet, Iterable, Union
from enum import Enum


class ToolCategory(str, Enum):
    DATA_RETRIEVAL = "data_retrieval"
    PROBLEM_MANAGEMENT = "problem_management"
    PROPOSAL_MANAGEMENT = "proposal_management"
    SCENARIO_MANAGEMENT = "scenario_management"
    INTERACTION = "interaction"
    UTILITY = "utility"


class UserRole(str, Enum):
    """Coarse-grained roles a session can be authenticated as.

    Attached to a ToolDefinition via `allowed_roles` to say WHO may select
    that tool. Deliberately separate from AgentTier/agent_tier above:
    agent_tier governs the RESPONSE style/consent once a tool has already
    been chosen and run; allowed_roles instead governs whether the tool is
    selectable in the first place for a given caller (see
    ToolDefinition.is_allowed_for and ToolRegistry.get_context_tools). The
    two are independent — a viewer-only, executor-tier tool and an
    admin-only, exploitative-tier tool are both perfectly valid.
    """

    ADMIN = "admin"
    STANDARD = "standard"
    VIEWER = "viewer"


class SessionMode(str, Enum):
    """Which surface the current turn is running under.

    Attached to a ToolDefinition via `allowed_modes` to say WHERE that
    tool may be selected from:

    - STANDALONE: the normal, user-facing chat (AgentState.integrated_mode
      is False). The only mode that can render widget/UI tools.
    - INTERNAL: the chat embedded inside another internal product surface
      (AgentState.integrated_mode is True) — the host page doesn't support
      Claude's own widget rendering, which is why widget tools declare
      allowed_modes={STANDALONE} rather than being available here too.
    - SYSTEM: a stateless, backend-triggered pipeline invoked directly via
      execute_selected_tool with a throwaway AgentState (see
      app.api.routes.run_selected_tools, the /agent/tool endpoint), never
      reached through the normal ReAct loop.

    Like UserRole, this is orthogonal to agent_tier and to the multi-level
    topic router (app.agent.nodes.router / route_groups.py): the router
    decides which tools are on-topic for THIS conversation turn once a
    tool is already reachable; SessionMode decides whether it's reachable
    from this surface at all.
    """

    STANDALONE = "standalone"
    INTERNAL = "internal"
    SYSTEM = "system"


ALL_USER_ROLES: FrozenSet[str] = frozenset(role.value for role in UserRole)
ALL_SESSION_MODES: FrozenSet[str] = frozenset(mode.value for mode in SessionMode)

# What a ToolDefinition's allowed_roles / allowed_modes constructor
# argument may be given as — None (unrestricted), a single value, or any
# iterable of values (str or the corresponding Enum members).
AccessSpec = Union[None, str, Enum, Iterable[Union[str, Enum]]]


def _normalize_access_set(
    value: AccessSpec, valid_values: FrozenSet[str], field_name: str
) -> Optional[FrozenSet[str]]:
    """Normalize an `allowed_roles`/`allowed_modes` constructor argument
    into either None (unrestricted — nobody is excluded on this axis) or a
    non-empty frozenset of plain strings.

    Accepts a single string/Enum member or any iterable of them, so a
    tool definition can write `allowed_roles="admin"` or
    `allowed_roles=[UserRole.ADMIN, UserRole.STANDARD]` interchangeably.
    Raises ValueError — at tool-registration time, not at filtering time —
    for an empty iterable (would silently mean "nobody may ever select
    this tool", almost certainly not what was intended) or any value
    outside `valid_values` (catches a typo like "amdin" immediately
    instead of it quietly locking every role out).
    """
    if value is None:
        return None
    if isinstance(value, (str, Enum)):
        value = [value]
    normalized = frozenset(v.value if isinstance(v, Enum) else v for v in value)
    if not normalized:
        raise ValueError(
            f"{field_name} must be None or non-empty (got an empty "
            f"collection) — an empty set would silently disallow every "
            f"caller. Use None instead to leave this axis unrestricted."
        )
    unknown = normalized - valid_values
    if unknown:
        raise ValueError(
            f"{field_name} contains unknown value(s) {sorted(unknown)}; "
            f"must be a subset of {sorted(valid_values)}"
        )
    return normalized


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

    # ---- Selectability gating: WHO / WHERE, orthogonal to agent_tier's
    # WHAT-happens-once-selected (see UserRole/SessionMode docstrings
    # above for the full rationale). Both default to None = unrestricted,
    # matching the "open by default" posture every tool had before these
    # fields existed, so adding them to ToolDefinition never silently
    # narrows an existing tool's audience — a tool only becomes gated once
    # someone deliberately sets one of these.
    #
    # Accepts None, a single role/mode (str or enum member), or any
    # iterable of them — normalized to a frozenset of strings by
    # __post_init__ below. Checked together by is_allowed_for(), and
    # enforced in two places: ToolRegistry.get_context_tools (so a
    # disallowed tool never appears as a selectable choice for the ReAct
    # reasoner in the first place) and tool_executor.execute_selected_tool
    # (so a direct/explicit invocation — e.g. the /agent/tool pipeline —
    # can't bypass the same rule just because it skips the registry
    # filtering step).
    allowed_roles: AccessSpec = None
    allowed_modes: AccessSpec = None

    def __post_init__(self) -> None:
        self.allowed_roles = _normalize_access_set(
            self.allowed_roles, ALL_USER_ROLES, "allowed_roles"
        )
        self.allowed_modes = _normalize_access_set(
            self.allowed_modes, ALL_SESSION_MODES, "allowed_modes"
        )

    def is_allowed_for(self, role: Optional[str], mode: Optional[str]) -> bool:
        """Whether a caller authenticated as `role`, running under session
        `mode`, may select/execute this tool.

        Each axis is independent and both must pass. An axis that was
        never restricted (allowed_roles/allowed_modes is None) never
        excludes anyone. An axis that WAS restricted excludes an
        unresolved caller (role/mode passed as None) by default —
        deliberately fail-closed, since an unresolved role/mode usually
        means the caller/session never had one assigned rather than that
        it should be trusted with everything.
        """
        if self.allowed_roles is not None:
            if role is None or role not in self.allowed_roles:
                return False
        if self.allowed_modes is not None:
            if mode is None or mode not in self.allowed_modes:
                return False
        return True

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
