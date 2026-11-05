import os
import requests
from langchain.tools import tool
import logging

from app.utils.backend_utils import get_data, post_data, put_data, delete_data

logger = logging.getLogger(__name__)

# Name of the field the backend stores a scenario's summary under when a
# temporary scenario is promoted (see promote_scenario).
SCENARIO_SUMMARY_FIELD = "summary"


def clean_scenario(raw_data):
    """Strip a raw `.../evaluations/{id}/data` backend payload down to what
    the rest of the app needs, split into two buckets:

    - "data": the tiny sustainability/KPI summary. Read directly (as the
      "data" sub-key of get_evaluation_data's output) by
      analyze_scenario_results/generate_summary for prompt text, and by
      show_analysis_widget as part of the widget payload it hands to the
      frontend (see app.tools.executors.analysis_widgets).
    - "plot_data": the additional raw fields needed to build the load and
      capacity plots (constraint curves, per-sample uncertainty/usage,
      capacity thresholds, x/y ranges). This used to be discarded entirely,
      which is why the plot widgets could only ever return mocks.

    IMPORTANT: "plot_data" is intentionally kept separate from "data" and
    is NEVER meant to be dumped wholesale into an LLM prompt — it can hold
    hundreds of sample points. Callers must only use it to build a widget
    payload (sent straight to the frontend) or a small derived summary, the
    same way `_HEAVY_FIELDS` in app/utils/common.py keeps other bulky
    backend fields (extras, evaluation_data, ...) out of prompt injection.
    It must also never be written into state.cognitive.context_cache — see
    app.utils.common.strip_plot_data, applied wherever evaluation data
    enters that (long-lived) cache — since show_analysis_widget is the only
    consumer and it fetches plot_data fresh for its own transient use
    rather than reading it back out of long-lived state.
    """
    data = raw_data["data"]
    return {
        "scenario_id": raw_data["scenario_id"],
        "evaluation_id": raw_data["evaluation_id"],
        "data": data.get("kpis", {}),
        "plot_data": data,
    }


def _safe_get_list(url: str) -> list | None:
    """GET a list endpoint for relationship look-ups. Returns None (instead
    of raising) when the call fails, so a failed look-up degrades to "links
    not available" rather than breaking the whole listing."""
    try:
        data = get_data(url)
        return data if isinstance(data, list) else None
    except Exception:
        logger.warning(f"Could not fetch {url} for relationship look-up", exc_info=True)
        return None


def _safe_base_scenario_id(territory: str) -> str | None:
    """Id of the territory's designated base scenario, or None if unknown."""
    try:
        return get_base_scenario.invoke({"territory": territory})
    except Exception:
        logger.warning("Could not fetch the base scenario id", exc_info=True)
        return None


def _related_scenario_ids(proposal: dict) -> list:
    """Scenario ids a proposal declares in its top-level
    ``related_scenario_ids`` field (entries may be plain ids or objects)."""
    ids = []
    for item in proposal.get("related_scenario_ids") or []:
        scenario_id = item.get("scenario_id") if isinstance(item, dict) else item
        if scenario_id and scenario_id not in ids:
            ids.append(scenario_id)
    return ids


def _scenario_links_for_proposal(
    proposal: dict, scenario_names: dict, base_id: str | None
) -> list:
    """Scenarios associated with a proposal, as [{scenario_id, name,
    is_base_scenario}].

    The base scenario (the as-is reference) is by default associated with
    EVERY proposal, so it is always included, first, even when the backend
    does not list it in the proposal's related_scenario_ids."""
    ids = _related_scenario_ids(proposal)
    if base_id and base_id not in ids:
        ids.insert(0, base_id)
    links = [
        {
            "scenario_id": sid,
            "name": scenario_names.get(sid, sid),
            "is_base_scenario": sid == base_id,
        }
        for sid in ids
    ]
    links.sort(key=lambda link: not link["is_base_scenario"])
    return links


def _proposal_links_for_scenario(
    scenario_id: str, proposals: list, base_id: str | None
) -> list:
    """Proposals a scenario is associated with, as [{proposal_id, name}].
    The base scenario is associated with every proposal by default."""
    is_base = bool(base_id) and scenario_id == base_id
    return [
        {"proposal_id": p.get("proposal_id"), "name": p.get("name")}
        for p in proposals
        if is_base or scenario_id in _related_scenario_ids(p)
    ]


