"""
This tools are temporary and are meant to be removed or modified when the new version of the backend is ready.
"""

import requests
from langchain.tools import tool
import logging
import json
import requests
from typing import Optional

import plotly.graph_objects as go

from app.config import BACKEND_URL

logger = logging.getLogger(__name__)


@tool
def get_RelatedScenario(scenario_ids):
    """Fetch scenario details from the API."""
    url = f"{BACKEND_URL}problems"
    headers = {
        "accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    api_response = response.json()

    # Build a lookup dict of scenario_id -> scenario data (first occurrence wins)
    scenario_lookup = {}
    for problem in api_response.get("data", []):
        for proposal in problem.get("proposals", []):
            for scenario in proposal.get("related_scenarios", []):
                s_id = scenario["scenario_id"]
                if s_id not in scenario_lookup:
                    scenario_lookup[s_id] = {
                        "scenario_name": scenario["scenario_name"],
                        "scenario_description": scenario["scenario_description"],
                        "index_diffs": scenario["index_diffs"]
                    }

    related_scenarios = []
    seen_ids = set()
    for s_id in scenario_ids:
        if s_id in seen_ids:
            continue
        seen_ids.add(s_id)
        if s_id in scenario_lookup:
            related_scenarios.append({
                "scenario_id": s_id,
                **scenario_lookup[s_id]
            })

    return related_scenarios


# ---------------------------------------------------------------------------
# Charts builders
# ---------------------------------------------------------------------------

def build_tourists_excursionists_chart(
    curves: list,
    points: list,
    x_max: float = None,
    y_max: float = None
) -> go.Figure:
    """Build the Turisti / Escursionisti (Bidimensionale) chart.
    
    Args:
        curves: List of curve objects, each with x, y, name, color, dash
        points: List of point objects for uncertainty visualization
        x_max: Maximum X-axis value
        y_max: Maximum Y-axis value
    """
    fig = go.Figure()

    # Add curves (constraint boundaries)
    for curve in curves:
        fig.add_trace(go.Scatter(
            x=curve.get("x", []),
            y=curve.get("y", []),
            mode="lines",
            name=curve.get("name", ""),
            line=dict(
                color=curve.get("color", "black"),
                dash=curve.get("dash", "solid"),
                width=3,
            ),
            hoverinfo="name",
            type="scatter",
        ))

    # Add uncertainty points
    if points:
        pt = points[0]  # Typically one "Presenze" point
        marker = pt.get("marker", {})
        fig.add_trace(go.Scatter(
            x=pt.get("x", []),
            y=pt.get("y", []),
            mode="markers",
            name=pt.get("name", "Presenze"),
            marker=dict(
                color=marker.get("color", pt.get("color", "black")),
                size=marker.get("size", 8),
                line=dict(width=1, color="black"),
                colorscale=marker.get("colorscale", "RdYlGn_r"),
                reversescale=marker.get("reversescale", True),
                cmin=marker.get("cmin", 0),
                cmax=marker.get("cmax", 1),
                showscale=marker.get("showscale", False),
            ),
            hovertemplate=pt.get("hovertemplate", "<b>Presenze</b><br><b>Turisti:</b> %{x}<br><b>Escursionisti:</b> %{y}<extra></extra>"),
            type="scatter",
        ))

    # Set axis ranges
    if x_max:
        fig.update_xaxes(range=[0, x_max])
    if y_max:
        fig.update_yaxes(range=[0, y_max])

    # Apply layout
    fig.update_layout(
        title="",
        xaxis_title="Turisti",
        yaxis_title="Escursionisti",
        margin=dict(t=30, l=50, r=30, b=50),
        showlegend=True,
        legend=dict(
            orientation="h",
            x=0,
            y=-0.2,
            xanchor="left",
            yanchor="top"
        ),
        hovermode="closest",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        # removed scaleanchor from here entirely
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False, range=[0, x_max] if x_max else None, rangemode="tozero")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False, range=[0, y_max] if y_max else None, rangemode="tozero")

    return fig


