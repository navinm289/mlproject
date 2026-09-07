from functools import reduce
from pyspark.sql import functions as F, Window
from gold_pipeline.transforms import GRAIN, reasons

def gold_rules(as_of, freshness_days):
    return {
        "complete_key": " AND ".join(f"{c} IS NOT NULL" for c in GRAIN),
        "unique_key": "key_count = 1",
        "attributes_complete": "customer_name IS NOT NULL AND product_name IS NOT NULL AND opened_date IS NOT NULL",
        "accepted_values": "account_status IN ('OPEN','CLOSED','SUSPENDED') AND category IN ('PAYMENTS','SAVINGS','CREDIT') AND customer_segment IN ('STANDARD','HIGH_VALUE')",
        "formats": "country RLIKE '^[A-Z]{2}$' AND currency RLIKE '^[A-Z]{3}$' AND summary_id RLIKE '^[0-9a-f]{64}$'",
        "numeric_range": "transaction_count > 0 AND abs(total_transaction_amount) <= transaction_count * 1000000000 AND risk_transaction_count BETWEEN 0 AND transaction_count AND total_amount_usd IS NOT NULL",
        "date_range": f"first_transaction_ts >= timestamp'2000-01-01' AND latest_transaction_ts <= timestamp'{as_of}'",
        "cross_column": "first_transaction_ts <= latest_transaction_ts AND opened_date <= to_date(first_transaction_ts) AND record_created_at <= record_updated_at AND abs(average_transaction_amount * transaction_count - total_transaction_amount) <= 0.01 * transaction_count",
    }, {
        "email_format": "email IS NOT NULL AND email RLIKE '^[^@ ]+@[^@ ]+\\.[^@ ]+$'",
        "freshness": f"latest_transaction_ts >= timestamp'{as_of}' - INTERVAL {freshness_days} DAYS",
        "closed_account_activity": "account_status = 'OPEN'",
    }

def check_gold(df, quarantine_rules, warning_rules):
    out = df.withColumn("key_count", F.count("*").over(Window.partitionBy(*GRAIN)))
    out = reasons(reasons(out, quarantine_rules), warning_rules, "warning_reasons")
    return out.withColumn("data_quality_status", F.when(F.size("rejection_reasons") > 0,"QUARANTINE").when(F.size("warning_reasons") > 0,"WARNING").otherwise("PASS"))

def rule_results(df, rules, table, severity, run_id, as_of):
    # One aggregate scan per dataset, then unpivot. Counts use SQL NULL-as-failure semantics.
    metrics = df.agg(F.count("*").alias("total"), *[
        F.coalesce(F.sum((~F.coalesce(F.expr(sql), F.lit(False))).cast("long")), F.lit(0)).alias(name)
        for name, sql in rules.items()])
    return (metrics.select("total", F.explode(F.array(*[F.struct(F.lit(name).alias("rule_name"), F.col(name).alias("fail_count")) for name in rules])).alias("m"))
        .select("m.*", (F.col("total")-F.col("m.fail_count")).alias("pass_count"),
                F.when(F.col("total")>0,100.0*F.col("m.fail_count")/F.col("total")).otherwise(0.0).alias("failure_percentage"))
        .withColumn("table_name",F.lit(table)).withColumn("severity",F.lit(severity))
        .withColumn("pipeline_run_id",F.lit(run_id)).withColumn("validation_timestamp",F.lit(as_of).cast("timestamp")))

def union_all(frames):
    return reduce(lambda a,b:a.unionByName(b), frames)
