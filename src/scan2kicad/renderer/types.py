"""Geometry dataclasses for the KiCad SVG renderer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    start: Point
    end: Point
    stroke_width: float = 0.254
    fill: str = "none"


@dataclass(frozen=True)
class Polyline:
    points: tuple[Point, ...]
    stroke_width: float = 0.254
    fill: str = "none"


@dataclass(frozen=True)
class Arc:
    start: Point
    mid: Point
    end: Point
    stroke_width: float = 0.254
    fill: str = "none"


@dataclass(frozen=True)
class Circle:
    center: Point
    radius: float
    stroke_width: float = 0.254
    fill: str = "none"


@dataclass(frozen=True)
class PinGraphic:
    position: Point
    length: float
    rotation: float  # degrees: 0=right, 90=up, 180=left, 270=down
    name: str = ""
    number: str = ""
    pin_type: str = "passive"
    pin_shape: str = "line"


@dataclass
class SymbolGraphics:
    """All drawable elements for a library symbol definition."""

    rectangles: list[Rect] = field(default_factory=list)
    polylines: list[Polyline] = field(default_factory=list)
    arcs: list[Arc] = field(default_factory=list)
    circles: list[Circle] = field(default_factory=list)
    pins: list[PinGraphic] = field(default_factory=list)
