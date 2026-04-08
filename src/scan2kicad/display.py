"""Notebook display helpers for schematic images."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from IPython.display import HTML, SVG, display
from IPython.display import Image as IPImage

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, Row

from .rendering import render_kicad_schematic


def display_schematic_from_row(row: Row) -> None:
    """Display a schematic from a Delta table row in a notebook."""
    if row["image"]:
        display(IPImage(data=row["image"]))
    else:
        svg = render_kicad_schematic(row["schematic"], fmt="svg")
        display(SVG(data=svg))


def display_schematic_gallery(df: DataFrame, n: int = 6, cols: int = 3) -> None:
    """Display a grid of schematics in a notebook."""
    rows = df.limit(n).collect()
    col_widths = " ".join(["1fr"] * cols)
    html = f'<div style="display:grid;grid-template-columns:{col_widths};gap:10px;">'

    for row in rows:
        b64 = base64.b64encode(row["image"]).decode()
        html += (
            '<div style="border:1px solid #ccc;padding:8px;">'
            f'<img src="data:image/png;base64,{b64}" style="width:100%;"/>'
            f'<p style="font-size:12px;margin-top:4px;"><b>{row["name"]}</b></p>'
            "</div>"
        )

    html += "</div>"
    display(HTML(html))
