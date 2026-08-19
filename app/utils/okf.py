"""
Minimal reader for Open Knowledge Format (OKF) bundles.

OKF (https://cloud.google.com/blog/products/data-analytics/how-the-open-
knowledge-format-can-improve-data-sharing) represents knowledge as a
directory of markdown files, each with a small YAML-style frontmatter block
(only "type" is required by the spec) and a markdown body. Concepts link to
each other with normal markdown links; the file layout is the graph.

This module is intentionally small and dependency-free (no PyYAML) because
the frontmatter this app writes is flat: scalars and one-level string lists.
That covers every field used by app.utils.knowledge. If a bundle ever needs
nested structures, swap this for a real YAML parser — nothing else in the
app needs to change, since callers only see the dict/str this module
returns.

This is a *reader*. Producing/editing bundle files is just editing markdown
by hand (that's the point of OKF) — there is no writer here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def _parse_scalar(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw


def _parse_list(raw: str) -> List[str]:
    """Parse a flow-style YAML list: `[a, "b c", d]` -> ["a", "b c", "d"]."""
    inner = raw.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    if not inner.strip():
        return []
    items = []
    for part in inner.split(","):
        part = part.strip()
        if part:
            items.append(_parse_scalar(part))
    return items


def parse_frontmatter(raw: str) -> Dict[str, Any]:
    """Parse a flat frontmatter block (between the two `---` fences) into a
    dict of str -> (str | List[str])."""
    fields: Dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("["):
            fields[key] = _parse_list(value)
        else:
            fields[key] = _parse_scalar(value)
    return fields


def parse_document(text: str) -> "OkfDocument":
    """Split a markdown file into (frontmatter dict, body str)."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm_raw = text[3:end]
            body = text[end + 4 :].lstrip("\n")
            return OkfDocument(frontmatter=parse_frontmatter(fm_raw), body=body)
    return OkfDocument(frontmatter={}, body=text)


class OkfDocument:
    def __init__(self, frontmatter: Dict[str, Any], body: str):
        self.frontmatter = frontmatter
        self.body = body

    @property
    def type(self) -> Optional[str]:
        return self.frontmatter.get("type")

    @property
    def title(self) -> str:
        return self.frontmatter.get("title") or self._h1_from_body() or ""

    def _h1_from_body(self) -> Optional[str]:
        for line in self.body.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            if line:
                break
        return None

    def first_paragraph(self) -> str:
        """Body text up to the first '## ' heading (or end of doc), with the
        leading '# Title' heading stripped if present. This is the
        definition/summary text for concept documents."""
        lines = self.body.splitlines()
        collected = []
        for line in lines:
            if line.strip().startswith("## "):
                break
            if line.strip().startswith("# "):
                continue
            collected.append(line)
        return "\n".join(collected).strip()

    def bullet_section(self, heading: str) -> List[str]:
        """Bullet items (`- ...`) under a `## {heading}` section."""
        lines = self.body.splitlines()
        items: List[str] = []
        in_section = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                in_section = stripped[3:].strip().lower() == heading.lower()
                continue
            if in_section and stripped.startswith("- "):
                items.append(stripped[2:].strip())
        return items


def load_bundle(root: Path, okf_type: Optional[str] = None) -> List[OkfDocument]:
    """Load every *.md file under `root`, optionally filtered to a single
    OKF `type`.

    Order: an optional numeric `order` frontmatter field first (for
    producers that care about presentation order, e.g. the glossary block
    injected into prompts), then filesystem path, for determinism."""
    if not root.exists():
        logger.error(f"OKF bundle directory not found: {root}")
        return []

    docs = []
    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error(f"Could not read OKF document {path}: {e}")
            continue
        doc = parse_document(text)
        doc.path = path  # type: ignore[attr-defined]
        if okf_type is None or doc.type == okf_type:
            docs.append(doc)

    def _sort_key(doc: OkfDocument):
        order = doc.frontmatter.get("order")
        try:
            order = int(order)
        except (TypeError, ValueError):
            order = 9999
        return (order, str(doc.path))  # type: ignore[attr-defined]

    docs.sort(key=_sort_key)
    return docs
