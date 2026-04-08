"""Shared fixtures for scan2kicad tests."""

from __future__ import annotations

import io

import pytest
from PIL import Image


@pytest.fixture()
def sample_kicad_sch() -> str:
    """Minimal .kicad_sch S-expression with two wires."""
    return (
        "(kicad_sch (version 20230121)\n"
        "  (wire (pts (xy 100.0 50.0) (xy 200.0 50.0)) (stroke (width 0)))\n"
        "  (wire (pts (xy 200.0 50.0) (xy 200.0 150.0)) (stroke (width 0)))\n"
        "  (wire (pts (xy 50.5 25.3) (xy 75.8 25.3)) (stroke (width 0)))\n"
        ")"
    )


@pytest.fixture()
def tiny_png_bytes() -> bytes:
    """A 1x1 red PNG image as bytes."""
    img = Image.new("RGB", (1, 1), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
