GENERAL_ERROR_MESSAGE = "Error: something went wrong while processing your request."

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

1. **Explore**: call list_available_scenarios → get_context_details → interact_with_context
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
        "aliases": ["issue", "challenge", "problematic", "problema"],
        "related_terms": ["proposal", "scenario"],
        "examples": ["Overtourism in the historic centre", "Mobility congestion during peak season"],
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
        "examples": ["Visitor cap at 500/day", "Visitor cap at 1000/day with shuttle service"],
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
    "carrying capacity": {
        "definition": (
            "The maximum number of visitors a destination can accommodate without degrading the "
            "experience for tourists or residents, or causing environmental damage."
        ),
        "aliases": ["visitor capacity", "max visitors", "capacità di carico"],
        "related_terms": ["overtourism", "visitor cap"],
        "examples": [],
    },
}