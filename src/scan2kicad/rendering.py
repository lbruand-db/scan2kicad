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

_WIRE_PATTERN = re.compile(
    r"\(wire\s+\(pts\s+"
    r"\(xy\s+([\d.e+-]+)\s+([\d.e+-]+)\)\s+"
    r"\(xy\s+([\d.e+-]+)\s+([\d.e+-]+)\)\)"
)


def parse_kicad_wires(sch_content: str) -> list[tuple[float, float, float, float]]:
    """Extract wire segments from .kicad_sch S-expression."""
    return [
        (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _WIRE_PATTERN.finditer(sch_content)
    ]


def render_schematic_matplotlib(sch_content: str) -> Figure:
    """Basic schematic rendering using matplotlib (wires only)."""
    import matplotlib.pyplot as plt

    wires = parse_kicad_wires(sch_content)
    fig, ax = plt.subplots(1, 1, figsize=(16, 12))

    for x1, y1, x2, y2 in wires:
        ax.plot([x1, x2], [-y1, -y2], "b-", linewidth=0.5)

    ax.set_aspect("equal")
    ax.set_title("KiCad Schematic (wire-level preview)")
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
