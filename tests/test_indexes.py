from unittest.mock import patch

import pytest

from app.tools import executor_backend_tools as backend_tools
from app.tools.definitions.indexes import create_query_territorial_index_values_tool
from app.tools.executors import indexes as index_executors


class TestAdditionalTerritorialIndexParams:
    def test_index_list_executor_returns_indicators_and_additional_labels(self):
        backend_payload = {
            "indicators": [
                {
                    "value": "ricettivita",
                    "label": "Ricettività",
                    "index_description": "Base index",
                }
            ],
            "additional_labels": [
                {
                    "value": "tasso-variazione",
                    "label": "Tasso di variazione",
                    "index_description": "Comparison operation",
                }
            ],
        }
        with patch.object(backend_tools, "get_data", return_value=backend_payload):
            result = index_executors.execute_get_territorial_index_list(state=None)

        assert result["indexes"][0]["index_id"] == "ricettivita"
        assert result["additional_labels"][0]["index_id"] == "tasso-variazione"

    def test_tasso_variazione_requires_indicator_and_both_comparison_dates(self):
        with pytest.raises(
            ValueError, match="start_date_comparison, end_date_comparison"
        ):
            index_executors._additional_index_params(
                "tasso-variazione", indicator="ricettivita"
            )

    def test_incidenza_periodo_rejects_unknown_seasonality(self):
        with pytest.raises(ValueError, match="requires seasonality"):
            index_executors._additional_index_params(
                "incidenza-periodo", indicator="ricettivita", seasonality="monthly"
            )

    def test_incidenza_periodo_normalizes_seasonality(self):
        assert index_executors._additional_index_params(
            "incidenza-periodo", indicator="ricettivita", seasonality="Weekend"
        ) == {"indicator": "ricettivita", "seasonality": "weekend"}

    def test_map_executor_passes_incidenza_arguments_to_backend(self):
        response = {"geo_data": {"data": {"features": []}}}
        with patch.object(
            backend_tools,
            "get_data",
            return_value=response,
        ) as mock_get:
            result = index_executors.execute_show_territorial_index_map(
                state=None,
                index_id="incidenza-periodo",
                start_date="2022-01-01",
                end_date="2022-12-31",
                indicator="ricettivita",
                seasonality="weekend",
            )

        assert mock_get.call_args.kwargs["params"] == {
            "index": "incidenza-periodo",
            "start_date": "2022-01-01",
            "end_date": "2022-12-31",
            "spatial_granularity": "comune",
            "indicator": "ricettivita",
            "seasonality": "weekend",
        }
        assert result["map_summary"]["seasonality"] == "weekend"

    def test_value_query_passes_tasso_comparison_to_backend(self):
        response = {
            "geo_data": {
                "data": {
                    "features": [
                        {
                            "properties": {
                                "AREA_NAME": "Molveno",
                                "INDICE": 12.5,
                            }
                        }
                    ]
                },
                "min_value": 12.5,
                "max_value": 12.5,
            }
        }
        with patch.object(
            backend_tools,
            "get_data",
            return_value=response,
        ) as mock_get:
            result = index_executors.execute_query_territorial_index_values(
                state=None,
                index_id="tasso-variazione",
                start_date="2022-01-01",
                end_date="2022-12-31",
                query_type="values",
                municipalities=["Molveno"],
                indicator="ricettivita",
                start_date_comparison="2023-01-01",
                end_date_comparison="2023-12-31",
            )

        assert mock_get.call_args.kwargs["params"] == {
            "index": "tasso-variazione",
            "start_date": "2022-01-01",
            "end_date": "2022-12-31",
            "spatial_granularity": "comune",
            "indicator": "ricettivita",
            "start_date_comparison": "2023-01-01",
            "end_date_comparison": "2023-12-31",
        }
        assert result["values"] == [{"area_name": "Molveno", "index_value": 12.5}]


