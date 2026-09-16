# Databricks SDP / Lakeflow Notes

Key notes from our discussion on Databricks Lakeflow Spark Declarative Pipelines (SDP), dataset types, and writing to externally managed Iceberg tables.

## 1. Dataset Types Supported in SDP

- **Streaming Table** — A persistent pipeline dataset designed for incremental/streaming processing. The pipeline manages the target and its incremental processing state.
- **Materialized View** — A persistent dataset representing the result of a batch-style query. Databricks manages refreshes and can use incremental refresh when supported.
- **Temporary View** — A pipeline-scoped, non-persistent intermediate dataset. Useful for transformations that do not need to be stored as a final table.

**Important:** Streaming tables and materialized views are the primary persistent dataset types. A temporary view is not physically persisted as a pipeline target.

## 2. Sink Concept

A sink is used when pipeline output needs to be written to an external destination rather than being managed as a normal SDP streaming table or materialized view.

For an Iceberg table that was created and is managed outside the pipeline, the table can be treated as an external target. Custom sink logic, such as a foreachBatch-style sink, can be used when an explicit write to that target is required.

## 3. Existing Iceberg Table as the Target

Scenario: Create an Iceberg table outside SDP and use the pipeline to process data and write into that existing table.

1. Read the source as a streaming DataFrame when incremental processing is required.
2. Apply the required transformations inside the pipeline.
3. Send the resulting micro-batches to sink logic.
4. Inside the sink logic, explicitly write each batch to the existing Iceberg table.

## 4. Return DataFrame vs. Explicit Write

For a normal SDP-managed dataset:

```
Read/Transform → return DataFrame → SDP manages the target write
```

For an externally managed Iceberg target:

```
Read/Transform → sink → explicit write → existing Iceberg table
```

Therefore, when the target is an existing Iceberg table managed outside SDP, simply returning the DataFrame is not the same as defining an SDP-managed table. The sink contains the explicit write behavior for the external target.

## 5. Conceptual Example

```python
source_df = spark.readStream.table("catalog.schema.source_table")

def write_to_iceberg(batch_df, batch_id):
    batch_df.writeTo("catalog.schema.existing_iceberg_table").append()

# The function is used through the pipeline's foreachBatch/custom sink mechanism.
```

## 6. Key Design Decision

Decide who owns the target table. If SDP owns it, define a supported pipeline dataset and let SDP manage writes. If the Iceberg table is created and managed independently, keep ownership outside SDP and use the appropriate sink/write mechanism to deliver pipeline output to it.

## 7. Example: Two Source Tables → Transform → Existing Iceberg Table

Requirement: Read two source tables incrementally, filter by `audit_load_date`, join and transform the records, then use a Lakeflow ForEachBatch sink to explicitly append each micro-batch to an existing Iceberg table.

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

AUDIT_LOAD_DATE = spark.conf.get("my_pipeline.audit_load_date")

@dp.foreach_batch_sink(name="existing_iceberg_sink")
def write_to_iceberg(batch_df, batch_id):
    output_df = (
        batch_df
        .withColumn("processed_ts", F.current_timestamp())
        .withColumn("pipeline_batch_id", F.lit(batch_id))
    )

    (
        output_df.writeTo("main.standard.existing_iceberg_table")
        .append()
    )

@dp.append_flow(
    name="customer_account_to_iceberg",
    target="existing_iceberg_sink"
)
def customer_account_flow():
    customers = (
        spark.readStream
        .table("main.raw.customers")
        .filter(F.col("audit_load_date") == F.lit(AUDIT_LOAD_DATE))
        .select(
            "customer_id",
            "customer_name",
            "country",
            "audit_load_date"
        )
    )

    accounts = (
        spark.readStream
        .table("main.raw.accounts")
        .filter(F.col("audit_load_date") == F.lit(AUDIT_LOAD_DATE))
        .select(
            "account_id",
            "customer_id",
            "account_type",
            "balance"
        )
    )

    transformed = (
        customers
        .join(accounts, "customer_id", "inner")
        .filter(F.col("balance") >= 0)
        .withColumn(
            "customer_name",
            F.upper(F.trim(F.col("customer_name")))
        )
        .withColumn(
            "balance_category",
            F.when(F.col("balance") >= 100000, "HIGH")
             .when(F.col("balance") >= 10000, "MEDIUM")
             .otherwise("LOW")
        )
        .withColumn("source_system", F.lit("CUSTOMER_ACCOUNT"))
        .select(
            "customer_id",
            "customer_name",
            "country",
            "account_id",
            "account_type",
            "balance",
            "balance_category",
            "audit_load_date",
            "source_system"
        )
    )

    return transformed
