# Deployment and operations

## Dev, test and production

Prerequisites: UC-enabled workspace with serverless Lakeflow support, current Databricks CLI with bundle support, OAuth authentication, source SELECT permissions, target schema creation permissions, and an approved service principal for production. Never commit tokens. Pin the CLI version in CI after validating it in your workspace.

1. Dev: set `DATABRICKS_HOST` and authenticate with `databricks auth login`. From the project root, run `sql/01_sources.sql` in a SQL editor with catalog/source_schema/gold_schema parameters. Catalog creation is a platform-admin responsibility. For existing sources, review schema compatibility and enable row tracking, CDF and deletion vectors in a separately approved upstream change. The sample DDL only configures newly created tables.
2. Load sample data on a Databricks development cluster: make the project available in a workspace Git folder, then run `tests/load_sample.py --source YOUR_CATALOG.customer_source_dev`. The loader first checks all tables are empty. Do not use production schemas for fixtures.
3. Supply bundle variables through CI or environment variables. For the sample:
   ```sh
   export BUNDLE_VAR_catalog=YOUR_CATALOG
   export BUNDLE_VAR_run_id=sample-001
   export BUNDLE_VAR_as_of='2026-09-01 00:00:00'
   export BUNDLE_VAR_max_quarantine_pct=30
   export BUNDLE_VAR_baseline_posted_rows=4
   databricks bundle validate -t dev
   databricks bundle deploy -t dev
   databricks bundle run -t dev refresh_gold
   ```
   Local imports are under `src/`; bundle sync uploads supporting Python files along with the entrypoint. Run the SQL integration assertions afterward. Bundle validation checks resource compatibility; local YAML parsing alone cannot do that.
4. Test: deploy the same reviewed commit with `-t test`, isolated schemas, synthetic inputs, and a test identity. Execute the transition tests below. Set realistic thresholds and approved baseline from a durable historical control dataset; the fixture baseline of 4 is not a production baseline.
5. Production: configure `workspace.host`, `run_as.service_principal_name`, deployment permissions and notification destinations according to your CI convention. Set source/Gold schemas and approved thresholds. `databricks bundle validate -t prod`, deploy, then run. Production mode may require workspace root/run-as settings depending on workspace policy; satisfy validation before deployment. Grant consumers SELECT only on Gold; auditors alone should access quarantine/results.
6. Each logical run must set a fresh immutable run ID and UTC as-of time, update the bundle configuration, and start the Job. `operations/run.py` automates validate/deploy/run with structured logs. Serialize the **entire orchestration**, including deploy, with a CI environment lock; Job concurrency alone does not prevent racing configuration deployments. Reuse context for retries. Do not add a recurring Job schedule that reuses stale deployed batch context. For high-frequency pipelines, move context to a managed release-control dataset and measure the resulting refresh invalidations.

This repository is deployment-ready source, not an assertion that your cloud workspace has passed acceptance testing. No remote deployment is performed by generating these files.

## Required integration transitions

Use a disposable test schema; execute each mutation between completed updates, advancing `as_of` and `run_id` as appropriate. Keep the same approved fixture volume band (2–8 posted rows).

| Mutation | Expected behavior |
|---|---|
| Repeat unchanged update with same context | Identical Gold values, no duplicate business key; current quarantine snapshot remains 2 rows |
| Add a late posted T6 for A1/P1/USD at 2026-08-30 09:00, amount 7, newer event/ingestion timestamp | Count 4, total 97, first timestamp becomes 09:00 |
| Add newer T2 revision changing amount -20 to -30 | After T6, count stays 4, total becomes 87; prior T2 quarantined |
| Add account MISSING for C1 opened before T3 | T3 leaves current quarantine; new Gold account group count 1, total 50 |
| Update customer name | Both account groups reflect current customer name without new transactions |
| Delete all versions of T4 | Original A1 group count decreases by 1, amount decreases by 10 |
| Append newest T1 with NULL amount | T1 no longer contributes; does not resurrect old valid version; source rule rejects winner |
| Introduce email NULL and max_email_null_pct=0 | Publication gate fails; Gold does not publish the new candidate |
| Initial sample with max_quarantine_pct=5 | Gate fails at 20% rejection; event log records expectation failure |
| Empty all fixture source tables | Minimum-volume control fails even though row rules see zero rows |
| Add physical source column | Ignored; drop required column → analysis failure |
| Full refresh vs regular refresh on fixed sources/context | Same business results; compare with EXCEPT ALL both directions |

Do not execute deletes against real production sources. Test changes to UDF code with a controlled full refresh because the platform may not detect indirect library behavior changes. SQL assertions cover the initial fixture; transition tests above are workspace acceptance scenarios, not a claim of locally tested Delta/Lakeflow behavior.

## Incremental processing and layout

