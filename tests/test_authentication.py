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