def build_tourist_load_chart(
    uncertainty_data: list,
    capacity_mean: float,
    subsystem: str = "default",
    capacity_mean_by_constraint: dict = None
) -> go.Figure:
    """Build the Tourist Load chart (Monodimensionale).
    
    This chart shows usage patterns sorted by usage value with uncertainty coloring.
    
    Args:
        uncertainty_data: List of dicts with keys: usage, usage_uncertainty
        capacity_mean: Mean capacity threshold
        subsystem: Subsystem name ('default' or constraint name)
        capacity_mean_by_constraint: Dict mapping constraint names to their capacity means
    """
    if not isinstance(uncertainty_data, list):
        uncertainty_data = []

    # Sort by usage ascending
    sorted_points = sorted(uncertainty_data, key=lambda item: item.get("usage", 0))
    
    x = list(range(len(sorted_points)))
    y = [p.get("usage", 0) for p in sorted_points]
    risk = [100 * p.get("usage_uncertainty", 0) for p in sorted_points]
    color_values = [p.get("usage_uncertainty", 0) for p in sorted_points]

    fig = go.Figure()

    # Capacity mean line (below traces, added first)
    if subsystem != "default" and capacity_mean_by_constraint:
        capacity_mean = capacity_mean_by_constraint.get(subsystem, capacity_mean)

    capacity_label = (
        "Soglia di sovraffollamento"
        if subsystem == "default" or subsystem == "overtourism"
        else "Capacità di carico"
    )
    
    fig.add_trace(go.Scatter(
        x=x,
        y=[capacity_mean] * len(x),
        mode="lines",
        name=capacity_label,
        line=dict(color="#FFA500", dash="dash", width=2),
        yaxis="y1",
        showlegend=True,
    ))

    # Usage scatter plot
    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        mode="markers",
        name="Presenze",
        marker=dict(
            color=color_values,
            colorscale="RdYlGn_r",
            cmin=0,
            cmax=1,
            size=8,
        ),
        customdata=risk,
        hovertemplate=(
            "Giorno: %{x}<br>Utilizzo: %{y:.1f}%<br>Livello di rischio: %{customdata:.1f}%<extra></extra>"
        ),
        showlegend=True,
    ))

    # Compute Y-axis range
    y_max = max(y) * 1.2 if y else capacity_mean * 1.2

    # Build y-axis label
    if subsystem == "default" or subsystem == "overtourism":
        yaxis_label = "Livello di utilizzo della destinazione"
    else:
        yaxis_label = f"Livello di utilizzo della risorsa {subsystem}"

    fig.update_layout(
        title="",
        xaxis_title="Giorni (ordinati per utilizzo)",
        yaxis_title=yaxis_label,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=13),
        margin=dict(t=50, b=80, l=80, r=60),
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
        hovermode="x unified",
    )
    fig.update_xaxes(
        range=None,
        showgrid=True,
        gridcolor="rgba(128,128,128,0.15)",
        zeroline=False,
        tickformat=".0f"
    )
    fig.update_yaxes(
        range=[0, y_max],
        showgrid=True,
        gridcolor="rgba(128,128,128,0.15)",
        zeroline=False,
        tickformat=".0f",
        layer="below traces"
    )

    return fig


