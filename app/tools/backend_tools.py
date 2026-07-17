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


def check_authorization(token: str, tenant: str) -> bool:
    """Check authorization against the backend."""
    url = f"{BACKEND_URL}{tenant}/auth/me"
    headers = {"Authorization": f"Bearer {token}"}
    api_response = get_data(url, headers=headers)
    return api_response.get("authenticated", False)


def put_data(url, json=None, headers=None, params=None):
    logger.info(f"Putting data to URL: {url}")
    merged_headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        **_merge_auth_headers(headers),
    }
    response = requests.put(url, headers=merged_headers, params=params, json=json)
    _log_response(response)
    response.raise_for_status()
    return response.json()


def delete_data(url, headers=None, params=None):
    logger.info(f"Deleting data at URL: {url}")
    response = requests.delete(url, headers=_merge_auth_headers(headers), params=params)
    _log_response(response)
    response.raise_for_status()  # 500 (or 404) on missing entry propagates as an exception here
    if not response.content:
        return {"success": True}
    return response.json()


@tool
def get_all_problems(tenant: str):
    """Fetch all problems from the API."""
    url = f"{BACKEND_URL}{tenant}/problems"
    return get_data(url)


@tool
def get_all_proposals(tenant: str):
    """Fetch all proposals from the API."""
    url = f"{BACKEND_URL}{tenant}/proposals"
    return get_data(url)


@tool
def get_all_scenarios(tenant: str):
    """Fetch all scenarios from the API."""
    url = f"{BACKEND_URL}{tenant}/scenarios"
    return get_data(url)


def get_single_problem(problem_id: str, tenant: str) -> dict:
    """Fetch a single problem instance (internal helper, not exposed as an agent tool)."""
    url = f"{BACKEND_URL}{tenant}/problems/{problem_id}"
    return get_data(url)


def get_single_proposal(proposal_id: str, tenant) -> dict:
    """Fetch a single proposal instance (internal helper, not exposed as an agent tool)."""
    url = f"{BACKEND_URL}{tenant}/proposals/{proposal_id}"
    return get_data(url)


def get_single_scenario(scenario_id: str, tenant) -> dict:
    """Fetch a single scenario instance (internal helper, not exposed as an agent tool)."""
    url = f"{BACKEND_URL}{tenant}/scenarios/{scenario_id}"
    return get_data(url)


@tool
def get_data_from_context(current_context, tenant):
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
    tenant: str,
    name: str,
    description: str,
    objective: str | None = None,
    additional_data: str | None = None,
):
    """
    Create a new problem instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool create_new_problem")

    url = f"{BACKEND_URL}{tenant}/problems/"

    body = {"name": name, "description": description, "extras": {}}
    if objective:
        body["extras"]["objective"] = objective
    if additional_data:
        body["extras"]["additional_data"] = additional_data
    # TODO: add other fields

    return post_data(url, json=body)


@tool
def create_new_proposal(
    tenant: str,
    name: str,
    problem_id: str,
    description: str,
    resources: str,
    context: str,
    impact: str,
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


@tool
def edit_problem(
    tenant: str,
    problem_id: str,
    name: str | None = None,
    description: str | None = None,
    objective: str | None = None,
    additional_data: str | None = None,
):
    """
    Edit an existing problem instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool edit_problem")

    url = f"{BACKEND_URL}{tenant}/problems/{problem_id}"

    # The backend expects the full instance on PUT (version, name, description,
    # extras), not a partial patch. Fetch the current instance first so any
    # field the user didn't mention is preserved instead of being wiped out.
    existing = get_single_problem(problem_id, tenant=tenant)

    extras = dict(existing.get("extras") or {})
    if objective:
        extras["objective"] = objective
    if additional_data:
        extras["additional_data"] = additional_data
    # TODO: add other fields

    body = {
        "version": existing.get("version", 0),
        "name": name if name else existing.get("name", ""),
        "description": description if description else existing.get("description", ""),
        "extras": extras,
    }

    return put_data(url, json=body)


@tool
def edit_proposal(
    tenant: str,
    proposal_id: str,
    name: str | None = None,
    problem_id: str | None = None,
    description: str | None = None,
    resources: str | None = None,
    context: str | None = None,
    impact: str | None = None,
):
    """
    Edit an existing proposal instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool edit_proposal")

    url = f"{BACKEND_URL}{tenant}/proposals/{proposal_id}"

    # The backend expects the full instance on PUT (version, name, description,
    # status, extras, related_scenario_ids), not a partial patch. Fetch the
    # current instance first so any field the user didn't mention (including
    # status and related scenarios) is preserved instead of being wiped out.
    existing = get_single_proposal(proposal_id, tenant=tenant)

    extras = dict(existing.get("extras") or {})
    if resources:
        extras["resources"] = resources
    if context:
        extras["context"] = context
    if impact:
        extras["impact"] = impact
    # TODO: add other fields

    body = {
        "version": existing.get("version", 0),
        "name": name if name else existing.get("name", ""),
        "description": description if description else existing.get("description", ""),
        "status": existing.get("status", "draft"),
        "extras": extras,
        "related_scenario_ids": existing.get("related_scenario_ids", []),
    }

    # problem_id here is only relevant if the proposal is being reassigned
    # to a different parent problem; omit it otherwise.
    params = {"problem_id": problem_id} if problem_id else None

    return put_data(url, json=body, params=params)


@tool
def delete_problem(problem_id: str, tenant: str):
    """
    Delete an existing problem instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool delete_problem")
    url = f"{BACKEND_URL}{tenant}/problems/{problem_id}"

    # DELETE responses are often empty (or just {"success": true}), which has
    # no "name" for the confirmation message. Grab it beforehand.
    name = problem_id
    try:
        existing = get_single_problem(problem_id, tenant=tenant)
        name = existing.get("name", problem_id)
    except Exception as e:
        logger.warning(f"Could not fetch problem '{problem_id}' before delete: {e}")

    delete_data(url)
    return {"success": True, "name": name}


@tool
def delete_proposal(proposal_id: str, tenant: str):
    """
    Delete an existing proposal instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool delete_proposal")
    url = f"{BACKEND_URL}{tenant}/proposals/{proposal_id}"

    name = proposal_id
    try:
        existing = get_single_proposal(proposal_id, tenant=tenant)
        name = existing.get("name", proposal_id)
    except Exception as e:
        logger.warning(f"Could not fetch proposal '{proposal_id}' before delete: {e}")

    delete_data(url)
    return {"success": True, "name": name}


@tool
def delete_scenario(scenario_id: str, tenant: str):
    """
    Delete an existing scenario instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool delete_scenario")
    url = f"{BACKEND_URL}{tenant}/scenarios/{scenario_id}"

    name = scenario_id
    try:
        existing = get_single_scenario(scenario_id, tenant=tenant)
        name = existing.get("name", scenario_id)
    except Exception as e:
        logger.warning(f"Could not fetch scenario '{scenario_id}' before delete: {e}")

    delete_data(url)
    return {"success": True, "name": name}
