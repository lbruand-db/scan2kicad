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


@pytest.fixture()
def complex_sch() -> str:
    return (FIXTURES / "sample_complex.kicad_sch").read_text()


@pytest.fixture()
def hierarchical_sch() -> str:
    return (FIXTURES / "sample_hierarchical.kicad_sch").read_text()


def _svg_root(svg_str: str) -> ET.Element:
    return ET.fromstring(svg_str)


def _count(root: ET.Element, tag: str) -> int:
    return len(root.findall(f".//{NS}{tag}"))


# ---------------------------------------------------------------------------
# Basic rendering tests
# ---------------------------------------------------------------------------


class TestRenderBasics:
    def test_render_returns_string(self, small_sch: str) -> None:
        result = render_schematic_svg(small_sch)
        assert isinstance(result, str)
        assert result.startswith("<?xml")

    def test_render_small_is_valid_svg(self, small_sch: str) -> None:
        root = _svg_root(render_schematic_svg(small_sch))
        assert root.tag.replace(NS, "") == "svg"
        assert "viewBox" in root.attrib

    def test_render_empty_minimal(self) -> None:
        content = '(kicad_sch (version 20231120) (generator "eeschema"))'
        root = _svg_root(render_schematic_svg(content))
        assert root.tag.replace(NS, "") == "svg"

    def test_custom_colors(self, small_sch: str) -> None:
        root = _svg_root(render_schematic_svg(small_sch, background="#000000"))
        rects = root.findall(f".//{NS}rect")
        assert rects[0].get("fill") == "#000000"

    @pytest.mark.parametrize(
        "fixture_name",
        ["sample_small", "sample_medium", "sample_rich", "sample_complex", "sample_hierarchical"],
    )
    def test_all_fixtures_produce_valid_svg(self, fixture_name: str) -> None:
        content = (FIXTURES / f"{fixture_name}.kicad_sch").read_text()
        root = _svg_root(render_schematic_svg(content))
        assert root.tag.replace(NS, "") == "svg"
        assert "viewBox" in root.attrib


# ---------------------------------------------------------------------------
# Wire rendering
# ---------------------------------------------------------------------------


class TestWires:
    def test_medium_has_wire_lines(self, medium_sch: str) -> None:
        root = _svg_root(render_schematic_svg(medium_sch))
        assert _count(root, "line") > 0

    def test_rich_has_multiple_wires(self, rich_sch: str) -> None:
        root = _svg_root(render_schematic_svg(rich_sch))
        # 5 wires → at least 5 line elements (may have more from pins etc.)
        assert _count(root, "line") >= 5

    def test_complex_has_many_wires(self, complex_sch: str) -> None:
        root = _svg_root(render_schematic_svg(complex_sch))
        assert _count(root, "line") >= 15


# ---------------------------------------------------------------------------
# Junction rendering
# ---------------------------------------------------------------------------


class TestJunctions:
    def test_rich_has_junction_dots(self, rich_sch: str) -> None:
        root = _svg_root(render_schematic_svg(rich_sch))
        circles = root.findall(f".//{NS}circle")
        filled = [c for c in circles if c.get("stroke") == "none"]
        assert len(filled) >= 1

    def test_complex_has_multiple_junctions(self, complex_sch: str) -> None:
        root = _svg_root(render_schematic_svg(complex_sch))
        circles = root.findall(f".//{NS}circle")
        filled = [c for c in circles if c.get("stroke") == "none"]
        assert len(filled) >= 3

    def test_hierarchical_has_junction(self, hierarchical_sch: str) -> None:
        root = _svg_root(render_schematic_svg(hierarchical_sch))
        circles = root.findall(f".//{NS}circle")
        filled = [c for c in circles if c.get("stroke") == "none"]
        assert len(filled) >= 1


# ---------------------------------------------------------------------------
# No-connect rendering
# ---------------------------------------------------------------------------


class TestNoConnects:
    def test_complex_has_no_connects(self, complex_sch: str) -> None:
        """No-connects render as X marks (2 lines each). 6 no-connects = 12 lines."""
        root = _svg_root(render_schematic_svg(complex_sch))
        # Total lines includes wires + no-connect X marks + pin lines
        # At minimum, 6 no-connects contribute 12 lines
        assert _count(root, "line") >= 15 + 12  # wires + no-connect crosses


# ---------------------------------------------------------------------------
# Label rendering
# ---------------------------------------------------------------------------


