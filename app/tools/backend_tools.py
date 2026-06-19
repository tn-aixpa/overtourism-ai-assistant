import requests
from langchain.tools import tool
import logging
# import json

from app.config import BACKEND_URL

logger = logging.getLogger(__name__)

@tool
def get_all_problems(tenant="molveno"):
    """Fetch all problems from the API."""
    url = f"{BACKEND_URL}{tenant}/problems"
    headers = {"accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

@tool
def get_all_proposals(tenant="molveno"):
    """Fetch all proposals from the API."""
    url = f"{BACKEND_URL}{tenant}/proposals"
    headers = {"accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

@tool
def get_all_scenarios(tenant="molveno"):
    """Fetch all scenarios from the API."""
    url = f"{BACKEND_URL}{tenant}/scenarios"
    headers = {"accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


@tool
def get_data_from_context(
    current_context,
    tenant="molveno",
):
    """Fetch data from the API."""

    retrieved = {}
    headers = {
        "accept": "application/json"
    }

    for key in ["problems", "proposals", "scenarios"]:
        for id in current_context[key]:
            url = f"{BACKEND_URL}{tenant}/{key}/{id}"
    
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            api_response = response.json()
        
            retrieved[f"{key} {id}"] = api_response

    return {
        "retrieved": retrieved,
    }
