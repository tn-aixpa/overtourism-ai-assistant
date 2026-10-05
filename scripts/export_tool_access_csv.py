"""
Export every registered tool's access-control metadata to a CSV.

Columns: tool_name, agent_tier, allowed_users, allowed_modes

`allowed_users` / `allowed_modes` are rendered as "ALL" when the tool
declares no restriction on that axis (ToolDefinition.allowed_roles /
allowed_modes is None), or as a comma-separated list of declared values
otherwise. User roles use privilege order (admin, multieditor, editor,
viewer); modes are sorted alphabetically.

Usage:
    python -m scripts.export_tool_access_csv [-o path/to/output.csv]

Run from the project root (so `app` is importable), or with the project
root on PYTHONPATH.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Allow running this script directly (`python scripts/export_tool_access_csv.py`)
# without the project root already being on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.tool_registry import _ensure_tool_registry  # noqa: E402

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "tool_access.csv"


def _format_access_set(values, *, preferred_order: tuple[str, ...] = ()) -> str:
    """None (unrestricted) -> "ALL"; otherwise ordered, comma-joined values."""
    if values is None:
        return "ALL"
    ordered = [value for value in preferred_order if value in values]
    ordered.extend(sorted(set(values) - set(ordered)))
    return ",".join(ordered)


def build_rows() -> list[dict[str, str]]:
    registry = _ensure_tool_registry()
    # Every registered tool, including disabled ones (e.g. summary_generation,
    # report_generation) — get_all_known_tools() filters those out, which is
    # right for tool *selection* but would silently drop rows from an audit
    # export, so list_tool_names()/get_tool() are used instead.
    tools = [registry.get_tool(name) for name in registry.list_tool_names()]

    rows = [
        {
            "tool_name": tool.name,
            "agent_tier": tool.agent_tier,
            "allowed_users": _format_access_set(
                tool.allowed_roles,
                preferred_order=("admin", "multieditor", "editor", "viewer"),
            ),
            "allowed_modes": _format_access_set(tool.allowed_modes),
        }
        for tool in tools
    ]
    rows.sort(key=lambda r: r["tool_name"])
    return rows


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["tool_name", "agent_tier", "allowed_users", "allowed_modes"]
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    rows = build_rows()
    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} tools to {args.output}")


if __name__ == "__main__":
    main()
