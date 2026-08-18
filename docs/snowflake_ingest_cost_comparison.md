# Snowflake ingest cost: COPY INTO from S3 vs Spark connector

This note compares **Snowflake `COPY INTO` from S3** with the **Snowflake Spark connector** (`spark.write` / `net.snowflake.spark.snowflake`). Both land data in Snowflake tables. They do **not** cost the same, because the connector still runs `COPY INTO` and also pays for Spark.

Use the estimator for your own volumes:

```bash
python -m mlproject compare-ingest-cost --data-gb 100 --warehouse SMALL --spark-dpu 10 --loads-per-month 30
```

If Spark already runs to convert SAS files, drop the cluster line:

```bash
python -m mlproject compare-ingest-cost --data-gb 100 --warehouse SMALL --omit-spark-cluster
```

## Bottom line

| Situation | Cheaper path |
| --- | --- |
| Files already in S3 (CSV/JSON/Parquet), same AWS region as Snowflake | **`COPY INTO`** |
| Spark is only used to push rows into Snowflake | **`COPY INTO`** (write Parquet to S3, then copy) |
| Spark already runs for SAS/ETL, and you only need to land the result | Usually still **`COPY INTO`**, because the warehouse session is shorter |
| You need Spark-only logic (UDFs, ML libs) *and* a Snowflake table | Spark connector can be simpler; expect **higher** $ |
| Interactive Databricks notebook writing small frames | Spark connector is convenient; cost gap is small at low volume |

For bulk loads, `COPY INTO` from S3 is the cost floor. The Spark connector is that floor **plus** Spark compute **plus** extra Snowflake warehouse time.

## How each path is billed

### COPY INTO from S3

```
S3 files  →  Snowflake warehouse COPY INTO  →  table
```

You pay:

1. **Snowflake warehouse credits** while `COPY INTO` runs (per-second, **60-second minimum** each resume).
2. **S3 GET requests** (about $0.0004 per 1,000 in us-east-1). Negligible next to credits.
3. **Snowflake storage** after load (same for both methods).
4. **No Snowflake ingress fee.** Same-region S3 → AWS Snowflake is not billed as Snowflake egress. Confirm AWS egress if the bucket is in another region or cloud.

Warehouse size: `COPY INTO` parallelizes **by file**. An X-Small can load 8 files at once; each size up doubles that. Snowflake’s target file size is **100–250 MB compressed**. Oversizing the warehouse with few files burns credits on idle slots.

Gen1 credit burn:

| Size | Credits / hour |
| --- | --- |
| X-Small | 1 |
| Small | 2 |
| Medium | 4 |
| Large | 8 |
| X-Large | 16 |

On-demand Standard on AWS US East is often **~$2 / credit** list. Use your contract rate in `--credit-usd`.

### Spark connector

```
Spark DataFrame  →  serialize files  →  PUT to internal stage or S3  →  COPY INTO  →  table
```

The connector (v2.2+ on AWS) creates a **temporary internal stage**, PUTs Spark partitions, then runs `COPY INTO`. Overwrite mode also uses a temp table and `SWAP WITH`. So Snowflake cost is **not** “instead of COPY”. It **is** COPY, with extra SQL and a warehouse that stays resumed while Spark writes.

You pay:

1. **Spark cluster** (Glue DPU-hours, EMR EC2 + EMR fee, or Databricks DBUs + VMs).
2. **Snowflake warehouse credits** for the whole write session, usually **longer** than a native `COPY INTO` of the same bytes.
3. **S3 PUT + GET** (external transfer) or internal-stage PUT.
4. **Cloud services** for the extra `PUT` / `DESC` / `SWAP` statements (usually inside the 10% daily warehouse allowance).

Snowflake’s own docs recommend **Snowpark** when you do not actually need a Spark cluster. Snowpark Python still stages + `COPY INTO`, but you drop the Spark bill.

## Worked examples (list prices)

