# Databricks notebook source

# MAGIC %md
# MAGIC # Register Qwen3VL Model for Serving
# MAGIC
# MAGIC Logs the Qwen3VL schematic model to MLflow, registers it in Unity Catalog,
# MAGIC and creates a Model Serving endpoint.

# COMMAND ----------

# MAGIC %pip install torch transformers accelerate Pillow mlflow huggingface-hub
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "lucasbruand_catalog")
dbutils.widgets.text("schema", "kicad")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Register model in Unity Catalog

# COMMAND ----------

from scan2kicad.serving import register_model

registered_name = register_model(catalog=catalog, schema=schema)
print(f"Registered model: {registered_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Create serving endpoint
# MAGIC
# MAGIC The serving endpoint is also declared in `resources/serving_endpoint.yml`
# MAGIC for DABs deployment. This cell creates it programmatically as an alternative.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

w.serving_endpoints.create(
    name="qwen3vl-schematics",
    config={
        "served_models": [
            {
                "model_name": f"{catalog}.{schema}.qwen3vl_open_schematics",
                "model_version": "1",
                "workload_type": "GPU_MEDIUM",
                "workload_size": "Small",
                "scale_to_zero_enabled": True,
            }
        ],
    },
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Test the endpoint

# COMMAND ----------

import base64

# Grab a sample image from the dataset
row = spark.table(f"{catalog}.{schema}.open_schematics").first()

response = w.serving_endpoints.query(
    name="qwen3vl-schematics",
    dataframe_records=[
        {
            "image": base64.b64encode(row["image"]).decode(),
            "name": row["name"],
            "type": row["type"],
        }
    ],
)
print(response.predictions)
