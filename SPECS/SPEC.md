# KiCAD on Databricks - Technical Specification

**Version:** 1.0
**Date:** 2026-04-08
**Status:** Draft

---

## Table of Contents

1. [Overview](#1-overview)
2. [Component 1: Open-Schematics Delta Table Ingestion](#2-component-1-open-schematics-delta-table-ingestion)
3. [Component 2: Qwen3VL Schematic Understanding](#3-component-2-qwen3vl-schematic-understanding)
4. [Component 3: KiCad File Rendering in Databricks](#4-component-3-kicad-file-rendering-in-databricks)
5. [Component 4: KiCad-Tools in Code Genie](#5-component-4-kicad-tools-in-code-genie)
6. [Architecture Overview](#6-architecture-overview)
7. [Dependencies & Prerequisites](#7-dependencies--prerequisites)

---

## 1. Overview

This specification describes four workstreams for bringing KiCad electronic design automation (EDA) capabilities into the Databricks platform:

| # | Workstream | Purpose |
|---|-----------|---------|
| 1 | **Delta Table Ingestion** | Download the open-schematics dataset from Hugging Face and store it as a Delta table |
| 2 | **Qwen3VL Inference** | Use qwen3vl-open-schematics-lora for schematic image understanding (notebook + Model Serving) |
| 3 | **KiCad Rendering** | Render `.kicad_sch` / `.kicad_pcb` files visually inside Databricks notebooks |
| 4 | **KiCad-Tools + Code Genie** | Expose kicad-tools agentic framework as a tool in Databricks Code Genie |

### External Resources

| Resource | URL | License |
|----------|-----|---------|
| open-schematics dataset | https://huggingface.co/datasets/bshada/open-schematics | CC-BY-4.0 |
| qwen3vl-open-schematics-lora | https://huggingface.co/kingabzpro/qwen3vl-open-schematics-lora | Apache 2.0 |
| kicad-python (official bindings) | https://gitlab.com/kicad/code/kicad-python/ | MIT |
| kicad-tools (agentic framework) | https://github.com/rjwalters/kicad-tools | See repo |

---

## 2. Component 1: Open-Schematics Delta Table Ingestion

### 2.1 Dataset Description

The **open-schematics** dataset contains **84,470 electronic schematics** (6.67 GB) from public hardware projects. It is distributed as Parquet files on Hugging Face.

**Schema:**

| Column | Type | Description |
|--------|------|-------------|
| `schematic` | `STRING` | Raw `.kicad_sch` file content (S-expression text) |
| `image` | `BINARY` (PNG) | Rendered PNG image of the schematic |
| `components_used` | `ARRAY<STRING>` | List of electronic component identifiers |
| `json` | `STRING` | JSON representation of schematic structure (libSymbols, etc.) |
| `yaml` | `STRING` | YAML metadata of the schematic |
| `name` | `STRING` | Project name (e.g., `TiebeDeclercq/Uart-programmer`) |
| `description` | `STRING` | Human-readable project description |
| `type` | `STRING` | File extension (e.g., `.kicad_sch`) |

### 2.2 Ingestion Job Design

**Job type:** Databricks Workflow (single task, idempotent)
**Cluster:** Single-node or small cluster (data is 6.67 GB, parallelism optional)
**Schedule:** One-shot with optional periodic refresh

#### Step 1: Download Parquet Files from Hugging Face

```python
# Option B: Use the datasets library (simpler but loads into memory)
from datasets import load_dataset

ds = load_dataset("bshada/open-schematics", split="train")
```

#### Step 2: Write to Delta Table

```python
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType, StructField, StringType, BinaryType, ArrayType
)

spark = SparkSession.builder.getOrCreate()

# Read all downloaded parquet files
df = spark.read.parquet(f"{LOCAL_DIR}/default/train/")

# Write as managed Delta table in Unity Catalog
CATALOG = "main"
SCHEMA = "kicad"
TABLE = "open_schematics"

df.write.format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.{TABLE}")

# Optimize for downstream queries
spark.sql(f"OPTIMIZE {CATALOG}.{SCHEMA}.{TABLE}")
```

#### Step 3: Create Derived Views

```sql
-- Exploded components view for analytics
CREATE OR REPLACE VIEW main.kicad.schematic_components AS
SELECT
    name,
    description,
    type,
    explode(components_used) AS component,
    length(schematic) AS schematic_size_bytes
FROM main.kicad.open_schematics;

-- Component frequency analysis
CREATE OR REPLACE VIEW main.kicad.component_frequency AS
SELECT
    component,
    count(*) AS usage_count
FROM main.kicad.schematic_components
GROUP BY component
ORDER BY usage_count DESC;
```

### 2.3 Delta Table Schema (Target)

```
main.kicad.open_schematics
├── schematic       STRING        -- raw .kicad_sch content
├── image           BINARY        -- PNG bytes
├── components_used ARRAY<STRING> -- component list
├── json            STRING        -- JSON structure
├── yaml            STRING        -- YAML metadata
├── name            STRING        -- project name
├── description     STRING        -- project description
└── type            STRING        -- file extension
```

### 2.4 Considerations

- **Image column**: Hugging Face stores images as PIL objects; when writing from Parquet directly, they arrive as binary (PNG bytes). No conversion needed.
- **Idempotency**: Use `mode("overwrite")` to ensure re-runs are safe.
- **Volume alternative**: For raw file access, also stage the Parquet files into a Unity Catalog Volume (`/Volumes/main/kicad/raw/`).

---

## 3. Component 2: Qwen3VL Schematic Understanding

### 3.1 Model Overview

**Model:** `kingabzpro/qwen3vl-open-schematics-lora`
**Base:** Qwen3-VL-8B-Instruct (8B parameter vision-language model)
**Task:** Image-Text-to-Text — reads schematic images and extracts component identifiers
**Training:** Fine-tuned on open-schematics dataset (~800 samples, 1 epoch)
**Precision:** bfloat16

**Input:** Schematic PNG image + text prompt
**Output:** Comma-separated list of component labels (part numbers, values, footprints, net labels)

### 3.2 Approach A: Spark UDF in Notebook

Run inference across the Delta table using a Pandas UDF on a GPU cluster.

**Cluster requirements:** GPU cluster with A10G or A100 nodes (8B model needs ~16 GB VRAM in bf16)

```python
import torch
import pandas as pd
from pyspark.sql.functions import pandas_udf
from pyspark.sql.types import StringType
from transformers import AutoProcessor, AutoModelForVision2Seq
from PIL import Image
import io

MODEL_ID = "kingabzpro/qwen3vl-open-schematics-lora"

# Broadcast model loading (once per executor)
def get_model():
    if not hasattr(get_model, "_model"):
        get_model._processor = AutoProcessor.from_pretrained(MODEL_ID)
        get_model._model = AutoModelForVision2Seq.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        ).eval()
    return get_model._model, get_model._processor

@pandas_udf(StringType())
def extract_components(
    image_col: pd.Series,
    name_col: pd.Series,
    type_col: pd.Series,
) -> pd.Series:
    model, processor = get_model()
    results = []

    for img_bytes, name, ftype in zip(image_col, name_col, type_col):
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
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
            out = model.generate(**inputs, max_new_tokens=256, do_sample=False)
        gen = out[0][inputs["input_ids"].shape[1]:]
        results.append(processor.decode(gen, skip_special_tokens=True))

    return pd.Series(results)

# Apply to Delta table
df = spark.table("main.kicad.open_schematics")

df_with_components = df.select(
    "*",
    extract_components("image", "name", "type").alias("extracted_components")
)

df_with_components.write.format("delta") \
    .mode("overwrite") \
    .saveAsTable("main.kicad.open_schematics_enriched")
```

### 3.3 Approach B: Databricks Model Serving

Deploy the model as a real-time endpoint for on-demand schematic analysis.

#### Step 1: Log Model to MLflow

```python
import mlflow
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import Schema, ColSpec

mlflow.set_registry_uri("databricks-uc")

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

class Qwen3VLSchematicModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import torch
        from transformers import AutoProcessor, AutoModelForVision2Seq

        self.processor = AutoProcessor.from_pretrained(
            context.artifacts["model_dir"]
        )
        self.model = AutoModelForVision2Seq.from_pretrained(
            context.artifacts["model_dir"],
            torch_dtype=torch.bfloat16,
            device_map="auto",
        ).eval()

    def predict(self, context, model_input):
        import io
        from PIL import Image
        import torch

        results = []
        for _, row in model_input.iterrows():
            image = Image.open(io.BytesIO(row["image"])).convert("RGB")
            prompt = (
                f"Project: {row['name']}\nFormat: {row['type']}\n"
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

# Download model weights locally first
from huggingface_hub import snapshot_download
model_dir = snapshot_download("kingabzpro/qwen3vl-open-schematics-lora")

with mlflow.start_run():
    mlflow.pyfunc.log_model(
        artifact_path="qwen3vl-schematics",
        python_model=Qwen3VLSchematicModel(),
        artifacts={"model_dir": model_dir},
        signature=signature,
        pip_requirements=[
            "torch>=2.0",
            "transformers>=4.40",
            "accelerate",
            "Pillow",
        ],
        registered_model_name="main.kicad.qwen3vl_open_schematics",
    )
```

#### Step 2: Create Serving Endpoint

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

#### Step 3: Query the Endpoint

```python
import base64
import requests

image_bytes = open("schematic.png", "rb").read()

response = w.serving_endpoints.query(
    name="qwen3vl-schematics",
    dataframe_records=[{
        "image": base64.b64encode(image_bytes).decode(),
        "name": "MyProject",
        "type": ".kicad_sch",
    }],
)
print(response.predictions)
```

### 3.4 Considerations

- **GPU sizing**: 8B bf16 model requires ~16 GB VRAM. A10G (24 GB) is the minimum. A100 recommended for batch.
- **Throughput**: For batch processing of all 84k schematics, use Approach A with multi-GPU cluster. For interactive / API use, use Approach B.
- **Cost**: Enable scale-to-zero on the serving endpoint for cost efficiency.

---

## 4. Component 3: KiCad File Rendering in Databricks

### 4.1 Problem Statement

The open-schematics dataset already includes pre-rendered PNG images, but we also need the ability to render arbitrary `.kicad_sch` and `.kicad_pcb` files on the fly — e.g., schematics generated by agents, user uploads, or modified designs.

### 4.2 Rendering Approaches

#### Approach A: kicad-cli (Recommended for Fidelity)

`kicad-cli` is the official KiCad command-line tool that can export schematics and PCBs to SVG/PNG/PDF without a GUI.

**Cluster init script** to install KiCad:

```bash
#!/bin/bash
# init_kicad.sh — install KiCad CLI on Databricks cluster nodes
apt-get update -qq
apt-get install -y -qq kicad kicad-library 2>/dev/null || {
    # Fallback: install from PPA for Ubuntu-based images
    add-apt-repository -y ppa:kicad/kicad-9.0-releases
    apt-get update -qq
    apt-get install -y -qq kicad kicad-library
}
```

**Rendering function:**

```python
import subprocess
import tempfile
import os
from IPython.display import display, Image as IPImage, SVG

def render_kicad_schematic(kicad_sch_content: str, fmt: str = "svg") -> bytes:
    """Render a .kicad_sch string to SVG or PNG using kicad-cli."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sch_path = os.path.join(tmpdir, "schematic.kicad_sch")
        out_path = os.path.join(tmpdir, f"output.{fmt}")

        with open(sch_path, "w") as f:
            f.write(kicad_sch_content)

        cmd = [
            "kicad-cli", "sch", "export", fmt,
            "--output", out_path,
            sch_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        with open(out_path, "rb") as f:
            return f.read()

def render_kicad_pcb(kicad_pcb_content: str, fmt: str = "svg") -> bytes:
    """Render a .kicad_pcb string to SVG or PNG using kicad-cli."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pcb_path = os.path.join(tmpdir, "board.kicad_pcb")
        out_path = os.path.join(tmpdir, f"output.{fmt}")

        with open(pcb_path, "w") as f:
            f.write(kicad_pcb_content)

        cmd = [
            "kicad-cli", "pcb", "export", fmt,
            "--output", out_path,
            pcb_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        with open(out_path, "rb") as f:
            return f.read()

# Usage in notebook
row = spark.table("main.kicad.open_schematics").first()
svg_bytes = render_kicad_schematic(row["schematic"], fmt="svg")
display(SVG(data=svg_bytes))
```

#### Approach B: Pure Python S-expression Parsing + Matplotlib

For lightweight rendering without installing KiCad, parse the `.kicad_sch` S-expression format and draw with matplotlib. This is lower fidelity but zero-dependency.

```python
import re
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def parse_kicad_wires(sch_content: str):
    """Extract wire segments from .kicad_sch S-expression."""
    wires = []
    # Match (wire (pts (xy x1 y1) (xy x2 y2)) ...)
    pattern = r'\(wire\s+\(pts\s+\(xy\s+([\d.e+-]+)\s+([\d.e+-]+)\)\s+\(xy\s+([\d.e+-]+)\s+([\d.e+-]+)\)\)'
    for m in re.finditer(pattern, sch_content):
        wires.append((
            float(m.group(1)), float(m.group(2)),
            float(m.group(3)), float(m.group(4)),
        ))
    return wires

def render_schematic_matplotlib(sch_content: str):
    """Basic schematic rendering using matplotlib."""
    wires = parse_kicad_wires(sch_content)
    fig, ax = plt.subplots(1, 1, figsize=(16, 12))

    for x1, y1, x2, y2 in wires:
        ax.plot([x1, x2], [-y1, -y2], "b-", linewidth=0.5)

    ax.set_aspect("equal")
    ax.set_title("KiCad Schematic (wire-level preview)")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig

# Usage
row = spark.table("main.kicad.open_schematics").first()
fig = render_schematic_matplotlib(row["schematic"])
display(fig)
```

#### Approach C: Spark UDF for Batch Rendering

For re-rendering all schematics at scale (e.g., after modifications):

```python
from pyspark.sql.functions import udf
from pyspark.sql.types import BinaryType

@udf(BinaryType())
def render_sch_udf(sch_content: str) -> bytes:
    return render_kicad_schematic(sch_content, fmt="png")

df = spark.table("main.kicad.open_schematics")
df_rendered = df.withColumn("rendered_png", render_sch_udf("schematic"))
```

### 4.3 Display Helpers for Notebooks

```python
import base64
from IPython.display import display, HTML, Image as IPImage

def display_schematic_from_row(row):
    """Display a schematic from a Delta table row in a notebook."""
    # Use pre-rendered image if available
    if row["image"]:
        display(IPImage(data=row["image"]))
    else:
        svg = render_kicad_schematic(row["schematic"], fmt="svg")
        display(SVG(data=svg))

def display_schematic_gallery(df, n=6, cols=3):
    """Display a grid of schematics in a notebook."""
    rows = df.limit(n).collect()
    html = '<div style="display:grid;grid-template-columns:' + ' '.join(['1fr']*cols) + ';gap:10px;">'
    for row in rows:
        b64 = base64.b64encode(row["image"]).decode()
        html += f'''
        <div style="border:1px solid #ccc;padding:8px;">
            <img src="data:image/png;base64,{b64}" style="width:100%;"/>
            <p style="font-size:12px;margin-top:4px;"><b>{row["name"]}</b></p>
        </div>'''
    html += '</div>'
    display(HTML(html))

# Usage
df = spark.table("main.kicad.open_schematics")
display_schematic_gallery(df, n=9, cols=3)
```

### 4.4 Considerations

- **Approach A** (kicad-cli) gives pixel-perfect rendering but requires a cluster init script and ~500 MB of installed libraries.
- **Approach B** (matplotlib) is lightweight but only draws wires; symbols and text require deeper S-expression parsing.
- For most use cases, the **pre-rendered `image` column** in the dataset is sufficient. On-the-fly rendering is needed only for newly generated or modified schematics.

---

## 5. Component 4: KiCad-Tools in Code Genie

### 5.1 Overview

[kicad-tools](https://github.com/rjwalters/kicad-tools) is an agentic framework that exposes KiCad file operations as tool calls consumable by LLMs. It can parse, analyze, and manipulate `.kicad_sch` and `.kicad_pcb` files **without a running KiCad instance**.

Key capabilities:
- Parse schematics/PCBs into structured Python objects
- Generate BOM, netlist, component lists
- Run DRC/ERC checks (pure Python, no kicad-cli needed)
- Autoroute PCBs with physics/evolutionary algorithms
- Provide an MCP server for LLM tool integration
- `PCBReasoningAgent` for iterative LLM-driven layout

### 5.2 Integration with Databricks Code Genie

Code Genie (Databricks Assistant) supports tool use through function calling. We integrate kicad-tools by:

#### Option A: MCP Server Integration

kicad-tools ships an MCP server that exposes tools directly compatible with LLM function calling:

```bash
pip install "kicad-tools[mcp]"
kct mcp serve
```

**Exposed MCP tools:**

| Category | Tools |
|----------|-------|
| Analysis | `analyze_board`, `get_drc_violations`, `measure_clearance` |
| Export | `export_gerbers`, `export_bom`, `export_assembly` |
| Placement | `placement_analyze`, `placement_suggestions` |
| Routing | `route_net`, `get_unrouted_nets` |
| Sessions | `start_session`, `query_move`, `apply_move`, `commit`, `rollback` |

To connect this to Code Genie, register the MCP server in the workspace Genie configuration (when MCP support is available in Genie), or wrap the tools as Genie tool functions.

#### Option B: Unity Catalog Functions (Recommended Today)

Wrap kicad-tools operations as Unity Catalog Python UDFs that Genie can call:

```sql
-- Parse a schematic and list components
CREATE OR REPLACE FUNCTION main.kicad.list_components(
    schematic_content STRING
)
RETURNS ARRAY<STRUCT<reference STRING, value STRING, footprint STRING>>
LANGUAGE PYTHON
AS $$
from kicad_tools import load_schematic, Schematic

doc = load_schematic_from_string(schematic_content)
sch = Schematic(doc)
return [
    {"reference": s.reference, "value": s.value, "footprint": s.footprint}
    for s in sch.symbols
]
$$;

-- Generate BOM from schematic
CREATE OR REPLACE FUNCTION main.kicad.generate_bom(
    schematic_content STRING
)
RETURNS STRING
LANGUAGE PYTHON
AS $$
from kicad_tools import load_schematic, Schematic
import json

doc = load_schematic_from_string(schematic_content)
sch = Schematic(doc)
bom = []
for s in sch.symbols:
    bom.append({
        "reference": s.reference,
        "value": s.value,
        "footprint": s.footprint,
    })
return json.dumps(bom, indent=2)
$$;

-- Trace a net through the schematic
CREATE OR REPLACE FUNCTION main.kicad.trace_net(
    schematic_content STRING,
    net_name STRING
)
RETURNS STRING
LANGUAGE PYTHON
AS $$
from kicad_tools import load_schematic, Schematic
import json

doc = load_schematic_from_string(schematic_content)
sch = Schematic(doc)
net_info = sch.trace_net(net_name)
return json.dumps(net_info, indent=2)
$$;

-- Run ERC (Electrical Rules Check)
CREATE OR REPLACE FUNCTION main.kicad.run_erc(
    schematic_content STRING
)
RETURNS STRING
LANGUAGE PYTHON
AS $$
from kicad_tools import load_schematic, Schematic
import json

doc = load_schematic_from_string(schematic_content)
sch = Schematic(doc)
violations = sch.run_erc()
return json.dumps(violations, indent=2)
$$;
```

#### Option C: Genie Tool Functions (Python)

If using Genie Spaces with custom tool support, define tools as Python functions:

```python
# genie_kicad_tools.py — register as Genie tool functions

from kicad_tools import load_schematic, Schematic, Project
from kicad_tools.validate import DRCChecker
from kicad_tools import PCB
import json


def list_schematic_components(schematic_content: str) -> str:
    """List all components in a KiCad schematic.

    Args:
        schematic_content: Raw .kicad_sch file content as a string.

    Returns:
        JSON array of components with reference, value, and footprint.
    """
    doc = load_schematic(schematic_content)
    sch = Schematic(doc)
    components = [
        {
            "reference": s.reference,
            "value": s.value,
            "footprint": s.footprint,
        }
        for s in sch.symbols
    ]
    return json.dumps(components, indent=2)


def analyze_pcb_board(pcb_content: str) -> str:
    """Analyze a KiCad PCB board file.

    Args:
        pcb_content: Raw .kicad_pcb file content as a string.

    Returns:
        JSON summary of board dimensions, layers, nets, and components.
    """
    pcb = PCB.from_string(pcb_content)
    summary = {
        "board_dimensions": pcb.dimensions,
        "layer_count": len(pcb.layers),
        "net_count": len(pcb.nets),
        "component_count": len(pcb.footprints),
        "unrouted_nets": len(pcb.get_unrouted_nets()),
    }
    return json.dumps(summary, indent=2)


def run_design_rule_check(pcb_content: str, manufacturer: str = "jlcpcb") -> str:
    """Run DRC on a KiCad PCB with manufacturer-specific rules.

    Args:
        pcb_content: Raw .kicad_pcb file content.
        manufacturer: Target manufacturer (jlcpcb, oshpark, etc.).

    Returns:
        JSON array of DRC violations.
    """
    pcb = PCB.from_string(pcb_content)
    checker = DRCChecker(pcb, manufacturer=manufacturer)
    results = checker.check_all()
    return json.dumps(results, indent=2)


def generate_bom_csv(schematic_content: str) -> str:
    """Generate a Bill of Materials from a KiCad schematic.

    Args:
        schematic_content: Raw .kicad_sch file content.

    Returns:
        CSV-formatted BOM string.
    """
    doc = load_schematic(schematic_content)
    sch = Schematic(doc)
    lines = ["Reference,Value,Footprint,Quantity"]
    for s in sch.symbols:
        lines.append(f"{s.reference},{s.value},{s.footprint},1")
    return "\n".join(lines)
```

### 5.3 Example Genie Conversations

With these tools registered, a Genie user can have conversations like:

> **User:** "What components are used in the UART programmer schematic?"
>
> **Genie:** *calls `list_components` on the schematic from `main.kicad.open_schematics` where name = 'TiebeDeclercq/Uart-programmer'`*
>
> "The UART programmer uses: U1 (CH340G USB-UART bridge), C1-C3 (100nF decoupling caps), R1-R2 (10K pull-ups), J1 (USB-A connector), J2 (6-pin header)..."

> **User:** "Run a design rule check on my PCB with JLCPCB rules"
>
> **Genie:** *calls `run_design_rule_check(pcb_content, manufacturer="jlcpcb")`*
>
> "Found 3 violations: minimum trace width violation on net VCC (0.15mm < 0.2mm required), silk-to-pad clearance on U1 pin 3..."

> **User:** "Generate a BOM for this schematic"
>
> **Genie:** *calls `generate_bom_csv(schematic_content)`*
>
> *Returns formatted BOM table*

### 5.4 Advanced: PCB Reasoning Agent Loop

For complex PCB layout tasks, use the `PCBReasoningAgent` in a notebook to run an iterative LLM-driven layout session:

```python
from kicad_tools import PCBReasoningAgent
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

agent = PCBReasoningAgent.from_pcb("board.kicad_pcb")

while not agent.is_complete():
    prompt = agent.get_prompt()

    # Use Databricks Foundation Model API or external LLM
    response = w.serving_endpoints.query(
        name="databricks-claude-sonnet",  # or any FMAPI endpoint
        messages=[{"role": "user", "content": prompt}],
    )
    command = response.choices[0].message.content

    result, diagnosis = agent.execute(command)
    print(f"Action: {command}")
    print(f"Result: {diagnosis}")

# Save final board
agent.save("board_optimized.kicad_pcb")
```

### 5.5 Installation on Databricks

**Cluster init script:**

```bash
#!/bin/bash
pip install kicad-tools
```

**Or in notebook:**

```python
%pip install kicad-tools
dbutils.library.restartPython()
```

---

## 6. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Databricks Workspace                        │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │  Ingestion   │    │        Unity Catalog                 │   │
│  │  Workflow     │───▶│  main.kicad.open_schematics (Delta) │   │
│  │  (HF → Delta)│    │  main.kicad.open_schematics_enriched│   │
│  └──────────────┘    │  main.kicad.list_components()  (UDF) │   │
│                      │  main.kicad.generate_bom()     (UDF) │   │
│                      │  main.kicad.run_erc()          (UDF) │   │
│                      └──────────────┬───────────────────────┘   │
│                                     │                           │
│  ┌──────────────┐    ┌──────────────▼───────────────────────┐   │
│  │  Model       │    │        Notebooks                     │   │
│  │  Serving     │    │  - Qwen3VL batch inference (Spark)   │   │
│  │  Endpoint    │    │  - KiCad rendering (kicad-cli/mpl)   │   │
│  │  (Qwen3VL)   │    │  - PCBReasoningAgent sessions        │   │
│  └──────┬───────┘    └──────────────────────────────────────┘   │
│         │                                                       │
│  ┌──────▼───────┐    ┌──────────────────────────────────────┐   │
│  │  REST API    │    │        Code Genie                    │   │
│  │  /serving/   │    │  - UC function tools (kicad-tools)   │   │
│  │  qwen3vl-sch │    │  - "List components in schematic X"  │   │
│  └──────────────┘    │  - "Run DRC on my PCB"               │   │
│                      │  - "Generate BOM"                     │   │
│                      └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Dependencies & Prerequisites

### 7.1 Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `huggingface_hub` | >= 0.20 | Download dataset from HF |
| `datasets` | >= 2.16 | Optional: load dataset via HF datasets lib |
| `transformers` | >= 4.40 | Qwen3VL model loading & inference |
| `torch` | >= 2.0 | PyTorch backend |
| `accelerate` | >= 0.27 | Multi-GPU / device_map support |
| `kicad-tools` | latest | Agentic KiCad file manipulation |
| `kicad-python` | >= 0.7 | Official KiCad IPC API bindings (optional) |
| `Pillow` | >= 10.0 | Image handling |
| `mlflow` | >= 2.10 | Model logging & serving |

### 7.2 Infrastructure

| Resource | Specification |
|----------|--------------|
| **Ingestion cluster** | Single-node, 8+ GB RAM, no GPU needed |
| **Qwen3VL batch cluster** | GPU cluster: A10G (24 GB) or A100 (40/80 GB) nodes |
| **Model Serving endpoint** | GPU_MEDIUM workload (A10G), scale-to-zero enabled |
| **Rendering cluster** | Cluster with kicad-cli init script (for Approach A) |
| **Unity Catalog** | Catalog `main`, schema `kicad` |

### 7.3 Permissions

- Unity Catalog: CREATE TABLE, CREATE FUNCTION on `main.kicad`
- Model Serving: CREATE_ENDPOINT permission
- Cluster: Custom init script permissions
- External access: Outbound HTTPS to `huggingface.co` for dataset download

---

## Appendix A: kicad-python vs kicad-tools

| Feature | kicad-python | kicad-tools |
|---------|-------------|-------------|
| **Requires running KiCad** | Yes (IPC API client) | No (standalone parsing) |
| **Headless mode** | KiCad 11+ via `kicad-cli api-server` | Native |
| **File parsing** | Via KiCad engine | Pure Python S-expression parser |
| **DRC/ERC** | Via KiCad engine (full fidelity) | Pure Python (good coverage) |
| **MCP support** | No | Yes (`kct mcp serve`) |
| **LLM integration** | Manual | Built-in (`PCBReasoningAgent`) |
| **Best for** | Production-grade operations needing KiCad engine | AI/agent workflows, Databricks integration |

**Recommendation:** Use **kicad-tools** for Databricks integration (Components 3 & 4) because it works without a running KiCad instance. Use **kicad-python** only if you need full-fidelity KiCad engine operations and can run a headless KiCad API server.

---

## Appendix B: open-schematics Dataset Statistics

- **Total schematics:** 84,470
- **Dataset size:** 6.67 GB (Parquet)
- **Primary format:** `.kicad_sch` (KiCad 6+)
- **Unique components:** Thousands of unique component identifiers
- **Source:** Public hardware repositories (GitHub, GitLab)
- **Use cases:** Circuit design AI, component recognition, BOM generation, design validation