def _proposal_links_for_problem(problem_id: str, proposals: list) -> list:
    return [
        {"proposal_id": p.get("proposal_id"), "name": p.get("name")}
        for p in proposals
        if p.get("problem_id") == problem_id
    ]


@tool
def get_all_problems(territory: str):
    """Fetch all problems from the API, each with the proposals that belong to it."""
    url = f"{territory}/problems"
    extracted_data = get_data(url)
    proposals = _safe_get_list(f"{territory}/proposals")

    cleaned_data = []
    for item in extracted_data:
        entry = {"problem_id": item["problem_id"], "name": item["name"]}
        if proposals is not None:
            entry["linked_proposals"] = _proposal_links_for_problem(
                item["problem_id"], proposals
            )
        cleaned_data.append(entry)

    return cleaned_data


@tool
def get_all_proposals(territory: str):
    """Fetch all proposals from the API, each with its associated scenarios
    (the base scenario is associated with every proposal by default)."""
    url = f"{territory}/proposals"
    extracted_data = get_data(url)
    scenarios = _safe_get_list(f"{territory}/scenarios")
    scenario_names = (
        {s["scenario_id"]: s.get("name", s["scenario_id"]) for s in scenarios}
        if scenarios is not None
        else None
    )
    base_id = _safe_base_scenario_id(territory)

    cleaned_data = []
    for item in extracted_data:
        entry = {
            "proposal_id": item["proposal_id"],
            "name": item["name"],
            "problem_id": item["problem_id"],
        }
        if scenario_names is not None:
            entry["linked_scenarios"] = _scenario_links_for_proposal(
                item, scenario_names, base_id
            )
        cleaned_data.append(entry)

    return cleaned_data


@tool
def get_all_scenarios(territory: str):
    """Fetch all scenarios from the API, each with the proposals it is
    associated with and a flag marking the base scenario."""
    url = f"{territory}/scenarios"
    extracted_data = get_data(url)
    proposals = _safe_get_list(f"{territory}/proposals")
    base_id = _safe_base_scenario_id(territory)

    cleaned_data = []
    for item in extracted_data:
        entry = {
            "scenario_id": item["scenario_id"],
            "name": item["name"],
            "is_base_scenario": bool(base_id) and item["scenario_id"] == base_id,
        }
        if proposals is not None:
            entry["linked_proposals"] = _proposal_links_for_scenario(
                item["scenario_id"], proposals, base_id
            )
        cleaned_data.append(entry)

    return cleaned_data


def get_single_problem(problem_id: str, territory: str, cleaned: bool = True) -> dict:
    """Fetch a single problem instance (internal helper, not exposed as an agent tool)."""
    logger.info(f"Retrieving info for problem {problem_id}")

    url = f"{territory}/problems/{problem_id}"
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
            "territory": extracted_data.get("territory", ""),
            "created": extracted_data.get("created", ""),
            "updated": extracted_data.get("updated", ""),
        },
    }

    proposals = _safe_get_list(f"{territory}/proposals")
    if proposals is not None:
        cleaned_data["linked_proposals"] = _proposal_links_for_problem(
            extracted_data.get("problem_id", problem_id), proposals
        )

    return cleaned_data


def get_single_proposal(proposal_id: str, territory, cleaned: bool = True) -> dict:
    """Fetch a single proposal instance (internal helper, not exposed as an agent tool)."""

    logger.info(f"Retrieving info for proposal {proposal_id}")

    url = f"{territory}/proposals/{proposal_id}"
    extracted_data = get_data(url)

    if not cleaned:
        return extracted_data

    cleaned_data = {
        "proposal_id": extracted_data.get("proposal_id", ""),
        "problem_id": extracted_data.get("problem_id", ""),
        "name": extracted_data.get("name", ""),
        "description": extracted_data.get("description", ""),
        "resources": extracted_data.get("resources", ""),
        "context": extracted_data.get("context", ""),
        "impact": extracted_data.get("impact", ""),
        "additional_data_available_on_specific_request": {
            "version": extracted_data.get("version", ""),
            "territory": extracted_data.get("territory", ""),
            "created": extracted_data.get("created", ""),
            "updated": extracted_data.get("updated", ""),
            "status": extracted_data.get("status", ""),
        },
    }

    # Associated scenarios come from the proposal's top-level
    # related_scenario_ids (this used to read extras.context by mistake, so
    # every proposal looked like it had no scenarios). The base scenario is
    # associated with every proposal by default.
    scenarios = _safe_get_list(f"{territory}/scenarios")
    if scenarios is not None:
        scenario_names = {
            sc["scenario_id"]: sc.get("name", sc["scenario_id"]) for sc in scenarios
        }
        cleaned_data["linked_scenarios"] = _scenario_links_for_proposal(
            extracted_data, scenario_names, _safe_base_scenario_id(territory)
        )

    return cleaned_data


