import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timedelta
from enum import StrEnum, Enum
import json

MAX_CONTEXT_WINDOW = 20
DEFAULT_REASONING_CONTEXT_SIZE = 8
# Safety cap on Thought/Action/Observation cycles within a single turn, so a
# reasoner that never emits "finish" (e.g. stuck bouncing between two tools)
# cannot loop forever. See react_reasoner_node in nodes/reasoner.py.
DEFAULT_MAX_REACT_STEPS = 8

# Agent tiers that require explicit, one-time user consent before a session
# may use them at all (see CognitiveState.has_valid_tier_consent). This is
# deliberately separate from CONFIRMATION_REQUIRED_TOOLS in tool_executor.py:
# that one confirms specific data about to be submitted, every single time;
# this one confirms permission to use a *capability*, rarely. Empty/absent
# tiers here are always allowed with no consent step.
TIERS_REQUIRING_CONSENT: Set[str] = {"exploitative"}
# How long a granted consent stays valid before we ask again. Wall-clock
# based (not turn-count based) so "ask again after a while" behaves the same
# whether the user comes back an hour or a week later, regardless of how
# many messages were exchanged in between.
TIER_CONSENT_TTL = timedelta(hours=24)


class AgentTier(StrEnum):
    """The four capability tiers, ordered lowest-license to highest.

    Orthogonal to routing (app.agent.nodes.router / route_groups.py, which
    decide which tools are SELECTABLE this turn): AgentTier instead decides
    the RESPONSE style/policy once a tool has actually been used (see
    ToolDefinition.agent_tier, tool_executor_node._bump_active_agent, and
    _reasoning_policy in answer_generation.py), and — for tiers in
    TIERS_REQUIRING_CONSENT — gates that tool behind one-time user consent.
    EXECUTOR is the baseline every turn starts at; a turn's active_agent is
    raised to the highest tier reached by any tool it actually calls.
    """

    EXECUTOR = "executor"
    OPERATIVE = "operative"
    METHODOLOGICAL = "methodological"
    EXPLOITATIVE = "exploitative"


@dataclass
class ConversationMessageBase:
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class UserMessage(ConversationMessageBase):
    role: str = field(default="user", init=False)


@dataclass
class AssistantMessage(ConversationMessageBase):
    role: str = field(default="assistant", init=False)
    generated_by: Optional[str] = None
    generated_by_agent: Optional[str] = None
    vote: Optional[str] = None
    comment: Optional[str] = None


ConversationMessage = (
    UserMessage | AssistantMessage
)  # kept as a type alias for existing annotations


