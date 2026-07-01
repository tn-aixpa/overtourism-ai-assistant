import os
import requests
from langchain.tools import tool
import logging
from app.utils.common import get_token


BACKEND_URL = os.environ.get("BACKEND_URL")

logger = logging.getLogger(__name__)


def _merge_auth_headers(headers: dict | None) -> dict:
    """Ensure Authorization is present, without overriding an explicitly-provided one."""
    merged = dict(headers) if headers else {}
    if "Authorization" not in merged:
        merged["Authorization"] = f"Bearer {get_token()}"
    return merged


def _log_response(response: requests.Response) -> None:
    logger.info(f"Response status: {response.status_code}")
    try:
        logger.info(f"Response body: {response.json()}")
    except Exception:
        logger.info(f"Response text: {response.text}")


def get_data(url, headers=None, params=None):
    logger.info(f"Fetching data from URL: {url}")
    response = requests.get(url, headers=_merge_auth_headers(headers), params=params)
    response.raise_for_status()
    return response.json()


def post_data(url, json=None, headers=None, params=None):
    logger.info(f"Posting data to URL: {url}")
    merged_headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        **_merge_auth_headers(headers),
    }
    response = requests.post(url, headers=merged_headers, params=params, json=json)
    _log_response(response)
    response.raise_for_status()
    return response.json()


def check_authorization(token: str, tenant: str = "molveno") -> bool:
    """Check authorization against the backend."""
    url = f"{BACKEND_URL}{tenant}/auth/me"
    headers = {"Authorization": f"Bearer {token}"}
    api_response = get_data(url, headers=headers)
    return api_response.get("authenticated", False)


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
def get_data_from_context(current_context, tenant="molveno"):
    """Fetch data from the API."""
    retrieved = {}

    for key in ["problems", "proposals", "scenarios"]:
        for id in current_context[key]:
            url = f"{BACKEND_URL}{tenant}/{key}/{id}"
            api_response = get_data(url)

            if key == "scenarios":
                try:
                    # TODO: now I get the first (latest)
                    evals_url = f"{BACKEND_URL}{tenant}/evaluations/"
                    scenarios_to_evals = get_data(evals_url)
                    item = next(
                        (e for e in scenarios_to_evals if e["scenario_id"] == id),
                        None,
                    )

                    if item is not None:
                        eval_id = item["evaluation_id"]
                        eval_url = f"{BACKEND_URL}{tenant}/evaluations/{eval_id}/data"
                        api_response["evaluation_data"] = get_data(eval_url)
                except Exception as e:
                    logger.warning(f"Unable to get scenario data due to error: {e}")

            retrieved[f"{key} {id}"] = api_response

    return {"retrieved": retrieved}


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

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool create_new_problem")

    url = f"{BACKEND_URL}{tenant}/problems/"

    body = {"name": name, "description": description, "extras": {}}
    if objectives:
        body["extras"]["objectives"] = objectives
    if additional_data:
        body["extras"]["additional_data"] = additional_data
    # TODO: add other fields

    return post_data(url, json=body)


@tool
def create_new_proposal(
    name: str,
    problem_id: str,
    description: str,
    resources: str,
    context: str,
    impact: str,
    tenant: str = "molveno",
):
    """
    Create a new proposal instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool create_new_proposal")

    url = f"{BACKEND_URL}{tenant}/proposals/"

    body = {"name": name, "description": description, "extras": {}}
    if resources:
        body["extras"]["resources"] = resources
    if context:
        body["extras"]["context"] = context
    if impact:
        body["extras"]["impact"] = impact
    # TODO: add other fields

    return post_data(url, json=body, params={"problem_id": problem_id})