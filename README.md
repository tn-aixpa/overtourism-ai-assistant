# DIGITAL TWIN AGENT

This projects aims at collecting useful information for the development of a first prototype of an Agentic AI for the Digital Twin project.

It will also contain the prototype, for now there is only a basic structure.

## Usage

You can run the agentic system as a service with the following command

```
uvicorn app.main:app --reload --port 9000
```

A different port can be used, just change it so that it does not conflic with overtourism, ollama or other services.

## Core idea

Model the system as a separate service exposing APIs that can be called both from a UX (e.g, webpage) or programattically.

The system will be a stateful, multi-node agent with explicit routing.

The LLM does not directly run actions, but rather
- Interprets intent
- Updates structured state
- Chooses which node should run next


## Structure

User  
&nbsp;&nbsp;↓  
Intent & Context Interpreter (LLM)  
&nbsp;&nbsp;↓  
Router (LangGraph conditional edges)  
&nbsp;&nbsp;↓  
[Action Nodes]  
&nbsp;&nbsp;├── Simulation Interaction  
&nbsp;&nbsp;├── Simulation Comparison  
&nbsp;&nbsp;├── Simulation Creation (multi-step)  
&nbsp;&nbsp;└── *... possible other nodes*

Current graph

![graph](Diagram.png)

## Agent frameworks vs custom build

Custom build agentic systems are recommanded when: 
- You need strict data control (GDPR, audits)
- You want transparent logs & reasoning
- You're integrating deeply with internal systems
- You want long-term maintainability

However, framworks have several advantages:
- They are faster to implement and better during first experimental phases
- They are recommended in case of multi-agent orchestration
- No need to maintain infra

The hidden cost of agent frameworks are:
- hide state transitions
- introduce non-determinism
- change APIs frequently

# interact_simulation pipeline

User question → Expert applicability check (per expert) → Expert answers (parallel, independent) → Answer merger → Final response

Each expert:
- Sees the same data
- Has a clearly defined scope
- Can explicitly say "not applicable"

Example experts:
- Data Scientist
    - Statistics
    - Trends
    - Anomalies
    - Correlations

- Mobility Expert
    - Traffic flow
    - Congestion
    - Travel times
    - Mode choice

- Environment Expert
    - Emissions
    - Pollution
    - Energy consumption
    - Sustainability indicators

## Useful material

Links:
- https://medium.com/@tahirbalarabe2/%EF%B8%8Flangchain-vs-langgraph-a-comparative-analysis-ce7749a80d9c
- https://docs.langchain.com/oss/python/langgraph/agentic-rag
- https://github.com/langchain-ai/langgraph?tab=readme-ov-file
- https://medium.com/@lorevanoudenhove/how-to-build-ai-agents-with-langgraph-a-step-by-step-guide-5d84d9c7e832
- https://learn.deeplearning.ai/courses/ai-agents-in-langgraph/lesson/qyrpc/introduction


Considering following this course:
- https://academy.langchain.com/courses/intro-to-langgraph

## TODO

- Implement nodes code
- Decide how to deal with memory in each node
    - Simple version: memory stored in LangGraph’s state;
    - Improved version: LangChain Memory objects (e.g. ConversationBufferMemory).
    - Decide what need to be in long and short term memory and the scope of memory: per session, per simulation, or global for all users.
- Error recovery might be improved with retries logic, especially for simulations
- Uniform LLM usage
- Allow multiple simulations, not only two

PROBLEMS:
- test with real data
- stardard data format (to prevent errors in computations) + finetuning (both for computations and for synonims)
- mixed language