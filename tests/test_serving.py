"""Tests for scan2kicad.serving."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from scan2kicad.serving import MODEL_SIGNATURE, Qwen3VLSchematicModel


class TestModelSignature:
    def test_input_schema_has_three_columns(self) -> None:
        inputs = MODEL_SIGNATURE.inputs.to_dict()
        assert len(inputs) == 3

    def test_input_column_names(self) -> None:
        inputs = MODEL_SIGNATURE.inputs.to_dict()
        names = [col["name"] for col in inputs]
        assert names == ["image", "name", "type"]

    def test_input_column_types(self) -> None:
        inputs = MODEL_SIGNATURE.inputs.to_dict()
        types = [col["type"] for col in inputs]
        assert types == ["binary", "string", "string"]

    def test_output_schema(self) -> None:
        outputs = MODEL_SIGNATURE.outputs.to_dict()
        assert len(outputs) == 1
        assert outputs[0]["name"] == "extracted_components"
        assert outputs[0]["type"] == "string"


class TestQwen3VLSchematicModel:
    def test_is_mlflow_pyfunc(self) -> None:
        import mlflow.pyfunc

        model = Qwen3VLSchematicModel()
        assert isinstance(model, mlflow.pyfunc.PythonModel)

    def test_has_required_methods(self) -> None:
        instance = Qwen3VLSchematicModel()
        assert hasattr(instance, "load_context")
        assert hasattr(instance, "predict")

    def test_predict_returns_dataframe(self, tiny_png_bytes: bytes) -> None:
        instance = Qwen3VLSchematicModel()

        # Set up mock model and processor
        instance.processor = MagicMock()
        instance.model = MagicMock()

        instance.processor.apply_chat_template.return_value.to.return_value = MagicMock()
        instance.model.generate.return_value = [MagicMock()]
        instance.processor.decode.return_value = "R1, C1"

        mock_context = MagicMock()
        model_input = pd.DataFrame(
            {
                "image": [tiny_png_bytes],
                "name": ["TestProject"],
                "type": [".kicad_sch"],
            }
        )

        mock_torch = MagicMock()
        with patch.dict("sys.modules", {"torch": mock_torch}):
            result = instance.predict(mock_context, model_input)

        assert isinstance(result, pd.DataFrame)
        assert "extracted_components" in result.columns
        assert result["extracted_components"].iloc[0] == "R1, C1"

    def test_predict_handles_multiple_rows(self, tiny_png_bytes: bytes) -> None:
        instance = Qwen3VLSchematicModel()
        instance.processor = MagicMock()
        instance.model = MagicMock()

        instance.processor.apply_chat_template.return_value.to.return_value = MagicMock()
        instance.model.generate.return_value = [MagicMock()]
        instance.processor.decode.side_effect = ["R1, C1", "U2, L3"]

        mock_context = MagicMock()
        model_input = pd.DataFrame(
            {
                "image": [tiny_png_bytes, tiny_png_bytes],
                "name": ["Proj1", "Proj2"],
                "type": [".kicad_sch", ".kicad_sch"],
            }
        )

        mock_torch = MagicMock()
        with patch.dict("sys.modules", {"torch": mock_torch}):
            result = instance.predict(mock_context, model_input)

        assert len(result) == 2


class TestRegisterModel:
    @patch("scan2kicad.serving.mlflow")
    @patch("scan2kicad.serving.snapshot_download", create=True)
    def test_returns_registered_name(
        self, mock_snapshot: MagicMock, mock_mlflow: MagicMock
    ) -> None:
        mock_snapshot.return_value = "/fake/model/dir"

        with patch("scan2kicad.serving.snapshot_download", mock_snapshot, create=True):
            # Need to import fresh to pick up the mock
            from scan2kicad.serving import register_model

            result = register_model(catalog="test", schema="kicad")

        assert result == "test.kicad.qwen3vl_open_schematics"

    @patch("scan2kicad.serving.mlflow")
    def test_sets_registry_uri(self, mock_mlflow: MagicMock) -> None:
        with patch("huggingface_hub.snapshot_download", return_value="/fake"):
            from scan2kicad.serving import register_model

            register_model()

        mock_mlflow.set_registry_uri.assert_called_once_with("databricks-uc")
