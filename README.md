# AI ASSISTANT

This project contains the AI Assistant developed to interact
with our overtourism management platform.
We develop this repository in the context of our R&D
activities at [Fondazione Bruno Kessler](https://www.fbk.eu/en/).

## Core idea

Model the system as a separate service exposing APIs that can be called both from a UX (e.g, webpage) or programmatically.
The Agents expoits ReAct (Reasoning + Acting) — from the 2022 paper "ReAct: Synergizing Reasoning and Acting in Language Models" (Yao et al.) 


## Getting started

## Getting Started

The code is written in Python. We recommend using [uv](https://astral.sh/uv)
for managing the Python version, the virtual environment, and the
dependencies. Please, refer to `uv` documentation regarding how to
install it for your operating system.

Once `uv` is installed, use these commands:

```bash
git clone git@github.com:fbk-most/digital-twin-agent.git
cd digital-twin-agent
uv venv
source .venv/bin/activate
uv sync --dev
```

In order to run this project you need first to setup API KEYS and
links in `run.sh` then use this script to run the code.

# Dependencies

You will additioanlly need these repos running:

1) [overtourism backend](https://github.com/fbk-most/overtourism)
2) [overtourism-fronted](https://github.com/fbk-most/overtourism-frontend)


## Tests

There are 297 unit tests covering the pure-logic parts of the codebase — no live
Anthropic/backend calls are made; HTTP and LLM calls are mocked.
Other 9 unit test cover Anthropic calls - these are skipped by default.

To run all the tests use

```bash
pytest
```

### Running the test on Anthropic calls

`test_anthropic_routing.py` makes *real* Anthropic API calls and checks
whether Claude actually picks the expected tool for realistic user
messages. Non-deterministic and billed, so it's **skipped by default**
and excluded from the coverage table above on purpose.

They're gated behind `ANTHROPIC_API_KEY_TEST` (deliberately a different
variable from `ANTHROPIC_API_KEY`, which `conftest.py` sets to a fake string
for the rest of the suite) so a normal `pytest` run never accidentally hits
the live API or spends money:

```bash
ANTHROPIC_API_KEY_TEST=sk-ant-your-real-key pytest tests/test_anthropic_routing.py -v
```

Notes:
- Each full run makes ~13 real API calls (6 golden cases + 2 negative cases
  + 5 repeat-stability runs) — budget for that.
- A single failure doesn't necessarily mean the code is broken; 
  failures might be caused by unavailable service or internet.
  Additionally, ambiguous   phrasing can legitimately get different tool choices.
  Treat `TestRepeatStability` (which requires an 80% pass rate over 5 runs on one
  unambiguous case) as the more trustworthy "did I break the prompt"
  signal, and use the golden/negative cases as a first look, not a hard gate.


### What's covered

| File | Covers |
|---|---|
| `test_state.py` | `AgentState`, `ConversationBuffer`, `TraceBuffer`, `CognitiveState` — message history, trace trimming, `generated_by` provider labeling, JSON serialization |
| `test_common_utils.py` | Prompt-size guards (`condense_for_matching`, `truncate_for_prompt`, `enforce_prompt_budget`, `build_prior_results_block`), the auth-token `ContextVar`, custom exceptions |
| `test_tool_schema.py` | `ToolDefinition.to_tool_description()` — LLM tool-calling schema generation |
| `test_tool_registry.py` | `ToolRegistry` CRUD, enable/disable, allowlist filtering, global singleton |
| `test_waiting_node.py` | Confirmation/cancellation natural-language parsing (`_is_confirmation`/`_is_cancellation`), confirmation recap text, the full `wait_user_input_node` state machine |
| `test_tool_executor.py` | Argument validation, missing-parameter detection, parent/target ID auto-resolution, tool-result trimming/eviction, glossary lookup, and the end-to-end `tool_executor_node` flow (confirmation gate, error routing, result-key collisions) |
| `test_general_node.py` | `safe()` error-wrapping, `error_recovery_node`, `_build_messages_from_tool_result` (every tool-result → user-message case), `generate_output_message_node` flow |
| `test_memory.py` | Session state load/save/delete, per-session locks |
| `test_events.py` | SSE event bus publish/consume, final-result handoff, session cleanup |
| `test_backend_tools.py` | All HTTP wrappers and CRUD tools (`requests` mocked) — auth headers, create/edit "preserve untouched fields" logic, delete-with-name-lookup fallback, scenario evaluation-data enrichment |
| `test_reasoner_routing.py` | `initialize_tools` and `react_reasoner_node` routing logic — enabled-tools allowlist enforcement, malformed/hallucinated LLM responses, markdown-fenced JSON, the max-react-steps safety valve. `react_step` is mocked, so no real Anthropic calls. |
