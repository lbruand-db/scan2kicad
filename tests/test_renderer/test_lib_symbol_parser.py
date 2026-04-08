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


class TestLibSymbolParser:
    def test_parse_empty_lib_symbols(self, small_sch: str) -> None:
        parser = LibSymbolParser(small_sch)
        # small_sch has empty lib_symbols
        assert parser.list_symbols() == []

    def test_parse_resistor_symbol(self, rich_sch: str) -> None:
        parser = LibSymbolParser(rich_sch)
        assert "Device:R" in parser.list_symbols()

        gfx = parser.get_symbol_graphics("Device:R")
        # R_0_1 has 1 rectangle (body)
        assert len(gfx.rectangles) == 1
        rect = gfx.rectangles[0]
        assert rect.start.x == pytest.approx(-1.016)
        assert rect.end.x == pytest.approx(1.016)

        # R_1_1 has 2 pins
        assert len(gfx.pins) == 2
        pin_numbers = sorted(p.number for p in gfx.pins)
        assert pin_numbers == ["1", "2"]

    def test_parse_medium_symbol(self, medium_sch: str) -> None:
        parser = LibSymbolParser(medium_sch)
        symbols = parser.list_symbols()
        assert len(symbols) > 0

    def test_unknown_symbol_returns_empty(self, rich_sch: str) -> None:
        parser = LibSymbolParser(rich_sch)
        gfx = parser.get_symbol_graphics("Nonexistent:Symbol")
        assert gfx.rectangles == []
        assert gfx.polylines == []
        assert gfx.arcs == []
        assert gfx.circles == []
        assert gfx.pins == []

    def test_pin_has_correct_attributes(self, rich_sch: str) -> None:
        parser = LibSymbolParser(rich_sch)
        gfx = parser.get_symbol_graphics("Device:R")
        pin1 = next(p for p in gfx.pins if p.number == "1")
        assert pin1.position.x == pytest.approx(0.0)
        assert pin1.position.y == pytest.approx(3.81)
        assert pin1.rotation == pytest.approx(270.0)
        assert pin1.length == pytest.approx(1.27)
        assert pin1.pin_type == "passive"
        assert pin1.pin_shape == "line"

    def test_minimal_content(self) -> None:
        content = '(kicad_sch (version 20231120) (generator "eeschema"))'
        parser = LibSymbolParser(content)
        assert parser.list_symbols() == []
