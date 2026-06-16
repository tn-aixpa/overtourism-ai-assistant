import requests
from langchain.tools import tool
import logging
import json

from app.utils.data import parse_data, parse_editable_indexes
from app.config import BASE_SCENARIO_ID, BACKEND_URL

logger = logging.getLogger(__name__)

def _get_all_problems(tenant="molveno"):
    """Fetch all problems from the API."""
    url = f"{BACKEND_URL}{tenant}/problems"
    headers = {"accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def _get_all_proposals(tenant="molveno"):
    """Fetch all proposals from the API."""
    url = f"{BACKEND_URL}{tenant}/proposals"
    headers = {"accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def _get_all_scenarios(tenant="molveno"):
    """Fetch all scenarios from the API."""
    url = f"{BACKEND_URL}{tenant}/scenarios"
    headers = {"accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


# Expose as tools
get_all_problems = tool(_get_all_problems)
get_all_proposals = tool(_get_all_proposals)
get_all_scenarios = tool(_get_all_scenarios)


@tool
def get_all_items(tenant="molveno"):
    """Fetch and aggregate problems, proposals, and scenarios from the API."""
    problems = _get_all_problems(tenant)
    proposals = _get_all_proposals(tenant)
    scenarios = _get_all_scenarios(tenant)

    ids_dict = {
        "problems": set(),
        "proposals": set(),
        "scenarios": set()
    }

    connections_dict = {
        "problem_to_proposals": {},
        "proposal_to_scenarios": {}
    }

    names_dict = {
        "problems": {},
        "proposals": {},
        "scenarios": {}
    }

    for problem in problems:
        pid = problem["problem_id"]
        ids_dict["problems"].add(pid)
        names_dict["problems"][pid] = problem["name"]

    # Build proposal -> scenarios connections using related_scenario_ids
    problem_to_proposals = {}
    for proposal in proposals:
        prop_id = proposal["proposal_id"]
        pid = proposal["problem_id"]
        ids_dict["proposals"].add(prop_id)
        names_dict["proposals"][prop_id] = proposal["name"]

        problem_to_proposals.setdefault(pid, []).append(prop_id)
        connections_dict["proposal_to_scenarios"][prop_id] = proposal.get("related_scenario_ids", [])

    connections_dict["problem_to_proposals"] = problem_to_proposals

    for scenario in scenarios:
        scen_id = scenario["scenario_id"]
        ids_dict["scenarios"].add(scen_id)
        names_dict["scenarios"][scen_id] = scenario["name"]

    all_ids = ids_dict["problems"] | ids_dict["proposals"] | ids_dict["scenarios"]

    return {
        "all_ids": all_ids,
        "ids_dict": ids_dict,
        "connections_dict": connections_dict,
        "names_dict": names_dict
    }


@tool
def get_data_from_context(
    context_type,
    context,
    relations,
    extract_editable,
    tenant="molveno",
):
    """Fetch data from the API."""

    retrieved = {}
    for context_item in context:
        if context_type == "problem":
            url = f"{BACKEND_URL}{tenant}/{context_type}s/{context_item}"

        elif context_type == "proposal":
            related_problem = None
            for k, v in relations["problem_to_proposals"].items():
                if context_item in v:
                    related_problem = k
                    break

            url = (
                f"{BACKEND_URL}{tenant}/{context_type}s/"
                f"{context_item}?problem_id={related_problem}"
            )

        elif context_type == "scenario":
            related_proposal = None
            related_problem = None

            for k, v in relations["proposal_to_scenarios"].items():
                if context_item in v:
                    related_proposal = k
                    break

            for k, v in relations["problem_to_proposals"].items():
                if related_proposal in v:
                    related_problem = k
                    break

            url = (
                f"{BACKEND_URL}{tenant}/{context_type}s/"
                f"{context_item}?problem_id={related_problem}"
            )

        headers = {
            "accept": "application/json"
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        api_response = response.json()

        retrieved[context_item] = parse_data(api_response, context_type)

    if extract_editable:
        url = f"{BACKEND_URL}{tenant}/widgets"

        headers = {
            "accept": "application/json"
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        assert response is not None

        editable_indexes = parse_editable_indexes(response.json())
    else:
        editable_indexes = None

    return {
        "retrieved": retrieved,
        "editable_indexes": editable_indexes
    }


@tool
def get_sliders(tenant="molveno"):
    """Fetch sliders data from the API."""

    url = f"{BACKEND_URL}{tenant}/widgets"

    headers = {
        "accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    assert response is not None

    return response.json()


@tool
def create_problem_instance(
    payload: dict,
    tenant="molveno",
) -> dict:
    """
    Create a new problem instance.

    Args:
        payload: Dictionary of other user defined data

    Returns:
        A dict with a confirmation message
    """

    logger.info("Entered tool create_problem_instance")

    url = f"{BACKEND_URL}{tenant}/problems/"

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    # curl for direct reproduction
    logger.info("Outgoing create_problem_instance request:")
    curl_command = f"""
curl -X POST "{url}" \\
-H "accept: application/json" \\
-H "Content-Type: application/json" \\
-d '{json.dumps(payload)}'
"""
    logger.info(curl_command)

    # --- actual request ---
    response = requests.post(url, headers=headers, json=payload)

    # Log response for comparison
    logger.info(f"Response status: {response.status_code}")
    try:
        logger.info(f"Response body: {response.json()}")
    except Exception:
        logger.info(f"Response text: {response.text}")

    response.raise_for_status()

    return response.json()


@tool
def create_proposal_instance(
    problem_id: str,
    payload: dict,
    tenant="molveno",
) -> dict:
    """
    Create a new proposal instance for a given problem.

    Args:
        problem_id: The ID of the problem this proposal belongs to.
        payload: Dictionary of other user defined data

    Returns:
        A dict with a confirmation message
    """

    logger.info("Entered tool create_proposal_instance")

    url = f"{BACKEND_URL}{tenant}/proposals/"

    params = {
        "problem_id": problem_id,
    }

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    # curl for direct reproduction
    logger.info("Outgoing create_proposal_instance request:")
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    curl_command = f"""
curl -X POST "{url}?{query_string}" \\
-H "accept: application/json" \\
-H "Content-Type: application/json" \\
-d '{json.dumps(payload)}'
"""
    logger.info(curl_command)

    # --- actual request ---
    response = requests.post(
        url,
        headers=headers,
        params=params,
        json=payload,
    )

    # Log response for comparison
    logger.info(f"Response status: {response.status_code}")
    try:
        logger.info(f"Response body: {response.json()}")
    except Exception:
        logger.info(f"Response text: {response.text}")

    response.raise_for_status()

    return response.json()


@tool
def create_scenario_instance(
    problem_id: str,
    session_id: str,
    scenario_name: str,
    scenario_description: str,
    values: dict,
    proposal_id: str | None = None,
    tenant="molveno",
) -> dict:
    """
    Create a new scenario instance for a given proposal.

    Args:
        problem_id: The ID of the problem this scenario belongs to.
        session_id: The session ID used to generate the unique scenario instance ID.
        scenario_name: Human-readable name for the new scenario.
        scenario_description: Description of the scenario.
        values: Dictionary of input values for the scenario model.
        proposal_id: Optional proposal ID to link this scenario to a proposal.

    Returns:
        A dict with a confirmation message
    """

    logger.info("Entered tool create_scenario_instance")

    url = f"{BACKEND_URL}{tenant}/scenarios/{BASE_SCENARIO_ID}"  # TODO: pass correct scenario id

    params = {
        "problem_id": problem_id,
        "session_id": session_id,
    }

    if proposal_id is not None:
        params["proposal_id"] = proposal_id

    payload = {
        "scenario_name": scenario_name,
        "scenario_description": scenario_description,
        "values": values,
    }

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    # curl for direct reproduction
    logger.info("Outgoing create_scenario_instance request:")
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    curl_command = f"""
curl -X POST "{url}?{query_string}" \\
-H "accept: application/json" \\
-H "Content-Type: application/json" \\
-d '{json.dumps(payload)}'
"""
    logger.info(curl_command)

    # --- actual request ---
    response = requests.post(
        url,
        headers=headers,
        params=params,
        json=payload,
    )

    # Log response for comparison
    logger.info(f"Response status: {response.status_code}")
    try:
        logger.info(f"Response body: {response.json()}")
    except Exception:
        logger.info(f"Response text: {response.text}")

    response.raise_for_status()

    return response.json()