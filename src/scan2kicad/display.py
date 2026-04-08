"""Notebook display helpers for schematic images."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from IPython.display import HTML, SVG, display
from IPython.display import Image as IPImage

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, Row

from .rendering import render_kicad_schematic


def _extract_image_bytes(image_field: object) -> bytes | None:
    """Extract raw bytes from an image column.

    HuggingFace datasets store images as structs with a ``bytes`` field.
    If the column is already raw bytes, return as-is.
    """
    if image_field is None:
        return None
    if isinstance(image_field, (bytes, bytearray)):
        return bytes(image_field)
    # HF struct: Row(bytes=b'...', path='...')
    if hasattr(image_field, "bytes"):
        raw = getattr(image_field, "bytes")
        return raw if isinstance(raw, bytes) else None
    if isinstance(image_field, dict):
        val = image_field.get("bytes")  # ty: ignore[invalid-argument-type]
        return val if isinstance(val, bytes) else None
    return None


def display_schematic_from_row(row: Row) -> None:
    """Display a schematic from a Delta table row in a notebook."""
    img_bytes = _extract_image_bytes(row["image"])
    if img_bytes:
        display(IPImage(data=img_bytes))
    else:
        svg = render_kicad_schematic(row["schematic"], fmt="svg")
        display(SVG(data=svg))


def display_schematic_gallery(df: DataFrame, n: int = 6, cols: int = 3) -> None:
    """Display a grid of schematics in a notebook."""
    rows = df.limit(n).collect()
    col_widths = " ".join(["1fr"] * cols)
    html = f'<div style="display:grid;grid-template-columns:{col_widths};gap:10px;">'

    for row in rows:
        img_bytes = _extract_image_bytes(row["image"])
        if img_bytes is None:
            continue
        b64 = base64.b64encode(img_bytes).decode()
        html += (
            '<div style="border:1px solid #ccc;padding:8px;">'
            f'<img src="data:image/png;base64,{b64}" style="width:100%;"/>'
            f'<p style="font-size:12px;margin-top:4px;"><b>{row["name"]}</b></p>'
            "</div>"
        )

    html += "</div>"
    display(HTML(html))
