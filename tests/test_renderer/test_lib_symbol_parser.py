"""Tests for LibSymbolParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from scan2kicad.renderer.lib_symbol_parser import LibSymbolParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


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


class TestEmptyAndMinimal:
    def test_parse_empty_lib_symbols(self, small_sch: str) -> None:
        parser = LibSymbolParser(small_sch)
        assert parser.list_symbols() == []

    def test_minimal_content(self) -> None:
        content = '(kicad_sch (version 20231120) (generator "eeschema"))'
        parser = LibSymbolParser(content)
        assert parser.list_symbols() == []

    def test_unknown_symbol_returns_empty(self, rich_sch: str) -> None:
        parser = LibSymbolParser(rich_sch)
        gfx = parser.get_symbol_graphics("Nonexistent:Symbol")
        assert gfx.rectangles == []
        assert gfx.polylines == []
        assert gfx.arcs == []
        assert gfx.circles == []
        assert gfx.pins == []


class TestResistorSymbol:
    def test_parse_resistor_has_rectangle(self, rich_sch: str) -> None:
        parser = LibSymbolParser(rich_sch)
        assert "Device:R" in parser.list_symbols()
        gfx = parser.get_symbol_graphics("Device:R")
        assert len(gfx.rectangles) == 1
        rect = gfx.rectangles[0]
        assert rect.start.x == pytest.approx(-1.016)
        assert rect.end.x == pytest.approx(1.016)

    def test_parse_resistor_has_two_pins(self, rich_sch: str) -> None:
        parser = LibSymbolParser(rich_sch)
        gfx = parser.get_symbol_graphics("Device:R")
        assert len(gfx.pins) == 2
        pin_numbers = sorted(p.number for p in gfx.pins)
        assert pin_numbers == ["1", "2"]

    def test_resistor_pin_attributes(self, rich_sch: str) -> None:
        parser = LibSymbolParser(rich_sch)
        gfx = parser.get_symbol_graphics("Device:R")
        pin1 = next(p for p in gfx.pins if p.number == "1")
        assert pin1.position.x == pytest.approx(0.0)
        assert pin1.position.y == pytest.approx(3.81)
        assert pin1.rotation == pytest.approx(270.0)
        assert pin1.length == pytest.approx(1.27)
        assert pin1.pin_type == "passive"
        assert pin1.pin_shape == "line"


class TestMediumSymbol:
    def test_parse_medium_has_symbols(self, medium_sch: str) -> None:
        parser = LibSymbolParser(medium_sch)
        symbols = parser.list_symbols()
        assert len(symbols) > 0

    def test_medium_symbol_has_rectangles(self, medium_sch: str) -> None:
        parser = LibSymbolParser(medium_sch)
        sym_name = parser.list_symbols()[0]
        gfx = parser.get_symbol_graphics(sym_name)
        # Medium fixture has rectangles in its bus connector symbol
        assert len(gfx.rectangles) >= 1 or len(gfx.pins) >= 1


class TestComplexSymbols:
    """Tests against sample_complex.kicad_sch which has polylines, arcs, circles."""

    def test_has_multiple_symbols(self, complex_sch: str) -> None:
        parser = LibSymbolParser(complex_sch)
        symbols = parser.list_symbols()
        assert len(symbols) >= 3

    def test_has_polylines(self, complex_sch: str) -> None:
        """At least one symbol should have polyline body graphics."""
        parser = LibSymbolParser(complex_sch)
        total_polylines = 0
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            total_polylines += len(gfx.polylines)
        assert total_polylines >= 1

    def test_has_arcs(self, complex_sch: str) -> None:
        """At least one symbol should have arc graphics."""
        parser = LibSymbolParser(complex_sch)
        total_arcs = 0
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            total_arcs += len(gfx.arcs)
        assert total_arcs >= 1

    def test_has_circles(self, complex_sch: str) -> None:
        """At least one symbol should have circle graphics."""
        parser = LibSymbolParser(complex_sch)
        total_circles = 0
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            total_circles += len(gfx.circles)
        assert total_circles >= 1

    def test_has_pins(self, complex_sch: str) -> None:
        """Symbols should have pins."""
        parser = LibSymbolParser(complex_sch)
        total_pins = 0
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            total_pins += len(gfx.pins)
        assert total_pins >= 5

    def test_pin_types_are_valid(self, complex_sch: str) -> None:
        parser = LibSymbolParser(complex_sch)
        valid_types = {
            "input",
            "output",
            "bidirectional",
            "tri_state",
            "passive",
            "free",
            "unspecified",
            "power_in",
            "power_out",
            "open_collector",
            "open_emitter",
            "no_connect",
        }
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            for pin in gfx.pins:
                assert pin.pin_type in valid_types, (
                    f"Invalid pin type '{pin.pin_type}' in {sym_name}"
                )

    def test_polyline_has_multiple_points(self, complex_sch: str) -> None:
        parser = LibSymbolParser(complex_sch)
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            for pl in gfx.polylines:
                assert len(pl.points) >= 2

    def test_arc_has_distinct_points(self, complex_sch: str) -> None:
        parser = LibSymbolParser(complex_sch)
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            for arc in gfx.arcs:
                # start, mid, end should not all be identical
                assert not (arc.start == arc.mid == arc.end), f"Degenerate arc in {sym_name}"

    def test_circle_has_positive_radius(self, complex_sch: str) -> None:
        parser = LibSymbolParser(complex_sch)
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            for circ in gfx.circles:
                assert circ.radius > 0, f"Zero radius circle in {sym_name}"


class TestHierarchicalSymbols:
    def test_hierarchical_has_symbols(self, hierarchical_sch: str) -> None:
        parser = LibSymbolParser(hierarchical_sch)
        symbols = parser.list_symbols()
        assert len(symbols) >= 1

    def test_hierarchical_symbol_has_polylines(self, hierarchical_sch: str) -> None:
        """The hierarchical fixture has at least 1 polyline in lib_symbols."""
        parser = LibSymbolParser(hierarchical_sch)
        total_polylines = 0
        for sym_name in parser.list_symbols():
            gfx = parser.get_symbol_graphics(sym_name)
            total_polylines += len(gfx.polylines)
        assert total_polylines >= 1
