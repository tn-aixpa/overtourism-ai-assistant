import os
import requests
from langchain.tools import tool
import logging

BACKEND_URL = os.environ.get("BACKEND_URL")

logger = logging.getLogger(__name__)

def get_data(url):
    response = requests.get(
        url,
        headers={"accept": "application/json"}
    )
    response.raise_for_status()
    return response.json()

@tool
def get_all_problems(tenant="molveno"):
    """Fetch all problems from the API."""
    url = f"{BACKEND_URL}{tenant}/problems"
    return get_data(url)

@tool
def get_all_proposals(tenant="molveno"):
    """Fetch all proposals from the API."""
    url = f"{BACKEND_URL}{tenant}/proposals"
    return get_data(url)

@tool
def get_all_scenarios(tenant="molveno"):
    """Fetch all scenarios from the API."""
    url = f"{BACKEND_URL}{tenant}/scenarios"
    return get_data(url)


@tool
def get_data_from_context(
    current_context,
    tenant="molveno",
):
    """Fetch data from the API."""

    retrieved = {}

    for key in ["problems", "proposals", "scenarios"]:
        for id in current_context[key]:
            url = f"{BACKEND_URL}{tenant}/{key}/{id}"
            api_response = get_data(url)

            if key == "scenarios":
                try:
                    #TODO: now I get the first (latest)
                    url = f"{BACKEND_URL}{tenant}/evaluations/"
                    scenarios_to_evals = get_data(url)
                    item = next((item for item in scenarios_to_evals if item["scenario_id"] == id), None)

                    if item is not None:
                        url = f"{BACKEND_URL}{tenant}/evaluations/{item["evaluation_id"]}/data"
                        api_response["evaluation_data"] = get_data(url)
                except Exception as e:
                    logger.warning(f"Unable to get scenario data due to error: {e}")
        
            retrieved[f"{key} {id}"] = api_response

    return {
        "retrieved": retrieved,
    }


@tool
def create_new_problem(
    name: str,
    description: str,
    objectives: str | None = None,
    additional_data: str | None = None,
    tenant: str = "molveno",
):
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


    body = {
        "name": name,
        "description": description,
        "extras": {},
    }

    if objectives:
        body["extras"]["objectives"] = objectives

    if additional_data:
        body["extras"]["additional_data"] = additional_data

    #TODO: add other fields

    # --- actual request ---
    response = requests.post(url, headers=headers, json=body)

    # Log response for comparison
    logger.info(f"Response status: {response.status_code}")
    try:
        logger.info(f"Response body: {response.json()}")
    except Exception:
        logger.info(f"Response text: {response.text}")

    response.raise_for_status()

    return response.json()