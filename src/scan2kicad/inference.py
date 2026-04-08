"""Component 2: Qwen3VL Schematic Understanding.

Provides both a Spark Pandas UDF for batch inference and an MLflow
pyfunc model class for Databricks Model Serving.
"""

from __future__ import annotations

import io
from typing import Any

MODEL_ID = "kingabzpro/qwen3vl-open-schematics-lora"

PROMPT_TEMPLATE = (
    "Project: {name}\nFormat: {ftype}\n"
    "From the schematic image, extract all component labels and "
    "identifiers exactly as shown (part numbers, values, footprints, "
    "net labels like +5V/GND).\n"
    "Output only a comma-separated list. Do not generalize or add extra text."
)

# Module-level cache for model and processor (populated on first call)
_cached_model: Any = None
_cached_processor: Any = None


def _get_model() -> tuple[Any, Any]:
    """Lazy-load model and processor (cached per executor)."""
    global _cached_model, _cached_processor  # noqa: PLW0603

    if _cached_model is None:
        import torch
        from transformers import AutoModelForVision2Seq, AutoProcessor

        _cached_processor = AutoProcessor.from_pretrained(MODEL_ID)
        _cached_model = AutoModelForVision2Seq.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        ).eval()
    return _cached_model, _cached_processor


def predict_single(image_bytes: bytes, name: str, ftype: str) -> str:
    """Run inference on a single schematic image."""
    import torch
    from PIL import Image

    model, processor = _get_model()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    prompt = PROMPT_TEMPLATE.format(name=name, ftype=ftype)

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)

    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=256, do_sample=False)

    gen = out[0][inputs["input_ids"].shape[1] :]
    return processor.decode(gen, skip_special_tokens=True)


def make_extract_components_udf():  # type: ignore[no-any-return]
    """Return a Spark Pandas UDF for batch extraction."""
    import pandas as pd
    from pyspark.sql.functions import pandas_udf
    from pyspark.sql.types import StringType

    @pandas_udf(StringType())
    def extract_components(
        image_col: pd.Series,  # type: ignore[type-arg]
        name_col: pd.Series,  # type: ignore[type-arg]
        type_col: pd.Series,  # type: ignore[type-arg]
    ) -> pd.Series:  # type: ignore[type-arg]
        results = []
        for img_bytes, name, ftype in zip(image_col, name_col, type_col):
            results.append(predict_single(img_bytes, name, ftype))
        return pd.Series(results)

    return extract_components