This is incremental **view maintenance**, not streaming `readStream` with a watermark. It handles arbitrary late records, source corrections, dimension changes and retained-history deletes with batch-equivalent semantics. No lateness watermark discards records. The system manages checkpoints/internal state; do not set manual checkpoint locations or manually delete internal tables. CDF is enabled to aid maintenance but this code does not explicitly consume CDF rows or require append-only sources.

Serverless chooses incremental or full recomputation automatically. Partitioned ROW_NUMBER, joins and decimal aggregates can be eligible. UDFs, configuration-literal changes, validation scans, cross joins and query-plan details can cause broad recomputation. A new run ID/as-of literal can rewrite output audit columns even if business facts are unchanged. The correctness design does **not** promise strictly incremental cost for every stage. Separate stable business MVs from run-level audit snapshots if rewrite costs dominate.

Use pipeline table incrementalization details/event logs and `EXPLAIN CREATE MATERIALIZED VIEW` on representative query SQL to verify actual plans. The current Python `refresh_policy` parameter is documented as Beta; do not enable `incremental_strict` in production without platform approval and eligibility tests. If full refresh is unaffordable, redesign ingestion around explicit CDC streaming state and test change propagation before adopting a strict-only policy.

- Unity Catalog managed output with automatic liquid clustering; no high-cardinality physical partitions. Do not combine static partitioning with liquid clustering.
- AQE and serverless shuffle tuning use platform defaults; avoid hard-coded production shuffle partition counts. The local tests use two partitions only for speed.
- Filter POSTED before joins, project explicit contracts, keep one row per dimension key to avoid join fan-out. Broadcast only genuinely small dimensions after measuring byte size; no forced broadcast hint assumes all customers fit memory.
- Keep native decimal arithmetic and high-order array functions. The UDF runs after source filtering; profile its worker overhead and limit policy complexity. Policy changes require regression tests.
- Track scan/shuffle bytes, skew, spill, refresh duration, full-recompute frequency, row volumes, backlog and DBU cost. Set compute-budget alerts and investigate regressions against the same source size.
- Avoid unconditional repartition/cache/count inside dataset functions; actions are only in tests/operations. Use predictive optimization where available and appropriately permitted; do not schedule overlapping OPTIMIZE jobs blindly.

## Observability, failure and recovery

Lakeflow's event log is the canonical structured execution log and lineage source. Dataset bodies may be evaluated repeatedly during planning: they do not print logs, generate random IDs, call APIs or write side-effect tables. `operations/run.py` emits JSON lifecycle logs without source payloads or credentials. UC and the pipeline graph preserve dataset lineage; note that arbitrary Python internals of the policy UDF are not column-level lineage documentation.

Monitor expectation pass/fail/drop metrics, update status, flow progress, source/Gold volumes, per-rule quality results and freshness. Configure Job failure notifications plus SQL alerts for quarantines, WARN freshness, NULL percentage trends, absent successful updates, and unexpected full recomputation. Missing email percentage is about SQL NULL, while malformed non-NULL email is independently a warning. Per-key freshness may flag dormant customers by design; separately alert on lack of an overall successful update within the ingestion SLA.

A critical expectation terminates its flow/update and blocks the downstream Gold dependency. **Lakeflow is not a multi-table transaction:** unrelated flows may commit; quarantine/results may or may not refresh before a failed gate. Existing Gold can remain at the last successful version. Never label a partially updated results table as a complete audit for the failed run. Record failure from the event log; persist complete results after successful updates and optionally refresh diagnostic flows separately after failure. Consumers requiring a consistent multi-table release should read only after orchestration marks the whole update successful, with release version metadata maintained outside this DAG.

Retry transient infrastructure failures with the Job's two bounded retries and a one-minute interval; retries preserve batch context. Retrying deterministic contract/quality failures without fixing input will not help. The example Job retries all failed pipeline tasks; an advanced orchestrator can classify failures and avoid unnecessary quality-failure retries. No `try/except` hides Spark analysis or expectation failures. The UDF converts malformed business policy into a quarantine reason but lets infrastructure failures surface.

Repair data in its source of truth, rerun, and verify reconciliation. Current quarantine records can disappear after repairs; use append/merge audit snapshots for forensic retention. Managed internal state supports ordinary recovery. Full refresh is an explicit maintenance action requiring complete retained source history and a cost review. Never VACUUM beyond the source recovery agreement. Store code SHA, logical run ID, platform update ID, configuration hash and relevant source versions in an external release log for reproducibility.

Quarantine payloads contain PII. Apply UC least privilege, retention policies and access audit logging. Consider a restricted quarantine schema for real deployments; update fully qualified target names/grants together. Do not enable row masks or row filters on source MVs without assessing the documented impact on incremental eligibility.
