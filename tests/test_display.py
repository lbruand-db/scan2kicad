"""Tests for scan2kicad.display."""

from __future__ import annotations

import base64
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_ipython():
    """Ensure IPython.display is mockable even when not installed."""
    mock_ipython = MagicMock()
    with patch.dict(
        sys.modules,
        {
            "IPython": mock_ipython,
            "IPython.display": mock_ipython.display,
        },
    ):
        # Force reimport so the module picks up the mocked IPython
        if "scan2kicad.display" in sys.modules:
            del sys.modules["scan2kicad.display"]
        yield


class TestDisplaySchematicFromRow:
    def test_displays_image_when_available(self) -> None:
        from scan2kicad.display import display_schematic_from_row

        with (
            patch("scan2kicad.display.display") as mock_display,
            patch("scan2kicad.display.IPImage") as mock_ipimage,
        ):
            row = {"image": b"\x89PNGfakedata", "schematic": "(kicad_sch)"}
            display_schematic_from_row(row)

            mock_ipimage.assert_called_once_with(data=b"\x89PNGfakedata")
            mock_display.assert_called_once()

    def test_renders_svg_when_no_image(self) -> None:
        from scan2kicad.display import display_schematic_from_row

        with (
            patch("scan2kicad.display.display") as mock_display,
            patch("scan2kicad.display.SVG") as mock_svg,
            patch("scan2kicad.display.render_kicad_schematic") as mock_render,
        ):
            mock_render.return_value = b"<svg>content</svg>"
            row = {"image": None, "schematic": "(kicad_sch (version 20230121))"}

            display_schematic_from_row(row)

            mock_render.assert_called_once_with("(kicad_sch (version 20230121))", fmt="svg")
            mock_svg.assert_called_once_with(data=b"<svg>content</svg>")
            mock_display.assert_called_once()


class TestDisplaySchematicGallery:
    def test_generates_html_grid(self, tiny_png_bytes: bytes) -> None:
        from scan2kicad.display import display_schematic_gallery

        with (
            patch("scan2kicad.display.display"),
            patch("scan2kicad.display.HTML") as mock_html,
        ):
            mock_row = {"image": tiny_png_bytes, "name": "TestProject"}
            mock_df = MagicMock()
            mock_df.limit.return_value.collect.return_value = [mock_row, mock_row]

            display_schematic_gallery(mock_df, n=2, cols=2)

            mock_df.limit.assert_called_once_with(2)
            mock_html.assert_called_once()
            html_content = mock_html.call_args[0][0]
            assert "grid-template-columns:1fr 1fr" in html_content
            assert "TestProject" in html_content

    def test_encodes_images_as_base64(self, tiny_png_bytes: bytes) -> None:
        from scan2kicad.display import display_schematic_gallery

        with (
            patch("scan2kicad.display.display"),
            patch("scan2kicad.display.HTML") as mock_html,
        ):
            b64_expected = base64.b64encode(tiny_png_bytes).decode()
            mock_row = {"image": tiny_png_bytes, "name": "P1"}
            mock_df = MagicMock()
            mock_df.limit.return_value.collect.return_value = [mock_row]

            display_schematic_gallery(mock_df, n=1, cols=1)

            html_content = mock_html.call_args[0][0]
            assert b64_expected in html_content

    def test_empty_dataframe(self) -> None:
        from scan2kicad.display import display_schematic_gallery

        with (
            patch("scan2kicad.display.display"),
            patch("scan2kicad.display.HTML") as mock_html,
        ):
            mock_df = MagicMock()
            mock_df.limit.return_value.collect.return_value = []

            display_schematic_gallery(mock_df, n=6, cols=3)

            html_content = mock_html.call_args[0][0]
            assert "grid-template-columns:1fr 1fr 1fr" in html_content
            assert "<img" not in html_content

    def test_default_cols(self, tiny_png_bytes: bytes) -> None:
        from scan2kicad.display import display_schematic_gallery

        with (
            patch("scan2kicad.display.display"),
            patch("scan2kicad.display.HTML") as mock_html,
        ):
            mock_row = {"image": tiny_png_bytes, "name": "P"}
            mock_df = MagicMock()
            mock_df.limit.return_value.collect.return_value = [mock_row]

            display_schematic_gallery(mock_df)

            html_content = mock_html.call_args[0][0]
            assert "1fr 1fr 1fr" in html_content
