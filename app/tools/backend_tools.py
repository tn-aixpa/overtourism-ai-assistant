import requests
from langchain.tools import tool
import logging
# import json

from app.config import BACKEND_URL

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
                    #TODO: check if correct API
                    url = f"{BACKEND_URL}{tenant}/evaluations/{id}"
                    extracted_evaluation_for_scenario = get_data(url)
                    evaluation_id = extracted_evaluation_for_scenario["evaluation_id"]

                    url = f"{BACKEND_URL}{tenant}/evaluations/{evaluation_id}/data"
                    api_response["evaluation_data"] = get_data(url)
                except Exception as e:
                    logger.warning(f"Unable to get scenario data due to error: {e}")
        
            retrieved[f"{key} {id}"] = api_response

    return {
        "retrieved": retrieved,
    }
