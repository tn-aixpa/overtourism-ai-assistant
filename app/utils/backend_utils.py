import os
import requests
from langchain.tools import tool
import logging

from app.utils.common import get_token

BACKEND_URL = os.environ.get("BACKEND_URL")

logger = logging.getLogger(__name__)

# Never let a backend call hang a turn forever (a hung turn never sends
# "__done__").
BACKEND_TIMEOUT = 30  # seconds

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() == "true"


def _merge_auth_headers(headers: dict | None) -> dict:
    """Ensure Authorization is present, without overriding an explicitly-provided one."""

    merged = dict(headers) if headers else {}

    if AUTH_ENABLED and "Authorization" not in merged:
        merged["Authorization"] = f"Bearer {get_token()}"

    return merged


def _log_response(response: requests.Response) -> None:
    logger.info(f"Response status: {response.status_code}")
    try:
        logger.info(f"Response body: {response.json()}")
    except Exception:
        logger.info(f"Response text: {response.text}")


def get_data(url_string, headers=None, params=None):
    url = f"{BACKEND_URL}{url_string}"
    logger.info(f"Fetching data from URL: {url}")
    response = requests.get(
        url,
        headers=_merge_auth_headers(headers),
        params=params,
        timeout=BACKEND_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def post_data(url_string, json=None, headers=None, params=None):
    url = f"{BACKEND_URL}{url_string}"
    logger.info(f"Posting data to URL: {url}")
    merged_headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        **_merge_auth_headers(headers),
    }
    response = requests.post(
        url, headers=merged_headers, params=params, json=json, timeout=BACKEND_TIMEOUT
    )
    _log_response(response)
    response.raise_for_status()
    return response.json()


def put_data(url_string, json=None, headers=None, params=None):
    url = f"{BACKEND_URL}{url_string}"
    logger.info(f"Putting data to URL: {url}")
    merged_headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        **_merge_auth_headers(headers),
    }
    response = requests.put(
        url, headers=merged_headers, params=params, json=json, timeout=BACKEND_TIMEOUT
    )
    _log_response(response)
    response.raise_for_status()
    return response.json()


def delete_data(url_string, headers=None, params=None):
    url = f"{BACKEND_URL}{url_string}"
    logger.info(f"Deleting data at URL: {url}")
    response = requests.delete(
        url,
        headers=_merge_auth_headers(headers),
        params=params,
        timeout=BACKEND_TIMEOUT,
    )
    _log_response(response)
    response.raise_for_status()  # 500 (or 404) on missing entry propagates as an exception here
    if not response.content:
        return {"success": True}
    return response.json()


def check_authorization(token: str) -> bool:
    """Check authorization against the backend."""
    url = f"auth/me"
    headers = {"Authorization": f"Bearer {token}"}
    api_response = get_data(url, headers=headers)
    return api_response.get("authenticated", False)


def get_user_role(token: str | None) -> str:
    """Get the user's role from the backend."""
    if not token:
        return "viewer"

    url = f"auth/roles"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        api_response = get_data(url, headers=headers)
    except Exception:
        logger.warning(
            "Could not resolve user role from backend; defaulting to viewer."
        )
        return "viewer"

    if not api_response:
        return "viewer"

    if isinstance(api_response, list):
        payload = api_response[0] if api_response else {}
    elif isinstance(api_response, dict):
        payload = api_response
    else:
        return "viewer"

    if isinstance(payload, dict):
        role = payload.get("role")
        if role:
            return (
                role
                if role in {"admin", "multieditor", "editor", "viewer"}
                else "viewer"
            )

        roles = payload.get("roles")
        if isinstance(roles, list) and roles:
            role = roles[0]
            return (
                role
                if role in {"admin", "multieditor", "editor", "viewer"}
                else "viewer"
            )

    return "viewer"


def get_allowed_territories(token: str | None = None):
    url = f"default/territories"
    headers = {"Authorization": f"Bearer {token}"} if token else None
    territories = get_data(url, headers=headers)
    logger.info(f"Allowed territories: {territories}")
    return territories
