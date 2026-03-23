import requests
from langchain.tools import tool

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
        names_dict["problems"][pid] = problem["problem_name"]
        
        # Collect proposals
        prop_ids = []
        for proposal in problem.get("proposals", []):
            prop_id = proposal["proposal_id"]
            ids_dict["proposals"].add(prop_id)
            names_dict["proposals"][prop_id] = proposal["proposal_title"]
            prop_ids.append(prop_id)
            
            # Collect related scenarios
            scen_ids = []
            for scenario in proposal.get("related_scenarios", []):
                scen_id = scenario["scenario_id"]
                ids_dict["scenarios"].add(scen_id)
                names_dict["scenarios"][scen_id] = scenario["scenario_name"]
                scen_ids.append(scen_id)
            
            connections_dict["proposal_to_scenarios"][prop_id] = scen_ids
        
        connections_dict["problem_to_proposals"][pid] = prop_ids
    
    #return ids_dict, connections_dict, names_dict
    return ids_dict, connections_dict