"""Tests for the rendering pipeline."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scan2kicad.renderer import render_schematic_svg

FIXTURES = Path(__file__).parent.parent / "fixtures"

NS = "{http://www.w3.org/2000/svg}"


@pytest.fixture()
def small_sch() -> str:
    return (FIXTURES / "sample_small.kicad_sch").read_text()


@pytest.fixture()
def medium_sch() -> str:
    return (FIXTURES / "sample_medium.kicad_sch").read_text()


@pytest.fixture()
def rich_sch() -> str:
    return (FIXTURES / "sample_rich.kicad_sch").read_text()


class TestRenderPipeline:
    def test_render_returns_string(self, small_sch: str) -> None:
        result = render_schematic_svg(small_sch)
        assert isinstance(result, str)
        assert result.startswith("<?xml")

    def test_render_small_is_valid_svg(self, small_sch: str) -> None:
        result = render_schematic_svg(small_sch)
        root = ET.fromstring(result)
        tag = root.tag.replace(NS, "")
        assert tag == "svg"
        assert "viewBox" in root.attrib

    def test_render_medium_has_wires(self, medium_sch: str) -> None:
        result = render_schematic_svg(medium_sch)
        root = ET.fromstring(result)
        lines = root.findall(f".//{NS}line")
        # Should have wire lines
        assert len(lines) > 0

    def test_render_rich_has_components(self, rich_sch: str) -> None:
        result = render_schematic_svg(rich_sch)
        root = ET.fromstring(result)
        # Should have groups for symbols
        groups = root.findall(f".//{NS}g")
        assert len(groups) > 0
        # Should have rect for resistor body
        rects = root.findall(f".//{NS}rect")
        assert len(rects) >= 2  # background + at least one component

    def test_render_rich_has_junctions(self, rich_sch: str) -> None:
        result = render_schematic_svg(rich_sch)
        root = ET.fromstring(result)
        # Junction = filled circle with stroke=none
        circles = root.findall(f".//{NS}circle")
        filled = [c for c in circles if c.get("stroke") == "none"]
        assert len(filled) >= 1

    def test_render_rich_has_labels(self, rich_sch: str) -> None:
        result = render_schematic_svg(rich_sch)
        root = ET.fromstring(result)
        texts = root.findall(f".//{NS}text")
        assert len(texts) > 0

    def test_render_empty_minimal(self) -> None:
        content = '(kicad_sch (version 20231120) (generator "eeschema"))'
        result = render_schematic_svg(content)
        root = ET.fromstring(result)
        tag = root.tag.replace(NS, "")
        assert tag == "svg"

    def test_custom_colors(self, small_sch: str) -> None:
        result = render_schematic_svg(
            small_sch,
            background="#000000",
            wire_color="#FF0000",
        )
        root = ET.fromstring(result)
        # Background rect should be black
        rects = root.findall(f".//{NS}rect")
        assert rects[0].get("fill") == "#000000"
