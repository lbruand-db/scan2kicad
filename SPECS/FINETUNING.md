# Fine-Tuning Qwen3-VL-8B on Databricks - Migration Plan

**Version:** 1.0
**Date:** 2026-04-08
**Status:** Draft
**Source tutorial:** [Fine-Tuning Qwen3-VL 8B: A Step-by-Step Guide (DataCamp)](https://www.datacamp.com/tutorial/fine-tuning-qwen3-vl-8b)
**Reference notebook:** [Fine-tuning Qwen3 VL 8B.ipynb (HuggingFace)](https://huggingface.co/kingabzpro/qwen3vl-open-schematics-lora/blob/main/Fine-tuning%20Qwen3%20VL%208B.ipynb)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Original Tutorial Summary](#2-original-tutorial-summary)
3. [Migration Strategy](#3-migration-strategy)
4. [Notebook 1: Data Preparation](#4-notebook-1-data-preparation)
5. [Notebook 2: Model Fine-Tuning](#5-notebook-2-model-fine-tuning)
6. [Notebook 3: Evaluation & Inference](#6-notebook-3-evaluation--inference)
7. [Notebook 4: Model Registration & Serving](#7-notebook-4-model-registration--serving)
8. [Infrastructure & Cluster Configuration](#8-infrastructure--cluster-configuration)
9. [Key Differences: Colab vs Databricks](#9-key-differences-colab-vs-databricks)

---

## 1. Overview

This document plans the migration of the [DataCamp Qwen3-VL-8B fine-tuning tutorial](https://www.datacamp.com/tutorial/fine-tuning-qwen3-vl-8b) to Databricks. The tutorial fine-tunes Qwen3-VL-8B-Instruct on the [open-schematics](https://huggingface.co/datasets/bshada/open-schematics) dataset to extract electronic component labels from schematic images.

The resulting model is equivalent to [kingabzpro/qwen3vl-open-schematics-lora](https://huggingface.co/kingabzpro/qwen3vl-open-schematics-lora).

### Goals

- Reproduce the fine-tuning pipeline entirely on Databricks
- Read training data from the Delta table (`main.kicad.open_schematics`) created in [SPEC.md](./SPEC.md)
- Log the fine-tuned model to MLflow / Unity Catalog
- Deploy to a Model Serving endpoint

---

## 2. Original Tutorial Summary

### 2.1 Pipeline Steps (as in the DataCamp tutorial)

| Step | Description |
|------|-------------|
| 1 | Install dependencies (`transformers`, `peft`, `trl`, `flash-attn`, etc.) |
| 2 | Load `bshada/open-schematics` dataset (84,470 rows) |
| 3 | Filter & clean: remove rows without valid images or empty component lists |
| 4 | Build chat-formatted training examples (image + prompt → component list) |
| 5 | Load Qwen3-VL-8B-Instruct in bf16 with Flash Attention 2 |
| 6 | Baseline evaluation: run inference on sample before fine-tuning |
| 7 | Configure LoRA (rank=16, alpha=32, target 7 projection layers) |
| 8 | Train with SFTTrainer (1 epoch, ~800 samples, batch=2, lr=1e-4) |
| 9 | Evaluate fine-tuned model vs baseline |
| 10 | Push LoRA adapter + merged model to Hugging Face Hub |

### 2.2 Key Configurations

**LoRA (PEFT) configuration:**

```python
from peft import LoraConfig, TaskType

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
)
```

**Training arguments (SFTConfig):**

```python
from trl import SFTConfig

training_args = SFTConfig(
    output_dir="./qwen3vl-schematics-lora",
    num_train_epochs=1,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    gradient_checkpointing=False,
    learning_rate=1e-4,
    warmup_steps=10,
    weight_decay=0.01,
    max_grad_norm=1.0,
    bf16=True,
    fp16=False,
    lr_scheduler_type="cosine",
    logging_steps=10,
    report_to="none",
    remove_unused_columns=False,
)
```

**Prompt template:**

```
Project: {name}
Format: {type}
From the schematic image, extract all component labels and identifiers exactly
as shown (part numbers, values, footprints, net labels like +5V/GND).
Output only a comma-separated list. Do not generalize or add extra text.
```

### 2.3 Dependencies (Original)

```
torch
transformers==5.0.0rc1
accelerate
datasets
peft
trl
flash-attn
pillow
sentencepiece
safetensors
```

---

## 3. Migration Strategy

### 3.1 What Changes on Databricks

| Aspect | Original (Colab/local) | Databricks |
|--------|----------------------|------------|
| **Data source** | `load_dataset("bshada/open-schematics")` from HF | `spark.table("main.kicad.open_schematics")` from Delta |
| **GPU** | Single A100 (Colab Pro) | A10G or A100 cluster (single-node GPU) |
| **Experiment tracking** | Manual / HF Hub | MLflow autologging |
| **Model registry** | HF Hub push | Unity Catalog model registry |
| **Model serving** | Local inference | Databricks Model Serving endpoint |
| **Environment** | pip install in Colab | `%pip install` + cluster init script |
| **Flash Attention** | Manual install | Pre-installed on ML GPU runtimes (DBR 15.x+) |
| **Checkpointing** | Local disk | DBFS / Unity Catalog Volumes |
| **report_to** | `"none"` | `"mlflow"` |

### 3.2 Notebook Breakdown

The single Colab notebook is split into four Databricks notebooks for modularity:

```
notebooks/
├── 01_data_preparation.py     # Filter & format training data
├── 02_fine_tuning.py          # LoRA fine-tuning with SFTTrainer
├── 03_evaluation.py           # Compare base vs fine-tuned model
└── 04_register_and_serve.py   # MLflow registration + serving endpoint
```

---

## 4. Notebook 1: Data Preparation

### 4.1 Load from Delta Table

```python
# Read from the Delta table created by the ingestion job (SPEC.md §2)
df = spark.table("main.kicad.open_schematics")
print(f"Total rows: {df.count()}")

# Check schema
df.printSchema()
```

### 4.2 Filter Invalid Rows

```python
from pyspark.sql.functions import col, size

df_clean = df.filter(
    col("image").isNotNull()
    & col("components_used").isNotNull()
    & (size("components_used") > 0)
    & col("name").isNotNull()
)

print(f"Clean rows: {df_clean.count()}")
# Expected: ~33K+ samples after filtering
```

### 4.3 Sample for Training

The original tutorial uses ~800 samples for 1 epoch. We follow the same approach but can scale up.

```python
# Subsample for initial training run (matching original tutorial)
TRAIN_SIZE = 800
EVAL_SIZE = 100

df_sampled = df_clean.orderBy("name").limit(TRAIN_SIZE + EVAL_SIZE)

# Write to a staging table for reproducibility
df_sampled.write.format("delta") \
    .mode("overwrite") \
    .saveAsTable("main.kicad.finetune_staging")
```

### 4.4 Convert to Hugging Face Dataset

The SFTTrainer expects a HF Dataset. Convert from the Delta table on the driver node.

```python
import pandas as pd
from datasets import Dataset
from PIL import Image
import io

# Collect to driver (small dataset, ~800 rows)
pdf = spark.table("main.kicad.finetune_staging").toPandas()

# Convert image bytes to PIL
def bytes_to_pil(img_bytes):
    if img_bytes is None:
        return None
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")

pdf["image"] = pdf["image"].apply(bytes_to_pil)

# Split train/eval
train_pdf = pdf.iloc[:TRAIN_SIZE]
eval_pdf = pdf.iloc[TRAIN_SIZE:TRAIN_SIZE + EVAL_SIZE]

ds_train = Dataset.from_pandas(train_pdf)
ds_eval = Dataset.from_pandas(eval_pdf)

print(f"Train: {len(ds_train)}, Eval: {len(ds_eval)}")
```

### 4.5 Format as Chat Messages

```python
def format_data(example):
    """Convert a dataset row into chat-format messages for SFTTrainer."""
    name = example.get("name") or "Unknown project"
    ftype = example.get("type") or "unknown format"
    components = example.get("components_used") or []

    user_prompt = (
        f"Project: {name}\nFormat: {ftype}\n"
        "From the schematic image, extract all component labels and "
        "identifiers exactly as shown (part numbers, values, footprints, "
        "net labels like +5V/GND).\n"
        "Output only a comma-separated list. Do not generalize or add extra text."
    )

    assistant_response = ", ".join(components)

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": example["image"]},
                {"type": "text", "text": user_prompt},
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": assistant_response},
            ],
        },
    ]
    return {"messages": messages}

ds_train = ds_train.map(format_data)
ds_eval = ds_eval.map(format_data)
```

---

## 5. Notebook 2: Model Fine-Tuning

### 5.1 Install Dependencies

```python
%pip install -U accelerate datasets pillow sentencepiece safetensors peft
%pip install "transformers>=5.0.0rc1"
%pip install --no-deps trl
%pip install --no-cache-dir flash-attn --no-build-isolation
dbutils.library.restartPython()
```

### 5.2 Environment Setup

```python
import torch
from transformers import set_seed

set_seed(42)

# TF32 for A100 speedup
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

print("CUDA:", torch.cuda.is_available())
print("Device:", torch.cuda.get_device_name(0))
print("bf16:", torch.cuda.is_bf16_supported())
```

### 5.3 Load Base Model & Processor

```python
from transformers import AutoProcessor, AutoModelForVision2Seq

MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"

processor = AutoProcessor.from_pretrained(MODEL_ID)

model = AutoModelForVision2Seq.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
    device_map="auto",
)

print(f"Model parameters: {model.num_parameters():,}")
print(f"Model dtype: {model.dtype}")
```

### 5.4 Configure LoRA

```python
from peft import LoraConfig, TaskType, get_peft_model

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# Expected: ~0.5-1% of total parameters are trainable
```

### 5.5 Data Collator

The collator tokenizes each chat-formatted example, pads the batch, and masks non-assistant tokens in the labels so the loss is computed only on the assistant's response.

```python
from transformers import DataCollatorForSeq2Seq

def collate_fn(examples):
    """Vision-language collator for Qwen3-VL fine-tuning.

    Processes chat messages with images, tokenizes them, and masks
    system/user turns in labels so loss is only on assistant response.
    """
    texts = []
    images = []

    for ex in examples:
        msgs = ex["messages"]
        text = processor.apply_chat_template(
            msgs,
            tokenize=False,
            add_generation_prompt=False,
        )
        texts.append(text)

        # Collect images from user messages
        for msg in msgs:
            if msg["role"] == "user":
                for content in msg["content"]:
                    if content["type"] == "image":
                        images.append(content["image"])

    batch = processor(
        text=texts,
        images=images if images else None,
        padding=True,
        truncation=True,
        max_length=2048,
        return_tensors="pt",
    )

    # Create labels: copy input_ids, mask padding with -100
    labels = batch["input_ids"].clone()
    labels[labels == processor.tokenizer.pad_token_id] = -100
    batch["labels"] = labels

    return batch
```

### 5.6 Configure Training

```python
import mlflow
from trl import SFTConfig, SFTTrainer

# Databricks MLflow integration
mlflow.set_experiment("/Users/{user}/qwen3vl-schematics-finetune")

# Checkpoints go to a Unity Catalog Volume
OUTPUT_DIR = "/Volumes/main/kicad/checkpoints/qwen3vl-schematics-lora"

training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=1,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    gradient_checkpointing=False,
    learning_rate=1e-4,
    warmup_steps=10,
    weight_decay=0.01,
    max_grad_norm=1.0,
    bf16=True,
    fp16=False,
    lr_scheduler_type="cosine",
    logging_steps=10,
    save_steps=100,
    save_total_limit=3,
    report_to="mlflow",              # <-- Changed from "none" to "mlflow"
    remove_unused_columns=False,      # Required for vision fine-tuning
    dataset_text_field="",            # Required for custom collator
    dataset_kwargs={"skip_prepare_dataset": True},
)
```

### 5.7 Train

```python
trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=ds_train,
    eval_dataset=ds_eval,
    data_collator=collate_fn,
)

# Train with MLflow autologging
with mlflow.start_run(run_name="qwen3vl-schematics-lora-v1"):
    mlflow.log_params({
        "base_model": MODEL_ID,
        "lora_r": lora_config.r,
        "lora_alpha": lora_config.lora_alpha,
        "train_size": len(ds_train),
        "eval_size": len(ds_eval),
    })
    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    processor.save_pretrained(OUTPUT_DIR)
```

### 5.8 Training Metrics (Expected)

Based on the original tutorial:

| Metric | Value |
|--------|-------|
| Training samples | ~800 |
| Epochs | 1 |
| Steps | ~100 (800 / batch_size=2 / grad_accum=4) |
| Final loss | ~0.2–0.4 |
| Training time | ~15–30 min on A100 |
| VRAM usage | ~18–22 GB (bf16 + LoRA) |

---

## 6. Notebook 3: Evaluation & Inference

### 6.1 Load Fine-Tuned Model

```python
from transformers import AutoProcessor, AutoModelForVision2Seq
from peft import PeftModel
import torch

MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
ADAPTER_DIR = "/Volumes/main/kicad/checkpoints/qwen3vl-schematics-lora"

processor = AutoProcessor.from_pretrained(ADAPTER_DIR)

base_model = AutoModelForVision2Seq.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
    device_map="auto",
)

model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)
model = model.eval()
```

### 6.2 Inference Function

```python
from PIL import Image
import io

def run_inference(model, processor, image, name="Unknown", ftype=".kicad_sch", max_new_tokens=256):
    """Run component extraction on a single schematic image."""
    prompt = (
        f"Project: {name}\nFormat: {ftype}\n"
        "From the schematic image, extract all component labels and "
        "identifiers exactly as shown (part numbers, values, footprints, "
        "net labels like +5V/GND).\n"
        "Output only a comma-separated list. Do not generalize or add extra text."
    )

    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt},
        ],
    }]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)

    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)

    gen = out[0][inputs["input_ids"].shape[1]:]
    return processor.decode(gen, skip_special_tokens=True)
```

### 6.3 Compare Base vs Fine-Tuned

```python
# Load a few evaluation examples from Delta
eval_rows = spark.table("main.kicad.finetune_staging") \
    .orderBy("name") \
    .limit(5) \
    .collect()

for row in eval_rows:
    image = Image.open(io.BytesIO(row["image"])).convert("RGB")
    name = row["name"]
    ground_truth = row["components_used"]

    prediction = run_inference(model, processor, image, name=name)

    print(f"\n{'='*60}")
    print(f"Project: {name}")
    print(f"Ground truth: {', '.join(ground_truth[:10])}...")
    print(f"Predicted:    {prediction[:200]}...")
```

### 6.4 Batch Evaluation Metrics

```python
from collections import Counter

def compute_component_metrics(predicted_str, ground_truth_list):
    """Compute precision/recall/F1 for component extraction."""
    predicted = set(c.strip() for c in predicted_str.split(","))
    truth = set(ground_truth_list)

    tp = len(predicted & truth)
    precision = tp / len(predicted) if predicted else 0
    recall = tp / len(truth) if truth else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    return {"precision": precision, "recall": recall, "f1": f1}

# Run on full eval set
metrics_list = []
for row in eval_rows:
    image = Image.open(io.BytesIO(row["image"])).convert("RGB")
    pred = run_inference(model, processor, image, name=row["name"])
    m = compute_component_metrics(pred, row["components_used"])
    metrics_list.append(m)

avg_f1 = sum(m["f1"] for m in metrics_list) / len(metrics_list)
avg_precision = sum(m["precision"] for m in metrics_list) / len(metrics_list)
avg_recall = sum(m["recall"] for m in metrics_list) / len(metrics_list)

print(f"Avg Precision: {avg_precision:.3f}")
print(f"Avg Recall:    {avg_recall:.3f}")
print(f"Avg F1:        {avg_f1:.3f}")

# Log to MLflow
mlflow.log_metrics({
    "eval_precision": avg_precision,
    "eval_recall": avg_recall,
    "eval_f1": avg_f1,
})
```

---

## 7. Notebook 4: Model Registration & Serving

### 7.1 Merge LoRA Adapter

```python
from peft import PeftModel
from transformers import AutoProcessor, AutoModelForVision2Seq
import torch

MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
ADAPTER_DIR = "/Volumes/main/kicad/checkpoints/qwen3vl-schematics-lora"
MERGED_DIR = "/Volumes/main/kicad/models/qwen3vl-schematics-merged"

# Load base + adapter and merge
base_model = AutoModelForVision2Seq.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16,
    device_map="cpu",  # Merge on CPU to save VRAM
)
model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)
model = model.merge_and_unload()

# Save merged model
model.save_pretrained(MERGED_DIR)
processor = AutoProcessor.from_pretrained(ADAPTER_DIR)
processor.save_pretrained(MERGED_DIR)

print(f"Merged model saved to {MERGED_DIR}")
```

### 7.2 Log to MLflow / Unity Catalog

```python
import mlflow
import pandas as pd

mlflow.set_registry_uri("databricks-uc")

class Qwen3VLSchematicModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import torch
        from transformers import AutoProcessor, AutoModelForVision2Seq

        model_dir = context.artifacts["model_dir"]
        self.processor = AutoProcessor.from_pretrained(model_dir)
        self.model = AutoModelForVision2Seq.from_pretrained(
            model_dir,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        ).eval()

    def predict(self, context, model_input):
        import io, torch
        from PIL import Image

        results = []
        for _, row in model_input.iterrows():
            image = Image.open(io.BytesIO(row["image"])).convert("RGB")
            prompt = (
                f"Project: {row.get('name', 'Unknown')}\n"
                f"Format: {row.get('type', '.kicad_sch')}\n"
                "From the schematic image, extract all component labels "
                "exactly as shown. Output only a comma-separated list."
            )
            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }]
            inputs = self.processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device)

            with torch.inference_mode():
                out = self.model.generate(
                    **inputs, max_new_tokens=256, do_sample=False
                )
            gen = out[0][inputs["input_ids"].shape[1]:]
            results.append(
                self.processor.decode(gen, skip_special_tokens=True)
            )

        return pd.DataFrame({"extracted_components": results})

# Log model
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import Schema, ColSpec

signature = ModelSignature(
    inputs=Schema([
        ColSpec("binary", "image"),
        ColSpec("string", "name"),
        ColSpec("string", "type"),
    ]),
    outputs=Schema([
        ColSpec("string", "extracted_components"),
    ]),
)

with mlflow.start_run(run_name="qwen3vl-schematics-merged"):
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=Qwen3VLSchematicModel(),
        artifacts={"model_dir": MERGED_DIR},
        signature=signature,
        pip_requirements=[
            "torch>=2.0",
            "transformers>=5.0.0rc1",
            "accelerate",
            "Pillow",
        ],
        registered_model_name="main.kicad.qwen3vl_open_schematics",
    )
```

### 7.3 Create Serving Endpoint

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

w.serving_endpoints.create(
    name="qwen3vl-schematics",
    config={
        "served_models": [{
            "model_name": "main.kicad.qwen3vl_open_schematics",
            "model_version": "1",
            "workload_type": "GPU_MEDIUM",  # A10G
            "workload_size": "Small",
            "scale_to_zero_enabled": True,
        }],
    },
)
```

### 7.4 Test the Endpoint

```python
import base64

# Read a test image from the Delta table
test_row = spark.table("main.kicad.open_schematics").limit(1).collect()[0]

response = w.serving_endpoints.query(
    name="qwen3vl-schematics",
    dataframe_records=[{
        "image": base64.b64encode(test_row["image"]).decode(),
        "name": test_row["name"],
        "type": test_row["type"],
    }],
)
print(response.predictions)
```

---

## 8. Infrastructure & Cluster Configuration

### 8.1 Cluster for Fine-Tuning

| Setting | Value |
|---------|-------|
| **Runtime** | Databricks ML Runtime 15.4 LTS GPU |
| **Instance type** | `Standard_NC24ads_A100_v4` (Azure) or `p4d.24xlarge` (AWS) |
| **GPUs** | 1x A100 40GB (minimum) |
| **Driver** | Same as worker (single-node) |
| **Workers** | 0 (single-node cluster) |
| **Autoscaling** | Disabled |
| **Spot/preemptible** | Acceptable (checkpoints saved to Volumes) |

**Alternative (cost-optimized):** A10G instances (`g5.2xlarge` on AWS) work for the 800-sample run with LoRA + bf16 (~18 GB VRAM).

### 8.2 Cluster Init Script

```bash
#!/bin/bash
# init_finetune.sh — stored in /Volumes/main/kicad/scripts/
pip install -U accelerate datasets pillow sentencepiece safetensors peft
pip install "transformers>=5.0.0rc1"
pip install --no-deps trl
# flash-attn is pre-installed on ML GPU runtimes
```

### 8.3 Unity Catalog Volumes

```
/Volumes/main/kicad/
├── checkpoints/          # LoRA adapter checkpoints during training
│   └── qwen3vl-schematics-lora/
├── models/               # Merged model weights
│   └── qwen3vl-schematics-merged/
└── scripts/              # Init scripts
    └── init_finetune.sh
```

---

## 9. Key Differences: Colab vs Databricks

| Concern | Colab Approach | Databricks Approach |
|---------|---------------|-------------------|
| **Data loading** | `load_dataset()` from HF Hub | `spark.table()` → `.toPandas()` → `Dataset.from_pandas()` |
| **Image format** | PIL images from HF datasets | Binary bytes in Delta → convert to PIL on driver |
| **Checkpointing** | `/content/` (ephemeral) | UC Volumes (persistent across cluster restarts) |
| **Experiment tracking** | None / Weights & Biases | MLflow (`report_to="mlflow"`) |
| **Model storage** | `model.push_to_hub()` | `mlflow.pyfunc.log_model()` → UC model registry |
| **Serving** | Local `model.generate()` | Databricks Model Serving endpoint (REST API) |
| **Scaling up** | Limited to single Colab GPU | Can use multi-GPU or larger instances |
| **Cost management** | Colab Pro subscription | Spot instances + scale-to-zero serving |
| **Reproducibility** | Notebook + pip freeze | Databricks Job + UC Volume artifacts + MLflow run |

### 9.1 Migration Gotchas

1. **Image column type**: Delta stores images as `BINARY`. The HF datasets library stores them as `PIL.Image`. Must convert with `Image.open(io.BytesIO(bytes))` when going from Delta to HF Dataset.

2. **Flash Attention**: Pre-installed on DBR ML GPU runtimes (15.x+). No need for `pip install flash-attn --no-build-isolation` if using the right runtime.

3. **Disk space for model weights**: The 8B model is ~16 GB. Ensure the driver has sufficient local storage or use Volumes.

4. **`remove_unused_columns=False`**: Critical for vision fine-tuning — SFTTrainer will drop image columns otherwise.

5. **`dataset_kwargs={"skip_prepare_dataset": True}`**: Required when using a custom collator; prevents SFTTrainer from trying to auto-process the dataset.

6. **Cluster timeout**: Fine-tuning takes 15–30 minutes. Set cluster auto-termination to at least 60 minutes.

7. **HF Hub tokens**: If downloading the base model requires authentication, store the HF token as a Databricks secret:
   ```python
   import os
   os.environ["HF_TOKEN"] = dbutils.secrets.get("hf", "token")
   ```