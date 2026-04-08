"""Component 1: Open-Schematics Delta Table Ingestion.

Downloads the open-schematics dataset from Hugging Face and writes it
as a managed Delta table in Unity Catalog.
"""

from __future__ import annotations

from pyspark.sql import SparkSession


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

    # Ensure schema exists
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")

    # Download via HF datasets library → temporary parquet on local disk,
    # then read into Spark.  The datasets lib handles caching automatically.
    from datasets import load_dataset

    ds = load_dataset("bshada/open-schematics", split="train")

    # Save as parquet to a temp location, then let Spark read it
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        ds.to_parquet(f"{tmpdir}/data.parquet")
        df = spark.read.parquet(f"{tmpdir}/data.parquet")

        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
            fqn
        )

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
