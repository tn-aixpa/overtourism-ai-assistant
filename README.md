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

The `web_search` tool uses the configured LLM provider's native web search,
so it needs no separate search API key. It is available only in the
exploitative agent tier and requires the tier's user consent. Azure
deployments must support the Responses API web-search tool.

# Dependencies

You will additioanlly need these repos running:

1) [overtourism backend](https://github.com/fbk-most/overtourism)
2) [overtourism-fronted](https://github.com/fbk-most/overtourism-frontend)

## Agent configuration
 
The agent service (`digital-twin-agent`) is configured through environment
variables. Each one is read from the process environment, so it can be set with
`docker run -e`, an `environment:` entry in your compose file or orchestrator,
or, when starting the service with `run.sh`, as an export or in the `.env` file
that `run.sh` loads. A variable set in the environment takes precedence over
the same variable in `.env`.
 
| Variable | Default | Values | Description |
| --- | --- | --- | --- |
| `SAVE_CONVERSATION_LOGS` | `false` | `true` / `false` | Save conversations to `logs/`: the per-session `state_<session_id>.json` dump. When `false`, no conversation content is written to disk. Token-usage accounting (`logs/tokens_usage.csv`) is not affected. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Verbosity of the console log (case-insensitive). `INFO` shows progress messages; `DEBUG` adds payload-level detail such as backend response bodies, tool arguments and user replies. |
 
`SAVE_CONVERSATION_LOGS` also accepts `1`/`0`, `yes`/`no` and `on`/`off`.
An invalid `LOG_LEVEL` makes `run.sh` exit with an error; when the service is
started some other way (for example in Docker), it logs a warning and falls
back to `INFO`. An unrecognised `SAVE_CONVERSATION_LOGS` is treated as `false`.
 
The Docker image sets both defaults (`false` and `INFO`). Override them at run
time:
 
```bash
docker run -e SAVE_CONVERSATION_LOGS=true -e LOG_LEVEL=DEBUG ...
```
 
or when using `run.sh`:
 
```bash
SAVE_CONVERSATION_LOGS=true LOG_LEVEL=DEBUG ./run.sh
```
 
When `LOG_CONFIG_FILE` is set, the logging configuration file controls
handlers and formats; an explicit `LOG_LEVEL` still sets the verbosity.
 
## License
 
```text
SPDX-License-Identifier: Apache-2.0
```