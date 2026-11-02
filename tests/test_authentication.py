from unittest.mock import patch

import pytest

from app.utils.authentication import check_authorization


@pytest.mark.parametrize(
    "payload, expected_authorized, expected_role, expected_user_id",
    [
        (
            {"authenticated": True, "role": "admin", "user_id": "user1"},
            True,
            "admin",
            "user1",
        ),
        (
            {"authenticated": True, "role": "multieditor", "user_id": "user1"},
            True,
            "multieditor",
            "user1",
        ),
        (
            {"authenticated": True, "role": "editor", "user_id": "user1"},
            True,
            "editor",
            "user1",
        ),
        (
            {"authenticated": True, "role": "viewer", "user_id": "user1"},
            True,
            "viewer",
            "user1",
        ),
        (
            {"authenticated": False, "role": "viewer", "user_id": "user1"},
            False,
            "viewer",
            "user1",
        ),
    ],
)
def test_check_authorization_returns_status_and_role(
    payload, expected_authorized, expected_role, expected_user_id
):
    with patch("app.utils.authentication.get_data", return_value=payload):
        assert check_authorization("test-token") == (
            expected_authorized,
            expected_role,
            expected_user_id,
        )


def test_check_authorization_uses_auth_me_endpoint():
    payload = {
        "authenticated": False,
        "role": "viewer",
        "user_id": "user1",
    }

    with patch("app.utils.authentication.get_data", return_value=payload) as get_data:
        assert check_authorization("test-token") == (False, "viewer", "user1")

    get_data.assert_called_once_with(
        "auth/me", headers={"Authorization": "Bearer test-token"}
    )


# ---------------------------------------------------------------------------
# Bearer-token helpers
# ---------------------------------------------------------------------------
from fastapi import HTTPException  # noqa: E402

from app.utils.authentication import (  # noqa: E402
    _extract_bearer_token,
    _require_bearer_token,
)


@pytest.mark.parametrize(
    ("header", "token"),
    [
        ("Bearer abc", "abc"),
        ("Bearer   abc  ", "abc"),
        ("Bearer a.b.c", "a.b.c"),
        (None, None),
        ("", None),
        ("bearer abc", None),  # scheme is case-sensitive here
        ("Basic abc", None),
        ("abc", None),
    ],
)
def test_extract_bearer_token(header, token):
    assert _extract_bearer_token(header) == token


def test_empty_bearer_value_yields_empty_string_and_is_rejected():
    assert _extract_bearer_token("Bearer ") in ("", None)
    with pytest.raises(HTTPException) as exc:
        _require_bearer_token("Bearer ")
    assert exc.value.status_code == 401


def test_require_bearer_token_returns_the_token():
    assert _require_bearer_token("Bearer tok") == "tok"


@pytest.mark.parametrize("header", [None, "", "Token x", "Basic x"])
def test_require_bearer_token_rejects_missing_or_malformed(header):
    with pytest.raises(HTTPException) as exc:
        _require_bearer_token(header)

    assert exc.value.status_code == 401
    assert "Authorization" in exc.value.detail


def test_check_authorization_defaults_for_a_sparse_backend_response():
    with patch("app.utils.authentication.get_data", return_value={}):
        assert check_authorization("t") == (False, "viewer", None)
