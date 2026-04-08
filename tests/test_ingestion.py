"""Tests for scan2kicad.ingestion."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import datasets  # noqa: F401 — imported to trigger pyarrow registration once
import pytest


@pytest.fixture(autouse=True)
def _mock_pyspark():
    """Mock pyspark since it's not installed locally."""
    mock_pyspark = MagicMock()
    with patch.dict(
        sys.modules,
        {
            "pyspark": mock_pyspark,
            "pyspark.sql": mock_pyspark.sql,
            "pyspark.sql.types": mock_pyspark.sql.types,
        },
    ):
        if "scan2kicad.ingestion" in sys.modules:
            del sys.modules["scan2kicad.ingestion"]
        yield


def _run_ingest(**kwargs: str) -> tuple[str, MagicMock]:
    """Helper: run ingest_open_schematics with mocked Spark and load_dataset."""
    from scan2kicad import ingestion

    mock_spark = MagicMock()

    with (
        patch.object(ingestion, "get_spark", return_value=mock_spark),
        patch("datasets.load_dataset", return_value=MagicMock()),
    ):
        fqn = ingestion.ingest_open_schematics(**kwargs)

    return fqn, mock_spark


class TestIngestOpenSchematics:
    def test_returns_fqn(self) -> None:
        fqn, _ = _run_ingest(catalog="test_cat", schema="test_sch", table="test_tbl")
        assert fqn == "test_cat.test_sch.test_tbl"

    def test_creates_schema(self) -> None:
        _, mock_spark = _run_ingest(catalog="lucasbruand_catalog", schema="kicad")
        first_sql = mock_spark.sql.call_args_list[0][0][0]
        assert "CREATE SCHEMA IF NOT EXISTS lucasbruand_catalog.kicad" in first_sql

    def test_writes_delta_table(self) -> None:
        _, mock_spark = _run_ingest(
            catalog="lucasbruand_catalog", schema="kicad", table="open_schematics"
        )
        mock_df = mock_spark.read.parquet.return_value
        mock_df.write.format.assert_called_once_with("delta")
        mock_df.write.format().mode.assert_called_once_with("overwrite")

    def test_runs_optimize(self) -> None:
        _, mock_spark = _run_ingest(catalog="lucasbruand_catalog", schema="kicad")
        last_sql = mock_spark.sql.call_args_list[-1][0][0]
        assert "OPTIMIZE lucasbruand_catalog.kicad.open_schematics" in last_sql

    def test_default_table_name(self) -> None:
        fqn, _ = _run_ingest()
        assert fqn == "lucasbruand_catalog.kicad.open_schematics"

    def test_calls_load_dataset(self) -> None:
        from scan2kicad import ingestion

        mock_spark = MagicMock()
        mock_load = MagicMock(return_value=MagicMock())

        with (
            patch.object(ingestion, "get_spark", return_value=mock_spark),
            patch("datasets.load_dataset", mock_load),
        ):
            ingestion.ingest_open_schematics()

        mock_load.assert_called_once_with("bshada/open-schematics", split="train")


class TestCreateDerivedViews:
    def test_creates_two_views(self) -> None:
        from scan2kicad.ingestion import create_derived_views

        with patch("scan2kicad.ingestion.get_spark") as mock_get_spark:
            mock_spark = MagicMock()
            mock_get_spark.return_value = mock_spark

            create_derived_views(catalog="lucasbruand_catalog", schema="kicad")

            assert mock_spark.sql.call_count == 2

    def test_creates_schematic_components_view(self) -> None:
        from scan2kicad.ingestion import create_derived_views

        with patch("scan2kicad.ingestion.get_spark") as mock_get_spark:
            mock_spark = MagicMock()
            mock_get_spark.return_value = mock_spark

            create_derived_views(catalog="mycat", schema="mysch")

            first_sql = mock_spark.sql.call_args_list[0][0][0]
            assert "CREATE OR REPLACE VIEW mycat.mysch.schematic_components" in first_sql
            assert "explode(components_used)" in first_sql

    def test_creates_component_frequency_view(self) -> None:
        from scan2kicad.ingestion import create_derived_views

        with patch("scan2kicad.ingestion.get_spark") as mock_get_spark:
            mock_spark = MagicMock()
            mock_get_spark.return_value = mock_spark

            create_derived_views(catalog="mycat", schema="mysch")

            second_sql = mock_spark.sql.call_args_list[1][0][0]
            assert "CREATE OR REPLACE VIEW mycat.mysch.component_frequency" in second_sql
            assert "GROUP BY component" in second_sql
