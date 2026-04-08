"""Tests for scan2kicad.inference."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scan2kicad.inference import MODEL_ID, PROMPT_TEMPLATE


class TestConstants:
    def test_model_id(self) -> None:
        assert MODEL_ID == "kingabzpro/qwen3vl-open-schematics-lora"

    def test_prompt_template_has_placeholders(self) -> None:
        assert "{name}" in PROMPT_TEMPLATE
        assert "{ftype}" in PROMPT_TEMPLATE

    def test_prompt_template_formats(self) -> None:
        result = PROMPT_TEMPLATE.format(name="MyProject", ftype=".kicad_sch")
        assert "MyProject" in result
        assert ".kicad_sch" in result


class TestGetModel:
    def test_returns_cached_when_set(self) -> None:
        import scan2kicad.inference as mod

        sentinel_model = object()
        sentinel_processor = object()
        with (
            patch.object(mod, "_cached_model", sentinel_model),
            patch.object(mod, "_cached_processor", sentinel_processor),
        ):
            model, processor = mod._get_model()
        assert model is sentinel_model
        assert processor is sentinel_processor


class TestPredictSingle:
    @patch("scan2kicad.inference._get_model")
    def test_predict_single_calls_model(
        self, mock_get_model: MagicMock, tiny_png_bytes: bytes
    ) -> None:
        mock_model = MagicMock()
        mock_processor = MagicMock()
        mock_get_model.return_value = (mock_model, mock_processor)

        mock_processor.apply_chat_template.return_value.to.return_value = MagicMock()
        mock_model.generate.return_value = [MagicMock()]
        mock_processor.decode.return_value = "R1, C1, U1"

        mock_torch = MagicMock()
        with patch.dict("sys.modules", {"torch": mock_torch}):
            from scan2kicad.inference import predict_single

            result = predict_single(tiny_png_bytes, "TestProject", ".kicad_sch")

        assert result == "R1, C1, U1"
        mock_processor.apply_chat_template.assert_called_once()

    @patch("scan2kicad.inference._get_model")
    def test_predict_single_uses_correct_prompt(
        self, mock_get_model: MagicMock, tiny_png_bytes: bytes
    ) -> None:
        mock_model = MagicMock()
        mock_processor = MagicMock()
        mock_get_model.return_value = (mock_model, mock_processor)

        mock_processor.apply_chat_template.return_value.to.return_value = MagicMock()
        mock_model.generate.return_value = [MagicMock()]
        mock_processor.decode.return_value = ""

        mock_torch = MagicMock()
        with patch.dict("sys.modules", {"torch": mock_torch}):
            from scan2kicad.inference import predict_single

            predict_single(tiny_png_bytes, "UART-Prog", ".kicad_sch")

        call_args = mock_processor.apply_chat_template.call_args
        messages = call_args[0][0]
        text_content = messages[0]["content"][1]["text"]
        assert "UART-Prog" in text_content
        assert ".kicad_sch" in text_content
