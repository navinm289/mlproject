"""Helpers for reading SAS datasets into PySpark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


_TYPE_MAP = {
    "string": StringType,
    "str": StringType,
    "integer": IntegerType,
    "int": IntegerType,
    "long": LongType,
    "bigint": LongType,
    "double": DoubleType,
    "float": DoubleType,
    "boolean": BooleanType,
    "bool": BooleanType,
    "date": DateType,
    "timestamp": TimestampType,
}


def _load_metadata(meta_path: str | Path | None) -> dict[str, Any]:
    if meta_path is None:
        return {}

    path = Path(meta_path)
    if not path.exists():
        raise FileNotFoundError(f"Metadata file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))

    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "Reading YAML metadata requires PyYAML to be installed."
            ) from exc

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data or {}

    raise ValueError(
        "Unsupported metadata format. Use a .json, .yaml, or .yml file."
    )


def _build_schema(schema_config: list[dict[str, Any]] | None) -> StructType | None:
    if not schema_config:
        return None

    fields: list[StructField] = []
    for column in schema_config:
        name = column["name"]
        dtype_name = str(column.get("type", "string")).lower()
        nullable = bool(column.get("nullable", True))

        dtype_factory = _TYPE_MAP.get(dtype_name)
        if dtype_factory is None:
            raise ValueError(f"Unsupported Spark type in metadata: {dtype_name}")

        fields.append(StructField(name, dtype_factory(), nullable))

    return StructType(fields)


def _apply_metadata_transforms(df: DataFrame, metadata: dict[str, Any]) -> DataFrame:
    rename_columns = metadata.get("rename_columns", {})
    casts = metadata.get("casts", {})
    date_columns = metadata.get("date_columns", [])
    timestamp_columns = metadata.get("timestamp_columns", [])

    for old_name, new_name in rename_columns.items():
        if old_name in df.columns and old_name != new_name:
            df = df.withColumnRenamed(old_name, new_name)

    for column_name, type_name in casts.items():
        if column_name not in df.columns:
            continue

        normalized = str(type_name).lower()
        if normalized == "date":
            df = df.withColumn(column_name, F.to_date(F.col(column_name)))
        elif normalized == "timestamp":
            df = df.withColumn(column_name, F.to_timestamp(F.col(column_name)))
        else:
            dtype_factory = _TYPE_MAP.get(normalized)
            if dtype_factory is None:
                raise ValueError(
                    f"Unsupported cast type in metadata for {column_name}: {type_name}"
                )
            df = df.withColumn(column_name, F.col(column_name).cast(dtype_factory()))

    for column_name in date_columns:
        if column_name in df.columns:
            df = df.withColumn(column_name, F.to_date(F.col(column_name)))

    for column_name in timestamp_columns:
        if column_name in df.columns:
            df = df.withColumn(column_name, F.to_timestamp(F.col(column_name)))

    return df


def read_sas_with_metadata(
    spark: SparkSession,
    sas_path: str | Path,
    meta_path: str | Path | None = None,
    **read_options: Any,
) -> DataFrame:
    """
    Read a SAS dataset into a PySpark DataFrame.

    If a metadata file is provided, its options are applied automatically.
    Supported metadata keys:
      - read_options: pandas.read_sas keyword arguments
      - schema: list of {"name": ..., "type": ..., "nullable": ...}
      - rename_columns: {"old_name": "new_name"}
      - casts: {"column_name": "string|int|double|date|timestamp|..."}
      - date_columns: ["col_a", ...]
      - timestamp_columns: ["col_b", ...]

    Keyword arguments passed directly to this function override metadata
    read_options entries.
    """

    metadata = _load_metadata(meta_path)
    pandas_read_options = dict(metadata.get("read_options", {}))
    pandas_read_options.update(read_options)

    schema = _build_schema(metadata.get("schema"))
    pandas_df = pd.read_sas(Path(sas_path), **pandas_read_options)

    if "column_names" in metadata:
        pandas_df.columns = metadata["column_names"]

    spark_df = spark.createDataFrame(pandas_df, schema=schema)
    return _apply_metadata_transforms(spark_df, metadata)