def build_comparison_bar_chart(
    left_data: dict,
    right_data: dict,
    label_left: str = "Scenario 1",
    label_right: str = "Scenario 2"
) -> go.Figure:
    """Build the comparison bar chart between two scenarios.
    
    Each scenario has categories with level and confidence values.
    Displays side-by-side bars with uncertainty bands and level indicators.
    
    Args:
        left_data: Dict mapping category names to {level, confidence}
        right_data: Dict mapping category names to {level, confidence}
        label_left: Label for left scenario
        label_right: Label for right scenario
    """
    categories = list(dict.fromkeys(list(left_data.keys()) + list(right_data.keys())))

    values_left = [left_data.get(cat, {}).get("level", 0) for cat in categories]
    errors_left = [left_data.get(cat, {}).get("confidence", 0) for cat in categories]
    values_right = [right_data.get(cat, {}).get("level", 0) for cat in categories]
    errors_right = [right_data.get(cat, {}).get("confidence", 0) for cat in categories]

    display_left = [round(v, 1) for v in values_left]
    display_right = [round(v, 1) for v in values_right]
    err_left = [round(e, 1) for e in errors_left]
    err_right = [round(e, 1) for e in errors_right]

    bar_width = 0.38
    fig = go.Figure()

    # LEFT scenario main bars (blue)
    fig.add_trace(go.Bar(
        x=categories,
        y=display_left,
        name=label_left,
        marker=dict(color="#0066CC"),
        offsetgroup="left",
        width=bar_width,
        type="bar",
    ))

    # RIGHT scenario main bars (gray)
    fig.add_trace(go.Bar(
        x=categories,
        y=display_right,
        name=label_right,
        marker=dict(color="#D9D9D9"),
        offsetgroup="right",
        width=bar_width,
        type="bar",
    ))

    # LEFT confidence band (yellow)
    fig.add_trace(go.Bar(
        x=categories,
        y=[e * 2 for e in err_left],
        base=[max(d - e, 0) for d, e in zip(display_left, err_left)],
        name=f"{label_left} conf",
        marker=dict(color="#e7b66e"),
        offsetgroup="left",
        width=bar_width,
        showlegend=False,
        hoverinfo="skip",
        text=[f"{v:.1f}" for v in display_left],
        textposition="outside",
    ))

    # RIGHT confidence band (yellow)
    fig.add_trace(go.Bar(
        x=categories,
        y=[e * 2 for e in err_right],
        base=[max(d - e, 0) for d, e in zip(display_right, err_right)],
        name=f"{label_right} conf",
        marker=dict(color="#e7b66e"),
        offsetgroup="right",
        width=bar_width,
        showlegend=False,
        hoverinfo="skip",
        text=[f"{v:.1f}" for v in display_right],
        textposition="outside",
    ))

    # LEFT level line (black)
    fig.add_trace(go.Bar(
        x=categories,
        y=[0.02] * len(categories),
        base=display_left,
        marker=dict(color="black"),
        showlegend=False,
        hoverinfo="skip",
        offsetgroup="left",
        width=bar_width,
    ))

    # RIGHT level line (black)
    fig.add_trace(go.Bar(
        x=categories,
        y=[0.02] * len(categories),
        base=display_right,
        marker=dict(color="black"),
        showlegend=False,
        hoverinfo="skip",
        offsetgroup="right",
        width=bar_width,
    ))

    # Legend entry for confidence (not shown as unique trace)
    fig.add_trace(go.Bar(
        x=[None],
        y=[None],
        marker=dict(color="#e7b66e"),
        name="Incertezza",
        showlegend=True,
        hoverinfo="skip",
    ))

    fig.update_layout(
        barmode="group",
        title="",
        xaxis_title="Categorie",
        yaxis_title="Livello (%)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=13),
        margin=dict(t=20, r=20, l=40, b=70),
        legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
        xaxis=dict(automargin=True),
        yaxis=dict(automargin=True),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False)

    return fig


