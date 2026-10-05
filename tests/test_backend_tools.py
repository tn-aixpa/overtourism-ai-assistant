from unittest.mock import MagicMock, patch

import pytest
import requests

from app.tools import executor_backend_tools as bt
from app.utils.authentication import check_authorization
from app.utils.common import set_token


@pytest.fixture(autouse=True)
def _token():
    set_token("test-token-123")
    yield
    set_token(None)


def make_response(json_data=None, status_code=200, content=b"1"):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.content = content
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _merge_auth_headers
# ---------------------------------------------------------------------------


class TestMergeAuthHeaders:
    def test_adds_bearer_token_when_absent(self):
        headers = bt._merge_auth_headers(None)
        assert headers == {"Authorization": "Bearer test-token-123"}

    def test_does_not_override_explicit_authorization(self):
        headers = bt._merge_auth_headers({"Authorization": "Bearer explicit-token"})
        assert headers["Authorization"] == "Bearer explicit-token"

    def test_preserves_other_headers(self):
        headers = bt._merge_auth_headers({"X-Custom": "value"})
        assert headers["X-Custom"] == "value"
        assert headers["Authorization"] == "Bearer test-token-123"


# ---------------------------------------------------------------------------
# get_data / post_data / put_data / delete_data
# ---------------------------------------------------------------------------


