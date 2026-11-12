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