```

### How the Example Works

1. The append flow reads the two source tables as streaming DataFrames.
2. Both sources are filtered using `audit_load_date`.
3. The two streams are joined and transformations are applied.
4. The append flow returns the transformed streaming DataFrame to the named sink.
5. The ForEachBatch sink receives one micro-batch at a time and explicitly appends it to the existing Iceberg table.
6. Because the target is outside normal pipeline dataset management, downstream cleanup and duplicate/idempotency handling must be designed explicitly.

**Important design note:** A stream-stream join has Structured Streaming requirements and state-management considerations. If one of these source tables is reference/dimension data rather than an incremental stream, it may be preferable to stream the changing source and read the reference side as a static table, depending on the required semantics.

## 8. Stream-Stream Join: Common Ambiguous/Same-Name Errors

If two streaming DataFrames are joined and both contain columns with the same name, Spark can raise an ambiguous-column error when a later select/filter references that column without identifying which input it belongs to. This is a schema-resolution issue, not simply a restriction that two streams cannot be joined.

Recommended pattern: alias both inputs and qualify duplicate column references, then select/rename the required output columns explicitly.

```python
left = spark.readStream.table("catalog.schema.table_a").alias("a")
right = spark.readStream.table("catalog.schema.table_b").alias("b")

joined = (
    left.join(
        right,
        F.col("a.customer_id") == F.col("b.customer_id"),
        "inner"
    )
    .select(
        F.col("a.customer_id").alias("customer_id"),
        F.col("a.audit_load_date").alias("customer_audit_load_date"),
        F.col("b.audit_load_date").alias("account_audit_load_date"),
        F.col("a.customer_name"),
        F.col("b.account_id"),
        F.col("b.balance")
    )
)
```

Also note: true stream-stream joins are stateful. For long-running streams, event-time constraints and watermarks are commonly needed to bound state. If one side is really reference/dimension data, consider a stream-static join instead of making both sides streaming.

Separate issue: if the error literally says that two pipeline datasets/flows have the same name, that is a pipeline naming conflict rather than a join problem. Flow names must be unique within a pipeline.

## 9. Audit-Load-Date Backfill: Batch Job Pattern

For a backfill driven by `audit_load_date`, a batch Databricks job is often simpler than a stream-stream SDP flow. The job accepts an audit date, reads the required slices from both source tables in batch, joins and transforms them, and explicitly writes to the existing Iceberg table.

Flow:

```
audit_load_date parameter
    ↓
batch read Table A + batch read Table B
    ↓
filter both inputs
    ↓
batch join
    ↓
transformations / DQ / deduplication
    ↓
idempotent write to Iceberg
```

```python
from pyspark.sql import functions as F

audit_date = dbutils.widgets.get("audit_load_date")

a = (
    spark.read.table("catalog.raw.table_a")
    .filter(F.col("audit_load_date") == audit_date)
    .alias("a")
)

b = (
    spark.read.table("catalog.raw.table_b")
    .filter(F.col("audit_load_date") == audit_date)
    .alias("b")
)

result = (
    a.join(
        b,
        F.col("a.customer_id") == F.col("b.customer_id"),
        "inner"
    )
    .select(
        F.col("a.customer_id"),
        F.col("a.customer_name"),
        F.col("b.account_id"),
        F.col("b.balance"),
        F.col("a.audit_load_date")
    )
    .withColumn("processed_ts", F.current_timestamp())
)

# Illustrative append only.
# For rerunnable backfills, use an idempotent strategy appropriate
# to the table design (for example MERGE or replacement of the target slice).
result.writeTo("catalog.standard.existing_iceberg_table").append()
```

### Is This Still an SDP Pipeline?

No. If this is implemented as a regular Databricks Job/notebook using `spark.read.table()`, normal DataFrame transformations, and an explicit write to Iceberg, the processing is standard Spark batch processing orchestrated by Databricks Jobs. It is not a Spark Declarative Pipelines (SDP/Lakeflow Declarative Pipelines) pipeline.

SDP uses declarative pipeline constructs such as streaming tables, materialized views, flows, and sinks, and the pipeline runtime manages dataset refresh/incremental semantics. A regular batch job gives the application explicit control over the audit date and write behavior, which is useful for targeted backfills.

A practical architecture can use both: SDP for continuously maintained/incremental datasets, and a separate batch job for explicit historical audit-date backfills when manual date-level control is required.
