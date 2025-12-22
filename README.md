# DIGITAL TWIN AGENT

This projects aims at collecting useful information for the development of a first prototype of an Agentic AI for the Digital Twin project.

It will also contain the prototype, for now there is only a basic structure.

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

## Choice motivation

LangX vs custom build.

Still using ollama run locally.

## Useful material

Links:
- https://medium.com/@tahirbalarabe2/%EF%B8%8Flangchain-vs-langgraph-a-comparative-analysis-ce7749a80d9c
- https://docs.langchain.com/oss/python/langgraph/agentic-rag
- https://github.com/langchain-ai/langgraph?tab=readme-ov-file
- https://medium.com/@lorevanoudenhove/how-to-build-ai-agents-with-langgraph-a-step-by-step-guide-5d84d9c7e832


Considering following this course:
- https://academy.langchain.com/courses/intro-to-langgraph

## TODO

- Implement node code
- Decide how to deal with memory in each node
    - Simple version: memory stored in LangGraph’s state;
    - Improved version: LangChain Memory objects (e.g. ConversationBufferMemory).
    - Decide what need to be in long and short term memory and the scope of memory: per session, per simulation, or global for all users.
- Error recovery might be improved with retries logic, especially for simulations