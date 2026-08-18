"""Estimate Snowflake load cost for COPY INTO vs the Spark connector.

The Spark connector still stages files and runs COPY INTO under the hood.
Its extra cost is the Spark cluster plus a longer Snowflake warehouse
session while Spark serializes and PUTs files.

Defaults are list-price approximations for AWS US East Standard edition
and AWS Glue ETL. Override them with your contract rates and measured
runtimes before treating the output as a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

WAREHOUSE_CREDITS_PER_HOUR: Mapping[str, float] = {
    "XSMALL": 1.0,
    "SMALL": 2.0,
    "MEDIUM": 4.0,
    "LARGE": 8.0,
    "XLARGE": 16.0,
    "X2LARGE": 32.0,
    "X3LARGE": 64.0,
    "X4LARGE": 128.0,
}

# COPY INTO parallelizes by file. XS can load 8 files at a time; each
# larger warehouse size doubles that. See Snowflake loading docs.
PARALLEL_FILES: Mapping[str, int] = {
    "XSMALL": 8,
    "SMALL": 16,
    "MEDIUM": 32,
    "LARGE": 64,
    "XLARGE": 128,
    "X2LARGE": 256,
    "X3LARGE": 512,
    "X4LARGE": 1024,
}

# Conservative compressed Parquet/CSV ingest rate per parallel slot.
# Real throughput varies by format, compression, and row width.
MB_PER_SECOND_PER_SLOT = 12.0

MIN_WAREHOUSE_SECONDS = 60.0
SECONDS_PER_HOUR = 3600.0
MB_PER_GB = 1024.0

WAREHOUSE_ALIASES = {
    "XS": "XSMALL",
    "X-SMALL": "XSMALL",
    "S": "SMALL",
    "M": "MEDIUM",
    "L": "LARGE",
    "XL": "XLARGE",
    "2XL": "X2LARGE",
    "3XL": "X3LARGE",
    "4XL": "X4LARGE",
}


@dataclass(frozen=True)
class Pricing:
    """List-price knobs. Replace with your contract numbers."""

    credit_usd: float = 2.00
    glue_dpu_hour_usd: float = 0.44
    s3_get_per_1000_usd: float = 0.0004
    s3_put_per_1000_usd: float = 0.005


@dataclass(frozen=True)
class CostBreakdown:
    method: str
    warehouse_seconds: float
    warehouse_credits: float
    snowflake_usd: float
    spark_usd: float
    s3_usd: float
    total_usd: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Comparison:
    data_gb: float
    file_count: int
    warehouse: str
    copy_into: CostBreakdown
    spark_connector: CostBreakdown
    cheaper_method: str
    spark_premium_usd: float
    spark_premium_pct: float


def normalize_warehouse(size: str) -> str:
    key = size.strip().upper().replace(" ", "")
    key = WAREHOUSE_ALIASES.get(key, key)
    if key not in WAREHOUSE_CREDITS_PER_HOUR:
        known = ", ".join(WAREHOUSE_CREDITS_PER_HOUR)
        raise ValueError(f"Unknown warehouse size {size!r}. Use one of: {known}")
    return key


def billed_warehouse_seconds(runtime_seconds: float) -> float:
    if runtime_seconds <= 0:
        return 0.0
    return max(MIN_WAREHOUSE_SECONDS, runtime_seconds)


def warehouse_credits(size: str, runtime_seconds: float) -> float:
    size = normalize_warehouse(size)
    seconds = billed_warehouse_seconds(runtime_seconds)
    return WAREHOUSE_CREDITS_PER_HOUR[size] * (seconds / SECONDS_PER_HOUR)


def default_file_count(data_gb: float, file_mb: float = 150.0) -> int:
    """Split volume into ~150 MB compressed files (Snowflake's 100-250 MB band)."""
    if data_gb <= 0:
        return 0
    return max(1, round(data_gb * MB_PER_GB / file_mb))


def estimate_copy_runtime_seconds(
    data_gb: float,
    warehouse: str,
    file_count: int | None = None,
    mb_per_second_per_slot: float = MB_PER_SECOND_PER_SLOT,
) -> float:
    """Estimate COPY INTO wall time from warehouse parallelism and file count."""
    if data_gb <= 0:
        return 0.0

    warehouse = normalize_warehouse(warehouse)
    files = file_count if file_count is not None else default_file_count(data_gb)
    slots = min(PARALLEL_FILES[warehouse], max(files, 1))
    throughput_mb_s = slots * mb_per_second_per_slot
    return (data_gb * MB_PER_GB) / throughput_mb_s


def estimate_copy_into(
    data_gb: float,
    warehouse: str = "SMALL",
    *,
    file_count: int | None = None,
    runtime_seconds: float | None = None,
    pricing: Pricing | None = None,
) -> CostBreakdown:
    """Cost of loading files that already sit in an S3 stage via COPY INTO."""
    pricing = pricing or Pricing()
    warehouse = normalize_warehouse(warehouse)
    files = file_count if file_count is not None else default_file_count(data_gb)
    runtime = (
        runtime_seconds
        if runtime_seconds is not None
        else estimate_copy_runtime_seconds(data_gb, warehouse, files)
    )
    credits = warehouse_credits(warehouse, runtime)
    snowflake_usd = credits * pricing.credit_usd
    s3_usd = (files / 1000.0) * pricing.s3_get_per_1000_usd
    notes = (
        "Snowflake warehouse credits for COPY INTO only.",
        "Same-region S3 GET request cost; Snowflake does not charge ingress.",
        "Assumes files are already staged in S3 (no Spark cluster).",
    )
    return CostBreakdown(
        method="copy_into_s3",
        warehouse_seconds=billed_warehouse_seconds(runtime),
        warehouse_credits=round(credits, 4),
        snowflake_usd=round(snowflake_usd, 4),
        spark_usd=0.0,
        s3_usd=round(s3_usd, 6),
        total_usd=round(snowflake_usd + s3_usd, 4),
        notes=notes,
    )


def estimate_spark_connector(
    data_gb: float,
    warehouse: str = "SMALL",
    *,
    file_count: int | None = None,
    spark_dpu: float = 10.0,
    spark_minutes: float | None = None,
    warehouse_overhead: float = 2.5,
    include_spark_cluster: bool = True,
    pricing: Pricing | None = None,
) -> CostBreakdown:
    """Cost of spark.write.format('snowflake') into a Snowflake table.

    warehouse_overhead stretches COPY runtime to cover Spark serialize + PUT
    while the Snowflake warehouse stays resumed. 2.5x is a conservative
    default until you measure QUERY_HISTORY for your job.
    """
    pricing = pricing or Pricing()
    warehouse = normalize_warehouse(warehouse)
    files = file_count if file_count is not None else default_file_count(data_gb)
    copy_runtime = estimate_copy_runtime_seconds(data_gb, warehouse, files)
    warehouse_runtime = copy_runtime * warehouse_overhead
    credits = warehouse_credits(warehouse, warehouse_runtime)
    snowflake_usd = credits * pricing.credit_usd

    if spark_minutes is None:
        # Spark write is usually slower than Snowflake COPY of the same files.
        spark_minutes = max(1.0, warehouse_runtime / 60.0)

    spark_usd = 0.0
    if include_spark_cluster:
        spark_usd = spark_dpu * (spark_minutes / 60.0) * pricing.glue_dpu_hour_usd

    # External transfer writes each Spark partition to S3 then COPY reads them.
    # Internal transfer still PUTs the same number of objects to a stage.
    s3_usd = (files / 1000.0) * (
        pricing.s3_put_per_1000_usd + pricing.s3_get_per_1000_usd
    )

    notes = (
        "Spark connector stages files then runs COPY INTO (plus temp table/SWAP).",
        "Snowflake warehouse stays up during Spark serialize and PUT.",
        (
            "Spark cluster billed as Glue DPU-hours; swap in EMR/Databricks rates "
            "if that is your compute."
            if include_spark_cluster
            else "Spark cluster cost omitted (shared with an existing transform job)."
        ),
    )
    return CostBreakdown(
        method="spark_connector",
        warehouse_seconds=billed_warehouse_seconds(warehouse_runtime),
        warehouse_credits=round(credits, 4),
        snowflake_usd=round(snowflake_usd, 4),
        spark_usd=round(spark_usd, 4),
        s3_usd=round(s3_usd, 6),
        total_usd=round(snowflake_usd + spark_usd + s3_usd, 4),
        notes=notes,
    )


def compare_ingest_costs(
    data_gb: float,
    warehouse: str = "SMALL",
    *,
    file_count: int | None = None,
    spark_dpu: float = 10.0,
    spark_minutes: float | None = None,
    warehouse_overhead: float = 2.5,
    include_spark_cluster: bool = True,
    pricing: Pricing | None = None,
) -> Comparison:
    """Side-by-side estimate for one load of ``data_gb`` compressed files."""
    warehouse = normalize_warehouse(warehouse)
    files = file_count if file_count is not None else default_file_count(data_gb)
    copy_into = estimate_copy_into(
        data_gb,
        warehouse,
        file_count=files,
        pricing=pricing,
    )
    spark = estimate_spark_connector(
        data_gb,
        warehouse,
        file_count=files,
        spark_dpu=spark_dpu,
        spark_minutes=spark_minutes,
        warehouse_overhead=warehouse_overhead,
        include_spark_cluster=include_spark_cluster,
        pricing=pricing,
    )
    cheaper = (
        copy_into.method
        if copy_into.total_usd <= spark.total_usd
        else spark.method
    )
    premium = spark.total_usd - copy_into.total_usd
    pct = 0.0 if copy_into.total_usd == 0 else (premium / copy_into.total_usd) * 100
    return Comparison(
        data_gb=data_gb,
        file_count=files,
        warehouse=warehouse,
        copy_into=copy_into,
        spark_connector=spark,
        cheaper_method=cheaper,
        spark_premium_usd=round(premium, 4),
        spark_premium_pct=round(pct, 1),
    )


def format_comparison(result: Comparison) -> str:
    copy_into = result.copy_into
    spark = result.spark_connector
    lines = [
        f"Load size: {result.data_gb:g} GB compressed, {result.file_count} files, "
        f"warehouse {result.warehouse}",
        "",
        "COPY INTO from S3",
        f"  Snowflake credits : {copy_into.warehouse_credits:g} "
        f"({copy_into.warehouse_seconds:.0f}s billed)",
        f"  Snowflake USD     : ${copy_into.snowflake_usd:.4f}",
        f"  S3 USD            : ${copy_into.s3_usd:.6f}",
        f"  Total             : ${copy_into.total_usd:.4f}",
        "",
        "Spark connector",
        f"  Snowflake credits : {spark.warehouse_credits:g} "
        f"({spark.warehouse_seconds:.0f}s billed)",
        f"  Snowflake USD     : ${spark.snowflake_usd:.4f}",
        f"  Spark USD         : ${spark.spark_usd:.4f}",
        f"  S3 USD            : ${spark.s3_usd:.6f}",
        f"  Total             : ${spark.total_usd:.4f}",
        "",
        f"Cheaper method      : {result.cheaper_method}",
        f"Spark premium       : ${result.spark_premium_usd:.4f} "
        f"({result.spark_premium_pct:+.1f}% vs COPY INTO)",
    ]
    return "\n".join(lines)
