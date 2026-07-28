import os
import requests
from langchain.tools import tool
import logging

from app.utils.common import _merge_auth_headers

BACKEND_URL = os.environ.get("BACKEND_URL")

logger = logging.getLogger(__name__)


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
    extracted_data = get_data(url)

    cleaned_data = [
        {
            "problem_id": item["problem_id"],
            "name": item["name"],
        }
        for item in extracted_data
    ]

    return cleaned_data


@tool
def get_all_proposals(tenant: str):
    """Fetch all proposals from the API."""
    url = f"{BACKEND_URL}{tenant}/proposals"
    extracted_data = get_data(url)

    cleaned_data = [
        {
            "proposal_id": item["proposal_id"],
            "name": item["name"],
            "problem_id": item["problem_id"],
        }
        for item in extracted_data
    ]

    return cleaned_data


@tool
def get_all_scenarios(tenant: str):
    """Fetch all scenarios from the API."""
    url = f"{BACKEND_URL}{tenant}/scenarios"
    extracted_data = get_data(url)

    cleaned_data = [
        {
            "scenario_id": item["scenario_id"],
            "name": item["name"],
        }
        for item in extracted_data
    ]

    return cleaned_data


def get_single_problem(problem_id: str, tenant: str, cleaned: bool = True) -> dict:
    """Fetch a single problem instance (internal helper, not exposed as an agent tool)."""
    logger.info(f"Retrieving info for problem {problem_id}")

    url = f"{BACKEND_URL}{tenant}/problems/{problem_id}"
    extracted_data = get_data(url)

    logger.info(f"AAAAAAA {extracted_data}")

    if not cleaned:
        return extracted_data

    cleaned_data = {
        "problem_id": extracted_data["problem_id"],
        "name": extracted_data["name"],
        "description": extracted_data["description"],
        "objective": extracted_data["extras"]["objective"],
        "links": extracted_data["extras"]["links"],
        "additional_data_available_on_specific_request": {
            "version": extracted_data["version"],
            "tenant": extracted_data["tenant"],
            "created": extracted_data["created"],
            "updated": extracted_data["updated"],
            "related_subsystem": extracted_data["extras"]["groups"],
        },
    }

    logger.info(f"BBBBBBB {cleaned_data}")

    return cleaned_data


def get_single_proposal(proposal_id: str, tenant, cleaned: bool = True) -> dict:
    """Fetch a single proposal instance (internal helper, not exposed as an agent tool)."""

    logger.info(f"Retrieving info for proposal {proposal_id}")

    url = f"{BACKEND_URL}{tenant}/proposals/{proposal_id}"
    extracted_data = get_data(url)

    if not cleaned:
        return extracted_data

    cleaned_data = {
        "proposal_id": extracted_data["proposal_id"],
        "problem_id": extracted_data["problem_id"],
        "name": extracted_data["name"],
        "description": extracted_data["description"],
        "resources": extracted_data["extras"]["resources"],
        "context": extracted_data["extras"]["context"],
        "impact": extracted_data["extras"]["impact"],
        "additional_data_available_on_specific_request": {
            "version": 2,
            "status": "draft",
            "created": "2026-06-16T16:09:03.521471+02:00",
            "updated": "2026-06-16T16:10:39.691952+02:00",
            "related_scenario_ids": extracted_data["related_scenario_ids"],
        },
    }

    return cleaned_data


def get_single_scenario(scenario_id: str, tenant, cleaned: bool = True) -> dict:
    """Fetch a single scenario instance (internal helper, not exposed as an agent tool)."""

    logger.info(f"Retrieving info for scenario {scenario_id}")

    url = f"{BACKEND_URL}{tenant}/scenarios/{scenario_id}"
    extracted_data = get_data(url)

    if not cleaned:
        return extracted_data

    cleaned_data = {
        "scenario_id": extracted_data["scenario_id"],
        "name": extracted_data["name"],
        "description": extracted_data["description"],
        "changes_wrt_base_scenario": extracted_data["index_diffs"],
        "additional_data_available_on_specific_request": {
            "version": 1,
            "created": "2026-06-16T16:09:44.825363+02:00",
            "updated": "2026-06-16T16:09:44.825363+02:00",
        },
    }

    return cleaned_data


