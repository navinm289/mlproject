"""Create a SparkSession wired to HMS + Iceberg using Hub env vars.

Usage in a notebook:
    from start_spark_session import get_spark
    spark = get_spark()
    spark.sql("SHOW DATABASES").show()
"""
from __future__ import annotations

import os
from functools import lru_cache

from pyspark.sql import SparkSession


def _conf_from_env() -> dict[str, str]:
    hms = os.environ.get(
        "HMS_THRIFT_URI",
        "thrift://hive-metastore.metastore.svc.cluster.local:9083",
    )
    warehouse = os.environ.get("ICEBERG_WAREHOUSE", "s3://REPLACE_LAKE_BUCKET/warehouse/")
    return {
        "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        "spark.sql.catalog.lake": "org.apache.iceberg.spark.SparkCatalog",
        "spark.sql.catalog.lake.type": "hive",
        "spark.sql.catalog.lake.uri": hms,
        "spark.sql.catalog.lake.warehouse": warehouse,
        "spark.sql.catalog.lake.io-impl": "org.apache.iceberg.aws.s3.S3FileIO",
        "spark.sql.defaultCatalog": "lake",
        "spark.hadoop.hive.metastore.uris": hms,
        "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
        "spark.hadoop.fs.s3a.aws.credentials.provider": (
            "com.amazonaws.auth.WebIdentityTokenCredentialsProvider"
        ),
    }


@lru_cache(maxsize=1)
def get_spark(app_name: str | None = None) -> SparkSession:
    """Return a cached SparkSession for this notebook kernel."""
    user = os.environ.get("JUPYTERHUB_USER", os.environ.get("USER", "scratch"))
    name = app_name or f"scratchbook-{user}"
    builder = SparkSession.builder.appName(name)
    for key, value in _conf_from_env().items():
        builder = builder.config(key, value)

    # Optional: user scratch path for writes
    scratch = os.environ.get("S3_SCRATCH_PREFIX", "s3://REPLACE_LAKE_BUCKET/scratch/")
    builder = builder.config("spark.scratchbook.user_scratch", f"{scratch.rstrip('/')}/{user}/")

    return builder.getOrCreate()


def user_scratch_path() -> str:
    spark = get_spark()
    return spark.conf.get("spark.scratchbook.user_scratch")