@dataclass
class ConversationBuffer:
    messages: List[ConversationMessage] = field(default_factory=list)
    max_window_size: int = MAX_CONTEXT_WINDOW

    def add_message(self, message: ConversationMessage):
        self.messages.append(message)

    def get_last_n(self, n: Optional[int] = None) -> List[ConversationMessage]:
        n = n or self.max_window_size
        return self.messages[-n:]

    def get_context_window(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        """Returns last N messages formatted for LLM reasoning."""
        msgs = self.get_last_n(n)
        return [{"role": m.role, "content": m.content} for m in msgs]


@dataclass
class TraceStep:
    step_type: str
    node: str | None = None
    data: Optional[Dict[str, Any]] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TraceBuffer:
    steps: List[TraceStep] = field(default_factory=list)
    max_trace_size: int = 1000

    def add_step(self, step: TraceStep):
        self.steps.append(step)
        if len(self.steps) > self.max_trace_size:
            self.steps = self.steps[-self.max_trace_size :]

    def get_last_n(self, n: Optional[int] = None) -> List[TraceStep]:
        n = n or self.max_trace_size
        return self.steps[-n:]


@dataclass
class ReActStep:
    """One Thought -> Action -> Observation cycle produced by the ReAct
    reasoner during a single turn.

    The scratchpad (a list of these) is the working memory of the loop: it
    is fed back into the reasoning prompt on every iteration so the model
    can decide its next action based on what it has already seen, and it is
    reset to empty at the start of every new user turn (see
    `initialize_tools`). It is NOT the same as `tool_results`, which is kept
    across the whole session as long-term memory.
    """

    thought: str = ""
    tool_name: Optional[str] = None
    tool_arguments: Dict[str, Any] = field(default_factory=dict)
    observation: Optional[Dict[str, Any]] = None
    # Key into cognitive.tool_results where the full observation is stored.
    observation_key: Optional[str] = None
    # Informational only (e.g. "awaiting_confirmation", "cancelled") — never
    # used for routing, just for tracing/debugging.
    status: Optional[str] = None


@dataclass
class CognitiveState:
    generation_pipeline: List[str] = field(default_factory=list)

    current_context: Dict[str, Any] = field(
        default_factory=lambda: {"problems": [], "proposals": [], "scenarios": []}
    )
    retrieved_context: Dict[str, Any] = field(default_factory=dict)

    # Object-level cache for get_context_details / analyze_scenario_results,
    # keyed like the "retrieved" dict (e.g. "scenarios <id>") so entries can
    # be looked up, merged, and evicted by the same key across both tools.
    # A scenario's cached entry may carry an "evaluation_data" field once
    # analyze_scenario_results has fetched it.
    #
    # Scope is deliberately "current topic", not "whole session": entries
    # are dropped as soon as the topic moves on (see prune_context_cache,
    # called whenever current_context is re-resolved by get_context_ids) and
    # as soon as the underlying object is edited/deleted (see
    # invalidate_cached_object). This avoids both the staleness risk of a
    # cache that outlives the topic and the near-zero benefit of a cache
    # that resets every turn (a single turn already only fetches each
    # object once).
    context_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Raw time-series payloads already fetched from get-variation-data this
    # session, keyed by the exact backend request (see
    # app.tools.executors.indexes._fetch_plot). Re-rendering the same data
    # as a different chart type (line -> bar) sends the backend a
    # byte-identical request, which it answers with an empty payload; serving
    # the earlier response avoids that second call. Bounded + TTL'd there.
    plot_data_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    trace: TraceBuffer = field(default_factory=TraceBuffer)

    error_details: str = ""

    messages_to_include: List[str] = field(default_factory=list)

    known_tools: List[str] = field(default_factory=list)
    enabled_tools: List[str] = field(default_factory=list)

    # "Pending action" slot: whichever tool the reasoner most recently
    # decided to call. Populated by react_reasoner_node, consumed by
    # tool_executor_node. Also doubles as the "tool awaiting confirmation"
    # reference while waiting_for is set.
    selected_tool: Optional[str] = None
    tool_arguments: Dict[str, Any] = field(default_factory=dict)
    # The reasoning text that justified `selected_tool`, staged here by
    # react_reasoner_node until tool_executor_node turns it into a
    # ReActStep on the scratchpad.
    pending_thought: str = ""

    # Thought/Action/Observation history for the turn currently in progress.
    # Reset to [] at the start of every new user turn.
    scratchpad: List[ReActStep] = field(default_factory=list)
    max_react_steps: int = DEFAULT_MAX_REACT_STEPS

    tool_result: Optional[Dict[str, Any]] = None
    # Long-term memory of every tool result produced this session (kept
    # across turns so the reasoner can see what already ran and avoid
    # redundant calls). Trimmed by tool_executor._trim_tool_results.
    tool_results: Dict[str, Any] = field(default_factory=dict)
    # The most recent tool call that FAILED: {"tool_name", "arguments",
    # "error"}. Survives across turns (unlike the scratchpad, which is
    # reset every turn) so a later "riprova"/"retry" can re-issue exactly the
    # same call. Cleared when that same tool later succeeds.
    last_failed_action: Optional[Dict[str, Any]] = None
    tool_confirmation_needed: bool = False
    # Set to True right after the user confirms a pending creation tool, so that
    # tool_executor knows to actually run it instead of pausing again.
    tool_confirmed: bool = False

    # The most recently created-and-evaluated temporary scenario (see
    # execute_create_new_temp_scenario), kept around so a later
    # create_new_scenario call can promote it to permanent. Cleared once
    # promoted (execute_create_new_scenario) or overwritten by the next
    # create_new_temp_scenario call.
    pending_temp_scenario: Optional[Dict[str, Any]] = None

    # Per-tier consent grants for this session (tier name -> when it was
    # granted). Persists across turns for the session's lifetime, unlike the
    # scratchpad; see has_valid_tier_consent for the TTL check.
    tier_consent: Dict[str, datetime] = field(default_factory=dict)
    # "Pending tier-access request" slot, set by whichever node is about to
    # enter/delegate into a gated tier without valid consent yet (today:
    # tool_executor_node, for a delegate_to_<tier> tool call; later, also
    # the top-level router when it wants to enter a gated tier directly).
    # Kept separate from `selected_tool` so a router-level request — which
    # may happen before any tool has been chosen — never collides with the
    # create/edit/delete confirmation flow, which keys off selected_tool.
    pending_tier_consent: Optional[str] = None
    # Node to resume at once the user grants consent. tool_executor_node
    # sets this to "tool_executor" (re-entering itself re-runs the gate,
    # which now passes); the router will set it to whatever node actually
    # starts that tier's reasoning loop once tiers exist as separate nodes.
    tier_consent_resume_goto: Optional[str] = None

    def has_valid_tier_consent(self, tier: str) -> bool:
        """Whether `tier` may be used without asking the user again right
        now. Tiers outside TIERS_REQUIRING_CONSENT are always allowed."""
        if tier not in TIERS_REQUIRING_CONSENT:
            return True
        granted_at = self.tier_consent.get(tier)
        return (
            granted_at is not None and (datetime.now() - granted_at) < TIER_CONSENT_TTL
        )

    def grant_tier_consent(self, tier: str) -> None:
        self.tier_consent[tier] = datetime.now()

    # ---- Multi-level topic routing ----------------------------------
    # Which top-level domain (see app.agent.nodes.router.ROUTE_GROUPS) the
    # session is currently reasoning in, and — for domains that have a
    # second level (LOCATION, INDEXES) — which sub-group within it.
    # Persists across turns exactly like tier_consent above: once resolved,
    # a session stays routed to the same domain until top_level_router_node
    # detects the user has actually changed topic, so an ongoing
    # conversation about e.g. proposals doesn't re-ask "which of the 4
    # areas do you mean?" on every single message.
    top_level_route: Optional[str] = None
    # A LIST, not a single value: a turn can legitimately resolve to more
    # than one sub-area at once (e.g. "quali problemi e scenari sono
    # disponibili?" -> ["problem", "scenario"]) — see
    # app.agent.nodes.router._apply_route / route_groups.resolve_allowed_tools,
    # which union each listed sub-group's tools/guidelines. None means "no
    # second_level resolved yet" (top_level either has no sub-levels, or
    # sub-level routing is still pending); never an empty list.
    second_level_route: Optional[List[str]] = None
    # Set by top_level_router_node while it is paused waiting for the user
    # to pick an option from an ambiguous routing prompt. "top" or
    # "second" — tells WAIT_USER_INPUT which menu (and matching logic) to
    # resume with. None the rest of the time.
    pending_route_clarification: Optional[str] = None
    # True while the turn is paused asking the user which territory to use
    # (see tool_executor_node's territory gate and waiting.py's
    # _handle_territory_wait). The tool that triggered the question stays in
    # selected_tool/tool_arguments and is resumed once a valid territory is
    # set.
    pending_territory_selection: bool = False

    def prune_context_cache(self) -> None:
        """Drop cached objects that are no longer part of current_context.

        Call this right after current_context is (re)resolved (i.e. in
        execute_get_context_ids). Keeps context_cache scoped to "what the
        user is currently talking about": an object stays cached across
        turns as long as the user keeps referring to it, but is evicted as
        soon as they move on to a different problem/proposal/scenario.
        """
        valid_keys = {
            f"{kind} {obj_id}"
            for kind in ("problems", "proposals", "scenarios")
            for obj_id in self.current_context.get(kind, [])
        }
        for key in list(self.context_cache):
            if key not in valid_keys:
                del self.context_cache[key]

    def invalidate_cached_object(self, kind: str, obj_id: str) -> None:
        """Evict a single cached object, e.g. right after it was edited or
        deleted, so a later get_context_details doesn't serve stale data."""
        self.context_cache.pop(f"{kind} {obj_id}", None)
        # The current turn's already-retrieved snapshot may also hold the
        # now-stale copy — drop it there too if present.
        retrieved = (
            self.retrieved_context.get("retrieved") if self.retrieved_context else None
        )
        if retrieved is not None:
            retrieved.pop(f"{kind} {obj_id}", None)

    def current_turn_result_keys(self) -> List[str]:
        """Ordered tool_results keys produced by the scratchpad of the turn
        currently in progress (i.e. this turn's observations only)."""
        return [
            step.observation_key for step in self.scratchpad if step.observation_key
        ]

    def _add_trace(
        self, step_type: str, node: str, data: Optional[Dict[str, Any]] = None
    ):
        self.trace.add_step(TraceStep(step_type=step_type, node=node, data=data))


@dataclass
class AgentState:
    # Orchestration
    session_id: str = ""
    user_id: str | None = None
    user_lang: str = "Italian"
    allowed_territories: List[str] = field(default_factory=list)
    territory: str = ""
    integrated_mode: bool = False
    integrated_context: Dict[str, Any] = field(default_factory=dict)
    # Coarse-grained role this session is authenticated as — "admin",
    # "multieditor", "editor", or "viewer" (see app.tools.tool_schema.UserRole). Kept
    # as a plain string rather than importing UserRole here, for the same
    # tools->agent circular-import reason agent_tier is a plain string on
    # ToolDefinition (see AgentTier's docstring below). Resolved once, from
    # the /auth/me response, when the session is first created (see
    # app.api.routes) and left
    # untouched for the rest of the session's lifetime — a role change
    # mid-session should start a new session, not silently reinterpret an
    # in-flight one. Consulted by ToolDefinition.allowed_roles via
    # ToolRegistry.get_context_tools (tool *selection*, in
    # initialize_tools) and again by execute_selected_tool (tool
    # *execution*, so a direct/explicit call — e.g. the /agent/tool
    # pipeline — can't bypass the same rule).
    user_role: str = "viewer"
    # Which surface this session is running under — "standalone",
    # "internal", or "system" (see app.tools.tool_schema.SessionMode).
    # Same plain-string rationale as user_role above. Derived once at
    # session creation from integrated_mode (True -> "internal", False ->
    # "standalone") for the two chat entry points, or set explicitly to
    # "system" for the stateless /agent/tool pipeline's throwaway state
    # (see app.api.routes) — that pipeline never sets integrated_mode at
    # all, so it needs its own explicit value rather than being derived.
    session_mode: str = "standalone"
    # Which capability tier this turn's response is generated under (see
    # AgentTier). Reset to the EXECUTOR baseline at the start of every
    # fresh turn (see initialize_tools), then raised at most, never
    # lowered, as tools actually run this turn (see
    # tool_executor_node._bump_active_agent and ToolDefinition.agent_tier)
    # — NOT persisted across turns, unlike top_level_route/second_level_
    # route or tier_consent on CognitiveState. Stamped onto the outgoing
    # message via add_assistant_message so callers can see which tier
    # answered.
    active_agent: AgentTier = AgentTier.EXECUTOR

    # Interface layer
    conversation: ConversationBuffer = field(default_factory=ConversationBuffer)
    assistant_action_data: Optional[List[Dict[str, Any]]] = None

    class WaitingFor(StrEnum):
        PROBLEM_INPUT = "PROBLEM_INPUT"
        PROBLEM_CONFIRMATION = "PROBLEM_CONFIRMATION"
        PROPOSAL_INPUT = "PROPOSAL_INPUT"
        PROPOSAL_CONFIRMATION = "PROPOSAL_CONFIRMATION"
        SCENARIO_INPUT = "SCENARIO_INPUT"
        SCENARIO_CONFIRMATION = "SCENARIO_CONFIRMATION"
        CONTEXT_INPUT = "CONTEXT_INPUT"
        # Asking whether the user consents to this session using a gated
        # agent tier at all (see TIERS_REQUIRING_CONSENT) — distinct from
        # *_CONFIRMATION above, which recap specific data about to be
        # submitted rather than asking about capability access.
        TIER_ACCESS_CONFIRMATION = "TIER_ACCESS_CONFIRMATION"
        # Waiting for the user to pick a domain/sub-area from an ambiguous
        # top-level or second-level routing prompt (see
        # app.agent.nodes.router.top_level_router_node).
        ROUTE_CLARIFICATION = "ROUTE_CLARIFICATION"
        # Waiting for the user to say which territory (one of
        # AgentState.allowed_territories) they want to work on, before a
        # territory-scoped tool (see ToolDefinition.requires_territory) can
        # run. The pending tool/arguments are kept and resumed afterwards.
        TERRITORY_SELECTION = "TERRITORY_SELECTION"

    waiting_for: Optional["AgentState.WaitingFor"] = None
    user_input: Optional[str] = None

    # Cognitive layer
    cognitive: CognitiveState = field(default_factory=CognitiveState)

    @property
    def last_node(self):
        if not self.cognitive.trace.steps:
            return None
        return self.cognitive.trace.steps[-1].node

    def add_trace(
        self,
        step_type: str,
        node: str | None = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.cognitive._add_trace(step_type=step_type, node=node, data=data)

    def add_user_message(self, content: str):
        self.conversation.add_message(UserMessage(content=content))

    def add_assistant_message(self, content: str):
        pipeline = self.cognitive.generation_pipeline

        def _provider_label(model_name: str) -> str:
            if model_name.startswith("claude"):
                return "anthropic"
            return f"{model_name}"

        labels = {_provider_label(m) for m in pipeline}

        if len(labels) == 0:
            generated_by = "unknown"
        elif len(labels) == 1:
            generated_by = labels.pop()
        else:
            generated_by = "mixed"

        self.conversation.add_message(
            AssistantMessage(
                content=content,
                generated_by=generated_by,
                generated_by_agent=str(self.active_agent),
            )
        )

    def get_last_user_message(self):
        for msg in reversed(self.conversation.messages):
            if isinstance(msg, UserMessage):
                return msg
        return None

    def get_last_message(self):
        if self.conversation.messages:
            return self.conversation.messages[-1]
        return None

    def get_reasoning_context(self, n: Optional[int] = DEFAULT_REASONING_CONTEXT_SIZE):
        return self.conversation.get_context_window(n)

    def _serialize(self, obj: Any):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, Exception):
            return str(obj)
        if isinstance(obj, set):
            return sorted(self._serialize(i) for i in obj)
        if isinstance(obj, list):
            return [self._serialize(i) for i in obj]
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {
                f.name: self._serialize(getattr(obj, f.name))
                for f in dataclasses.fields(obj)
            }
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return repr(obj)

    def dump_to_file(self, filepath: str):
        import os

        os.makedirs("logs", exist_ok=True)
        serialized = self._serialize(self.__dict__)

        # Keep interface widget payloads useful for debugging without
        # persisting their potentially large rendered data.
        actions = serialized.get("assistant_action_data")
        if isinstance(actions, list):
            serialized["assistant_action_data"] = [
                (
                    {
                        key: action[key]
                        for key in ("type", "widgetName")
                        if key in action
                    }
                    if isinstance(action, dict)
                    else action
                )
                for action in actions
            ]

        # Trace entries should retain their diagnostic metadata, but not
        # backend data payloads accidentally attached under retrieved* keys.
        def omit_retrieved_data(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: omit_retrieved_data(item)
                    for key, item in value.items()
                    if "retrieved" not in str(key).lower().replace("_", "")
                }
            if isinstance(value, list):
                return [omit_retrieved_data(item) for item in value]
            return value

        # Raw plot payloads are a pure runtime cache; keep only their keys.
        cog = serialized.get("cognitive", {})
        if isinstance(cog.get("plot_data_cache"), dict):
            cog["plot_data_cache"] = {k: "<omitted>" for k in cog["plot_data_cache"]}

        trace = cog.get("trace", {})
        for step in trace.get("steps", []):
            if isinstance(step, dict) and "data" in step:
                step["data"] = omit_retrieved_data(step["data"])

        # Write to a temp file and rename over the target, rather than
        # writing filepath directly: a plain open(filepath, "w") is
        # truncate-then-write, so any interruption mid-write (process
        # killed, disk full) — or, previously, two overlapping saves for
        # the same session_id racing on this same path (see _IN_FLIGHT in
        # app.agent.memory) — could leave a half-written/corrupt JSON file
        # on disk. os.replace is atomic on POSIX and Windows: readers only
        # ever see the fully-old or fully-new content, never a partial write.
        tmp_path = f"{filepath}.tmp-{os.getpid()}-{id(self)}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, filepath)
