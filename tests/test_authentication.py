from unittest.mock import patch

import pytest

from app.utils.authentication import check_authorization


@pytest.mark.parametrize(
    "payload, expected_authorized, expected_role",
    [
        ({"authenticated": True, "role": "admin"}, True, "admin"),
        ({"authenticated": True, "role": "multieditor"}, True, "multieditor"),
        ({"authenticated": True, "role": "editor"}, True, "editor"),
        ({"authenticated": True, "role": "viewer"}, True, "viewer"),
        ({"authenticated": False, "role": "viewer"}, False, "viewer"),
    ],
)
def test_check_authorization_returns_status_and_role(
    payload, expected_authorized, expected_role
):
    with patch("app.utils.authentication.get_data", return_value=payload):
        assert check_authorization("test-token") == (expected_authorized, expected_role)


def test_check_authorization_uses_auth_me_endpoint():
    with patch("app.utils.authentication.get_data", return_value={}) as get_data:
        assert check_authorization("test-token") == (False, "viewer")

    get_data.assert_called_once_with(
        "auth/me", headers={"Authorization": "Bearer test-token"}
    )
