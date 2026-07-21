# DIGITAL TWIN AGENT

This projects aims contains the first prototype of an Agentic AI for the Digital Twin project.

## Core idea

Model the system as a separate service exposing APIs that can be called both from a UX (e.g, webpage) or programmatically.
The Agents expoits ReAct (Reasoning + Acting) — from the 2022 paper "ReAct: Synergizing Reasoning and Acting in Language Models" (Yao et al.) 


### Getting started

In order to run this project you need first to setup the working virtual environment doing

```
uv venv
source .venv/bin/activate
uv sync --dev
```

Then you can run the agentic system with the following command 

You can run the agentic system as a service with the following command

```
uvicorn app.main:app --reload --port 9000
```

A different port can be used, just change it so that it does not conflic with other services.

Additionally you will need

1) [overtourism backend](https://github.com/fbk-most/overtourism)
2) [overtourism-fronted](https://github.com/fbk-most/overtourism-frontend)



# TO FIX LATER

1) Set up CORS correcly
2) Everything lives in process memory (_STATE_STORE, _LOCKS (memory.py), _queues, _results) and sessions are never cleaned up unless the client explicitly calls /agent/reset. Implement proper saving + TTL-based eviction.
Also, dump_to_file writes the entire state to disk on every single turn (logs/state_<id>.json), synchronously, on a relative logs/ path with no rotation. That's an I/O bottleneck under load and an unbounded-disk-growth risk. error_recovery_node does the same to logs/errors.txt.
4) The SSE stream has no timeout or heartbeat. queue.get() blocks forever if a session never finishes; most reverse proxies/load balancers will silently kill idle connections without periodic keepalive pings, and a stuck session ties up a thread forever.
5) No /health or /ready endpoint for orchestration probes.

# TODO:
- pass tenant and token to all endpoints
- feedback as post
- passare dati più strutturati per l'analisi delle differenze, parlare degli scenari
- evitare allucinazioni su numero istanze (sandbox ignorato o scenario base ignorato)
- spiegare meglio come effettuare confronto