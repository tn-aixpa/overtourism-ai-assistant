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


def clean_scenario(raw_data):
    """Strip a raw `.../evaluations/{id}/data` backend payload down to what
    the rest of the app needs, split into two buckets:

    - "data": the tiny sustainability/KPI summary (used by _parse_kpis for
      the histogramComparison / indexComparison widgets). Unchanged from
      before — anything reading `["data"]` keeps working exactly as-is.
    - "plot_data": the additional raw fields needed to build the load and
      capacity plots (constraint curves, per-sample uncertainty/usage,
      capacity thresholds, x/y ranges). This used to be discarded entirely,
      which is why show_load_plot/show_capacity_plot could only ever
      return mocks.

    IMPORTANT: "plot_data" is intentionally kept separate from "data" and
    is NEVER meant to be dumped wholesale into an LLM prompt — it can hold
    hundreds of sample points. Callers must only use it to build a widget
    payload (sent straight to the frontend) or a small derived summary, the
    same way `_HEAVY_FIELDS` in app/utils/common.py keeps other bulky
    backend fields (extras, evaluation_data, ...) out of prompt injection.
    """
    data = raw_data["data"]
    return {
        "scenario_id": raw_data["scenario_id"],
        "evaluation_id": raw_data["evaluation_id"],
        "data": data.get("kpis", {}),
        "plot_data": {
            # "constraint_curves": data.get("constraint_curves", {}) or {},
            # "uncertainty": data.get("uncertainty", []) or [],
            # "uncertainty_by_constraint": data.get("uncertainty_by_constraint", {})
            # or {},
            # "usage": data.get("usage", []) or [],
            # "usage_by_constraint": data.get("usage_by_constraint", {}) or {},
            # "sample_x": data.get("sample_x", []) or [],
            # "sample_y": data.get("sample_y", []) or [],
            # "capacity_mean": data.get("capacity_mean"),
            # "capacity_mean_by_constraint": data.get("capacity_mean_by_constraint", {})
            # or {},
            # "x_max": data.get("x_max"),
            # "y_max": data.get("y_max"),
            # "kpis": data.get("kpis", {}) or {},
        },
    }


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

    if not cleaned:
        return extracted_data

    cleaned_data = {
        "problem_id": extracted_data.get("problem_id", ""),
        "name": extracted_data.get("name", ""),
        "description": extracted_data.get("description", ""),
        "objective": extracted_data.get("extras", {}).get("objective", ""),
        "links": extracted_data.get("extras", {}).get("links", ""),
        "additional_data_available_on_specific_request": {
            "version": extracted_data.get("version", ""),
            "tenant": extracted_data.get("tenant", ""),
            "created": extracted_data.get("created", ""),
            "updated": extracted_data.get("updated", ""),
            "related_subsystem": extracted_data.get("extras", {}).get("groups", ""),
        },
    }

    return cleaned_data