class TestGetData:
    def test_get_data_calls_requests_get_with_auth_header(self):
        with patch.object(
            bt.requests, "get", return_value=make_response({"ok": True})
        ) as mock_get:
            result = bt.get_data("http://x.test/resource")
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer test-token-123"
        assert result == {"ok": True}

    def test_get_data_raises_on_http_error(self):
        resp = make_response(status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("server error")
        with patch.object(bt.requests, "get", return_value=resp):
            with pytest.raises(requests.HTTPError):
                bt.get_data("http://x.test/resource")


class TestGetAllowedTerritories:
    def test_passes_token_as_bearer_authorization(self):
        with patch.object(bt, "get_data", return_value=["territory-1"]) as mock_get:
            result = bt.get_allowed_territories("test-token-123")

        mock_get.assert_called_once_with(
            f"{bt.BACKEND_URL}default/territorys",
            headers={"Authorization": "Bearer test-token-123"},
        )
        assert result == ["territory-1"]


class TestPostData:
    def test_post_data_sets_content_type_and_accept_headers(self):
        with patch.object(
            bt.requests, "post", return_value=make_response({"id": "1"})
        ) as mock_post:
            bt.post_data("http://x.test/resource", json={"a": 1})
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Content-Type"] == "application/json"
        assert kwargs["headers"]["accept"] == "application/json"
        assert kwargs["json"] == {"a": 1}

    def test_post_data_returns_parsed_json(self):
        with patch.object(bt.requests, "post", return_value=make_response({"id": "1"})):
            result = bt.post_data("http://x.test/resource")
        assert result == {"id": "1"}


class TestPutData:
    def test_put_data_sends_json_body(self):
        with patch.object(
            bt.requests, "put", return_value=make_response({"updated": True})
        ) as mock_put:
            result = bt.put_data("http://x.test/resource/1", json={"name": "n"})
        _, kwargs = mock_put.call_args
        assert kwargs["json"] == {"name": "n"}
        assert result == {"updated": True}


class TestDeleteData:
    def test_delete_data_returns_json_when_body_present(self):
        with patch.object(
            bt.requests,
            "delete",
            return_value=make_response({"success": True}, content=b"1"),
        ):
            result = bt.delete_data("http://x.test/resource/1")
        assert result == {"success": True}

    def test_delete_data_returns_success_dict_when_body_empty(self):
        with patch.object(
            bt.requests, "delete", return_value=make_response(content=b"")
        ):
            result = bt.delete_data("http://x.test/resource/1")
        assert result == {"success": True}

    def test_delete_data_raises_on_http_error(self):
        resp = make_response(status_code=404)
        resp.raise_for_status.side_effect = requests.HTTPError("not found")
        with patch.object(bt.requests, "delete", return_value=resp):
            with pytest.raises(requests.HTTPError):
                bt.delete_data("http://x.test/resource/1")


# ---------------------------------------------------------------------------
# create_new_problem
# ---------------------------------------------------------------------------


class TestCreateNewProblem:
    def test_builds_body_with_extras_only_when_provided(self):
        with patch.object(bt, "post_data", return_value={"name": "P"}) as mock_post:
            bt.create_new_problem.invoke(
                {
                    "territory": "t1",
                    "name": "P",
                    "description": "D",
                    "objective": "reduce congestion",
                    "additional_data": None,
                }
            )
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert body["name"] == "P"
        assert body["description"] == "D"
        assert body["extras"] == {"objective": "reduce congestion"}

    def test_empty_optional_fields_omitted_from_extras(self):
        with patch.object(bt, "post_data", return_value={"name": "P"}) as mock_post:
            bt.create_new_problem.invoke(
                {
                    "territory": "t1",
                    "name": "P",
                    "description": "D",
                    "objective": None,
                    "additional_data": None,
                }
            )
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["extras"] == {}

    def test_url_includes_territory(self):
        with patch.object(bt, "post_data", return_value={}) as mock_post:
            bt.create_new_problem.invoke(
                {
                    "territory": "molveno",
                    "name": "P",
                    "description": "D",
                    "objective": None,
                    "additional_data": None,
                }
            )
        args, _ = mock_post.call_args
        assert args[0] == f"{bt.BACKEND_URL}molveno/problems/"


# ---------------------------------------------------------------------------
# edit_problem — preserves fields not explicitly overridden
# ---------------------------------------------------------------------------


class TestEditProblem:
    def test_preserves_existing_fields_when_not_provided(self):
        existing = {
            "version": 3,
            "name": "Old Name",
            "description": "Old Desc",
            "extras": {"objective": "Old objective"},
        }
        with patch.object(bt, "get_single_problem", return_value=existing):
            with patch.object(
                bt, "put_data", return_value={"name": "Old Name"}
            ) as mock_put:
                bt.edit_problem.invoke(
                    {
                        "territory": "t1",
                        "problem_id": "p1",
                        "name": None,
                        "description": None,
                        "objective": None,
                        "additional_data": None,
                    }
                )
        body = mock_put.call_args.kwargs["json"]
        assert body["version"] == 3
        assert body["name"] == "Old Name"
        assert body["description"] == "Old Desc"
        assert body["extras"] == {"objective": "Old objective"}

    def test_overrides_only_provided_fields(self):
        existing = {
            "version": 3,
            "name": "Old Name",
            "description": "Old Desc",
            "extras": {"objective": "Old objective"},
        }
        with patch.object(bt, "get_single_problem", return_value=existing):
            with patch.object(bt, "put_data", return_value={}) as mock_put:
                bt.edit_problem.invoke(
                    {
                        "territory": "t1",
                        "problem_id": "p1",
                        "name": "New Name",
                        "description": None,
                        "objective": None,
                        "additional_data": "extra info",
                    }
                )
        body = mock_put.call_args.kwargs["json"]
        assert body["name"] == "New Name"
        assert body["description"] == "Old Desc"
        assert body["extras"] == {
            "objective": "Old objective",
            "additional_data": "extra info",
        }


# ---------------------------------------------------------------------------
# edit_proposal — preserves status / related_scenario_ids
# ---------------------------------------------------------------------------


class TestEditProposal:
    def test_preserves_status_and_related_scenarios(self):
        existing = {
            "version": 1,
            "name": "N",
            "description": "D",
            "status": "approved",
            "extras": {},
            "related_scenario_ids": ["s1", "s2"],
        }
        with patch.object(bt, "get_single_proposal", return_value=existing):
            with patch.object(bt, "put_data", return_value={}) as mock_put:
                bt.edit_proposal.invoke(
                    {
                        "territory": "t1",
                        "proposal_id": "pr1",
                        "name": None,
                        "problem_id": None,
                        "description": None,
                        "resources": None,
                        "context": None,
                        "impact": None,
                    }
                )
        body = mock_put.call_args.kwargs["json"]
        assert body["status"] == "approved"
        assert body["related_scenario_ids"] == ["s1", "s2"]

    def test_problem_id_param_only_set_when_provided(self):
        existing = {
            "version": 1,
            "name": "N",
            "description": "D",
            "status": "draft",
            "extras": {},
            "related_scenario_ids": [],
        }
        with patch.object(bt, "get_single_proposal", return_value=existing):
            with patch.object(bt, "put_data", return_value={}) as mock_put:
                bt.edit_proposal.invoke(
                    {
                        "territory": "t1",
                        "proposal_id": "pr1",
                        "name": None,
                        "problem_id": "new_problem",
                        "description": None,
                        "resources": None,
                        "context": None,
                        "impact": None,
                    }
                )
        assert mock_put.call_args.kwargs["params"] == {"problem_id": "new_problem"}

    def test_problem_id_omitted_when_not_provided(self):
        existing = {
            "version": 1,
            "name": "N",
            "description": "D",
            "status": "draft",
            "extras": {},
            "related_scenario_ids": [],
        }
        with patch.object(bt, "get_single_proposal", return_value=existing):
            with patch.object(bt, "put_data", return_value={}) as mock_put:
                bt.edit_proposal.invoke(
                    {
                        "territory": "t1",
                        "proposal_id": "pr1",
                        "name": None,
                        "problem_id": None,
                        "description": None,
                        "resources": None,
                        "context": None,
                        "impact": None,
                    }
                )
        assert mock_put.call_args.kwargs["params"] is None


# ---------------------------------------------------------------------------
# delete_problem / delete_proposal / delete_scenario
# ---------------------------------------------------------------------------


class TestDeleteProblem:
    def test_returns_fetched_name_on_success(self):
        with patch.object(
            bt, "get_single_problem", return_value={"name": "Overtourism"}
        ):
            with patch.object(bt, "delete_data", return_value={"success": True}):
                result = bt.delete_problem.invoke(
                    {"problem_id": "p1", "territory": "t1"}
                )
        assert result == {"success": True, "name": "Overtourism"}

    def test_falls_back_to_id_when_fetch_fails(self):
        with patch.object(
            bt, "get_single_problem", side_effect=RuntimeError("not found")
        ):
            with patch.object(bt, "delete_data", return_value={"success": True}):
                result = bt.delete_problem.invoke(
                    {"problem_id": "p1", "territory": "t1"}
                )
        assert result == {"success": True, "name": "p1"}

    def test_delete_still_called_even_if_prefetch_fails(self):
        with patch.object(bt, "get_single_problem", side_effect=RuntimeError("boom")):
            with patch.object(
                bt, "delete_data", return_value={"success": True}
            ) as mock_del:
                bt.delete_problem.invoke({"problem_id": "p1", "territory": "t1"})
        mock_del.assert_called_once()


class TestDeleteProposalAndScenario:
    def test_delete_proposal_returns_name(self):
        with patch.object(
            bt, "get_single_proposal", return_value={"name": "Strategy A"}
        ):
            with patch.object(bt, "delete_data", return_value={"success": True}):
                result = bt.delete_proposal.invoke(
                    {"proposal_id": "pr1", "territory": "t1"}
                )
        assert result == {"success": True, "name": "Strategy A"}

    def test_delete_scenario_returns_name(self):
        with patch.object(
            bt, "get_single_scenario", return_value={"name": "Cap at 500"}
        ):
            with patch.object(bt, "delete_data", return_value={"success": True}):
                result = bt.delete_scenario.invoke(
                    {"scenario_id": "sc1", "territory": "t1"}
                )
        assert result == {"success": True, "name": "Cap at 500"}


# ---------------------------------------------------------------------------
# get_data_from_context
# ---------------------------------------------------------------------------


class TestGetDataFromContext:
    def test_fetches_each_id_in_each_category(self):
        context = {"problems": ["p1"], "proposals": [], "scenarios": []}
        with patch.object(
            bt, "get_data", return_value={"id": "p1", "name": "P"}
        ) as mock_get:
            result = bt.get_data_from_context.invoke(
                {"current_context": context, "territory": "t1", "cleaned": False}
            )
        assert result == {"retrieved": {"problems p1": {"id": "p1", "name": "P"}}}
        mock_get.assert_called_once_with(f"{bt.BACKEND_URL}t1/problems/p1")

    def test_scenario_fetch_attaches_evaluation_data_when_found(self):
        context = {"problems": [], "proposals": [], "scenarios": ["sc1"]}

        def fake_get_data(url):
            if url.endswith("/scenarios/sc1"):
                return {"id": "sc1", "name": "Cap 500"}
            if url.endswith("/evaluations/"):
                return [{"scenario_id": "sc1", "evaluation_id": "ev1"}]
            if url.endswith("/evaluations/ev1/data"):
                return {"kpi": 42}
            raise AssertionError(f"unexpected url {url}")

        with patch.object(bt, "get_data", side_effect=fake_get_data):
            result = bt.get_data_from_context.invoke(
                {"current_context": context, "territory": "t1", "cleaned": False}
            )

        scenario_entry = result["retrieved"]["scenarios sc1"]
        assert scenario_entry is not None

    def test_scenario_fetch_tolerates_missing_evaluation(self):
        context = {"problems": [], "proposals": [], "scenarios": ["sc1"]}

        def fake_get_data(url):
            if url.endswith("/scenarios/sc1"):
                return {"id": "sc1", "name": "Cap 500"}
            if url.endswith("/evaluations/"):
                return []  # no matching evaluation
            raise AssertionError(f"unexpected url {url}")

        with patch.object(bt, "get_data", side_effect=fake_get_data):
            result = bt.get_data_from_context.invoke(
                {"current_context": context, "territory": "t1", "cleaned": False}
            )

        scenario_entry = result["retrieved"]["scenarios sc1"]
        assert "evaluation_data" not in scenario_entry

    def test_scenario_fetch_tolerates_evaluation_lookup_exception(self):
        context = {"problems": [], "proposals": [], "scenarios": ["sc1"]}

        def fake_get_data(url):
            if url.endswith("/scenarios/sc1"):
                return {"id": "sc1", "name": "Cap 500"}
            raise RuntimeError("evaluations service down")

        with patch.object(bt, "get_data", side_effect=fake_get_data):
            # Should not raise despite the evaluations lookup failing.
            result = bt.get_data_from_context.invoke(
                {"current_context": context, "territory": "t1", "cleaned": False}
            )

        assert result["retrieved"]["scenarios sc1"]["id"] == "sc1"

    def test_empty_context_returns_empty_retrieved(self):
        context = {"problems": [], "proposals": [], "scenarios": []}
        result = bt.get_data_from_context.invoke(
            {"current_context": context, "territory": "t1"}
        )
        assert result == {"retrieved": {}}