class TestTerritorialIndexRanking:
    @pytest.fixture
    def index_response(self):
        features = [
            {"properties": {"AREA_NAME": "Cembra", "INDICE": 4}},
            {"properties": {"AREA_NAME": "Trento", "INDICE": 9}},
            {"properties": {"AREA_NAME": "Ala", "INDICE": 9}},
            {"properties": {"AREA_NAME": "Molveno", "INDICE": 1}},
        ]
        return {
            "geo_data": {
                "data": {"features": features},
                "min_value": 1,
                "max_value": 9,
            }
        }

    def test_returns_requested_highest_municipalities_with_values(self, index_response):
        with patch.object(backend_tools, "get_data", return_value=index_response):
            result = index_executors.execute_query_territorial_index_values(
                state=None,
                index_id="ricettivita",
                start_date="2023-01-01",
                end_date="2023-12-31",
                query_type="ranking",
                ranking_order="highest",
                top_n=2,
            )

        assert result["ranked_municipalities"] == [
            {"area_name": "Ala", "index_value": 9},
            {"area_name": "Trento", "index_value": 9},
        ]
        assert result["requested_count"] == 2
        assert result["total_areas_considered"] == 4
        assert result["returned_count"] == 2
        assert result["ranking_tie_expanded"] is False

    def test_defaults_to_five_municipalities(self, index_response):
        with patch.object(backend_tools, "get_data", return_value=index_response):
            result = index_executors.execute_query_territorial_index_values(
                state=None,
                index_id="ricettivita",
                start_date="2023-01-01",
                end_date="2023-12-31",
                query_type="ranking",
                ranking_order="highest",
            )

        assert result["requested_count"] == 5
        assert result["returned_count"] == 4

    def test_expands_ties_at_extreme_when_tie_group_fits_limit(self):
        features = [
            {"properties": {"AREA_NAME": f"Town {i:02}", "INDICE": 10}}
            for i in range(1, 8)
        ] + [{"properties": {"AREA_NAME": "Other", "INDICE": 3}}]
        response = {"geo_data": {"data": {"features": features}}}

        with patch.object(backend_tools, "get_data", return_value=response):
            result = index_executors.execute_query_territorial_index_values(
                state=None,
                index_id="ricettivita",
                start_date="2023-01-01",
                end_date="2023-12-31",
                query_type="ranking",
                ranking_order="highest",
                top_n=5,
            )

        assert result["extreme_value"] == 10
        assert result["extreme_value_count"] == 7
        assert result["ranking_tie_expanded"] is True
        assert result["ranking_list_omitted"] is False
        assert result["returned_count"] == 7
        assert len(result["ranked_municipalities"]) == 7

    def test_omits_names_when_extreme_tie_exceeds_limit(self):
        features = [
            {"properties": {"AREA_NAME": f"Town {i:02}", "INDICE": 10}}
            for i in range(1, index_executors._MAX_RANKED_MUNICIPALITIES + 2)
        ]
        response = {"geo_data": {"data": {"features": features}}}

        with patch.object(backend_tools, "get_data", return_value=response):
            result = index_executors.execute_query_territorial_index_values(
                state=None,
                index_id="ricettivita",
                start_date="2023-01-01",
                end_date="2023-12-31",
                query_type="ranking",
                ranking_order="lowest",
                top_n=5,
            )

        assert (
            result["extreme_value_count"]
            == index_executors._MAX_RANKED_MUNICIPALITIES + 1
        )
        assert result["ranking_tie_expanded"] is True
        assert result["ranking_list_omitted"] is True
        assert result["returned_count"] == 0
        assert result["ranked_municipalities"] == []

    def test_returns_lowest_municipalities_in_ascending_order(self, index_response):
        with patch.object(backend_tools, "get_data", return_value=index_response):
            result = index_executors.execute_query_territorial_index_values(
                state=None,
                index_id="ricettivita",
                start_date="2023-01-01",
                end_date="2023-12-31",
                query_type="ranking",
                ranking_order="lowest",
                top_n=3,
            )

        assert result["ranked_municipalities"] == [
            {"area_name": "Molveno", "index_value": 1},
            {"area_name": "Cembra", "index_value": 4},
            {"area_name": "Ala", "index_value": 9},
        ]

    def test_ranks_using_raw_precision_before_display_rounding(self):
        response = {
            "geo_data": {
                "data": {
                    "features": [
                        {"properties": {"AREA_NAME": "Lower", "INDICE": 5.00001}},
                        {"properties": {"AREA_NAME": "Higher", "INDICE": 5.00004}},
                    ]
                }
            }
        }
        with patch.object(backend_tools, "get_data", return_value=response):
            result = index_executors.execute_query_territorial_index_values(
                state=None,
                index_id="ricettivita",
                start_date="2023-01-01",
                end_date="2023-12-31",
                query_type="ranking",
                ranking_order="highest",
                top_n=1,
            )

        assert result["ranked_municipalities"] == [
            {"area_name": "Higher", "index_value": 5.00004}
        ]

    @pytest.mark.parametrize(
        "arguments, message",
        [
            ({"top_n": 2}, "ranking_order"),
            ({"ranking_order": "middle", "top_n": 2}, "highest.*lowest"),
            ({"ranking_order": "highest", "top_n": 0}, "positive integer"),
            ({"ranking_order": "highest", "top_n": 21}, "cannot exceed 20"),
        ],
    )
    def test_validates_ranking_arguments(self, arguments, message):
        with pytest.raises(ValueError, match=message):
            index_executors.execute_query_territorial_index_values(
                state=None,
                index_id="ricettivita",
                start_date="2023-01-01",
                end_date="2023-12-31",
                query_type="ranking",
                **arguments,
            )

    def test_tool_schema_exposes_ranking_mode(self):
        tool = create_query_territorial_index_values_tool()
        parameters = {parameter.name: parameter for parameter in tool.parameters}

        assert parameters["query_type"].schema["enum"] == [
            "values",
            "threshold",
            "ranking",
        ]
        assert parameters["ranking_order"].schema["enum"] == ["highest", "lowest"]
        assert parameters["top_n"].type == "integer"
        assert parameters["top_n"].default == 5
