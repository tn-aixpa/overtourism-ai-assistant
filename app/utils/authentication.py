from fastapi import HTTPException
import jwt
from app.utils.common import get_data, BACKEND_URL
import logging

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


def _authorize_territory(token: str, territory: str) -> None:
    if not territory:
        raise HTTPException(status_code=400, detail="territory is required")
    if not check_authorization(token=token, territory=territory):
        raise HTTPException(status_code=403, detail="Not authorized")


def check_authorization(token: str) -> bool:
    """Check authorization against the backend."""
    url = f"{BACKEND_URL}auth/me"
    headers = {"Authorization": f"Bearer {token}"}
    api_response = get_data(url, headers=headers)
    return api_response.get("authenticated", False)


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


# Recognized role values, highest-privilege first. Must match
# app.tools.tool_schema.UserRole's values — kept as plain strings here
# rather than importing that enum, the same way this module already keeps
# no dependency on the agent/tools layers.
_KNOWN_ROLES_BY_PRIVILEGE = ("admin", "standard", "viewer")


def get_user_role(token: str | None) -> str:
    """Best-effort role resolution from the bearer token, for tool
    role-gating (see app.tools.tool_schema.UserRole / ToolDefinition.
    allowed_roles).

    Checks a few common claim shapes defensively (a flat "role" string, a
    "roles" list, or Keycloak-style "realm_access.roles") since the exact
    shape the backend issues hasn't been confirmed yet — TODO: confirm
    against the real token and drop whichever shapes turn out unused. If
    more than one recognized role is present, the highest-privilege one
    wins.

    Defaults to "standard" whenever the token is missing or carries no
    recognizable role claim — the same access level every caller
    effectively had before roles existed — so introducing role-gated
    tools doesn't retroactively lock existing callers out of tools that
    don't declare allowed_roles. This is a rollout convenience, not a
    long-term security posture: tighten it (e.g. default to "viewer")
    once the backend reliably issues a role claim.
    """
    if token is None:
        return "standard"

    payload = jwt.decode(token, options={"verify_signature": False})

    candidates: list[str] = []
    if isinstance(payload.get("role"), str):
        candidates.append(payload["role"])
    if isinstance(payload.get("roles"), list):
        candidates.extend(r for r in payload["roles"] if isinstance(r, str))
    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
        candidates.extend(r for r in realm_access["roles"] if isinstance(r, str))

    normalized = {c.strip().lower() for c in candidates}
    for role in _KNOWN_ROLES_BY_PRIVILEGE:
        if role in normalized:
            return role

    return "standard"
