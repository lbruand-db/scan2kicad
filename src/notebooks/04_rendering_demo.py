# Databricks notebook source

# MAGIC %md
# MAGIC # KiCad Schematic Rendering Demo
# MAGIC
# MAGIC Demonstrates rendering `.kicad_sch` files from the Delta table using:
# MAGIC - Pre-rendered PNG images from the dataset
# MAGIC - kicad-cli (high fidelity, requires init script)
# MAGIC - matplotlib (lightweight wire-level preview)

# COMMAND ----------

dbutils.widgets.text("catalog", "lucasbruand_catalog")
dbutils.widgets.text("schema", "kicad")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gallery: pre-rendered images from dataset

# COMMAND ----------

from scan2kicad.display import display_schematic_gallery

df = spark.table(f"{catalog}.{schema}.open_schematics")
display_schematic_gallery(df, n=9, cols=3)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Single schematic display

# COMMAND ----------

from scan2kicad.display import display_schematic_from_row

row = df.first()
display_schematic_from_row(row)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Matplotlib wire-level preview (no kicad-cli needed)

# COMMAND ----------

from scan2kicad.rendering import render_schematic_matplotlib

row = df.first()
fig = render_schematic_matplotlib(row["schematic"])
display(fig)

# COMMAND ----------

# MAGIC %md
# MAGIC ## kicad-cli rendering (requires init script)
# MAGIC
# MAGIC Uncomment the cell below if `kicad-cli` is installed via the init script.

# COMMAND ----------

# from scan2kicad.rendering import render_kicad_schematic
# from IPython.display import SVG, display
#
# row = df.first()
# svg_bytes = render_kicad_schematic(row["schematic"], fmt="svg")
# display(SVG(data=svg_bytes))
