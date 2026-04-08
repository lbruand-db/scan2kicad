"""Component 2b: MLflow model for Databricks Model Serving."""

from __future__ import annotations

from typing import Any

import mlflow
import pandas as pd
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import ColSpec, Schema


class Qwen3VLSchematicModel(mlflow.pyfunc.PythonModel):
    """MLflow pyfunc wrapper around Qwen3VL for schematic understanding."""

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        import torch
        from transformers import AutoModelForVision2Seq, AutoProcessor

        model_dir = context.artifacts["model_dir"]
        self.processor = AutoProcessor.from_pretrained(model_dir)
        self.model = AutoModelForVision2Seq.from_pretrained(
            model_dir,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        ).eval()

    def predict(
        self,
        context: mlflow.pyfunc.PythonModelContext,
        model_input: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        import io

        import torch
        from PIL import Image

        results = []
        for _, row in model_input.iterrows():
            image = Image.open(io.BytesIO(row["image"])).convert("RGB")
            prompt = (
                f"Project: {row['name']}\nFormat: {row['type']}\n"
                "From the schematic image, extract all component labels "
                "exactly as shown. Output only a comma-separated list."
            )
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            inputs = self.processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device)

            with torch.inference_mode():
                out = self.model.generate(**inputs, max_new_tokens=256, do_sample=False)
            gen = out[0][inputs["input_ids"].shape[1] :]
            results.append(self.processor.decode(gen, skip_special_tokens=True))

        return pd.DataFrame({"extracted_components": results})


MODEL_SIGNATURE = ModelSignature(
    inputs=Schema(
        [
            ColSpec("binary", "image"),
            ColSpec("string", "name"),
            ColSpec("string", "type"),
        ]
    ),
    outputs=Schema([ColSpec("string", "extracted_components")]),
)


def register_model(
    catalog: str = "main",
    schema: str = "kicad",
) -> str:
    """Download model weights, log to MLflow, and register in Unity Catalog.

    Returns the registered model name.
    """
    from huggingface_hub import snapshot_download

    from .inference import MODEL_ID

    mlflow.set_registry_uri("databricks-uc")
    registered_name = f"{catalog}.{schema}.qwen3vl_open_schematics"

    model_dir = snapshot_download(MODEL_ID)

    with mlflow.start_run():
        mlflow.pyfunc.log_model(
            artifact_path="qwen3vl-schematics",
            python_model=Qwen3VLSchematicModel(),
            artifacts={"model_dir": model_dir},
            signature=MODEL_SIGNATURE,
            pip_requirements=[
                "torch>=2.0",
                "transformers>=4.40",
                "accelerate",
                "Pillow",
            ],
            registered_model_name=registered_name,
        )

    return registered_name