class TestLabels:
    def test_rich_has_local_labels(self, rich_sch: str) -> None:
        root = _svg_root(render_schematic_svg(rich_sch))
        texts = root.findall(f".//{NS}text")
        assert len(texts) >= 3  # 3 local labels

    def test_complex_has_hierarchical_labels(self, complex_sch: str) -> None:
        root = _svg_root(render_schematic_svg(complex_sch))
        texts = root.findall(f".//{NS}text")
        # 4 hierarchical labels + component ref/value texts
        assert len(texts) >= 4

    def test_hierarchical_has_many_labels(self, hierarchical_sch: str) -> None:
        root = _svg_root(render_schematic_svg(hierarchical_sch))
        texts = root.findall(f".//{NS}text")
        # 10 local + 2 global + 2 hierarchical + ref/value texts
        assert len(texts) >= 10

    def test_medium_has_global_label(self, medium_sch: str) -> None:
        root = _svg_root(render_schematic_svg(medium_sch))
        texts = root.findall(f".//{NS}text")
        assert len(texts) >= 1


# ---------------------------------------------------------------------------
# Symbol / component rendering
# ---------------------------------------------------------------------------


class TestSymbols:
    def test_small_has_power_symbol_group(self, small_sch: str) -> None:
        root = _svg_root(render_schematic_svg(small_sch))
        groups = root.findall(f".//{NS}g")
        # At least 1 group for the GND power symbol
        assert len(groups) >= 1

    def test_rich_has_resistor_rect(self, rich_sch: str) -> None:
        root = _svg_root(render_schematic_svg(rich_sch))
        rects = root.findall(f".//{NS}rect")
        # background + at least 1 resistor body rectangle
        assert len(rects) >= 2

    def test_complex_has_multiple_symbol_groups(self, complex_sch: str) -> None:
        root = _svg_root(render_schematic_svg(complex_sch))
        groups = root.findall(f".//{NS}g")
        # 5 placed symbols → at least 5 groups
        assert len(groups) >= 5

    def test_complex_has_reference_texts(self, complex_sch: str) -> None:
        root = _svg_root(render_schematic_svg(complex_sch))
        texts = root.findall(f".//{NS}text")
        text_content = [t.text for t in texts if t.text]
        # Should contain component references
        assert any(t for t in text_content if t and t[0] in "RCULJDQ")


# ---------------------------------------------------------------------------
# Polyline rendering (lib_symbol body graphics)
# ---------------------------------------------------------------------------


class TestPolylines:
    def test_complex_has_polylines(self, complex_sch: str) -> None:
        """Complex schematic has 16 polylines in lib_symbols (transistor/IC bodies)."""
        root = _svg_root(render_schematic_svg(complex_sch))
        polylines = root.findall(f".//{NS}polyline")
        assert len(polylines) >= 1


# ---------------------------------------------------------------------------
# Arc rendering
# ---------------------------------------------------------------------------


class TestArcs:
    def test_complex_has_arcs(self, complex_sch: str) -> None:
        """Complex schematic has 1 arc in lib_symbols."""
        root = _svg_root(render_schematic_svg(complex_sch))
        paths = root.findall(f".//{NS}path")
        # Arcs render as SVG <path> with arc commands
        assert len(paths) >= 1


# ---------------------------------------------------------------------------
# Circle rendering
# ---------------------------------------------------------------------------


class TestCircles:
    def test_complex_has_stroked_circles(self, complex_sch: str) -> None:
        """Complex schematic has circles in lib_symbols (e.g., transistor body)."""
        root = _svg_root(render_schematic_svg(complex_sch))
        circles = root.findall(f".//{NS}circle")
        stroked = [c for c in circles if c.get("stroke") != "none"]
        assert len(stroked) >= 1


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------


class TestText:
    def test_complex_has_free_text(self, complex_sch: str) -> None:
        root = _svg_root(render_schematic_svg(complex_sch))
        texts = root.findall(f".//{NS}text")
        assert len(texts) >= 1


# ---------------------------------------------------------------------------
# Hierarchical sheets
# ---------------------------------------------------------------------------


class TestBuses:
    def test_hierarchical_has_bus_lines(self, hierarchical_sch: str) -> None:
        """Hierarchical schematic has 33 buses — rendered as thick lines."""
        root = _svg_root(render_schematic_svg(hierarchical_sch))
        # Buses are thicker lines; total lines should be substantial
        assert _count(root, "line") >= 19  # at least the 19 wires


class TestSheets:
    def test_hierarchical_produces_valid_svg(self, hierarchical_sch: str) -> None:
        """Schematic with 2 sheets, 33 buses renders without error."""
        root = _svg_root(render_schematic_svg(hierarchical_sch))
        assert root.tag.replace(NS, "") == "svg"
        # Should have substantial content
        total_elements = (
            _count(root, "line")
            + _count(root, "rect")
            + _count(root, "circle")
            + _count(root, "text")
            + _count(root, "polyline")
        )
        assert total_elements >= 20
