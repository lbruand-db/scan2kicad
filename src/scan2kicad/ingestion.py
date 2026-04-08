"""Component 1: Open-Schematics Delta Table Ingestion.

Downloads the open-schematics dataset from Hugging Face and writes it
as a managed Delta table in Unity Catalog.
"""

from __future__ import annotations

import glob
import os
import shutil
import tempfile

from huggingface_hub import snapshot_download
from pyspark.sql import SparkSession

VOLUME_PATH = "/Volumes/{catalog}/{schema}/raw"


def get_spark() -> SparkSession:
    return SparkSession.builder.getOrCreate()


def ingest_open_schematics(
    catalog: str = "lucasbruand_catalog",
    schema: str = "kicad",
    table: str = "open_schematics",
) -> str:
    """Download open-schematics from Hugging Face and write to Delta.

    Returns the fully-qualified table name.
    """
    spark = get_spark()
    fqn = f"{catalog}.{schema}.{table}"

    # Ensure schema and volume exist
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.raw")

    volume_dir = VOLUME_PATH.format(catalog=catalog, schema=schema)
    parquet_dir = f"{volume_dir}/open_schematics_parquet"

    # Download parquet files from HF Hub into a temp directory, then copy to Volume
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, "cache")
        local_dir = os.path.join(tmpdir, "data")

        snapshot_download(
            repo_id="bshada/open-schematics",
            repo_type="dataset",
            local_dir=local_dir,
            cache_dir=cache_dir,
        )

        # Copy parquet files to UC Volume
        os.makedirs(parquet_dir, exist_ok=True)
        for pq_file in glob.glob(f"{local_dir}/**/*.parquet", recursive=True):
            dest = os.path.join(parquet_dir, os.path.basename(pq_file))
            shutil.copy2(pq_file, dest)

    # Read from UC Volume path (accessible by serverless Spark)
    df = spark.read.parquet(parquet_dir)

    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)

    spark.sql(f"OPTIMIZE {fqn}")
    return fqn


def create_derived_views(catalog: str = "lucasbruand_catalog", schema: str = "kicad") -> None:
    """Create analytics views on top of the open_schematics table."""
    spark = get_spark()

    spark.sql(f"""
        CREATE OR REPLACE VIEW {catalog}.{schema}.schematic_components AS
        SELECT
            name,
            description,
            type,
            explode(components_used) AS component,
            length(schematic) AS schematic_size_bytes
        FROM {catalog}.{schema}.open_schematics
    """)

    spark.sql(f"""
        CREATE OR REPLACE VIEW {catalog}.{schema}.component_frequency AS
        SELECT
            component,
            count(*) AS usage_count
        FROM {catalog}.{schema}.schematic_components
        GROUP BY component
        ORDER BY usage_count DESC
    """)
