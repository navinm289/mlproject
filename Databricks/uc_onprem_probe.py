"""Read-only on-prem Spark -> Databricks UC Iceberg REST -> AWS S3 probe.

Example assumes Spark 3.5 + Scala 2.12 + matching Iceberg runtime/AWS bundle.
Do not commit real bearer tokens; use environment/approved secret injection.
"""

import os
from pyspark.sql import SparkSession


def required(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError("Missing required environment variable: " + name)
    return value


def quote_ident(name):
    return "`" + name.replace("`", "``") + "`"


def main():
    host = required("DB_HOST").rstrip("/")
    token = required("UC_TOKEN")
    catalog = required("UC_CATALOG")
    schema = required("UC_SCHEMA")
    table = required("UC_TABLE")
    required("AWS_REGION")

    builder = (
        SparkSession.builder
        .appName("OnPrem_UC_ReadOnly_Probe")
        .config("spark.sql.catalog.uc", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.uc.type", "rest")
        .config("spark.sql.catalog.uc.uri", host + "/api/2.1/unity-catalog/iceberg-rest")
        .config("spark.sql.catalog.uc.warehouse", catalog)
        .config("spark.sql.catalog.uc.token", token)
        .config("spark.sql.catalog.uc.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.redaction.regex", "(?i)secret|password|token|credential|access.key")
    )

    proxy_host = os.environ.get("UC_PROXY_HOST")
    proxy_port = os.environ.get("UC_PROXY_PORT")
    if bool(proxy_host) != bool(proxy_port):
        raise ValueError("Set BOTH UC_PROXY_HOST and UC_PROXY_PORT (or neither).")
    if proxy_host:
        builder = (
            builder
            .config("spark.sql.catalog.uc.rest.client.proxy.hostname", proxy_host)
            .config("spark.sql.catalog.uc.rest.client.proxy.port", proxy_port)
        )

    spark = builder.getOrCreate()
    try:
        print("TEST 1: UC namespace list")
        spark.sql("SHOW NAMESPACES IN uc").show(truncate=False)

        print("TEST 2: UC table list")
        spark.sql("SHOW TABLES IN uc." + quote_ident(schema)).show(truncate=False)

        print("TEST 3: Table schema")
        df = spark.table("uc." + quote_ident(schema) + "." + quote_ident(table))
        df.printSchema()

        print("TEST 4: S3 data read")
        df.limit(5).show(truncate=False)
        print("SUCCESS: Spark -> UC metadata + S3 data read completed")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
