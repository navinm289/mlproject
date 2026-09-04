"""Serverless Auto Loader ingestion with same-folder control-file validation.

Expected pair::

    orders_20260904.csv
    orders_20260904.control.json

The CSV is persisted to one Bronze Delta table. Validation updates technical
columns on those same Bronze rows; this application creates no Silver table.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from pyspark.sql import DataFrame, SparkSession, functions as F, types as T


CONTROL_SCHEMA = T.StructType(
    [
        T.StructField("data_file", T.StringType(), False),
        T.StructField("record_count", T.LongType(), False),
        T.StructField("checksum_algorithm", T.StringType(), False),
        T.StructField("checksum", T.StringType(), False),
        T.StructField("file_creation_time", T.TimestampType(), False),
    ]
)


@dataclass(frozen=True)
class IngestionConfig:
    landing_path: str
    checkpoint_path: str
    schema_path: str
    bronze_table: str
    csv_glob: str = "*.csv"
    control_glob: str = "*.control.json"
    header: bool = True
    delimiter: str = ","
    managed_file_events: bool = True
    creation_time_tolerance_seconds: int = 300

    def validate(self) -> None:
        if not self.landing_path.startswith(("s3://", "/Volumes/")):
            raise ValueError("landing_path must be an s3:// path or UC Volume path")
        if self.checkpoint_path.rstrip("/") == self.landing_path.rstrip("/"):
            raise ValueError("checkpoint_path must be outside the landing directory")
        if self.bronze_table.count(".") != 2:
            raise ValueError("bronze_table must be catalog.schema.table")


def read_csv_stream(spark: SparkSession, config: IngestionConfig) -> DataFrame:
    reader = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaLocation", config.schema_path)
        .option("cloudFiles.inferColumnTypes", "true")
        .option("cloudFiles.schemaEvolutionMode", "rescue")
        .option("pathGlobFilter", config.csv_glob)
        .option("header", str(config.header).lower())
        .option("delimiter", config.delimiter)
    )
    if config.managed_file_events:
        reader = reader.option("cloudFiles.useManagedFileEvents", "true")
    return reader.load(config.landing_path)


def add_bronze_metadata(df: DataFrame) -> DataFrame:
    return (
        df.withColumn("_source_file_path", F.col("_metadata.file_path"))
        .withColumn("_source_file_name", F.col("_metadata.file_name"))
        .withColumn("_source_file_size", F.col("_metadata.file_size"))
        .withColumn("_source_file_modification_time", F.col("_metadata.file_modification_time"))
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_control_file_name", F.lit(None).cast("string"))
        .withColumn("_expected_record_count", F.lit(None).cast("long"))
        .withColumn("_actual_record_count", F.lit(None).cast("long"))
        .withColumn("_expected_checksum", F.lit(None).cast("string"))
        .withColumn("_actual_checksum", F.lit(None).cast("string"))
        .withColumn("_validation_status", F.lit("WAITING_FOR_CONTROL"))
        .withColumn("_validation_error", F.lit(None).cast("string"))
    )


def ingest_available_csv_files(spark: SparkSession, config: IngestionConfig) -> None:
    bronze_df = add_bronze_metadata(read_csv_stream(spark, config))

    # toTable() would create a Delta table by default. Create the empty managed
    # Iceberg table explicitly on the first run, then use it as the stream sink.
    if not spark.catalog.tableExists(config.bronze_table):
        bronze_df.limit(0).write.format("iceberg").saveAsTable(config.bronze_table)

    provider = (
        spark.sql(f"DESCRIBE DETAIL {config.bronze_table}")
        .select(F.lower("format").alias("format"))
        .first()["format"]
    )
    if provider != "iceberg":
        raise ValueError(
            f"{config.bronze_table} already exists with format {provider!r}; Iceberg is required"
        )

    query = (
        bronze_df
        .writeStream.option("checkpointLocation", config.checkpoint_path)
        .trigger(availableNow=True)
        .toTable(config.bronze_table)
    )
    query.awaitTermination()


def read_controls(spark: SparkSession, config: IngestionConfig) -> DataFrame:
    controls = (
        spark.read.schema(CONTROL_SCHEMA)
        .option("pathGlobFilter", config.control_glob)
        .json(config.landing_path)
        .withColumn("_control_file_path", F.input_file_name())
        .withColumn("_control_file_name", F.regexp_extract("_control_file_path", r"([^/]+)$", 1))
    )
    safe_name = (
        F.col("data_file").isNotNull()
        & F.col("data_file").endswith(".csv")
        & ~F.col("data_file").contains("/")
        & ~F.col("data_file").contains("\\")
    )
    return controls.filter(safe_name).withColumn(
        "_source_file_path",
        F.concat(F.regexp_extract("_control_file_path", r"^(.*)/[^/]+$", 1), F.lit("/"), F.col("data_file")),
    )


def build_validation_results(spark: SparkSession, config: IngestionConfig) -> DataFrame:
    controls = read_controls(spark, config)
    bronze = spark.table(config.bronze_table)

    counts = bronze.groupBy("_source_file_path").agg(
        F.count(F.lit(1)).alias("_actual_record_count"),
        F.max("_source_file_modification_time").alias("_actual_file_time"),
    )
    checksums = (
        spark.read.format("binaryFile")
        .option("pathGlobFilter", config.csv_glob)
        .load(config.landing_path)
        .select(
            F.col("path").alias("_source_file_path"),
            F.sha2(F.col("content"), 256).alias("_actual_checksum"),
        )
    )

    joined = controls.join(counts, "_source_file_path", "left").join(
        checksums, "_source_file_path", "left"
    )
    tolerance = F.lit(config.creation_time_tolerance_seconds)
    algorithm_ok = F.upper(F.regexp_replace("checksum_algorithm", "-", "")) == F.lit("SHA256")
    count_ok = F.col("record_count") == F.col("_actual_record_count")
    checksum_ok = F.lower("checksum") == F.lower("_actual_checksum")
    timestamp_ok = (
        F.abs(F.col("file_creation_time").cast("long") - F.col("_actual_file_time").cast("long"))
        <= tolerance
    )

    return (
        joined.withColumn(
            "_validation_status",
            F.when(F.col("_actual_record_count").isNull(), "DATA_NOT_INGESTED")
            .when(~algorithm_ok, "UNSUPPORTED_CHECKSUM")
            .when(~count_ok, "COUNT_MISMATCH")
            .when(~checksum_ok, "CHECKSUM_MISMATCH")
            .when(~timestamp_ok, "CREATION_TIME_MISMATCH")
            .otherwise("VALID"),
        )
        .withColumn(
            "_validation_error",
            F.when(F.col("_validation_status") == "VALID", F.lit(None).cast("string")).otherwise(
                F.concat(
                    F.lit("Control validation failed: "), F.col("_validation_status")
                )
            ),
        )
        .select(
            "_source_file_path",
            "_control_file_name",
            F.col("record_count").alias("_expected_record_count"),
            "_actual_record_count",
            F.lower("checksum").alias("_expected_checksum"),
            F.lower("_actual_checksum").alias("_actual_checksum"),
            "_validation_status",
            "_validation_error",
        )
    )


def validate_bronze(spark: SparkSession, config: IngestionConfig) -> None:
    results = build_validation_results(spark, config)
    results.createOrReplaceTempView("autoloader_validation_results")
    spark.sql(
        f"""
        MERGE INTO {config.bronze_table} AS bronze
        USING autoloader_validation_results AS validation
          ON bronze._source_file_path = validation._source_file_path
        WHEN MATCHED THEN UPDATE SET
          bronze._control_file_name = validation._control_file_name,
          bronze._expected_record_count = validation._expected_record_count,
          bronze._actual_record_count = validation._actual_record_count,
          bronze._expected_checksum = validation._expected_checksum,
          bronze._actual_checksum = validation._actual_checksum,
          bronze._validation_status = validation._validation_status,
          bronze._validation_error = validation._validation_error
        """
    )


def run(spark: SparkSession, config: IngestionConfig) -> None:
    config.validate()
    ingest_available_csv_files(spark, config)
    validate_bronze(spark, config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-path", required=True)
    parser.add_argument("--checkpoint-path", required=True)
    parser.add_argument("--schema-path", required=True)
    parser.add_argument("--bronze-table", required=True)
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--creation-time-tolerance-seconds", type=int, default=300)
    parser.add_argument("--disable-managed-file-events", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spark = SparkSession.builder.getOrCreate()
    run(
        spark,
        IngestionConfig(
            landing_path=args.landing_path,
            checkpoint_path=args.checkpoint_path,
            schema_path=args.schema_path,
            bronze_table=args.bronze_table,
            delimiter=args.delimiter,
            managed_file_events=not args.disable_managed_file_events,
            creation_time_tolerance_seconds=args.creation_time_tolerance_seconds,
        ),
    )


if __name__ == "__main__":
    main()
