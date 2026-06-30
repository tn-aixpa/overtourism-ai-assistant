# DIGITAL TWIN AGENT

This projects aims contains the first prototype of an Agentic AI for the Digital Twin project.

## Core idea

Model the system as a separate service exposing APIs that can be called both from a UX (e.g, webpage) or programmatically.

## Usage

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
2) ollama server (optional)

To install the ollama server, please follow [this](https://github.com/ollama/ollama?tab=readme-ov-file) guide.
Onece installed use 

```
ollama pull mistral
```

To run the backend server please

# TODO
3) Aggiungere creazione proposta
4) Aggiungere altri tool vuoti (disegno)