@tool
def get_base_scenario(tenant) -> str:
    """Fetch the id of the base scenario"""

    logger.info(f"Retrieving id of base scenario")

    url = f"{BACKEND_URL}{tenant}/scenarios?base_only=true"
    extracted_data = get_data(url)

    return extracted_data["scenario_id"]


@tool
def get_data_from_context(current_context, tenant, cleaned: bool = True):
    """Fetch stored problem/proposal/scenario data from the API (no evaluations)."""
    retrieved = {}

    for problem_id in current_context.get("problems", []):
        retrieved[f"problems {problem_id}"] = get_single_problem(
            problem_id, tenant, cleaned=cleaned
        )

    for proposal_id in current_context.get("proposals", []):
        retrieved[f"proposals {proposal_id}"] = get_single_proposal(
            proposal_id, tenant, cleaned=cleaned
        )

    for scenario_id in current_context.get("scenarios", []):
        retrieved[f"scenarios {scenario_id}"] = get_single_scenario(
            scenario_id, tenant, cleaned=cleaned
        )

    return {"retrieved": retrieved}


@tool
def get_evaluation_data(current_context, tenant):
    """Fetch evaluation data for each scenario in the current context.

    Returns a dict keyed the same way as get_data_from_context's "retrieved"
    entries (e.g. "scenarios <id>") so the two can be merged easily.
    """
    # TODO: split data according to need (fe action, useful info), here or in tool_executor
    evaluations = {}
    scenario_ids = current_context.get("scenarios", [])
    if not scenario_ids:
        return evaluations

    evaluations_ids = {}
    for scenario_id in scenario_ids:
        try:
            evals_url = f"{BACKEND_URL}{tenant}/evaluations/?scenario_id={scenario_id}"
            support = get_data(evals_url)
            evaluations_ids[scenario_id] = support[0]["evaluation_id"]
        except Exception as e:
            logger.warning(
                f"Unable to fetch evaluation for scenario {scenario_id} due to error: {e}"
            )

    for scenario_id, eval_id in evaluations_ids.items():
        try:
            eval_url = f"{BACKEND_URL}{tenant}/evaluations/{eval_id}/data"
            raw_data = get_data(eval_url)

            cleaned = {
                "scenario_id": raw_data["scenario_id"],
                "evaluation_id": raw_data["evaluation_id"],
                "data": {
                    # "sustainable_area": ev["data"]["sustainable_area"],
                    "sustainability_index": raw_data["data"]["sustainability_index"],
                    "sustainability_by_constraint": raw_data["data"][
                        "sustainability_by_constraint"
                    ],
                },
            }

            evaluations[f"scenarios {scenario_id}"] = cleaned
        except Exception as e:
            logger.warning(
                f"Unable to get evaluation data for scenario {scenario_id}: {e}"
            )

    return evaluations  # return also other data for plots


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
    existing = get_single_problem(problem_id, tenant=tenant, cleaned=False)

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
    existing = get_single_proposal(proposal_id, tenant=tenant, cleaned=False)

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
def edit_scenario(
    tenant: str,
    scenario_id: str,
    name: str | None = None,
    description: str | None = None,
):
    """
    Edit an existing scenario instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool edit_scenario")

    url = f"{BACKEND_URL}{tenant}/scenarios/{scenario_id}"

    # The backend expects the full instance on PUT (version, name, description,
    # status, extras, related_scenario_ids), not a partial patch. Fetch the
    # current instance first so any field the user didn't mention (including
    # status and related scenarios) is preserved instead of being wiped out.
    existing = get_single_scenario(scenario_id, tenant=tenant, cleaned=False)

    body = {
        "version": existing.get("version", 0),
        "name": name if name else existing.get("name", ""),
        "description": description if description else existing.get("description", ""),
        "values": existing.get("values", {"additionalProp1": {}}),
        "extras": existing.get("extras", {"additionalProp1": {}}),
    }

    logger.info(body)

    return put_data(url, json=body)


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
        existing = get_single_problem(problem_id, tenant=tenant, cleaned=False)
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
        existing = get_single_proposal(proposal_id, tenant=tenant, cleaned=False)
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
        existing = get_single_scenario(scenario_id, tenant=tenant, cleaned=False)
        name = existing.get("name", scenario_id)
    except Exception as e:
        logger.warning(f"Could not fetch scenario '{scenario_id}' before delete: {e}")

    delete_data(url)
    return {"success": True, "name": name}
