# scan2kicad

KiCAD on Databricks — ingest, understand, and render electronic schematics.

## Components

1. **Delta Table Ingestion** — Download the open-schematics dataset from Hugging Face and store as Delta
2. **Qwen3VL Inference** — Extract component labels from schematic images using a fine-tuned VLM
3. **KiCad Rendering** — Render `.kicad_sch` / `.kicad_pcb` files in Databricks notebooks

## Setup

```bash
uv sync
databricks bundle validate
databricks bundle deploy
```