def get_single_scenario(scenario_id: str, territory, cleaned: bool = True) -> dict:
    """Fetch a single scenario instance (internal helper, not exposed as an agent tool)."""

    logger.info(f"Retrieving info for scenario {scenario_id}")

    url = f"{territory}/scenarios/{scenario_id}"
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

    base_id = _safe_base_scenario_id(territory)
    cleaned_data["is_base_scenario"] = bool(base_id) and (
        extracted_data["scenario_id"] == base_id
    )
    proposals = _safe_get_list(f"{territory}/proposals")
    if proposals is not None:
        cleaned_data["linked_proposals"] = _proposal_links_for_scenario(
            extracted_data["scenario_id"], proposals, base_id
        )

    return cleaned_data


@tool
def get_widgets(territory: str) -> list:
    """Fetch the raw list of tunable configuration parameters (the "indexes"
    of the /configuration payload: scalar, categorical and distribution
    entries). Shape them with app.utils.configuration_parameters."""
    url = f"{territory}/configuration"
    extracted_data = get_data(url)
    return extracted_data.get("indexes", [])


@tool
def create_cration_session(territory: str):
    """Create a creation session to handle temporary scenario(s)"""
    url = f"{territory}/sessions/"
    raw_data = post_data(url, json={})
    return raw_data["session_id"]


