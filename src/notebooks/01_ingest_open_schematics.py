# Databricks notebook source

# MAGIC %md
# MAGIC # Open-Schematics Dataset Ingestion
# MAGIC
# MAGIC Downloads the [open-schematics](https://huggingface.co/datasets/bshada/open-schematics)
# MAGIC dataset (84,470 electronic schematics, 6.67 GB) from Hugging Face and writes it
# MAGIC as a managed Delta table in Unity Catalog.

# COMMAND ----------

# MAGIC %pip install huggingface-hub
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "lucasbruand_catalog")
dbutils.widgets.text("schema", "kicad")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Ingest dataset to Delta table

# COMMAND ----------

from scan2kicad.ingestion import ingest_open_schematics

fqn = ingest_open_schematics(catalog=catalog, schema=schema)
print(f"Ingested to {fqn}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Verify

# COMMAND ----------

df = spark.table(f"{catalog}.{schema}.open_schematics")
print(f"Row count: {df.count()}")
df.printSchema()
df.show(5, truncate=40)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Create derived views

# COMMAND ----------

from scan2kicad.ingestion import create_derived_views

create_derived_views(catalog=catalog, schema=schema)
print("Views created")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Component frequency preview

# COMMAND ----------

display(spark.table(f"{catalog}.{schema}.component_frequency").limit(20))
