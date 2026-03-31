"""Helpers for reading SAS datasets into PySpark."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *


_SAS_READER_FORMAT = "com.github.saurfang.sas.spark"
_DECIMAL_PATTERN = re.compile(r"^decimal\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$")
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


def _resolve_spark_type(type_name: str):
    normalized = str(type_name).strip().lower()
    decimal_match = _DECIMAL_PATTERN.fullmatch(normalized)
    if decimal_match is not None:
        precision = int(decimal_match.group(1))
        scale = int(decimal_match.group(2))
        if scale > precision:
            raise ValueError(
                f"Invalid decimal type '{type_name}': scale cannot exceed precision."
            )
        return DecimalType(precision=precision, scale=scale)

    dtype_factory = _TYPE_MAP.get(normalized)
    if dtype_factory is None:
        raise ValueError(f"Unsupported Spark type in metadata: {type_name}")

    return dtype_factory()


def _load_metadata(
    spark: SparkSession, meta_path: str | Path | None
) -> dict[str, Any]:
    if meta_path is None:
        return {}

    path = Path(meta_path)
    if not path.exists():
        raise FileNotFoundError(f"Metadata file not found: {path}")

    metadata_df = (
        spark.read.options(header="true", delimiter=";", mode="FAILFAST")
        .csv(str(path))
    )
    if not metadata_df.columns:
        return {}

    field_lookup = {
        "".join(char for char in field.lower() if char.isalnum()): field
        for field in metadata_df.columns
        if field
    }
    name_field = next(
        (
            field_lookup[key]
            for key in ("columnname", "columname", "name", "column", "colname")
            if key in field_lookup
        ),
        None,
    )
    type_field = next(
        (
            field_lookup[key]
            for key in ("datatype", "type", "sparktype")
            if key in field_lookup
        ),
        None,
    )
    nullable_field = next(
        (
            field_lookup[key]
            for key in ("nullable", "isnullable")
            if key in field_lookup
        ),
        None,
    )

    if name_field is None or type_field is None:
        raise ValueError(
            "Metadata file must include ';'-separated 'columnname' and "
            "'datatype' headers."
        )

    schema: list[dict[str, Any]] = []
    for index, row in enumerate(metadata_df.collect(), start=2):
        row_data = row.asDict(recursive=True)
        name = str(row_data.get(name_field) or "").strip()
        dtype_name = str(row_data.get(type_field) or "").strip().lower() or "string"

        if not name and not dtype_name:
            continue
        if not name:
            raise ValueError(f"Metadata row {index} is missing a column name: {row_data}")

        nullable = True
        if nullable_field is not None:
            raw_nullable = str(row_data.get(nullable_field) or "").strip().lower()
            if raw_nullable:
                if raw_nullable in {"true", "1", "yes", "y"}:
                    nullable = True
                elif raw_nullable in {"false", "0", "no", "n"}:
                    nullable = False
                else:
                    raise ValueError(
                        "Nullable values must be true/false, yes/no, or 1/0. "
                        f"Found '{raw_nullable}' on row {index}."
                    )

        schema.append(
            {
                "name": name,
                "type": dtype_name,
                "nullable": nullable,
            }
        )

    return {"schema": schema}


def _normalize_sas_paths(
    sas_path: str | Path | Sequence[str | Path],
) -> list[str]:
    if isinstance(sas_path, (str, Path)):
        return [str(Path(sas_path))]

    normalized_paths = [str(Path(path)) for path in sas_path]
    if not normalized_paths:
        raise ValueError("At least one SAS path must be provided.")

    return normalized_paths


def _build_schema(schema_config: list[dict[str, Any]] | None) -> StructType | None:
    if not schema_config:
        return None

    fields: list[StructField] = []
    for column in schema_config:
        name = column["name"]
        dtype_name = str(column.get("type", "string")).lower()
        nullable = bool(column.get("nullable", True))
        fields.append(StructField(name, _resolve_spark_type(dtype_name), nullable))

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
            try:
                spark_type = _resolve_spark_type(normalized)
            except ValueError as exc:
                raise ValueError(
                    f"Unsupported cast type in metadata for {column_name}: {type_name}"
                ) from exc
            df = df.withColumn(column_name, F.col(column_name).cast(spark_type))

    for column_name in date_columns:
        if column_name in df.columns:
            df = df.withColumn(column_name, F.to_date(F.col(column_name)))

    for column_name in timestamp_columns:
        if column_name in df.columns:
            df = df.withColumn(column_name, F.to_timestamp(F.col(column_name)))

    return df


def read_sas_with_metadata(
    spark: SparkSession,
    sas_path: str | Path | Sequence[str | Path],
    meta_path: str | Path | None = None,
    **read_options: Any,
) -> DataFrame:
    """
    Read a SAS dataset into a PySpark DataFrame.

    If a metadata file is provided, it is read as a ';'-separated schema file
    with headers like 's.no;columnname;datatype' and an optional 'nullable'
    column. The SAS file is read with ``spark.read`` using the same Spark SAS
    data source format used in the Scala implementation.
    """

    metadata = _load_metadata(spark, meta_path)
    schema = _build_schema(metadata.get("schema"))
    reader_options = {"encoding": "UTF-8", "mode": "FAILFAST"}
    reader_options.update({key: str(value) for key, value in read_options.items()})

    dataframes: list[DataFrame] = []
    first_columns: list[str] | None = None
    for path in _normalize_sas_paths(sas_path):
        reader = spark.read.format(_SAS_READER_FORMAT).options(**reader_options)
        if schema is not None:
            reader = reader.schema(schema)

        dataframe = (
            reader.load(path)
            .withColumn(
                "source_file_name",
                F.substring_index(F.input_file_name(), "/", -1),
            )
            .withColumn("source_file_name_with_path", F.input_file_name())
        )

        if first_columns is None:
            first_columns = dataframe.columns
        else:
            dataframe = dataframe.select(*first_columns)

        dataframes.append(dataframe)

    if not dataframes:
        raise ValueError("No SAS files were loaded.")

    combined_df = dataframes[0]
    for dataframe in dataframes[1:]:
        combined_df = combined_df.unionByName(dataframe)

    return _apply_metadata_transforms(combined_df, metadata)
