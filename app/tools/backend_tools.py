import requests
from langchain.tools import tool
import logging
import json

from app.utils.data import parse_data, parse_editable_indexes
from app.config import BASE_SCENARIO_ID

logger = logging.getLogger(__name__)
BACKEND_URL = "http://0.0.0.0:8000/api/v1/"

@tool
def get_problems():
    """Fetch problems from the API."""
    url = f"{BACKEND_URL}problems"
    headers = {
        "accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    api_response = response.json()

    all_ids = set()

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
    
    for problem in api_response.get("data", []):
        pid = problem["problem_id"]
        ids_dict["problems"].add(pid)
        all_ids.add(pid)
        names_dict["problems"][pid] = problem["problem_name"]
        
        # Collect proposals
        prop_ids = []
        for proposal in problem.get("proposals", []):
            prop_id = proposal["proposal_id"]
            ids_dict["proposals"].add(prop_id)
            all_ids.add(prop_id)
            names_dict["proposals"][prop_id] = proposal["proposal_title"]
            prop_ids.append(prop_id)
            
            # Collect related scenarios
            scen_ids = []
            for scenario in proposal.get("related_scenarios", []):
                scen_id = scenario["scenario_id"]
                ids_dict["scenarios"].add(scen_id)
                all_ids.add(scen_id)
                names_dict["scenarios"][scen_id] = scenario["scenario_name"]
                scen_ids.append(scen_id)
            
            connections_dict["proposal_to_scenarios"][prop_id] = scen_ids
        
        connections_dict["problem_to_proposals"][pid] = prop_ids
    
    return {
        "all_ids": all_ids,
        "ids_dict": ids_dict,
        "connections_dict": connections_dict,
        "names_dict": names_dict
    }

@tool
def get_data_from_context(context_type, context, relations, extract_editable):
    """Fetch problems from the API."""

    retrieved = {}
    for context_item in context:
        if context_type=="problem":
            url = f"{BACKEND_URL}{context_type}s/{context_item}"
        elif context_type=="proposal":
            for k, v in relations["problem_to_proposals"].items():
                if context_item in v:
                    related_problem = k
                    break
            url = f"{BACKEND_URL}{context_type}s/{context_item}?problem_id={related_problem}"
        elif context_type=="scenario":
            for k, v in relations["proposal_to_scenarios"].items():
                if context_item in v:
                    related_proposal = k
                    break
            for k, v in relations["problem_to_proposals"].items():
                if related_proposal in v:
                    related_problem = k
                    break
            url = f"{BACKEND_URL}{context_type}s/{context_item}?problem_id={related_problem}"
        
        headers = {
            "accept": "application/json"
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        api_response = response.json()

        retrieved[context_item] = parse_data(api_response, context_type)

    if extract_editable:
        url = f"{BACKEND_URL}widgets"
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
def create_proposal_instance(
    problem_id: str,
    payload: dict
) -> dict:
    """
    Create a new proposal instance for a given problem.

    Args:
        problem_id: The ID of the problem this proposal belongs to.
        payload: Dictionary of other user defined data

    Returns:
        A dict with a confirmation message, e.g. {"message": "Scenario saved!"}
    """

    logger.info("Entered tool create_proposal_instance")
    url = f"{BACKEND_URL}proposals/"

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
    response = requests.post(url, headers=headers, params=params, json=payload)

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
        A dict with a confirmation message, e.g. {"message": "Scenario saved!"}
    """
    
    logger.info("Entered tool create_scenario_instance")
    
    url = f"{BACKEND_URL}scenarios/{BASE_SCENARIO_ID}" #TODO: pass correct scenario id

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
    response = requests.post(url, headers=headers, params=params, json=payload)

    # Log response for comparison
    logger.info(f"Response status: {response.status_code}")
    try:
        logger.info(f"Response body: {response.json()}")
    except Exception:
        logger.info(f"Response text: {response.text}")

    response.raise_for_status()

    return response.json()


@tool
def get_RelatedScenario(scenario_ids):
    """Fetch scenario details from the API."""
    url = f"{BACKEND_URL}problems"
    headers = {
        "accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    api_response = response.json()

    # Build a lookup dict of scenario_id -> scenario data (first occurrence wins)
    scenario_lookup = {}
    for problem in api_response.get("data", []):
        for proposal in problem.get("proposals", []):
            for scenario in proposal.get("related_scenarios", []):
                s_id = scenario["scenario_id"]
                if s_id not in scenario_lookup:
                    scenario_lookup[s_id] = {
                        "scenario_name": scenario["scenario_name"],
                        "scenario_description": scenario["scenario_description"],
                        "index_diffs": scenario["index_diffs"]
                    }

    related_scenarios = []
    seen_ids = set()
    for s_id in scenario_ids:
        if s_id in seen_ids:
            continue
        seen_ids.add(s_id)
        if s_id in scenario_lookup:
            related_scenarios.append({
                "scenario_id": s_id,
                **scenario_lookup[s_id]
            })

    return related_scenarios