"""SVG document builder for KiCad schematic rendering."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET


class SvgBuilder:
    """Accumulates SVG elements and produces the final SVG string."""

    def __init__(
        self,
        viewbox: tuple[float, float, float, float],
        background: str = "#FFFFFF",
        margin: float = 5.0,
    ) -> None:
        x, y, w, h = viewbox
        self._vb_x = x - margin
        self._vb_y = y - margin
        self._vb_w = w + 2 * margin
        self._vb_h = h + 2 * margin
        self._background = background
        self._elements: list[ET.Element | tuple[str, ET.Element | None]] = []
        self._defs: list[ET.Element] = []

    def add_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = "#000000",
        width: float = 0.254,
    ) -> None:
        el = ET.Element(
            "line",
            x1=_f(x1),
            y1=_f(y1),
            x2=_f(x2),
            y2=_f(y2),
            stroke=color,
        )
        el.set("stroke-width", _f(width))
        el.set("stroke-linecap", "round")
        self._elements.append(el)

    def add_polyline(
        self,
        points: list[tuple[float, float]],
        color: str = "#000000",
        width: float = 0.254,
        fill: str = "none",
    ) -> None:
        pts_str = " ".join(f"{_f(x)},{_f(y)}" for x, y in points)
        el = ET.Element(
            "polyline",
            points=pts_str,
            stroke=color,
            fill=fill,
        )
        el.set("stroke-width", _f(width))
        el.set("stroke-linecap", "round")
        el.set("stroke-linejoin", "round")
        self._elements.append(el)

    def add_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color: str = "#000000",
        width: float = 0.254,
        fill: str = "none",
    ) -> None:
        el = ET.Element(
            "rect",
            x=_f(min(x, x + w)),
            y=_f(min(y, y + h)),
            width=_f(abs(w)),
            height=_f(abs(h)),
            stroke=color,
            fill=fill,
        )
        el.set("stroke-width", _f(width))
        self._elements.append(el)

    def add_circle(
        self,
        cx: float,
        cy: float,
        r: float,
        color: str = "#000000",
        width: float = 0.254,
        fill: str = "none",
    ) -> None:
        el = ET.Element(
            "circle",
            cx=_f(cx),
            cy=_f(cy),
            r=_f(r),
            stroke=color,
            fill=fill,
        )
        el.set("stroke-width", _f(width))
        self._elements.append(el)

    def add_dot(self, cx: float, cy: float, r: float, color: str = "#008000") -> None:
        el = ET.Element(
            "circle",
            cx=_f(cx),
            cy=_f(cy),
            r=_f(r),
            fill=color,
            stroke="none",
        )
        self._elements.append(el)

    def add_cross(
        self,
        cx: float,
        cy: float,
        size: float = 0.7,
        color: str = "#0000FF",
        width: float = 0.254,
    ) -> None:
        """Draw an X mark (for no-connects)."""
        self.add_line(cx - size, cy - size, cx + size, cy + size, color, width)
        self.add_line(cx - size, cy + size, cx + size, cy - size, color, width)

    def add_text(
        self,
        x: float,
        y: float,
        text: str,
        size: float = 1.27,
        color: str = "#000000",
        rotation: float = 0.0,
        anchor: str = "start",
        font_family: str = "monospace",
        bold: bool = False,
    ) -> None:
        el = ET.Element("text", x=_f(x), y=_f(y), fill=color)
        el.set("font-size", _f(size))
        el.set("font-family", font_family)
        el.set("text-anchor", anchor)
        el.set("dominant-baseline", "central")
        if bold:
            el.set("font-weight", "bold")
        if rotation != 0:
            el.set("transform", f"rotate({_f(rotation)},{_f(x)},{_f(y)})")
        el.text = text
        self._elements.append(el)

    def add_arc(
        self,
        start: tuple[float, float],
        mid: tuple[float, float],
        end: tuple[float, float],
        color: str = "#000000",
        width: float = 0.254,
        fill: str = "none",
    ) -> None:
        """Draw an arc through start, mid, end using SVG arc path."""
        cx, cy, r = _circle_from_three_points(start, mid, end)
        if r is None:
            # Degenerate: draw a line
            self.add_line(start[0], start[1], end[0], end[1], color, width)
            return
        # Determine sweep direction
        cross = (mid[0] - start[0]) * (end[1] - start[1]) - (mid[1] - start[1]) * (
            end[0] - start[0]
        )
        sweep = 1 if cross > 0 else 0
        # large-arc flag
        angle_start = math.atan2(start[1] - cy, start[0] - cx)
        angle_mid = math.atan2(mid[1] - cy, mid[0] - cx)
        angle_end = math.atan2(end[1] - cy, end[0] - cx)
        # Normalize angles
        if sweep == 1:
            if angle_mid < angle_start:
                angle_mid += 2 * math.pi
            if angle_end < angle_mid:
                angle_end += 2 * math.pi
            arc_span = angle_end - angle_start
        else:
            if angle_mid > angle_start:
                angle_mid -= 2 * math.pi
            if angle_end > angle_mid:
                angle_end -= 2 * math.pi
            arc_span = angle_start - angle_end
        large_arc = 1 if arc_span > math.pi else 0

        d = (
            f"M {_f(start[0])},{_f(start[1])} "
            f"A {_f(r)},{_f(r)} 0 {large_arc},{sweep} {_f(end[0])},{_f(end[1])}"
        )
        el = ET.Element("path", d=d, stroke=color, fill=fill)
        el.set("stroke-width", _f(width))
        el.set("stroke-linecap", "round")
        self._elements.append(el)

    def open_group(self, transform: str = "") -> None:
        """Open a <g> group. Call close_group() to close."""
        el = ET.Element("g")
        if transform:
            el.set("transform", transform)
        self._elements.append(("open", el))
    def close_group(self) -> None:
        self._elements.append(("close", None))
    def to_string(self) -> str:
        """Produce the final SVG string."""
        svg = ET.Element(
            "svg",
            xmlns="http://www.w3.org/2000/svg",
            viewBox=f"{_f(self._vb_x)} {_f(self._vb_y)} {_f(self._vb_w)} {_f(self._vb_h)}",
        )
        # Background
        ET.SubElement(
            svg,
            "rect",
            x=_f(self._vb_x),
            y=_f(self._vb_y),
            width=_f(self._vb_w),
            height=_f(self._vb_h),
            fill=self._background,
        )

        # Build element tree with group nesting
        stack: list[ET.Element] = [svg]
        for item in self._elements:
            if isinstance(item, tuple):
                tag, el = item
                if tag == "open" and el is not None:
                    stack[-1].append(el)
                    stack.append(el)
                elif tag == "close" and len(stack) > 1:
                    stack.pop()
            elif isinstance(item, ET.Element):
                stack[-1].append(item)

        ET.indent(svg, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(svg, encoding="unicode")


def _f(v: float) -> str:
    """Format float for SVG (compact, no trailing zeros)."""
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _circle_from_three_points(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> tuple[float, float, float | None]:
    """Compute center (cx, cy) and radius of the circle through three points."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-10:
        return 0.0, 0.0, None
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    r = math.sqrt((ax - ux) ** 2 + (ay - uy) ** 2)
    return ux, uy, r
