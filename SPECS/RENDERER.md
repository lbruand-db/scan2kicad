# KiCad Schematic to SVG Renderer — Technical Specification

**Version:** 1.0
**Date:** 2026-04-08
**Status:** Draft

---

## 1. Goal

Build a pure-Python renderer that converts `.kicad_sch` S-expression content into SVG, without requiring a KiCad installation. The renderer will use **kicad-sch-api** (MIT, actively maintained) for structured parsing and **sexpdata** for low-level lib_symbols extraction.

---

## 2. Why kicad-sch-api + sexpdata

| Concern | kicad-sch-api | sexpdata |
|---------|--------------|----------|
| Wires, junctions, labels, no-connects, text | Typed dataclasses (`Wire`, `Junction`, `Label`, etc.) | Raw nested lists |
| Symbol placements (position, rotation, reference, value) | `SchematicSymbol` with `get_pin_position()` | Manual traversal |
| lib_symbols (symbol body graphics) | **Not parsed** (`_parse_lib_symbols()` returns `{}`) | Parses full S-expression tree |
| License | MIT | BSD-2 |

**Approach:** Use kicad-sch-api for schematic-level elements. Use sexpdata to parse the `lib_symbols` section from the raw file content, extracting symbol body graphics (rectangles, polylines, arcs, circles, pins).

---

## 3. Architecture

```
.kicad_sch string
       │
       ├─── kicad-sch-api ───► Schematic object
       │      │                  ├── wires: List[Wire]
       │      │                  ├── junctions: List[Junction]
       │      │                  ├── labels: List[Label]
       │      │                  ├── no_connects: List[NoConnect]
       │      │                  ├── texts: List[Text]
       │      │                  ├── components: List[SchematicSymbol]
       │      │                  └── _data["polylines"|"arcs"|"circles"|"rectangles"]
       │      │
       └─── sexpdata ────────► lib_symbols dict
                                 └── symbol_id → List[graphic elements]
                                       ├── rectangles (start, end, stroke, fill)
                                       ├── polylines (points, stroke, fill)
                                       ├── arcs (start, mid, end)
                                       ├── circles (center, radius)
                                       └── pins (position, length, rotation, type, shape)
       │
       ▼
  SVG Renderer (scan2kicad.renderer)
       │
       ▼
  SVG string (or bytes)
```

---

## 4. Module Design: `scan2kicad.renderer`

### 4.1 Public API

```python
def render_schematic_svg(
    kicad_sch_content: str,
    *,
    width: int | None = None,
    height: int | None = None,
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
    """Render a .kicad_sch string to an SVG string.

    KiCad coordinate system: origin top-left, Y increases downward.
    SVG coordinate system: same convention — no Y-flip needed.
    Units: KiCad uses mm. SVG viewBox will use the same mm units.
    """
```

### 4.2 Internal Components

#### `LibSymbolParser`

Extracts symbol graphics from `lib_symbols` using sexpdata.

```python
@dataclass
class SymbolGraphics:
    """Drawable elements for a library symbol definition."""
    rectangles: list[Rect]        # (start_x, start_y, end_x, end_y, stroke_w, fill)
    polylines: list[Polyline]     # (points: list[Point], stroke_w, fill)
    arcs: list[Arc]               # (start, mid, end, stroke_w, fill)
    circles: list[Circle]         # (center_x, center_y, radius, stroke_w, fill)
    pins: list[PinGraphic]        # (x, y, length, rotation, name, number, type, shape)

class LibSymbolParser:
    def __init__(self, kicad_sch_content: str): ...
    def get_symbol_graphics(self, lib_id: str, unit: int = 1) -> SymbolGraphics: ...
```

The parser extracts the `(lib_symbols ...)` block, then for each `(symbol "lib_id" ...)`, collects the sub-symbols `(symbol "lib_id_0_1" ...)` (unit 0 = shared graphics) and `(symbol "lib_id_{unit}_1" ...)`.

**lib_symbols structure:**
```
(lib_symbols
  (symbol "Device:R"
    (symbol "R_0_1"          ← unit 0: shared body graphics
      (rectangle (start -1.016 -2.54) (end 1.016 2.54) ...)
    )
    (symbol "R_1_1"          ← unit 1: pins
      (pin passive line (at 0 3.81 270) (length 1.27) (name "~") (number "1"))
      (pin passive line (at 0 -3.81 90) (length 1.27) (name "~") (number "2"))
    )
  )
)
```

#### `SvgBuilder`

Accumulates SVG elements and produces the final SVG string.

```python
class SvgBuilder:
    def __init__(self, viewbox: tuple[float, float, float, float], **style): ...
    def add_line(self, x1, y1, x2, y2, color, width): ...
    def add_rect(self, x, y, w, h, color, width, fill): ...
    def add_circle(self, cx, cy, r, color, width, fill): ...
    def add_arc(self, start, mid, end, color, width): ...
    def add_polyline(self, points, color, width, fill): ...
    def add_text(self, x, y, text, size, color, rotation, anchor): ...
    def add_cross(self, x, y, size, color, width): ...  # for no-connects
    def add_dot(self, x, y, r, color): ...               # for junctions
    def add_group(self, transform) -> SvgGroup: ...       # for symbol transforms
    def to_string(self) -> str: ...
```

