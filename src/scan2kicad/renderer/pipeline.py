"""Rendering pipeline: .kicad_sch content → SVG string."""

from __future__ import annotations

import math
import tempfile

from .lib_symbol_parser import LibSymbolParser
from .svg_builder import SvgBuilder
from .types import PinGraphic


def _comp_unit(comp) -> int:
    """Get the unit number from a component, handling API differences."""
    if hasattr(comp, "unit"):
        return comp.unit or 1
    if hasattr(comp, "_data") and hasattr(comp._data, "unit"):
        return comp._data.unit or 1
    return 1


def render_schematic_svg(
    kicad_sch_content: str,
    *,
    background: str = "#FFFFFF",
    wire_color: str = "#008000",
    bus_color: str = "#0000C8",
    junction_color: str = "#008000",
    component_color: str = "#800000",
    label_color: str = "#008000",
    text_color: str = "#000000",
    pin_color: str = "#800000",
    no_connect_color: str = "#0000FF",
    stroke_width: float = 0.254,
    font_family: str = "monospace",
) -> str:
    """Render a .kicad_sch string to an SVG string."""

    # 1. Parse schematic via kicad-sch-api (requires file on disk)
    sch = _load_schematic(kicad_sch_content)

    # 2. Parse lib_symbols via sexpdata
    lib_parser = LibSymbolParser(kicad_sch_content)

    # 3. Compute bounding box
    bbox = _compute_bounding_box(sch, lib_parser)

    # 4. Create SVG builder
    svg = SvgBuilder(viewbox=bbox, background=background)

    # 5. Render layers (back to front)
    _render_schematic_graphics(svg, sch, component_color, stroke_width)
    _render_wires(svg, sch, wire_color, bus_color, stroke_width)
    _render_symbols(svg, sch, lib_parser, component_color, pin_color, stroke_width, font_family)
    _render_junctions(svg, sch, junction_color)
    _render_no_connects(svg, sch, no_connect_color, stroke_width)
    _render_labels(svg, sch, label_color, font_family)
    _render_texts(svg, sch, text_color, font_family)

    return svg.to_string()


def _load_schematic(content: str):
    """Load schematic from string content via kicad-sch-api."""
    import kicad_sch_api as ksa

    with tempfile.NamedTemporaryFile(mode="w", suffix=".kicad_sch", delete=False) as f:
        f.write(content)
        f.flush()
        return ksa.load_schematic(f.name)


def _compute_bounding_box(sch, lib_parser: LibSymbolParser) -> tuple[float, float, float, float]:
    """Compute (x, y, width, height) bounding box from all elements."""
    xs: list[float] = []
    ys: list[float] = []

    for wire in sch.wires:
        for pt in wire.points:
            xs.append(pt.x)
            ys.append(pt.y)

    for comp in sch.components:
        xs.append(comp.position.x)
        ys.append(comp.position.y)
        # Expand by symbol graphics bounding box
        gfx = lib_parser.get_symbol_graphics(comp.lib_id, unit=_comp_unit(comp))
        for rect in gfx.rectangles:
            xs.extend([comp.position.x + rect.start.x, comp.position.x + rect.end.x])
            ys.extend([comp.position.y + rect.start.y, comp.position.y + rect.end.y])
        for pin in gfx.pins:
            px, py = _pin_endpoint(pin)
            xs.append(comp.position.x + px)
            ys.append(comp.position.y + py)

    for junc in sch.junctions:
        xs.append(junc.position.x)
        ys.append(junc.position.y)

    for label in sch.labels:
        xs.append(label.position.x)
        ys.append(label.position.y)

    for nc in sch.no_connects:
        xs.append(nc.position.x)
        ys.append(nc.position.y)

    for text in sch.texts:
        xs.append(text.position.x)
        ys.append(text.position.y)

    if not xs or not ys:
        return (0, 0, 297, 210)  # A4 default

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return (min_x, min_y, max_x - min_x, max_y - min_y)


def _pin_endpoint(pin: PinGraphic) -> tuple[float, float]:
    """Compute the endpoint of a pin line given position, length, rotation."""
    rad = math.radians(pin.rotation)
    dx = pin.length * math.cos(rad)
    dy = -pin.length * math.sin(rad)  # KiCad: 90° = up = -Y
    return (pin.position.x + dx, pin.position.y + dy)


# ---- Layer renderers ----


def _render_wires(svg: SvgBuilder, sch, wire_color: str, bus_color: str, width: float) -> None:
    for wire in sch.wires:
        color = bus_color if wire.wire_type.value == "bus" else wire_color
        w = width * 3 if wire.wire_type.value == "bus" else width
        pts = wire.points
        if len(pts) == 2:
            svg.add_line(pts[0].x, pts[0].y, pts[1].x, pts[1].y, color, w)
        elif len(pts) > 2:
            svg.add_polyline([(p.x, p.y) for p in pts], color, w)


def _render_junctions(svg: SvgBuilder, sch, color: str) -> None:
    for junc in sch.junctions:
        r = junc.diameter / 2 if junc.diameter > 0 else 0.508
        svg.add_dot(junc.position.x, junc.position.y, r, color)


