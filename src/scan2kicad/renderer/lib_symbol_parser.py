"""Parse lib_symbols from .kicad_sch content using sexpdata.

kicad-sch-api's _parse_lib_symbols() returns {}, so we use sexpdata
directly to extract symbol body graphics (rectangles, polylines, arcs,
circles, pins) from the lib_symbols section.
"""

from __future__ import annotations

import sexpdata

from .types import Arc, Circle, PinGraphic, Point, Polyline, Rect, SymbolGraphics


def _sym(name: str) -> sexpdata.Symbol:
    return sexpdata.Symbol(name)


def _find(sexp: list, tag: str) -> list | None:
    """Find first sub-expression with the given tag."""
    for item in sexp:
        if isinstance(item, list) and len(item) > 0 and item[0] == _sym(tag):
            return item
    return None


def _find_all(sexp: list, tag: str) -> list[list]:
    """Find all sub-expressions with the given tag."""
    return [
        item for item in sexp if isinstance(item, list) and len(item) > 0 and item[0] == _sym(tag)
    ]


def _get_float(sexp: list, tag: str, default: float = 0.0) -> float:
    """Extract a float value from (tag value)."""
    node = _find(sexp, tag)
    if node and len(node) > 1:
        try:
            return float(node[1])
        except (ValueError, TypeError):
            return default
    return default


def _parse_point(sexp: list) -> Point:
    """Parse (xy x y) into a Point."""
    return Point(float(sexp[1]), float(sexp[2]))


def _parse_stroke_width(sexp: list) -> float:
    stroke = _find(sexp, "stroke")
    if stroke:
        return _get_float(stroke, "width", 0.254)
    return 0.254


def _parse_fill_type(sexp: list) -> str:
    fill = _find(sexp, "fill")
    if fill:
        ft = _find(fill, "type")
        if ft and len(ft) > 1:
            val = ft[1]
            return val.value() if isinstance(val, sexpdata.Symbol) else str(val)
    return "none"


def _parse_rectangle(sexp: list) -> Rect:
    start_node = _find(sexp, "start")
    end_node = _find(sexp, "end")
    start = Point(float(start_node[1]), float(start_node[2]))
    end = Point(float(end_node[1]), float(end_node[2]))
    return Rect(
        start=start,
        end=end,
        stroke_width=_parse_stroke_width(sexp),
        fill=_parse_fill_type(sexp),
    )


def _parse_polyline(sexp: list) -> Polyline:
    pts_node = _find(sexp, "pts")
    points = tuple(_parse_point(xy) for xy in _find_all(pts_node, "xy"))
    return Polyline(
        points=points,
        stroke_width=_parse_stroke_width(sexp),
        fill=_parse_fill_type(sexp),
    )


def _parse_arc(sexp: list) -> Arc:
    start_node = _find(sexp, "start")
    mid_node = _find(sexp, "mid")
    end_node = _find(sexp, "end")
    return Arc(
        start=Point(float(start_node[1]), float(start_node[2])),
        mid=Point(float(mid_node[1]), float(mid_node[2])),
        end=Point(float(end_node[1]), float(end_node[2])),
        stroke_width=_parse_stroke_width(sexp),
        fill=_parse_fill_type(sexp),
    )


def _parse_circle(sexp: list) -> Circle:
    center_node = _find(sexp, "center")
    radius_val = _get_float(sexp, "radius")
    return Circle(
        center=Point(float(center_node[1]), float(center_node[2])),
        radius=radius_val,
        stroke_width=_parse_stroke_width(sexp),
        fill=_parse_fill_type(sexp),
    )


def _parse_pin(sexp: list) -> PinGraphic:
    """Parse (pin type shape (at x y rot) (length l) (name ...) (number ...))."""
    pin_type = sexp[1].value() if isinstance(sexp[1], sexpdata.Symbol) else str(sexp[1])
    pin_shape = sexp[2].value() if isinstance(sexp[2], sexpdata.Symbol) else str(sexp[2])

    at_node = _find(sexp, "at")
    x, y = float(at_node[1]), float(at_node[2])
    rotation = float(at_node[3]) if len(at_node) > 3 else 0.0

    length = _get_float(sexp, "length", 2.54)

    name_node = _find(sexp, "name")
    name = ""
    if name_node and len(name_node) > 1:
        name = str(name_node[1])

    number_node = _find(sexp, "number")
    number = ""
    if number_node and len(number_node) > 1:
        number = str(number_node[1])

    return PinGraphic(
        position=Point(x, y),
        length=length,
        rotation=rotation,
        name=name,
        number=number,
        pin_type=pin_type,
        pin_shape=pin_shape,
    )


class LibSymbolParser:
    """Extracts symbol graphics from the lib_symbols section of a .kicad_sch file."""

    def __init__(self, kicad_sch_content: str) -> None:
        self._symbols: dict[str, list] = {}
        self._parse(kicad_sch_content)

    def _parse(self, content: str) -> None:
        tree = sexpdata.loads(content)
        lib_symbols = _find(tree, "lib_symbols")
        if not lib_symbols:
            return
        for sym in _find_all(lib_symbols, "symbol"):
            if len(sym) > 1:
                name = str(sym[1]).strip('"')
                self._symbols[name] = sym

    def list_symbols(self) -> list[str]:
        return list(self._symbols.keys())

    def get_symbol_graphics(self, lib_id: str, unit: int = 1) -> SymbolGraphics:
        """Get drawable elements, merging shared (unit 0) and unit-specific graphics."""
        sym = self._symbols.get(lib_id)
        if sym is None:
            return SymbolGraphics()

        graphics = SymbolGraphics()
        short_name = lib_id.split(":")[-1] if ":" in lib_id else lib_id

        # Collect sub-symbols: unit 0 (shared) + requested unit
        for sub in _find_all(sym, "symbol"):
            if len(sub) < 2:
                continue
            sub_name = str(sub[1]).strip('"')
            # Match patterns like "R_0_1" (shared) and "R_1_1" (unit 1)
            parts = sub_name.rsplit("_", 2)
            if len(parts) >= 3:
                try:
                    sub_unit = int(parts[-2])
                except ValueError:
                    continue
                if sub_unit not in (0, unit):
                    continue
            elif sub_name != short_name:
                continue

            # Extract graphic elements from this sub-symbol
            for rect in _find_all(sub, "rectangle"):
                graphics.rectangles.append(_parse_rectangle(rect))
            for pl in _find_all(sub, "polyline"):
                graphics.polylines.append(_parse_polyline(pl))
            for arc in _find_all(sub, "arc"):
                graphics.arcs.append(_parse_arc(arc))
            for circ in _find_all(sub, "circle"):
                graphics.circles.append(_parse_circle(circ))
            for pin in _find_all(sub, "pin"):
                graphics.pins.append(_parse_pin(pin))

        return graphics
