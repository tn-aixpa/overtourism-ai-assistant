import logging
from typing import Any, Dict, Callable

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def _parse_kpis(state: AgentState, scenario_id: str) -> Dict[str, Dict[str, float]]:
    """Return KPIs in the format expected by the histogramComparison widget.

    Output format:
    {
        "sustainability_index": {
            "level": 95,
            "confidence": 0.52,
        },
        "parking": {
            "level": 100,
            "confidence": 0.00,
        },
        ...
    }
    """
    data = (
        state.cognitive.context_cache.get(f"scenarios {scenario_id}", {})
        .get("evaluation_data", {})
        .get("data", {})
    )

    raw_kpis = {
        "sustainability_index": data.get("sustainability_index", {}),
        **data.get("sustainability_by_constraint", {}),
    }

    parsed = {}

    for name, value in raw_kpis.items():
        if isinstance(value, dict):
            level = value.get("index", value.get("level", value.get("value", 0)))
            confidence = value.get(
                "confidence",
                value.get("uncertainty", value.get("ci", 0)),
            )
        else:
            level = value
            confidence = 0

        parsed[name] = {
            "level": round(level * 100),
            "confidence": confidence * 100,
        }

    return parsed
