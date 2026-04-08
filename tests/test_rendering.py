"""Tests for scan2kicad.rendering."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from scan2kicad.rendering import (
    parse_kicad_wires,
    render_kicad_pcb,
    render_kicad_schematic,
    render_schematic_matplotlib,
)


class TestParseKicadWires:
    def test_extracts_wires(self, sample_kicad_sch: str) -> None:
        wires = parse_kicad_wires(sample_kicad_sch)
        assert len(wires) == 3

    def test_wire_coordinates(self, sample_kicad_sch: str) -> None:
        wires = parse_kicad_wires(sample_kicad_sch)
        assert wires[0] == (100.0, 50.0, 200.0, 50.0)
        assert wires[1] == (200.0, 50.0, 200.0, 150.0)
        assert wires[2] == (50.5, 25.3, 75.8, 25.3)

    def test_empty_schematic(self) -> None:
        wires = parse_kicad_wires("(kicad_sch (version 20230121))")
        assert wires == []

    def test_no_match_on_garbage(self) -> None:
        wires = parse_kicad_wires("this is not a kicad file")
        assert wires == []

    def test_scientific_notation(self) -> None:
        content = "(wire (pts (xy 1.5e+02 2.0e-01) (xy 3e+02 4e+00)) (stroke (width 0)))"
        wires = parse_kicad_wires(content)
        assert len(wires) == 1
        assert wires[0] == (150.0, 0.2, 300.0, 4.0)

    def test_multiline_format(self) -> None:
        """Real KiCad 9 format uses newlines and tabs between wire and pts."""
        content = """(wire
		(pts
			(xy 180.34 104.14) (xy 173.99 104.14)
		)
		(stroke
			(width 0)
			(type default)
		)
		(uuid "0145d46e")
	)"""
        wires = parse_kicad_wires(content)
        assert len(wires) == 1
        assert wires[0] == (180.34, 104.14, 173.99, 104.14)


class TestRenderSchematicMatplotlib:
    def test_returns_figure(self, sample_kicad_sch: str) -> None:
        from matplotlib.figure import Figure

        fig = render_schematic_matplotlib(sample_kicad_sch)
        assert isinstance(fig, Figure)

    def test_empty_schematic_still_returns_figure(self) -> None:
        from matplotlib.figure import Figure

        fig = render_schematic_matplotlib("")
        assert isinstance(fig, Figure)

    def test_figure_has_axes(self, sample_kicad_sch: str) -> None:
        fig = render_schematic_matplotlib(sample_kicad_sch)
        axes = fig.get_axes()
        assert len(axes) == 1
        assert "KiCad Schematic Preview" in axes[0].get_title()


class TestRenderKicadSchematic:
    def test_writes_file_and_calls_kicad_cli(self, tmp_path: object) -> None:
        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            # Write a fake output file so the function can read it back
            out_path = cmd[cmd.index("--output") + 1]
            with open(out_path, "wb") as f:
                f.write(b"<svg>fake</svg>")
            return MagicMock(returncode=0)

        with patch("scan2kicad.rendering.subprocess.run", side_effect=fake_run) as mock_run:
            result = render_kicad_schematic("(kicad_sch)", fmt="svg")

        assert result == b"<svg>fake</svg>"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "kicad-cli"
        assert cmd[1:4] == ["sch", "export", "svg"]

    def test_raises_on_kicad_cli_failure(self) -> None:
        with patch(
            "scan2kicad.rendering.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "kicad-cli"),
        ):
            with pytest.raises(subprocess.CalledProcessError):
                render_kicad_schematic("(kicad_sch)")

    def test_png_format(self) -> None:
        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            out_path = cmd[cmd.index("--output") + 1]
            with open(out_path, "wb") as f:
                f.write(b"\x89PNG")
            return MagicMock(returncode=0)

        with patch("scan2kicad.rendering.subprocess.run", side_effect=fake_run):
            result = render_kicad_schematic("(kicad_sch)", fmt="png")

        assert result == b"\x89PNG"


class TestRenderKicadPcb:
    def test_writes_file_and_calls_kicad_cli(self) -> None:
        def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
            out_path = cmd[cmd.index("--output") + 1]
            with open(out_path, "wb") as f:
                f.write(b"<svg>pcb</svg>")
            return MagicMock(returncode=0)

        with patch("scan2kicad.rendering.subprocess.run", side_effect=fake_run) as mock_run:
            result = render_kicad_pcb("(kicad_pcb)", fmt="svg")

        assert result == b"<svg>pcb</svg>"
        cmd = mock_run.call_args[0][0]
        assert cmd[1:4] == ["pcb", "export", "svg"]
