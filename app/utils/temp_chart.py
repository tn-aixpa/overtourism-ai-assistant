import json
from datetime import datetime, timedelta
import random

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def build_line_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["temperature"],
        name="Temperature (°C)", mode="lines",
        line=dict(color="#1D9E75", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["humidity"],
        name="Humidity (%)", mode="lines",
        line=dict(color="#378ADD", width=2),
        yaxis="y2",
    ))
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", showgrid=False),
    )

    return fig


def build_bar_chart(df: pd.DataFrame) -> go.Figure:
    fig = px.bar(df, x="month", y="revenue", color="category",
                    labels={"revenue": "Revenue (€)", "month": "Month"})
    return fig



BUILDERS = {
    "line":    build_line_chart,
    "bar":     build_bar_chart
}


def apply_common_layout(fig: go.Figure, title: str) -> None:
    """Apply shared layout settings (theme-neutral, client handles dark mode)."""
    fig.update_layout(
        title=title or None,
        paper_bgcolor="rgba(0,0,0,0)",   # transparent — let the client apply bg
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="sans-serif", size=13),
        margin=dict(l=48, r=24, t=40 if title else 16, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False)



def load_dataset(name: str) -> pd.DataFrame:
    """
    Load and filter a dataset by name.
    Replace this function with real DB queries, file reads, API calls, etc.
    """
    if name == "line":
        dates = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(168)]
        df = pd.DataFrame({
            "timestamp": dates,
            "temperature": [20 + 5 * (0.5 - random.random()) + (i % 24) * 0.3 for i in range(168)],
            "humidity":    [60 + 10 * (0.5 - random.random()) for _ in range(168)],
        })
    elif name == "bar":
        months = pd.date_range("2024-01", periods=12, freq="MS")
        df = pd.DataFrame({
            "month":    months,
            "revenue":  [random.randint(80_000, 150_000) for _ in range(12)],
            "units":    [random.randint(200, 600) for _ in range(12)],
            "category": ["Q1","Q1","Q1","Q2","Q2","Q2","Q3","Q3","Q3","Q4","Q4","Q4"],
        })

    return df
# ---------------------------------------------------------------------------
# Endpoint mock
# ---------------------------------------------------------------------------

def generate_chart(chart_type) -> dict:
    
    df = load_dataset(chart_type)

    if chart_type == "line":
        fig = build_line_chart(df)
    elif chart_type == "bar":
        fig = build_bar_chart(df)
    else:
        return None

    apply_common_layout(fig, "Sample Chart")

    figure_json = json.loads(fig.to_json())

    return figure_json