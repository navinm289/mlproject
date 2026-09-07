"""Run on a Databricks dev cluster from the project root. Inserts sample rows once.
Use --source sandbox_catalog.customer_source_dev after running sql/01_sources.sql.
Refuses nonempty tables: intentionally prevents accidental duplicate fixture ingestion.
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pyspark.sql import SparkSession, functions as F
from gold_pipeline.contracts import CONTRACTS
from sample_data import DATA

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--source",required=True); args=parser.parse_args()
    spark=SparkSession.builder.getOrCreate()
    for name in DATA:
        if spark.table(f"{args.source}.{name}").limit(1).count():
            raise ValueError(f"{name} is not empty; use a fresh sandbox schema")
    for name, rows in DATA.items():
        frame=spark.createDataFrame(rows, ','.join(f"{c} string" for c in CONTRACTS[name]))
        frame.select(*[F.col(c).cast(t).alias(c) for c,t in CONTRACTS[name].items()]).write.mode("append").saveAsTable(f"{args.source}.{name}")
