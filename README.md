# scan2kicad

[![CI](https://github.com/lbruand-db/scan2kicad/actions/workflows/ci.yml/badge.svg)](https://github.com/lbruand-db/scan2kicad/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/badge/type--checked-ty-blue)](https://github.com/astral-sh/ty)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![KiCad](https://img.shields.io/badge/KiCad-314CB0?logo=kicad&logoColor=white)](https://www.kicad.org/)
[![Databricks](https://img.shields.io/badge/Databricks-FF3621?logo=databricks&logoColor=white)](https://databricks.com/)
[![Hugging Face](https://img.shields.io/badge/HuggingFace-FFD21E?logo=huggingface&logoColor=black)](https://huggingface.co/datasets/bshada/open-schematics)
[![MLflow](https://img.shields.io/badge/MLflow-0194E2?logo=mlflow&logoColor=white)](https://mlflow.org/)
[![Built with Claude](https://img.shields.io/badge/Built%20with-Claude-blueviolet?logo=anthropic&logoColor=white)](https://claude.ai/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

KiCAD on Databricks — ingest, understand, and render electronic schematics.

## Components

1. **Delta Table Ingestion** — Download the [open-schematics](https://huggingface.co/datasets/bshada/open-schematics) dataset (84,470 schematics, 6.67 GB) from Hugging Face and store as a managed Delta table in Unity Catalog.
2. **Qwen3VL Inference** — Extract component labels from schematic images using the [qwen3vl-open-schematics-lora](https://huggingface.co/kingabzpro/qwen3vl-open-schematics-lora) fine-tuned VLM. Supports batch inference via Spark Pandas UDF and real-time inference via Databricks Model Serving.
3. **KiCad Rendering** — Render `.kicad_sch` / `.kicad_pcb` files in Databricks notebooks using kicad-cli (high fidelity) or matplotlib (lightweight wire-level preview).

## Project Structure

```
src/scan2kicad/          # Python package
  ingestion.py           # HuggingFace → Delta table
  inference.py           # Qwen3VL batch inference (Pandas UDF)
  serving.py             # MLflow pyfunc model + registration
  rendering.py           # kicad-cli + matplotlib rendering
  display.py             # Notebook display helpers (gallery, single)
src/notebooks/           # Databricks notebooks
  01_ingest_open_schematics.py
  02_qwen3vl_batch_inference.py
  03_model_serving_setup.py
  04_rendering_demo.py
resources/               # Databricks Asset Bundle job/endpoint definitions
init_scripts/            # Cluster init scripts (kicad-cli install)
tests/                   # pytest test suite
SPECS/                   # Technical specification
```

## Setup

```bash
# Install dependencies
uv sync --extra dev

# Validate and deploy the Databricks bundle
databricks bundle validate
databricks bundle deploy
```

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Lint and format
ruff check src/ tests/
ruff format src/ tests/

# Type check
ty check src/scan2kicad/
```

## Configuration

| Setting | Default |
|---------|---------|
| Catalog | `lucasbruand_catalog` |
| Schema  | `kicad` |

Catalog and schema can be overridden via DABs variables or notebook widget parameters.

## Notebooks

| Notebook | Description | Cluster |
|----------|-------------|---------|
| `01_ingest_open_schematics` | Download dataset and write to Delta | CPU, single-node |
| `02_qwen3vl_batch_inference` | Run VLM across all schematics | GPU (A10G/A100) |
| `03_model_serving_setup` | Register model and create serving endpoint | GPU |
| `04_rendering_demo` | Display schematics (gallery, matplotlib, kicad-cli) | CPU |