#### Rendering Pipeline

```python
def render_schematic_svg(kicad_sch_content, **opts):
    # 1. Parse schematic via kicad-sch-api (write to tempfile, load)
    sch = _load_schematic(kicad_sch_content)

    # 2. Parse lib_symbols via sexpdata
    lib_parser = LibSymbolParser(kicad_sch_content)

    # 3. Compute bounding box from all elements
    bbox = _compute_bounding_box(sch, lib_parser)

    # 4. Create SVG builder with viewBox
    svg = SvgBuilder(viewbox=bbox, **opts)

    # 5. Render layers (back to front)
    _render_rectangles(svg, sch)       # background shapes
    _render_wires(svg, sch)            # wire segments
    _render_buses(svg, sch)            # bus segments
    _render_symbols(svg, sch, lib_parser)  # component bodies + pins
    _render_junctions(svg, sch)        # junction dots
    _render_no_connects(svg, sch)      # X marks
    _render_labels(svg, sch)           # net labels, global labels
    _render_texts(svg, sch)            # free text
    _render_polylines(svg, sch)        # schematic-level polylines
    _render_arcs(svg, sch)             # schematic-level arcs

    return svg.to_string()
```

---

## 5. Element Rendering Details

### 5.1 Wires

Source: `sch.wires` → `List[Wire]`
Each wire has `points: List[Point]`, `wire_type: WireType` (WIRE or BUS).

```svg
<line x1="..." y1="..." x2="..." y2="..." stroke="#008000" stroke-width="0.254" stroke-linecap="round"/>
```

For multi-point wires, render as `<polyline>`.

### 5.2 Junctions

Source: `sch.junctions` → `List[Junction]`
Each has `position: Point`, `diameter: float` (0 = default 1.016mm).

```svg
<circle cx="..." cy="..." r="0.508" fill="#008000"/>
```

### 5.3 No-Connects

Source: `sch.no_connects` → `List[NoConnect]`
Each has `position: Point`. Render as an X mark (two crossing lines, ±0.5mm).

### 5.4 Labels

Source: `sch.labels` → `List[Label]`
Types: `LOCAL`, `GLOBAL`, `HIERARCHICAL`.
Each has `position`, `text`, `rotation`, `size`.

- **Local labels:** text with an overline
- **Global labels:** text inside a flag shape (rectangle with pointed end)
- **Hierarchical labels:** text inside a directional flag (input/output/bidirectional shape)

### 5.5 Symbols (Components)

Source: `sch.components` → `List[SchematicSymbol]`
Each has `lib_id`, `position`, `rotation`, `unit`, `reference`, `value`.

Rendering steps per symbol:
1. Look up `lib_id` in `LibSymbolParser` → get `SymbolGraphics` for the correct unit
2. Create SVG `<g>` with `transform="translate(x,y) rotate(rotation)"`
3. Draw body graphics (rectangles, polylines, arcs, circles) in `component_color`
4. Draw pins: line from pin position extending `length` mm at `rotation` angle
5. Draw pin numbers and names (if not hidden)
6. Draw reference designator and value text at their property positions

**Rotation/mirror transform:**
KiCad uses `(at x y angle)` plus optional `(mirror x)` or `(mirror y)`. The SVG transform is:
```
translate(pos_x, pos_y) rotate(angle) scale(mirror_x, mirror_y)
```

### 5.6 Schematic-level Graphics

Source: `sch._data["polylines"]`, `sch._data["arcs"]`, `sch._data["circles"]`, `sch._data["rectangles"]`
These are raw dicts (not typed). Render directly.

### 5.7 Text

Source: `sch.texts` → `List[Text]`
Each has `position`, `text`, `rotation`, `size`, `bold`, `italic`.

### 5.8 Power Symbols

Power symbols (e.g., `power:GND`, `power:+5V`) are regular symbols with `power_symbol: true` in their lib definition. They render using the same symbol pipeline but typically have distinctive graphics (GND bars, VCC arrows, etc.).

---

## 6. KiCad Coordinate System

- Units: millimeters
- Origin: top-left of the paper
- X: increases rightward
- Y: increases downward (same as SVG)
- Rotation: degrees, counter-clockwise
- Pin angles: 0=right, 90=up, 180=left, 270=down

No Y-flip is needed for SVG since both coordinate systems have Y increasing downward.

---

## 7. Dependencies

```toml
[project]
dependencies = [
    "kicad-sch-api>=0.5",
    "sexpdata>=1.0",
]
```

Both are pure Python, MIT/BSD licensed, compatible with Python 3.10+.

---

## 8. Test Plan

