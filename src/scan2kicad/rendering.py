"""Component 3: KiCad File Rendering.

Approach A: kicad-cli subprocess (high fidelity, requires kicad installed).
Approach B: Pure-Python S-expression parsing + matplotlib (lightweight).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.figure import Figure


# ---------------------------------------------------------------------------
# Approach A: kicad-cli
# ---------------------------------------------------------------------------


def render_kicad_schematic(kicad_sch_content: str, fmt: str = "svg") -> bytes:
    """Render a .kicad_sch string to SVG or PNG using kicad-cli."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sch_path = os.path.join(tmpdir, "schematic.kicad_sch")
        out_path = os.path.join(tmpdir, f"output.{fmt}")

        with open(sch_path, "w") as f:
            f.write(kicad_sch_content)

        cmd = [
            "kicad-cli",
            "sch",
            "export",
            fmt,
            "--output",
            out_path,
            sch_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        with open(out_path, "rb") as f:
            return f.read()


def render_kicad_pcb(kicad_pcb_content: str, fmt: str = "svg") -> bytes:
    """Render a .kicad_pcb string to SVG or PNG using kicad-cli."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pcb_path = os.path.join(tmpdir, "board.kicad_pcb")
        out_path = os.path.join(tmpdir, f"output.{fmt}")

        with open(pcb_path, "w") as f:
            f.write(kicad_pcb_content)

        cmd = [
            "kicad-cli",
            "pcb",
            "export",
            fmt,
            "--output",
            out_path,
            pcb_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        with open(out_path, "rb") as f:
            return f.read()


# ---------------------------------------------------------------------------
# Approach B: matplotlib
# ---------------------------------------------------------------------------

# Multiline-aware: (wire ... (pts (xy x1 y1) (xy x2 y2)) ...)
_WIRE_PATTERN = re.compile(
    r"\(wire\s+\(pts\s+"
    r"\(xy\s+([\d.e+-]+)\s+([\d.e+-]+)\)\s+"
    r"\(xy\s+([\d.e+-]+)\s+([\d.e+-]+)\)\s*\)",
    re.DOTALL,
)

# Symbol placement: (symbol ... (at x y angle) ...)
_SYMBOL_AT_PATTERN = re.compile(
    r"\(symbol\s+\(lib_id\s+\"([^\"]+)\"\)"  # lib_id
    r".*?\(at\s+([\d.e+-]+)\s+([\d.e+-]+)\s+[\d.e+-]+\)",  # (at x y angle)
    re.DOTALL,
)

# Symbol property labels: (property "Reference" "R1" (at x y ...) ...)
_PROPERTY_PATTERN = re.compile(
    r'\(property\s+"Reference"\s+"([^"]+)"\s+'
    r"\(at\s+([\d.e+-]+)\s+([\d.e+-]+)",
    re.DOTALL,
)

# Junction markers: (junction (at x y))
_JUNCTION_PATTERN = re.compile(r"\(junction\s+\(at\s+([\d.e+-]+)\s+([\d.e+-]+)\)")

# No-connect markers: (no_connect (at x y))
_NO_CONNECT_PATTERN = re.compile(r"\(no_connect\s+\(at\s+([\d.e+-]+)\s+([\d.e+-]+)\)")

# Labels: (label "text" (at x y angle))
_LABEL_PATTERN = re.compile(
    r'\((?:label|global_label|hierarchical_label)\s+"([^"]+)"\s+'
    r"\(at\s+([\d.e+-]+)\s+([\d.e+-]+)",
    re.DOTALL,
)


def parse_kicad_wires(sch_content: str) -> list[tuple[float, float, float, float]]:
    """Extract wire segments from .kicad_sch S-expression."""
    return [
        (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _WIRE_PATTERN.finditer(sch_content)
    ]


def _parse_symbols(sch_content: str) -> list[tuple[str, float, float]]:
    """Extract symbol placements (lib_id, x, y) from top-level symbols only."""
    results = []
    # Only match symbols outside lib_symbols block
    # Find end of lib_symbols section
    lib_end = sch_content.find(")\n\n")
    body = sch_content[lib_end:] if lib_end > 0 else sch_content
    for m in _SYMBOL_AT_PATTERN.finditer(body):
        results.append((m.group(1), float(m.group(2)), float(m.group(3))))
    return results


def _parse_labels(sch_content: str) -> list[tuple[str, float, float]]:
    """Extract labels (text, x, y)."""
    return [
        (m.group(1), float(m.group(2)), float(m.group(3)))
        for m in _LABEL_PATTERN.finditer(sch_content)
    ]


def _parse_junctions(sch_content: str) -> list[tuple[float, float]]:
    """Extract junction points."""
    return [(float(m.group(1)), float(m.group(2))) for m in _JUNCTION_PATTERN.finditer(sch_content)]


def _parse_references(sch_content: str) -> list[tuple[str, float, float]]:
    """Extract component reference designators with positions."""
    return [
        (m.group(1), float(m.group(2)), float(m.group(3)))
        for m in _PROPERTY_PATTERN.finditer(sch_content)
    ]


def render_schematic_matplotlib(sch_content: str) -> Figure:
    """Schematic rendering using matplotlib with wires, symbols, and labels."""
    import matplotlib.pyplot as plt

    wires = parse_kicad_wires(sch_content)
    symbols = _parse_symbols(sch_content)
    labels = _parse_labels(sch_content)
    junctions = _parse_junctions(sch_content)
    references = _parse_references(sch_content)

    fig, ax = plt.subplots(1, 1, figsize=(16, 12))

    # Draw wires
    for x1, y1, x2, y2 in wires:
        ax.plot([x1, x2], [-y1, -y2], "b-", linewidth=0.5)

    # Draw symbol locations
    if symbols:
        sx = [x for _, x, _ in symbols]
        sy = [-y for _, _, y in symbols]
        ax.scatter(sx, sy, marker="s", c="red", s=30, zorder=5, alpha=0.7)

    # Draw junctions
    if junctions:
        jx = [x for x, _ in junctions]
        jy = [-y for _, y in junctions]
        ax.scatter(jx, jy, marker="o", c="green", s=15, zorder=6)

    # Draw reference designators
    for ref, x, y in references:
        ax.annotate(
            ref,
            (x, -y),
            fontsize=5,
            color="darkred",
            ha="center",
            va="bottom",
            zorder=7,
        )

    # Draw labels (net names, global labels)
    for text, x, y in labels:
        ax.annotate(
            text,
            (x, -y),
            fontsize=5,
            color="darkgreen",
            ha="center",
            va="top",
            zorder=7,
            bbox={"boxstyle": "round,pad=0.1", "fc": "lightyellow", "ec": "gray", "lw": 0.3},
        )

    ax.set_aspect("equal")
    n_elements = len(wires) + len(symbols) + len(labels) + len(junctions)
    ax.set_title(
        f"KiCad Schematic Preview — {len(wires)} wires, "
        f"{len(symbols)} components, {len(labels)} labels"
    )
    if n_elements == 0:
        ax.text(
            0.5,
            0.5,
            "No elements parsed",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=14,
            color="gray",
        )
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Spark UDF for batch rendering
# ---------------------------------------------------------------------------


def make_render_udf():
    """Return a Spark UDF that renders .kicad_sch content to PNG bytes."""
    from pyspark.sql.functions import udf
    from pyspark.sql.types import BinaryType

    @udf(BinaryType())
    def render_sch_udf(sch_content: str) -> bytes:
        return render_kicad_schematic(sch_content, fmt="png")

    return render_sch_udf