def get_single_proposal(proposal_id: str, tenant, cleaned: bool = True) -> dict:
    """Fetch a single proposal instance (internal helper, not exposed as an agent tool)."""

    logger.info(f"Retrieving info for proposal {proposal_id}")

    url = f"{BACKEND_URL}{tenant}/proposals/{proposal_id}"
    extracted_data = get_data(url)

    if not cleaned:
        return extracted_data

    cleaned_data = {
        "problem_id": extracted_data.get("problem_id", ""),
        "name": extracted_data.get("name", ""),
        "description": extracted_data.get("description", ""),
        "objective": extracted_data.get("extras", {}).get("objective", ""),
        "links": extracted_data.get("extras", {}).get("links", ""),
        "additional_data_available_on_specific_request": {
            "version": extracted_data.get("version", ""),
            "tenant": extracted_data.get("tenant", ""),
            "created": extracted_data.get("created", ""),
            "updated": extracted_data.get("updated", ""),
            "related_subsystem": extracted_data.get("extras", {}).get("groups", ""),
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

    logger.info(extracted_data)

    cleaned_data = {
        "scenario_id": extracted_data["scenario_id"],
        "name": extracted_data["name"],
        "description": extracted_data["description"],
        "changes_wrt_base_scenario": extracted_data["extras"]["index_diffs"],
        "additional_data_available_on_specific_request": {
            "version": extracted_data.get("version", ""),
            "created": extracted_data.get("created", ""),
            "updated": extracted_data.get("updated", ""),
        },
    }

    return cleaned_data


@tool
def get_widgets(tenant: str) -> dict:
    """Fetch all tunable configuration parameters (widgets) from the API."""
    url = f"{BACKEND_URL}{tenant}/widgets"
    return get_data(url)


def _strong_html_to_markdown(text: str) -> str:
    """The backend wraps emphasized terms in index descriptions with raw
    <strong>...</strong> HTML. Convert those to markdown bold so the text
    renders correctly wherever it ends up (chat, prompts) instead of
    leaking HTML tags."""
    if not text:
        return text
    return text.replace("<strong>", "**").replace("</strong>", "**")


@tool
def get_territorial_index_list(tenant: str) -> list:
    """Fetch the list of available territorial indexes (with descriptions) from the API."""
    url = f"{BACKEND_URL}{tenant}/indexes/get-index-list"
    extracted_data = get_data(url)

    cleaned_data = [
        {
            "index_id": item["value"],
            "label": item["label"],
            "description": _strong_html_to_markdown(item["index_description"]),
            "available_for_variation": item.get("availableForVariation", False),
            "years_range": item.get("years_range", {}),
        }
        for item in extracted_data.get("indicators", [])
    ]

    return cleaned_data


@tool
def get_territorial_index_data(
    tenant: str, index: str, start_date: str, end_date: str
) -> dict:
    """Fetch the geo-referenced values (GeoJSON + value range) of a single
    territorial index for the given date range from the API."""
    url = f"{BACKEND_URL}{tenant}/indexes/get_index_data"
    params = {"index": index, "start_date": start_date, "end_date": end_date}
    return get_data(url, params=params)


@tool
def create_cration_session(tenant: str):
    """Create a creation session to handle temporary scenario(s)"""
    url = f"{BACKEND_URL}{tenant}/sessions/"
    raw_data = post_data(url, json={})
    return raw_data["session_id"]


@tool
def create_temp_scenario(
    tenant: str,
    values: dict,
    base_scenario_id: str,
    creation_session: str,
) -> dict:
    """
    Create a temporary (unsaved) scenario applying the given parameter
    overrides on top of a base scenario.

    NOTE: assumes a `temporary: true` flag on the standard POST /scenarios/
    payload keeps the backend from treating this as a permanent scenario.
    Adjust to the real contract (e.g. a dedicated /scenarios/temp endpoint)
    if that differs.

    Returns:
        The created (temporary) scenario record, including its scenario_id.
    """
    logger.info(
        f"Entered tool create_temp_scenario for values {values}. Current creation session {creation_session}"
    )

    # Step 1. Create the temporary scenario
    url = f"{BACKEND_URL}{tenant}/sessions/{creation_session}/scenarios/"

    body = {
        "base_scenario_id": base_scenario_id,
        "values": values,
    }

    params = {"base_scenario_id": base_scenario_id} if base_scenario_id else None

    created_scenario = post_data(url, json=body, params=params)
    logger.info(f"Step1. Created scenario: {created_scenario}")

    # Step 2. Created associated evaluation
    url = f"{BACKEND_URL}{tenant}/sessions/{creation_session}/evaluations/"
    body = {
        "scenario_id": created_scenario["scenario_id"],
        "ensemble_size": 20,
        "kwargs": {},
    }

    created_eval = post_data(url, json=body, params=params)
    logger.info(f"Step 2. Created evalutation: {created_eval}")

    # Step 3. Return evaluation results
    eval_url = f"{BACKEND_URL}{tenant}/sessions/{creation_session}/evaluations/{created_eval["evaluation_id"]}/data"
    raw_data = get_data(eval_url)

    logger.info(f"Step 3.1 Raw eval results {raw_data}")

    cleaned = clean_scenario(raw_data)
    cleaned["creation_session"] = creation_session

    logger.info(f"Step 3.2 cleaned {cleaned}")

    return cleaned


@tool
def create_evaluation(tenant: str, scenario_id: str) -> dict:
    """
    Trigger evaluation of a scenario.

    Returns:
        The created evaluation record, including its evaluation_id.
    """
    logger.info("Entered tool create_evaluation")

    url = f"{BACKEND_URL}{tenant}/evaluations/"
    body = {"scenario_id": scenario_id}

    return post_data(url, json=body)


@tool
def promote_scenario(
    tenant: str,
    creation_session: str,
    scenario_id: str,
    name: str,
    description: str | None = None,
    proposal_id: str = "",
) -> dict:
    """
    Promote a temporary scenario (already created and evaluated) into a
    permanent, named scenario.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool promote_scenario")

    url = f"{BACKEND_URL}{tenant}/sessions/{creation_session}/scenarios/{scenario_id}"

    body = {"name": name, "description": description, "proposal_id": proposal_id}

    return post_data(url, json=body)


@tool
def get_base_scenario(tenant) -> str:
    """Fetch the id of the base scenario"""

    logger.info(f"Retrieving id of base scenario")

    url = f"{BACKEND_URL}{tenant}/scenarios?base_only=true"
    extracted_data = get_data(url)

    return extracted_data["scenario_id"]


@tool
def get_temp_evaluation_data(
    tenant: str, creation_session: str, evaluation_id: str
) -> dict:
    """
    Fetch evaluation results for a temporary (session-scoped, not-yet-saved)
    scenario, given the creation_session and evaluation_id returned earlier
    by create_temp_scenario.

    Mirrors Step 3 of create_temp_scenario, but as a standalone call for
    when the temp scenario/evaluation were created in a previous request
    (e.g. the /agent/tool "summary" pipeline) and only their ids are
    available now.

    Returns:
        The cleaned evaluation record (scenario_id, evaluation_id, data),
        with creation_session attached.
    """
    logger.info(
        f"Entered tool get_temp_evaluation_data for session {creation_session}, "
        f"evaluation {evaluation_id}"
    )

    eval_url = f"{BACKEND_URL}{tenant}/sessions/{creation_session}/evaluations/{evaluation_id}/data"
    raw_data = get_data(eval_url)

    cleaned = clean_scenario(raw_data)
    cleaned["creation_session"] = creation_session

    return cleaned


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

            cleaned = clean_scenario(raw_data)

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

    body = {
        "problem_id": problem_id,
        "name": name,
        "description": description,
        "extras": {},
    }
    if resources:
        body["extras"]["resources"] = resources
    if context:
        body["extras"]["context"] = context
    if impact:
        body["extras"]["impact"] = impact
    # TODO: add other fields

    return post_data(url, json=body)


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