@tool
def create_temp_scenario(
    territory: str,
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
    url = f"{territory}/sessions/{creation_session}/scenarios/"

    body = {
        "base_scenario_id": base_scenario_id,
        "params_overrides": values,
    }

    params = {"base_scenario_id": base_scenario_id} if base_scenario_id else None

    created_scenario = post_data(url, json=body, params=params)
    logger.info(f"Step1. Created scenario: {created_scenario}")

    # Step 2. Created associated evaluation
    url = f"{territory}/sessions/{creation_session}/evaluations/"
    body = {
        "scenario_id": created_scenario["scenario_id"],
    }

    created_eval = post_data(url, json=body, params=params)
    logger.info(f"Step 2. Created evalutation: {created_eval}")

    # Step 3. Return evaluation results
    eval_url = f"{territory}/sessions/{creation_session}/evaluations/{created_eval["evaluation_id"]}/data"
    raw_data = get_data(eval_url)

    logger.info(f"Step 3.1 Raw eval results {raw_data}")

    cleaned = clean_scenario(raw_data)
    cleaned["creation_session"] = creation_session

    logger.info(f"Step 3.2 cleaned {cleaned}")

    return cleaned


@tool
def create_evaluation(territory: str, scenario_id: str) -> dict:
    """
    Trigger evaluation of a scenario.

    Returns:
        The created evaluation record, including its evaluation_id.
    """
    logger.info("Entered tool create_evaluation")

    url = f"{territory}/evaluations/"
    body = {"scenario_id": scenario_id}

    return post_data(url, json=body)


@tool
def promote_scenario(
    territory: str,
    creation_session: str,
    scenario_id: str,
    name: str,
    description: str | None = None,
    proposal_id: str = "",
    summary: str | None = None,
) -> dict:
    """
    Promote a temporary scenario (already created and evaluated) into a
    permanent, named scenario, optionally storing its summary with it.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool promote_scenario")

    url = f"{territory}/sessions/{creation_session}/scenarios/{scenario_id}"

    body = {"name": name, "description": description, "proposal_id": proposal_id}
    if summary:
        body[SCENARIO_SUMMARY_FIELD] = summary

    return post_data(url, json=body)


@tool
def get_base_scenario(territory) -> str:
    """Fetch the id of the base scenario"""

    logger.info(f"Retrieving id of base scenario")

    url = f"{territory}/scenarios?base_only=true"
    extracted_data = get_data(url)

    return extracted_data["scenario_id"]


@tool
def get_temp_evaluation_data(
    territory: str, creation_session: str, evaluation_id: str
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

    eval_url = (
        f"{territory}/sessions/{creation_session}/evaluations/{evaluation_id}/data"
    )
    raw_data = get_data(eval_url)

    cleaned = clean_scenario(raw_data)
    cleaned["creation_session"] = creation_session

    return cleaned


@tool
def get_data_from_context(current_context, territory, cleaned: bool = True):
    """Fetch stored problem/proposal/scenario data from the API (no evaluations)."""
    retrieved = {}

    for problem_id in current_context.get("problems", []):
        retrieved[f"problems {problem_id}"] = get_single_problem(
            problem_id, territory, cleaned=cleaned
        )

    for proposal_id in current_context.get("proposals", []):
        retrieved[f"proposals {proposal_id}"] = get_single_proposal(
            proposal_id, territory, cleaned=cleaned
        )

    for scenario_id in current_context.get("scenarios", []):
        retrieved[f"scenarios {scenario_id}"] = get_single_scenario(
            scenario_id, territory, cleaned=cleaned
        )

    return {"retrieved": retrieved}


@tool
def get_evaluation_data(current_context, territory):
    """Fetch evaluation data for each scenario in the current context.

    Returns a dict keyed the same way as get_data_from_context's "retrieved"
    entries (e.g. "scenarios <id>") so the two can be merged easily.
    """
    evaluations = {}
    scenario_ids = current_context.get("scenarios", [])
    if not scenario_ids:
        return evaluations

    evaluations_ids = {}
    for scenario_id in scenario_ids:
        try:
            evals_url = f"{territory}/evaluations/?scenario_id={scenario_id}"
            support = get_data(evals_url)
            evaluations_ids[scenario_id] = support[0]["evaluation_id"]
        except Exception as e:
            logger.warning(
                f"Unable to fetch evaluation for scenario {scenario_id} due to error: {e}"
            )

    for scenario_id, eval_id in evaluations_ids.items():
        try:
            eval_url = f"{territory}/evaluations/{eval_id}/data"
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
    territory: str,
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

    url = f"{territory}/problems/"

    body = {"name": name, "description": description, "extras": {}}
    if objective:
        body["extras"]["objective"] = objective
    if additional_data:
        body["extras"]["additional_data"] = additional_data

    return post_data(url, json=body)


@tool
def create_new_proposal(
    territory: str,
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

    url = f"{territory}/proposals/"

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

    return post_data(url, json=body)


@tool
def edit_problem(
    territory: str,
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

    url = f"{territory}/problems/{problem_id}"

    # The backend expects the full instance on PUT (version, name, description,
    # extras), not a partial patch. Fetch the current instance first so any
    # field the user didn't mention is preserved instead of being wiped out.
    existing = get_single_problem(problem_id, territory=territory, cleaned=False)

    extras = dict(existing.get("extras") or {})
    if objective:
        extras["objective"] = objective
    if additional_data:
        extras["additional_data"] = additional_data

    body = {
        "version": existing.get("version", 0),
        "name": name if name else existing.get("name", ""),
        "description": description if description else existing.get("description", ""),
        "extras": extras,
    }

    return put_data(url, json=body)


@tool
def edit_proposal(
    territory: str,
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

    url = f"{territory}/proposals/{proposal_id}"

    # The backend expects the full instance on PUT (version, name, description,
    # status, extras, related_scenario_ids), not a partial patch. Fetch the
    # current instance first so any field the user didn't mention (including
    # status and related scenarios) is preserved instead of being wiped out.
    existing = get_single_proposal(proposal_id, territory=territory, cleaned=False)

    extras = dict(existing.get("extras") or {})
    if resources:
        extras["resources"] = resources
    if context:
        extras["context"] = context
    if impact:
        extras["impact"] = impact

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
    territory: str,
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

    url = f"{territory}/scenarios/{scenario_id}"

    # The backend expects the full instance on PUT (version, name, description,
    # status, extras, related_scenario_ids), not a partial patch. Fetch the
    # current instance first so any field the user didn't mention (including
    # status and related scenarios) is preserved instead of being wiped out.
    existing = get_single_scenario(scenario_id, territory=territory, cleaned=False)

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
def delete_problem(problem_id: str, territory: str):
    """
    Delete an existing problem instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool delete_problem")
    url = f"{territory}/problems/{problem_id}"

    # DELETE responses are often empty (or just {"success": true}), which has
    # no "name" for the confirmation message. Grab it beforehand.
    name = problem_id
    try:
        existing = get_single_problem(problem_id, territory=territory, cleaned=False)
        name = existing.get("name", problem_id)
    except Exception as e:
        logger.warning(f"Could not fetch problem '{problem_id}' before delete: {e}")

    delete_data(url)
    return {"success": True, "name": name}


@tool
def delete_proposal(proposal_id: str, territory: str):
    """
    Delete an existing proposal instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool delete_proposal")
    url = f"{territory}/proposals/{proposal_id}"

    name = proposal_id
    try:
        existing = get_single_proposal(proposal_id, territory=territory, cleaned=False)
        name = existing.get("name", proposal_id)
    except Exception as e:
        logger.warning(f"Could not fetch proposal '{proposal_id}' before delete: {e}")

    delete_data(url)
    return {"success": True, "name": name}


@tool
def delete_scenario(scenario_id: str, territory: str):
    """
    Delete an existing scenario instance.

    Returns:
        A dict with a confirmation message
    """
    logger.info("Entered tool delete_scenario")
    url = f"{territory}/scenarios/{scenario_id}"

    name = scenario_id
    try:
        existing = get_single_scenario(scenario_id, territory=territory, cleaned=False)
        name = existing.get("name", scenario_id)
    except Exception as e:
        logger.warning(f"Could not fetch scenario '{scenario_id}' before delete: {e}")

    delete_data(url)
    return {"success": True, "name": name}


def _strong_html_to_markdown(text: str) -> str:
    """The backend wraps emphasized terms in index descriptions with raw
    <strong>...</strong> HTML. Convert those to markdown bold so the text
    renders correctly wherever it ends up (chat, prompts) instead of
    leaking HTML tags."""
    if not text:
        return text
    return text.replace("<strong>", "**").replace("</strong>", "**")


@tool
def get_territorial_index_list() -> dict:
    """Fetch the list of available territorial indexes (with descriptions) from the API."""
    url = f"indexes/get-index-list"
    extracted_data = get_data(url)

    indicators = [
        {
            "index_id": item["value"],
            "label": item["label"],
            "description": _strong_html_to_markdown(item["index_description"]),
            "value_unit_description": item.get("index_value_unit_description", ""),
            "available_for_variation": item.get("availableForVariation", False),
            "years_range": item.get("years_range", {}),
        }
        for item in extracted_data.get("indicators", [])
    ]

    additional_labels = [
        {
            "index_id": item["value"],
            "label": item["label"],
            "description": _strong_html_to_markdown(item.get("index_description", "")),
            "value_unit_description": item.get("index_value_unit_description", ""),
        }
        for item in extracted_data.get("additional_labels", [])
    ]

    return {"indicators": indicators, "additional_labels": additional_labels}


@tool
def get_territorial_index_map_data(
    index: str,
    start_date: str,
    end_date: str,
    spatial_granularity: str = "comune",
    indicator: str | None = None,
    start_date_comparison: str | None = None,
    end_date_comparison: str | None = None,
    seasonality: str | None = None,
) -> dict:
    """Fetch the geo-referenced values (GeoJSON + value range) of a single
    territorial index for the given date range from the API."""
    url = f"indexes/get_index_data"
    params = {
        "index": index,
        "start_date": start_date,
        "end_date": end_date,
        "spatial_granularity": spatial_granularity,
    }
    optional_params = {
        "indicator": indicator,
        "start_date_comparison": start_date_comparison,
        "end_date_comparison": end_date_comparison,
        "seasonality": seasonality,
    }
    params.update({key: value for key, value in optional_params.items() if value})
    return get_data(url, params=params)


@tool
def get_spatial_areas() -> dict:
    """Fetch the territories that can be selected in plots: municipalities
    ("comuni") and macro-areas/APT ("areas"), each as [{code, name}]. Both lists
    also contain the entry {code: "-1", name: "Provincia"} (the whole province)."""
    return get_data("indexes/get-spatial-areas")


@tool
def get_territorial_index_plot_data(
    index: str,
    start_date: str,
    end_date: str,
    granularity: str,
    spatial_granularity: str = "provincia",
    selected_territories: list[str] | None = None,
) -> dict:
    """Fetch the time-series (variation) data of a single territorial index for
    the given date range and territories from the API.

    selected_territories holds the comune / macro-area IDs the endpoint filters
    series on (matched against each series' label). It is sent as a repeated
    query parameter and omitted when empty (e.g. provincia, which returns only
    the province-wide series). spatial_granularity is read by the backend from
    the query string (comune | macro_area | provincia)."""
    url = "indexes/get-variation-data"
    params = {
        "index": index,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
        "spatial_granularity": spatial_granularity,
    }
    if selected_territories:
        params["selected_territories"] = list(selected_territories)
    return get_data(url, params=params)