def load_plot_input(
    scenario_id: str,
    problem_id: str,
) -> Optional[dict]:
    """Load plot input data from backend for a scenario.
    
    Args:
        scenario_id: Scenario ID to fetch
        problem_id: Problem ID (required parameter)
        api_url: Backend API base URL
        
    Returns:
        Parsed plot input dict or None on error
    """
    try:
        response = requests.get(
            f"{BACKEND_URL}scenarios/{scenario_id}",
            params={"problem_id": problem_id}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", data)  # Handle both nested and flat responses
    except requests.RequestException as e:
        print(f"Error loading plot input for scenario {scenario_id}: {e}")
        return None



def extract_plot_data_for_bidimensionale(plot_data: dict) -> tuple:
    if not plot_data:
        return [], [], 0, 0

    curves = []
    if "constraint_curves" in plot_data:
        for group_name, curve_data in plot_data["constraint_curves"].items():
            curves.append({
                "x": curve_data[0] if isinstance(curve_data, (list, tuple)) else [],
                "y": curve_data[1] if isinstance(curve_data, (list, tuple)) else [],
                "name": group_name,
                "color": "black",
                "dash": get_dash_for_group(group_name),
            })

    # Resolve uncertainty data from any known location
    uncertainty_data = (
        plot_data.get("points", {}).get("uncertainty")
        or plot_data.get("kpis", {}).get("uncertainty")
        or plot_data.get("uncertainty")
        or []
    )

    points = []
    if uncertainty_data:
        tourists     = [u["tourists"]     for u in uncertainty_data]
        excursionists= [u["excursionists"] for u in uncertainty_data]
        index        = [u.get("index", 0) for u in uncertainty_data]

        points.append({
            "name": "Presenze",
            "x": tourists,
            "y": excursionists,
            "marker": {
                "color": index,
                "colorscale": "RdYlGn_r",  # already reversed – do NOT set reversescale=True
                "reversescale": False,
                "cmin": 0,
                "cmax": 1,
                "size": 6,
                "showscale": True,          # show the colorbar so users can read risk
            },
            "hovertemplate": (
                "<b>Presenze</b><br>"
                "<b>Turisti:</b> %{x}<br>"
                "<b>Escursionisti:</b> %{y}<br>"
                "<b>Indice:</b> %{marker.color:.2f}"
                "<extra></extra>"
            ),
        })

    x_max = plot_data.get("x_max", 0)
    y_max = plot_data.get("y_max", 0)

    if not x_max and tourists:
        x_max = max(tourists) * 1.2
    if not y_max and excursionists:
        y_max = max(excursionists) * 1.2

    return curves, points, x_max, y_max


def extract_plot_data_for_monodimensionale(plot_data: dict) -> tuple:
    if not plot_data:
        return [], 0, {}

    # Same unified resolver
    uncertainty_data = (
        plot_data.get("points", {}).get("uncertainty")
        or plot_data.get("kpis", {}).get("uncertainty")
        or plot_data.get("uncertainty")
        or []
    )

    # capacity_mean: prefer explicit key, else derive from data (100th pct of usage)
    capacity_mean = plot_data.get("capacity_mean", 0)
    if capacity_mean == 0 and uncertainty_data:
        usages = [u.get("usage", 0) for u in uncertainty_data]
        capacity_mean = max(usages) if usages else 0

    capacity_mean_by_constraint = plot_data.get("capacity_mean_by_constraint", {})
    return uncertainty_data, capacity_mean, capacity_mean_by_constraint


def extract_kpis_for_comparison(plot_data: dict) -> dict:
    """Extract KPI data for comparison chart showing all available subsystems.
    
    Returns:
        Dict mapping subsystem names to {level, confidence}
    """
    if not plot_data or "kpis" not in plot_data:
        return {}
    
    kpis = plot_data["kpis"]
    result = {}
    
    # List of subsystems to extract
    subsystems = ["parcheggi", "spiaggia", "alberghi", "ristoranti"]
    
    # Try both key formats: underscore and space-separated
    for subsystem in subsystems:
        key_underscore = f"constraint_level_{subsystem}"
        key_space = f"constraint level {subsystem}"
        
        # Check underscore format first
        if key_underscore in kpis:
            val = kpis[key_underscore]
        elif key_space in kpis:
            val = kpis[key_space]
        else:
            val = None
        
        if val is not None:
            if isinstance(val, dict):
                result[subsystem] = {
                    "level": val.get("level", 0),
                    "confidence": val.get("confidence", 0)
                }
            elif isinstance(val, (int, float)):
                result[subsystem] = {"level": val, "confidence": 0}
    
    # Also add overtourism_level if available
    if "overtourism_level" in kpis:
        val = kpis["overtourism_level"]
        if isinstance(val, dict):
            result["overtourism_level"] = {
                "level": val.get("level", 0),
                "confidence": val.get("confidence", 0)
            }
        elif isinstance(val, (int, float)):
            result["overtourism_level"] = {"level": val, "confidence": 0}
    
    return result


def get_dash_for_group(group_name: str) -> str:
    """Get dash style for a group name."""
    dashes = {
        "parcheggi": "solid",
        "spiaggia": "dot",
        "alberghi": "dash",
        "ristoranti": "dashdot",
    }
    return dashes.get(group_name, "solid")


def generate_tourists_excursionists_chart(
    scenario_id: str,
    problem_id: str,
) -> dict:
    """Generate the Turisti/Escursionisti chart JSON for a scenario.
    
    Args:
        scenario_id: Scenario ID to fetch
        problem_id: Problem ID
        api_url: Backend API URL
        
    Returns:
        Plotly figure JSON dict
    """
    plot_data = load_plot_input(scenario_id, problem_id)
    if not plot_data:
        return {}
    
    curves, points, x_max, y_max = extract_plot_data_for_bidimensionale(plot_data)
    fig = build_tourists_excursionists_chart(curves, points, x_max, y_max)
    return json.loads(fig.to_json())


def generate_tourist_load_chart(
    scenario_id: str,
    problem_id: str,
    subsystem: str = "default",
) -> dict:
    """Generate the Tourist Load (Monodimensionale) chart JSON for a scenario.
    
    Args:
        scenario_id: Scenario ID to fetch
        problem_id: Problem ID
        subsystem: Subsystem to plot ('default' or constraint name)
        api_url: Backend API URL
        
    Returns:
        Plotly figure JSON dict
    """
    plot_data = load_plot_input(scenario_id, problem_id)
    if not plot_data:
        return {}
    
    uncertainty_data, capacity_mean, capacity_by_constraint = extract_plot_data_for_monodimensionale(plot_data)
    
    # Filter by subsystem if needed
    if subsystem != "default" and "kpis" in plot_data:
        kpis = plot_data["kpis"]
        by_constraint = kpis.get("uncertainty_by_constraint", {})
        if subsystem in by_constraint:
            uncertainty_data = by_constraint[subsystem]
    
    fig = build_tourist_load_chart(
        uncertainty_data,
        capacity_mean,
        subsystem,
        capacity_by_constraint
    )
    return json.loads(fig.to_json())


def generate_comparison_chart(
    scenario_left_id: str,
    scenario_right_id: str,
    problem_id: str,
    label_left: str = "Scenario 1",
    label_right: str = "Scenario 2",
) -> dict:
    """Generate comparison chart JSON between two scenarios.
    
    Args:
        scenario_left_id: Left scenario ID
        scenario_right_id: Right scenario ID
        problem_id: Problem ID
        label_left: Label for left scenario
        label_right: Label for right scenario
        api_url: Backend API URL
        
    Returns:
        Plotly figure JSON dict
    """
    plot_left = load_plot_input(scenario_left_id, problem_id)
    plot_right = load_plot_input(scenario_right_id, problem_id)
    
    if not plot_left or not plot_right:
        return {}
    
    kpis_left = extract_kpis_for_comparison(plot_left)
    kpis_right = extract_kpis_for_comparison(plot_right)
    
    fig = build_comparison_bar_chart(kpis_left, kpis_right, label_left, label_right)
    return json.loads(fig.to_json())


def generate_chart(chart_type: str, **kwargs) -> dict:
    """Generic chart generation function.
    
    Args:
        chart_type: Type of chart ('tourists_excursionists', 'tourist_load', 'comparison_bar')
        **kwargs: Additional arguments passed to specific functions
                  - scenario_id: for single-scenario charts
                  - scenario_left_id, scenario_right_id: for comparison
                  - problem_id: required
                  - subsystem: for tourist_load (default: 'default')
                
    Returns:
        Plotly figure JSON dict
    """
    print(f"Chart to generate: {chart_type}")
    if chart_type == "tourists_excursionists":
        return generate_tourists_excursionists_chart(
            kwargs.get("scenario_id", "scenario_base"),
            kwargs.get("problem_id", "parcheggi_molveno"),
        )
    elif chart_type == "tourist_load":
        return generate_tourist_load_chart(
            kwargs.get("scenario_id", "scenario_base"),
            kwargs.get("problem_id", "parcheggi_molveno"),
            kwargs.get("subsystem", "default"),
        )
    elif chart_type == "comparison_bar":
        return generate_comparison_chart(
            kwargs.get("scenario_left_id", "scenario_base"),
            kwargs.get("scenario_right_id", "scenario_allargamento_parcheggi_300"),
            kwargs.get("problem_id", "parcheggi_molveno"),
            kwargs.get("label_left", "Scenario 1"),
            kwargs.get("label_right", "Scenario 2"),
        )
    else:
        raise ValueError(f"Unsupported chart_type: {chart_type}")