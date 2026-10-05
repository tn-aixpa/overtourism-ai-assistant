from unittest.mock import patch

import pytest

from app.utils.backend_utils import get_user_role


@pytest.mark.parametrize(
    "payload, expected",
    [
        ([{"role": "admin"}], "admin"),
        ([{"role": "multieditor"}], "multieditor"),
        ([{"role": "editor"}], "editor"),
        ([{"roles": ["viewer"]}], "viewer"),
        ([{"role": "unknown"}], "viewer"),
        ([{"role": "standard"}], "viewer"),
        ([], "viewer"),
        ([{}], "viewer"),
    ],
)
def test_get_user_role_resolves_role_from_backend_and_defaults_to_viewer(
    payload, expected
):
    with patch("app.utils.backend_utils.get_data", return_value=payload):
        assert get_user_role("test-token") == expected


def test_get_user_role_without_token_defaults_to_viewer():
    assert get_user_role(None) == "viewer"
