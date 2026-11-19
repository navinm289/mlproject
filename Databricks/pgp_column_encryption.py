# Databricks notebook source
# PGP column-level encryption of a 7-column table using a pandas UDF (pgpy).

# COMMAND ----------

# MAGIC %pip install pgpy

# COMMAND ----------

from typing import Iterator
import pandas as pd
from pyspark.sql.functions import pandas_udf, col

pub_key_str = dbutils.secrets.get("my_scope", "pgp_public_key")


@pandas_udf("string")
def pgp_encrypt(batches: Iterator[pd.Series]) -> Iterator[pd.Series]:
    import pgpy
    key, _ = pgpy.PGPKey.from_blob(pub_key_str)   # loaded once per task

    def enc(v):
        if pd.isna(v):
            return None
        return str(key.encrypt(pgpy.PGPMessage.new(str(v))))

    for s in batches:
        yield s.map(enc)


cols_to_encrypt = ["col1", "col2", "col3", "col4", "col5", "col6", "col7"]

df = spark.table("source_table").repartition(2000)
for c in cols_to_encrypt:
    df = df.withColumn(c, pgp_encrypt(col(c)))

df.write.mode("overwrite").saveAsTable("target_table_encrypted")