def _render_no_connects(svg: SvgBuilder, sch, color: str, width: float) -> None:
    for nc in sch.no_connects:
        svg.add_cross(nc.position.x, nc.position.y, 0.7, color, width)


def _render_labels(svg: SvgBuilder, sch, color: str, font_family: str) -> None:
    for label in sch.labels:
        svg.add_text(
            label.position.x,
            label.position.y,
            label.text,
            size=label.size if hasattr(label, "size") else 1.27,
            color=color,
            rotation=label.rotation if hasattr(label, "rotation") else 0,
            font_family=font_family,
        )
    # Also render hierarchical labels
    for label in sch.hierarchical_labels:
        svg.add_text(
            label.position.x,
            label.position.y,
            label.text,
            size=label.size if hasattr(label, "size") else 1.27,
            color=color,
            rotation=label.rotation if hasattr(label, "rotation") else 0,
            font_family=font_family,
        )


def _render_texts(svg: SvgBuilder, sch, color: str, font_family: str) -> None:
    for text in sch.texts:
        svg.add_text(
            text.position.x,
            text.position.y,
            text.text,
            size=text.size if hasattr(text, "size") else 1.27,
            color=color,
            rotation=text.rotation if hasattr(text, "rotation") else 0,
            font_family=font_family,
            bold=getattr(text, "bold", False),
        )


def _render_symbols(
    svg: SvgBuilder,
    sch,
    lib_parser: LibSymbolParser,
    comp_color: str,
    pin_color: str,
    width: float,
    font_family: str,
) -> None:
    for comp in sch.components:
        gfx = lib_parser.get_symbol_graphics(comp.lib_id, unit=_comp_unit(comp))
        px, py = comp.position.x, comp.position.y
        rot = comp.rotation if hasattr(comp, "rotation") else 0

        transform = f"translate({px},{py})"
        if rot:
            transform += f" rotate({rot})"

        svg.open_group(transform)

        # Draw body rectangles
        for rect in gfx.rectangles:
            svg.add_rect(
                rect.start.x,
                rect.start.y,
                rect.end.x - rect.start.x,
                rect.end.y - rect.start.y,
                comp_color,
                rect.stroke_width or width,
                _fill_to_svg(rect.fill, comp_color),
            )

        # Draw body polylines
        for pl in gfx.polylines:
            svg.add_polyline(
                [(p.x, p.y) for p in pl.points],
                comp_color,
                pl.stroke_width or width,
                _fill_to_svg(pl.fill, comp_color),
            )

        # Draw body arcs
        for arc in gfx.arcs:
            svg.add_arc(
                (arc.start.x, arc.start.y),
                (arc.mid.x, arc.mid.y),
                (arc.end.x, arc.end.y),
                comp_color,
                arc.stroke_width or width,
            )

        # Draw body circles
        for circ in gfx.circles:
            svg.add_circle(
                circ.center.x,
                circ.center.y,
                circ.radius,
                comp_color,
                circ.stroke_width or width,
                _fill_to_svg(circ.fill, comp_color),
            )

        # Draw pins
        for pin in gfx.pins:
            ex, ey = _pin_endpoint(pin)
            svg.add_line(pin.position.x, pin.position.y, ex, ey, pin_color, width)

        svg.close_group()

        # Draw reference and value text (outside group, in schematic coords)
        svg.add_text(
            px,
            py - 2.0,
            comp.reference,
            size=1.27,
            color=comp_color,
            anchor="middle",
            font_family=font_family,
            bold=True,
        )
        svg.add_text(
            px,
            py + 2.0,
            comp.value if hasattr(comp, "value") else "",
            size=1.0,
            color=comp_color,
            anchor="middle",
            font_family=font_family,
        )


def _render_schematic_graphics(svg: SvgBuilder, sch, color: str, width: float) -> None:
    """Render schematic-level polylines, arcs, circles, rectangles from raw data."""
    data = sch._data if hasattr(sch, "_data") else {}

    for pl in data.get("polylines", []):
        points = [(p["x"], p["y"]) for p in pl.get("points", [])]
        if points:
            svg.add_polyline(points, color, pl.get("stroke_width", width))

    for arc in data.get("arcs", []):
        s = arc.get("start", {})
        m = arc.get("mid", {})
        e = arc.get("end", {})
        if s and m and e:
            svg.add_arc(
                (s["x"], s["y"]),
                (m["x"], m["y"]),
                (e["x"], e["y"]),
                color,
                arc.get("stroke_width", width),
            )

    for circ in data.get("circles", []):
        c = circ.get("center", {})
        if c:
            svg.add_circle(
                c["x"], c["y"], circ.get("radius", 1), color, circ.get("stroke_width", width)
            )

    for rect in data.get("rectangles", []):
        s = rect.get("start", {})
        e = rect.get("end", {})
        if s and e:
            svg.add_rect(
                s["x"],
                s["y"],
                e["x"] - s["x"],
                e["y"] - s["y"],
                color,
                rect.get("stroke_width", width),
            )


def _fill_to_svg(fill_type: str, color: str) -> str:
    """Convert KiCad fill type to SVG fill value."""
    if fill_type == "background":
        return "#FFFFFF"
    if fill_type in ("outline", "filled"):
        return color
    return "none"
