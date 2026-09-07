import re
from pyspark.sql import functions as F, Window
from pyspark.sql.types import StructType, StructField, BooleanType, StringType
from gold_pipeline.contracts import CONTRACTS, KEYS
from gold_pipeline.policy import evaluate_policy

policy_udf = F.udf(evaluate_policy, StructType([StructField("matched", BooleanType()), StructField("error", StringType())]))

def normalize(df, source):
    names = [re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_") for c in df.columns]
    if len(names) != len(set(names)):
        raise ValueError(f"{source}: normalized column name collision")
    df = df.toDF(*names)
    missing = set(CONTRACTS[source]) - set(names)
    if missing:
        raise ValueError(f"{source}: missing required columns {sorted(missing)}")
    raw = F.to_json(F.struct(*[F.col(c) for c in sorted(names)]))
    # Project explicitly: additive source columns do not silently enter Gold.
    out = df.select(raw.alias("raw_payload"), *[
        F.expr(f"try_cast(`{c}` as {t})").alias(c) for c,t in CONTRACTS[source].items()])
    for c,t in CONTRACTS[source].items():
        if t == "string":
            out = out.withColumn(c, F.when(F.length(F.trim(F.col(c))) > 0, F.trim(F.col(c))))
    for c in ("country", "currency", "status", "account_status", "category"):
        if c in out.columns:
            out = out.withColumn(c, F.upper(c))
    if "email" in out.columns:
        out = out.withColumn("email", F.lower("email"))
    return out

def reasons(df, rules, column="rejection_reasons"):
    return df.withColumn(column, F.filter(F.array(*[
        F.when(~F.coalesce(F.expr(sql), F.lit(False)), F.lit(name))
        for name, sql in rules.items()]), lambda x: x.isNotNull()))

def source_rules(source, as_of):
    rules = {"required_"+c: f"`{c}` IS NOT NULL" for c in KEYS[source] + ["event_ts", "ingested_at"]}
    rules["source_time_range"] = f"event_ts >= timestamp'2000-01-01' AND event_ts <= timestamp'{as_of}' AND ingested_at <= timestamp'{as_of}'"
    if source == "customers": rules.update(customer_name="customer_name IS NOT NULL", country="country RLIKE '^[A-Z]{2}$'")
    if source == "accounts": rules.update(customer_id="customer_id IS NOT NULL", account_status="account_status IN ('OPEN','CLOSED','SUSPENDED')", opened_date="opened_date IS NOT NULL")
    if source == "products": rules.update(product_name="product_name IS NOT NULL", category="category IN ('PAYMENTS','SAVINGS','CREDIT')", policy="risk_policy IS NOT NULL")
    if source == "reference_data": rules.update(rate="usd_rate > 0 AND usd_rate <= 100000", currency_format="currency RLIKE '^[A-Z]{3}$'")
    if source == "transactions": rules.update(
        account_id="account_id IS NOT NULL", product_id="product_id IS NOT NULL",
        amount="amount IS NOT NULL AND abs(amount) <= 1000000000",
        transaction_time=f"transaction_ts >= timestamp'2000-01-01' AND transaction_ts <= timestamp'{as_of}'",
        status="status IN ('POSTED','PENDING','REVERSED')", currency_format="currency RLIKE '^[A-Z]{3}$'",
        tags="from_json(tags_json, 'array<string>') IS NOT NULL")
    return rules

def rank_versions(df, source):
    w = Window.partitionBy(*KEYS[source]).orderBy(F.col("event_ts").desc_nulls_last(), F.col("ingested_at").desc_nulls_last(), F.sha2("raw_payload",256).desc())
    # Rank before filtering quality: never silently resurrect an older valid version.
    return df.withColumn("version_rank", F.row_number().over(w))

def enrich(t, a, c, p, r):
    t = t.filter("status = 'POSTED'").withColumn("rate_date", F.to_date("transaction_ts"))
    t = t.withColumn("tags", F.array_sort(F.array_distinct(F.filter(F.transform(F.from_json("tags_json", "array<string>"), lambda x: F.lower(F.trim(x))), lambda x: x.isNotNull() & (F.length(x)>0)))))
    def dim(df, marker):
        return df.drop("raw_payload", "rejection_reasons", "version_rank", "ingested_at").withColumnRenamed("event_ts", marker+"_updated_at").withColumn(marker, F.lit(True))
    out = (t.join(dim(a,"has_account"), "account_id", "left")
        .join(dim(c,"has_customer"), "customer_id", "left")
        .join(dim(p,"has_product"), "product_id", "left")
        .join(dim(r,"has_rate"), ["currency","rate_date"], "left"))
    return (out.withColumn("risk", policy_udf("risk_policy", "tags"))
        .withColumn("amount_usd", F.expr("try_cast(amount * usd_rate as decimal(28,2))"))
        .withColumn("business_updated_at", F.greatest("event_ts", "ingested_at", "has_account_updated_at", "has_customer_updated_at", "has_product_updated_at", "has_rate_updated_at")))

JOIN_RULES = {"account_fk":"has_account = true", "customer_fk":"has_customer = true", "product_fk":"has_product = true", "currency_date_fk":"has_rate = true", "policy_valid":"risk.error IS NULL", "converted_amount":"amount_usd IS NOT NULL", "opened_before_transaction":"opened_date <= to_date(transaction_ts)"}
GRAIN = ["customer_id", "account_id", "product_id", "currency"]
ATTRIBUTES = ["customer_name", "email", "country", "account_status", "opened_date", "product_name", "category"]

def summarize(df):
    out = df.groupBy(*(GRAIN+ATTRIBUTES)).agg(
        F.sum("amount").alias("total_transaction_amount"), F.count("*").alias("transaction_count"),
        F.avg("amount").alias("average_transaction_amount"), F.sum("amount_usd").alias("total_amount_usd"),
        F.min("transaction_ts").alias("first_transaction_ts"), F.max("transaction_ts").alias("latest_transaction_ts"),
        F.min("ingested_at").alias("record_created_at"), F.max("business_updated_at").alias("record_updated_at"),
        F.sum(F.col("risk.matched").cast("long")).alias("risk_transaction_count"))
    return (out.withColumn("summary_id", F.sha2(F.to_json(F.struct(*GRAIN)),256))
        .withColumn("customer_segment", F.when(F.col("total_amount_usd") >= 10000,"HIGH_VALUE").otherwise("STANDARD"))
        .withColumn("product_segment", F.concat_ws("_", "category", F.when(F.col("risk_transaction_count")>0,"REVIEW").otherwise("NORMAL"))))
