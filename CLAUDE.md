# CLAUDE.md

## Project

scan2kicad — KiCAD on Databricks. Ingest, understand, and render electronic schematics using Delta tables, Qwen3VL, and KiCad rendering.

## Stack

- **Python** ≥3.11, managed with **uv**
- **Databricks Asset Bundles** (DABs) for deployment (`databricks.yml`)
- **Linting**: ruff (E, F, I, W, UP rules, line-length 100)
- **Type checking**: ty (unresolved-import set to warn — GPU/Spark deps not installed locally)
- **Testing**: pytest
- **Build**: hatchling

## Commands

```bash
uv sync --extra dev       # Install all deps including pytest
uv run pytest tests/ -v   # Run tests (43 tests)
ruff check src/ tests/    # Lint
ruff format src/ tests/   # Format
ty check src/scan2kicad/  # Type check (warnings expected for torch/pyspark/IPython)
```

## Layout

```
src/scan2kicad/          # Python package
  ingestion.py           # Component 1: HuggingFace → Delta table
  inference.py           # Component 2: Qwen3VL batch inference (Pandas UDF)
  serving.py             # Component 2b: MLflow pyfunc + model registration
  rendering.py           # Component 3: kicad-cli + matplotlib rendering
  display.py             # Notebook display helpers
src/notebooks/           # Databricks notebooks (excluded from ruff)
resources/               # DABs job/endpoint definitions (YAML)
init_scripts/            # Cluster init scripts (kicad-cli install)
tests/                   # pytest tests for all modules
SPECS/                   # Technical specification docs
```

## Conventions

- Default catalog: `lucasbruand_catalog`, default schema: `kicad`
- Notebooks use Databricks format (`# Databricks notebook source` / `# COMMAND ----------`)
- Notebooks are excluded from ruff (`extend-exclude = ["src/notebooks"]`)
- GPU dependencies (torch, transformers, accelerate) are optional (`[project.optional-dependencies] gpu`)
- Spark/IPython/torch imports in library code use lazy imports or `TYPE_CHECKING` guards since they're only available on Databricks clusters
- Tests mock pyspark and IPython via `sys.modules` patching
