"""Tests for SvgBuilder."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from scan2kicad.renderer.svg_builder import SvgBuilder


def _parse_svg(svg_str: str) -> ET.Element:
    return ET.fromstring(svg_str)


class TestSvgBuilder:
    def test_empty_svg(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        result = svg.to_string()
        root = _parse_svg(result)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"
        assert "viewBox" in root.attrib

    def test_has_background_rect(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100), background="#EEEEEE")
        result = svg.to_string()
        root = _parse_svg(result)
        rects = root.findall(".//{http://www.w3.org/2000/svg}rect")
        assert len(rects) >= 1
        assert rects[0].get("fill") == "#EEEEEE"

    def test_add_line(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.add_line(10, 20, 30, 40, "#FF0000", 0.5)
        result = svg.to_string()
        root = _parse_svg(result)
        lines = root.findall(".//{http://www.w3.org/2000/svg}line")
        assert len(lines) == 1
        assert lines[0].get("x1") == "10"
        assert lines[0].get("stroke") == "#FF0000"

    def test_add_rect(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.add_rect(10, 20, 30, 40, "#00FF00", 0.3)
        result = svg.to_string()
        root = _parse_svg(result)
        rects = root.findall(".//{http://www.w3.org/2000/svg}rect")
        # 1 background + 1 user rect
        assert len(rects) == 2

    def test_add_circle(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.add_circle(50, 50, 10, "#0000FF", 0.2)
        result = svg.to_string()
        root = _parse_svg(result)
        circles = root.findall(".//{http://www.w3.org/2000/svg}circle")
        assert len(circles) == 1
        assert circles[0].get("cx") == "50"

    def test_add_dot(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.add_dot(25, 25, 3, "#008000")
        result = svg.to_string()
        root = _parse_svg(result)
        circles = root.findall(".//{http://www.w3.org/2000/svg}circle")
        assert len(circles) == 1
        assert circles[0].get("fill") == "#008000"
        assert circles[0].get("stroke") == "none"

    def test_add_cross(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.add_cross(50, 50)
        result = svg.to_string()
        root = _parse_svg(result)
        lines = root.findall(".//{http://www.w3.org/2000/svg}line")
        assert len(lines) == 2  # X mark = 2 lines

    def test_add_text(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.add_text(10, 20, "Hello", size=2.0, color="#333333")
        result = svg.to_string()
        root = _parse_svg(result)
        texts = root.findall(".//{http://www.w3.org/2000/svg}text")
        assert len(texts) == 1
        assert texts[0].text == "Hello"

    def test_add_polyline(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.add_polyline([(10, 10), (20, 30), (40, 30)], "#000000", 0.5)
        result = svg.to_string()
        root = _parse_svg(result)
        pls = root.findall(".//{http://www.w3.org/2000/svg}polyline")
        assert len(pls) == 1

    def test_add_arc(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.add_arc((10, 50), (50, 10), (90, 50), "#000000", 0.3)
        result = svg.to_string()
        root = _parse_svg(result)
        paths = root.findall(".//{http://www.w3.org/2000/svg}path")
        assert len(paths) == 1
        assert "A" in paths[0].get("d", "")

    def test_group_nesting(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 100, 100))
        svg.open_group("translate(10,20)")
        svg.add_line(0, 0, 10, 10, "#000000", 0.1)
        svg.close_group()
        result = svg.to_string()
        root = _parse_svg(result)
        groups = root.findall(".//{http://www.w3.org/2000/svg}g")
        assert len(groups) >= 1
        assert "translate(10,20)" in groups[0].get("transform", "")
        # Line should be inside the group
        lines = groups[0].findall("{http://www.w3.org/2000/svg}line")
        assert len(lines) == 1

    def test_svg_is_valid_xml(self) -> None:
        svg = SvgBuilder(viewbox=(0, 0, 200, 150))
        svg.add_line(10, 10, 100, 100, "#000", 0.5)
        svg.add_circle(50, 50, 5, "#F00", 0.2)
        svg.add_text(30, 30, "Test")
        result = svg.to_string()
        # Should not raise
        root = ET.fromstring(result)
        assert root is not None
