import os

GENERAL_ERROR_MESSAGE = "Error: something went wrong while processing your request."

# ---------------------------------------------------------------------------
# STARTUP VALIDATION
# ---------------------------------------------------------------------------
# Config the app cannot function without. Missing any of these currently
# fails silently deep inside a request (e.g. BACKEND_URL=None produces a URL
# like "Nonetenant/problems" that only errors when a tool actually runs).
# Checked once at process startup instead, so misconfiguration is caught
# immediately with a clear message rather than surfacing as a confusing
# runtime error to whichever user happens to trigger it first.
REQUIRED_ENV_VARS = ["BACKEND_URL", "ANTHROPIC_API_KEY"]


def validate_environment() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. Set them (e.g. in .env) before starting the app."
        )


SYSTEM_DESCRIPTION = """
# General description
The system supports analysis and decision-making for overtourism and mobility problems,
through a structured hierarchy of Problems, Proposals, and Scenarios.

# Core concepts

- **Problem**: a critical situation or phenomenon to be analyzed or managed (e.g., overtourism,
  extreme events, unregistered tourism), which requires data- and model-based decision support.
- **Proposal**: a possible strategy to address a problem. A proposal may include multiple scenarios,
  each exploring different parameter configurations.
- **Scenario**: a simulation that explores the consequences of changes in a model's parameters,
  useful for evaluating and comparing alternative strategies.

# Typical workflows

1. **Explore**: call list_available_scenarios → get_context_details → analyze_scenario_results
2. **Create a proposal**: set a problem context → extract_proposal_details → confirm → create_proposal
3. **Create a scenario**: set a proposal context → extract_scenario_details → confirm → create_scenario

"""

# ---------------------------------------------------------------------------
# GLOSSARY
# ---------------------------------------------------------------------------
# Each entry: term -> {definition, aliases, related_terms}
# The agent can query this via the `lookup_glossary` tool.

GLOSSARY: dict = {
    "problem": {
        "definition": (
            "A critical situation or phenomenon to be analyzed or managed within the platform "
            "(e.g., overtourism, extreme weather events, unregistered tourism). "
            "A Problem is the top-level concept: it owns one or more Proposals."
        ),
        "aliases": ["issue", "challenge", "problematic", "problema", "ambit", "ambito"],
        "related_terms": ["proposal", "scenario"],
        "examples": [
            "Overtourism in the historic centre",
            "Mobility congestion during peak season",
        ],
    },
    "proposal": {
        "definition": (
            "A possible strategy or intervention designed to address a specific Problem. "
            "A Proposal groups one or more Scenarios that explore different parameter configurations "
            "for that strategy. Each Proposal belongs to exactly one Problem."
        ),
        "aliases": ["strategy", "intervention", "solution", "proposta"],
        "related_terms": ["problem", "scenario"],
        "examples": ["Introduce visitor caps", "Promote off-peak mobility incentives"],
    },
    "scenario": {
        "definition": (
            "A simulation run that explores the consequences of a specific set of parameter changes "
            "within a Proposal. Scenarios are used to evaluate and compare alternative configurations "
            "of the same strategy. Each Scenario belongs to exactly one Proposal."
        ),
        "aliases": ["simulation", "run", "configuration", "scenario"],
        "related_terms": ["proposal", "problem", "evaluation"],
        "examples": [
            "Visitor cap at 500/day",
            "Visitor cap at 1000/day with shuttle service",
        ],
    },
    "evaluation": {
        "definition": (
            "The computed output data associated with a Scenario after a simulation run. "
            "Contains KPIs, metrics, and model outputs that allow comparing Scenarios."
        ),
        "aliases": ["result", "output", "kpi", "metrics", "valutazione"],
        "related_terms": ["scenario"],
        "examples": ["Congestion index reduction by 30%", "Visitor satisfaction score"],
    },
    "overtourism": {
        "definition": (
            "A phenomenon where the number of tourists visiting a destination exceeds its carrying "
            "capacity, causing negative impacts on residents, infrastructure, and the environment."
        ),
        "aliases": ["over-tourism", "mass tourism", "turismo eccessivo"],
        "related_terms": ["problem", "mobility", "visitor cap"],
        "examples": [],
    },
    "digital twin": {
        "definition": (
            "A virtual replica of a physical destination (city, region, attraction) used to simulate "
            "the effects of management decisions before implementing them in the real world. "
            "This platform is built around the digital twin concept."
        ),
        "aliases": ["DT", "digital model", "gemello digitale"],
        "related_terms": ["scenario", "simulation"],
        "examples": [],
    },
    "tenant": {
        "definition": (
            "An isolated organisational unit within the platform, typically representing a destination "
            "or municipality (e.g., 'molveno'). All data (problems, proposals, scenarios) is scoped "
            "to a tenant."
        ),
        "aliases": ["destination", "municipality", "organisation"],
        "related_terms": ["problem", "proposal", "scenario"],
        "examples": ["molveno"],
    },
    "constraint capacity": {
        "definition": (
            "The maximum acceptable value for a specific constraint before it is considered "
            "violated. A constraint capacity may refer to the number of visitors, parked cars, "
            "accommodation occupancy, restaurant demand, beach attendance, or any other resource "
            "or indicator used in the simulation."
        ),
        "aliases": [
            "capacity",
            "constraint threshold",
            "limit",
            "maximum capacity",
            "capacità di carico",
        ],
        "related_terms": ["constraint", "sustainability", "overtourism"],
        "examples": [
            "Maximum number of visitors in the historic centre.",
            "Maximum parking occupancy.",
            "Maximum beach attendance.",
        ],
    },
    "sustainability": {
        "definition": (
            "A measure of how often one or more constraints remain within their respective "
            "capacity limits during a simulation. It is expressed as the proportion of time "
            "or simulation outcomes in which the selected constraint (or all selected constraints) "
            "are not exceeded. A higher sustainability value indicates that capacity limits are "
            "respected more consistently."
        ),
        "aliases": [
            "sustainability index",
            "constraint compliance",
            "capacity compliance",
            "sustainability score",
            "sostenibilità",
        ],
        "related_terms": [
            "constraint capacity",
            "evaluation",
            "scenario",
            "uncertainty",
        ],
        "examples": [
            "A parking sustainability of 0.92 means the parking capacity is respected in 92% of the simulation.",
            "An overall sustainability of 0.81 means all considered constraints are simultaneously respected in 81% of the simulation.",
        ],
    },
    "uncertainty": {
        "definition": (
            "A measure of the confidence associated with a prediction or simulation result. "
            "Uncertainty reflects the expected reliability of the model output and arises from "
            "(i) assumptions about people behaviour and other tourism-related processes, and "
            "(ii) approximations introduced by the statistical and computational models. "
        ),
        "aliases": [
            "confidence",
            "confidence level",
            "prediction uncertainty",
            "model uncertainty",
            "forecast uncertainty",
            "uncertainty band",
            "incertezza",
        ],
        "related_terms": [
            "evaluation",
            "scenario",
            "prediction",
            "simulation",
        ],
        "examples": [],
    },
}
