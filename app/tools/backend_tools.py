import requests
from langchain.tools import tool

from app.utils.data import parse_data, parse_editable_indexes

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
        "connections_dict": connections_dict
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