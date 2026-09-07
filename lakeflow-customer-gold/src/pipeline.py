"""Lakeflow entrypoint. Dataset functions only construct plans; no writes/actions/logging."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pyspark import pipelines as dp
from pyspark.sql import SparkSession, functions as F
from gold_pipeline.contracts import CONTRACTS
from gold_pipeline.transforms import normalize, source_rules, rank_versions, reasons, enrich, summarize, JOIN_RULES, GRAIN
from gold_pipeline.quality import gold_rules, check_gold, rule_results, union_all

spark = SparkSession.active()
SOURCE = spark.conf.get("gold.source")
RUN = spark.conf.get("gold.run_id")
AS_OF = spark.conf.get("gold.as_of")
# Explicit immutable batch context: orchestrator must replace these for every logical run.
from datetime import datetime
import re
if not re.fullmatch(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+", SOURCE):
    raise ValueError("gold.source must be catalog.schema with simple SQL identifiers")
datetime.strptime(AS_OF, "%Y-%m-%d %H:%M:%S")
if not RUN or RUN.startswith("REPLACE"):
    raise ValueError("Set gold.run_id to an immutable logical batch identifier")
MAX_BAD = float(spark.conf.get("gold.max_quarantine_pct", "5"))
MAX_NULL = float(spark.conf.get("gold.max_email_null_pct", "20"))
MIN_ROWS = int(spark.conf.get("gold.min_posted_rows", "1"))
BASELINE = int(spark.conf.get("gold.baseline_posted_rows", "1"))
MIN_RATIO = float(spark.conf.get("gold.min_volume_ratio", "0.5"))
MAX_RATIO = float(spark.conf.get("gold.max_volume_ratio", "2.0"))
FRESH = int(spark.conf.get("gold.freshness_days", "30"))
if not (0 <= MAX_BAD <= 100 and 0 <= MAX_NULL <= 100 and BASELINE > 0 and MIN_ROWS >= 0 and 0 <= MIN_RATIO <= MAX_RATIO and FRESH >= 0):
    raise ValueError("Invalid quality thresholds")
Q_RULES, W_RULES = gold_rules(AS_OF, FRESH)
read = spark.read.table
PROPS = {"delta.enableRowTracking":"true", "delta.enableChangeDataFeed":"true"}

# Factory scope binds names, avoiding Python late-binding bugs in dataset loops.
def register_source(source):
    @dp.materialized_view(name=f"checked_{source}", private=True, table_properties=PROPS)
    def checked():
        return rank_versions(reasons(normalize(read(f"{SOURCE}.{source}"), source), source_rules(source, AS_OF)), source)
    @dp.materialized_view(name=f"clean_{source}", private=True, table_properties=PROPS)
    def clean():
        return read(f"checked_{source}").filter("version_rank = 1 AND size(rejection_reasons) = 0")
for source in CONTRACTS:
    register_source(source)

@dp.materialized_view(name="checked_transactions_enriched", private=True, table_properties=PROPS)
def checked_transactions_enriched():
    return reasons(enrich(*[read(f"clean_{s}") for s in ["transactions","accounts","customers","products","reference_data"]]), JOIN_RULES)

@dp.materialized_view(name="accepted_transactions", private=True, table_properties=PROPS)
def accepted_transactions():
    return read("checked_transactions_enriched").filter("size(rejection_reasons) = 0")

@dp.materialized_view(name="summary_candidate", private=True, table_properties=PROPS)
def summary_candidate():
    return check_gold(summarize(read("accepted_transactions")), Q_RULES, W_RULES)

@dp.materialized_view(name="customer_transaction_quarantine", cluster_by_auto=True)
def customer_transaction_quarantine():
    frames = []
    for source in CONTRACTS:
        df = read(f"checked_{source}")
        df = df.withColumn("rejection_reasons", F.when(F.col("version_rank")>1, F.array_union("rejection_reasons",F.array(F.lit("superseded_duplicate")))).otherwise(F.col("rejection_reasons")))
        frames.append(df.filter("size(rejection_reasons)>0").select(F.lit(source).alias("source_table"), "raw_payload", "rejection_reasons"))
    e = read("checked_transactions_enriched")
    frames.append(e.filter("size(rejection_reasons)>0").select(F.lit("joined_transactions").alias("source_table"), "raw_payload", "rejection_reasons"))
    g = read("summary_candidate")
    frames.append(g.filter("size(rejection_reasons)>0").select(F.lit("summary_candidate").alias("source_table"), F.to_json(F.struct(*[F.col(c) for c in g.columns])).alias("raw_payload"), "rejection_reasons"))
    return (union_all(frames).withColumn("pipeline_run_id",F.lit(RUN))
            .withColumn("validation_timestamp",F.lit(AS_OF).cast("timestamp")))

@dp.materialized_view(name="quality_controls", private=True)
def quality_controls():
    # Reconcile against deduplicated source facts *before* enrichment. Left-anti determines
    # rejected IDs; native source amount/count must equal accepted summary plus rejected.
    src = read("clean_transactions").filter("status = 'POSTED'")
    accepted = read("accepted_transactions")
    rejected = src.join(accepted.select("transaction_id"), "transaction_id", "left_anti")
    def sums(df, prefix, count_col=None, amount_col="amount"):
        return df.agg((F.sum(count_col) if count_col else F.count("*")).alias(prefix+"_count"), F.coalesce(F.sum(amount_col),F.lit(0)).alias(prefix+"_amount"))
    controls = sums(src,"source").crossJoin(sums(rejected,"rejected")).crossJoin(sums(read("summary_candidate"),"summary","transaction_count","total_transaction_amount"))
    # Per-key reconciliation protects against distributing correct global totals to wrong keys.
    expected = accepted.groupBy(*GRAIN).agg(F.count("*").alias("expected_count"),F.sum("amount").alias("expected_amount"))
    actual = read("summary_candidate").select(*GRAIN,"transaction_count","total_transaction_amount")
    mismatches = expected.join(actual,GRAIN,"full").filter("expected_count IS NULL OR transaction_count IS NULL OR expected_count <> transaction_count OR expected_amount <> total_transaction_amount").agg(F.count("*").alias("key_mismatches"))
    email = read("summary_candidate").agg(F.count("*").alias("gold_rows"),F.coalesce(F.sum(F.col("email").isNull().cast("long")),F.lit(0)).alias("null_emails"))
    versions = read("checked_transactions").filter("version_rank = 1").agg(F.count("*").alias("latest_rows"),F.coalesce(F.sum((F.size("rejection_reasons")>0).cast("long")),F.lit(0)).alias("invalid_source_rows"))
    return (controls.crossJoin(mismatches).crossJoin(email).crossJoin(versions)
        .withColumn("quarantine_pct", F.when(F.col("latest_rows")>0,100.0*(F.col("invalid_source_rows")+F.col("rejected_count"))/F.col("latest_rows")).otherwise(0.0))
        .withColumn("email_null_pct",F.when(F.col("gold_rows")>0,100.0*F.col("null_emails")/F.col("gold_rows")).otherwise(0.0)))

CONTROL_RULES = {
 "reconciliation": "source_count = coalesce(summary_count,0) + rejected_count AND source_amount = summary_amount + rejected_amount AND key_mismatches = 0",
 "quarantine_threshold": f"quarantine_pct <= {MAX_BAD}",
 "null_percentage": f"email_null_pct <= {MAX_NULL}",
 "minimum_volume": f"source_count >= {MIN_ROWS}",
 "volume_anomaly": f"source_count >= {BASELINE} * {MIN_RATIO} AND source_count <= {BASELINE} * {MAX_RATIO}",
}

@dp.materialized_view(name="data_quality_results")
def data_quality_results():
    frames = []
    for s in CONTRACTS:
        frames.append(rule_results(read(f"checked_{s}"),source_rules(s,AS_OF),f"{SOURCE}.{s}","Quarantine",RUN,AS_OF))
        frames.append(rule_results(read(f"checked_{s}"),{"duplicate_version":"version_rank = 1"},f"{SOURCE}.{s}","Quarantine",RUN,AS_OF))
    frames.extend([
        rule_results(read("checked_transactions_enriched"),JOIN_RULES,"joined_transactions","Quarantine",RUN,AS_OF),
        rule_results(read("summary_candidate"),Q_RULES,"customer_transaction_summary","Quarantine",RUN,AS_OF),
        rule_results(read("summary_candidate"),W_RULES,"customer_transaction_summary","Warning",RUN,AS_OF),
        rule_results(read("quality_controls"),CONTROL_RULES,"customer_transaction_summary","Failure",RUN,AS_OF)])
    return union_all(frames)

@dp.materialized_view(name="publication_gate", private=True)
@dp.expect_all_or_fail(CONTROL_RULES)
def publication_gate():
    return read("quality_controls")

@dp.materialized_view(name="customer_transaction_summary", cluster_by_auto=True,
    comment="Grain: customer_id, account_id, product_id, currency; lifetime posted transactions; current dimensions.", table_properties=PROPS)
@dp.expect_all({"warnings_clear":"size(warning_reasons) = 0"})
def customer_transaction_summary():
    # Explicit dependency on gate. Retain marker so gate isn't an unused projection.
    gate = read("publication_gate").select(F.lit("PASSED").alias("publication_gate_status"))
    return (read("summary_candidate").filter("size(rejection_reasons) = 0").crossJoin(gate)
        .drop("key_count", "rejection_reasons")
        .withColumn("pipeline_run_id",F.lit(RUN)).withColumn("validation_timestamp",F.lit(AS_OF).cast("timestamp")))
