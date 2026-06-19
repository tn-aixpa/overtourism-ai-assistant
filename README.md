# DIGITAL TWIN AGENT

This projects aims contains the first prototype of an Agentic AI for the Digital Twin project.

## Core idea

Model the system as a separate service exposing APIs that can be called both from a UX (e.g, webpage) or programmatically.

The system is a context-aware, stateful, multi-node agent with explicit routing. In this way each node has clear boundaries and responsibilities.

## Usage

### Requirements

In order to run this project you need first to active

1) ollama server
2) overtourism backend

To install the ollama server, please follow [this](https://github.com/ollama/ollama?tab=readme-ov-file) guide.
Onece installed use 

```
ollama pull mistral
```

To run the backend server please

### Production
You can run the agentic system as a service with the following command

```
LOCAL=true uvicorn app.main:app --reload --port 9000
```

A different port can be used, just change it so that it does not conflic with overtourism, ollama or other services.
Set LOCAL to true for testing on local machine. LOCAL=false for coder.

### Demo

A UX is implemented for demo proposal (later this can be expanded into a production front-end).
To run it use the following:

```
cd chatbot-fronted
npm start
```

On the first run, before ```npm start``` you need to use
```
npm install
```

Refer to chatbot-fronted README for more details.


## Open points and future improvements

- Dialog flexibility
    - Fixed conversation structure (pro: stable and predictable, cons: might feel unnatural)
    - Fixed messages (e.g. for confirmation). Addding variablity might increase latency.
- Error recovery might be improved with retries logic, especially for scenario
- stardard data format and language (to prevent errors in computations) + finetuning (both for computations and for synonims)
- parallelize operations (different expers or simulations)
- design token-budget-aware compression for context