### 8.1 Test Fixtures

Three `.kicad_sch` files from the open-schematics dataset, stored in `tests/fixtures/`:

| Fixture | Source | Size | Elements |
|---------|--------|------|----------|
| `sample_small.kicad_sch` | `DK10106/Generatingcircuitagent` | 225 B | 1 power symbol (GND), no wires |
| `sample_medium.kicad_sch` | `xmaz-project/88va2-circuit` | 2.8 KB | lib_symbols with pins/rectangles, multiple wires, hierarchical labels |
| `sample_rich.kicad_sch` | `Terstegge/SimCad` | 5.5 KB | Device:R lib_symbol with rectangle+pins, wires, junctions, labels |

### 8.2 Unit Tests: `tests/test_renderer.py`

#### LibSymbolParser tests

```
test_parse_empty_lib_symbols
    Input: schematic with empty (lib_symbols)
    Assert: parser returns no symbols

test_parse_resistor_symbol
    Input: sample_rich.kicad_sch (has Device:R)
    Assert: get_symbol_graphics("Device:R") returns:
        - 1 rectangle (body)
        - 2 pins (pin 1 at top, pin 2 at bottom)

test_parse_multi_unit_symbol
    Input: sample_medium.kicad_sch (has Bus_System_VA2)
    Assert: graphics for unit 0 (shared) extracted correctly

test_unknown_symbol_returns_empty
    Assert: get_symbol_graphics("Nonexistent:Symbol") returns empty SymbolGraphics
```

#### SvgBuilder tests

```
test_empty_svg
    Assert: valid SVG with only background rect

test_add_line
    Assert: output contains <line> with correct coordinates

test_add_rect
    Assert: output contains <rect> with correct x, y, width, height

test_add_circle
    Assert: output contains <circle> with correct cx, cy, r

test_add_text
    Assert: output contains <text> with correct content and position

test_add_group_transform
    Assert: <g transform="translate(...) rotate(...)"> wraps children

test_svg_is_valid_xml
    Assert: output parses as valid XML (xml.etree.ElementTree)
```

#### Rendering pipeline tests

```
test_render_small_schematic
    Input: sample_small.kicad_sch
    Assert: returns valid SVG string, contains at least one <g> for the GND symbol

test_render_medium_schematic
    Input: sample_medium.kicad_sch
    Assert: SVG contains <line> elements for wires

test_render_rich_schematic
    Input: sample_rich.kicad_sch
    Assert: SVG contains:
        - <line> for wires (5 wires)
        - <circle> for junctions (1 junction)
        - <text> for labels (3 labels)
        - <rect> for resistor body
        - <line> for resistor pins

test_render_returns_valid_svg_xml
    Input: each fixture
    Assert: xml.etree.ElementTree.fromstring() succeeds
    Assert: root tag is "svg"
    Assert: viewBox attribute present

test_render_empty_string
    Input: minimal "(kicad_sch (version 20231120) (generator eeschema))"
    Assert: returns valid SVG with no graphical elements
```

#### Visual regression tests

```
test_render_matches_dataset_image
    Input: sample from open_schematics with both schematic and image columns
    Action: render SVG, rasterize to PNG (via cairosvg or pillow)
    Assert: structural similarity (SSIM) > threshold
    Note: this is a stretch goal — initial implementation may skip this
```

### 8.3 Integration Test

```
test_render_from_delta_table
    Run on Databricks (or mock Spark):
    - Read a row from lucasbruand_catalog.kicad.open_schematics
    - Call render_schematic_svg(row["schematic"])
    - Assert valid SVG returned
```

---

## 9. Rendering Quality Tiers

### Tier 1 (MVP)

- Wires (lines)
- Junctions (filled circles)
- No-connects (X marks)
- Local labels (text)
- Component bounding boxes (rectangles at symbol positions)
- Reference designators and values as text

### Tier 2

- Full lib_symbol body graphics (rectangles, polylines, arcs, circles)
- Pin rendering (lines with correct length and rotation)
- Global label shapes (flag outlines)
- Power symbol graphics
- Text rotation and sizing

### Tier 3

- Pin names and numbers
- Hierarchical label shapes (directional flags)
- Fill patterns (outline, background, filled)
- Bus rendering (thicker lines)
- Hierarchical sheets (rectangles with name)
- Embedded images

---

## 10. File Layout

```
src/scan2kicad/
  renderer/
    __init__.py             # re-exports render_schematic_svg
    svg_builder.py          # SvgBuilder class
    lib_symbol_parser.py    # LibSymbolParser (sexpdata-based)
    pipeline.py             # render_schematic_svg() orchestrator
    types.py                # Rect, Polyline, Arc, Circle, PinGraphic dataclasses

tests/
  fixtures/
    sample_small.kicad_sch
    sample_medium.kicad_sch
    sample_rich.kicad_sch
  test_renderer/
    test_lib_symbol_parser.py
    test_svg_builder.py
    test_pipeline.py
```
