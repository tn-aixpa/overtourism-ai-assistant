from fastapi import HTTPException
import jwt
import logging

from app.utils.backend_utils import get_data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AUTH / SESSION-OWNERSHIP HELPERS
# ---------------------------------------------------------------------------
# Every endpoint below that reads or mutates an existing session_id needs to
# both (a) confirm the caller holds a valid token for the claimed territory, and
# (b) confirm the session actually belongs to that territory — otherwise anyone
# who knows/guesses a session_id could read or reset someone else's
# conversation. Centralized here so each route applies the same check.


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip()


def _require_bearer_token(authorization: str | None) -> str:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=401, detail="Missing or malformed Authorization header"
        )
    return token


def get_user_id(token: str) -> str:
    if token is None:
        return "unidentified"

    payload = jwt.decode(token, options={"verify_signature": False})

    if "email" in payload:
        return payload["email"]

    if "given_name" in payload:
        return payload["given_name"]

    if "preferred_username" in payload:
        return payload["preferred_username"]

    return "unidentified"


def check_authorization(token: str) -> tuple[bool, str]:
    """Return whether the backend authorizes the token and the user's role."""
    api_response = get_data(
        "auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return (
        api_response.get("authenticated", False),
        api_response.get("role", "viewer"),
    )
