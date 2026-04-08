# Databricks notebook source

# MAGIC %md
# MAGIC # Qwen3VL Batch Inference on Schematics
# MAGIC
# MAGIC Runs the [qwen3vl-open-schematics-lora](https://huggingface.co/kingabzpro/qwen3vl-open-schematics-lora)
# MAGIC model across the open-schematics Delta table to extract component labels from
# MAGIC schematic images.
# MAGIC
# MAGIC **Cluster requirements:** GPU with A10G or A100 (≥16 GB VRAM for bf16 8B model).

# COMMAND ----------

# MAGIC %pip install torch transformers accelerate Pillow
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "kicad")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run batch inference

# COMMAND ----------

from scan2kicad.inference import make_extract_components_udf

extract_components = make_extract_components_udf()

df = spark.table(f"{catalog}.{schema}.open_schematics")

df_enriched = df.select(
    "*",
    extract_components("image", "name", "type").alias("extracted_components"),
)

df_enriched.write.format("delta").mode("overwrite").saveAsTable(
    f"{catalog}.{schema}.open_schematics_enriched"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Preview results

# COMMAND ----------

display(
    spark.table(f"{catalog}.{schema}.open_schematics_enriched")
    .select("name", "type", "extracted_components")
    .limit(10)
)