Assumptions: **$2 / credit**, Glue **$0.44 / DPU-hour**, **10 DPUs**, Small warehouse, ~150 MB files, Spark warehouse time **2.5×** native COPY (conservative until measured). Same-region S3.

| Daily load | COPY INTO | Spark connector (cluster billed) | Spark premium |
| --- | --- | --- | --- |
| 10 GB | $0.07 | $0.31 | ~4.7× |
| 100 GB | $0.59 | $3.11 | ~5.3× |
| 1 TB | $6.07 | $31.90 | ~5.3× |

Monthly at 30 loads of 100 GB: **~$18 COPY INTO** vs **~$93 Spark connector**.

If Spark **already** runs for SAS conversion (`--omit-spark-cluster`), the 100 GB load is **$0.59 vs $1.49** (about **2.5×** Snowflake credits only). Monthly that is **~$18 vs ~$45**. Writing Parquet to S3 from the same job is still the cheaper landing step.

These are **models**, not invoices. Replace runtimes with `QUERY_HISTORY` and your Spark job duration.

## This repo’s SAS → Spark path

`read_sas_with_metadata` already needs Spark (or pandas) to parse SAS. That Spark hour is **shared**. The ingest choice is only how the DataFrame reaches Snowflake:

**Preferred for cost**

1. Spark writes compressed Parquet to S3 in 100–250 MB files.
2. Dedicated load warehouse runs `COPY INTO` and auto-suspends (30–60 s).
3. Do not keep a Medium/Large warehouse resumed while Spark is still converting SAS.

**Spark connector**

```python
df.write.format("snowflake").options(**sf_options).option("dbtable", "TARGET").mode("append").save()
```

Simpler operationally (one action, no stage SQL). More expensive because the warehouse waits on PUT and Spark still paid for the SAS read.

## When the Spark connector is still the right tool

- Transforms must stay in Spark (libraries Snowflake/Snowpark cannot run).
- You are reading **from** Snowflake into Spark for ML, and the connector’s unload + pushdown beats JDBC.
- Iceberg tables that need Spark to enforce Snowflake Horizon row/column policies (Snowflake’s documented exception).
- Low-volume notebooks where engineer time dominates a few extra credits.

## How to measure a real bake-off

Run the **same GB**, same file layout, same warehouse size, warehouse auto-suspend 60 s:

1. `COPY INTO` from the S3 prefix.
2. `spark.write` of the same DataFrame.

Then compare:

```sql
-- Warehouse credits for the load warehouse
SELECT start_time, credits_used, credits_used_compute
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name = 'LOAD_WH'
  AND start_time >= DATEADD('day', -1, CURRENT_TIMESTAMP());

-- Per-query elapsed time and cloud services
SELECT query_text, execution_time, warehouse_size, credits_used_cloud_services
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name = 'LOAD_WH'
  AND start_time >= DATEADD('day', -1, CURRENT_TIMESTAMP())
ORDER BY start_time;
```

Add Spark cost from Glue job metrics, EMR billing, or Databricks DBU reports. Include idle cluster time if the cluster does not auto-terminate.

## Tuning that actually moves cost

- **File size 100–250 MB compressed** for both paths.
- **Right-size the warehouse to file count**, not to “make COPY faster” when you only have four files.
- **Batch to ≥60 seconds** of useful work so the resume minimum is not wasted.
- **Same region** as the Snowflake account.
- **Auto-suspend 60s** on the load warehouse; do not share it with long Spark sessions.
- Prefer **Parquet or compressed CSV**; avoid thousands of tiny files.
- If you must use the connector, set a **dedicated small warehouse** and do not leave all-purpose Databricks clusters up.

## Recommendation

Default to **S3 + `COPY INTO`** for landing data in Snowflake. Keep Spark for SAS conversion and ML, then write Parquet and copy. Use the Spark connector when Spark must own the write and you accept the extra cluster + warehouse time.

Plug your GB, warehouse, DPU count, and measured minutes into `python -m mlproject compare-ingest-cost` and keep the 2.5× overhead only until you replace it with `QUERY_HISTORY`.
