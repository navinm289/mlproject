# Customer transaction Gold pipeline

A serverless Lakeflow Spark Declarative Pipeline producing the Unity Catalog managed materialized view `<catalog>.<gold_schema>.customer_transaction_summary`, plus quarantine and rule-level quality results. Materialized views store Delta data and serve ordinary table reads. This project creates a new, isolated solution; it does not modify the existing infrastructure examples.

## Architecture and grain

Five source Delta tables → typed, checked and version-ranked private materialized views → latest valid versions → four left joins → transaction quarantine/accepted facts → lifetime summary → Gold rule evaluation → critical publication gate → valid Gold.

The Gold grain and composite business key are **(customer_id, account_id, product_id, currency)**. `summary_id` is a deterministic SHA-256 surrogate, not a substitute for composite-key validation. A customer may have multiple accounts, products and currencies. Original-currency amounts are never summed across currencies in Gold. USD conversions are calculated per transaction using its UTC date's rate. Negative posted amounts represent refunds. Aggregates are net signed amounts, including zero net balances.

Current customer/account/product attributes restate history (SCD type 1). Daily currency rates are unique by `(currency, rate_date)`. Missing joins are retained until explicitly quarantined; inner joins must not silently lose money. A quarantined orphan is re-evaluated when its dimension arrives. Accounts closed today can have historical transactions: this is a warning, not an automatic rejection.

## Files

| File | Purpose |
|---|---|
| `databricks.yml` | Dev/test/prod bundle, serverless pipeline, serialized retrying Job |
| `src/pipeline.py` | Dataset definitions, routing, reconciliation, critical gate |
| `src/gold_pipeline/contracts.py` | Required source columns, casts and business keys |
| `src/gold_pipeline/transforms.py` | Native Spark normalization, windows, joins, arrays, financial aggregation |
| `src/gold_pipeline/policy.py` | Bounded recursive JSON risk-policy interpreter |
| `src/gold_pipeline/quality.py` | Row rules, warnings, rule metrics |
| `sql/01_sources.sql` | Parameterized UC schema and five Delta source definitions |
| `sql/02_integration_assertions.sql` | Sample-output SQL assertions |
| `sql/03_monitoring.sql` | Event-log monitoring and durable results snapshot example |
| `tests/` | Sample data, guarded loader, unit/Spark/integration examples |
| `docs/operations.md` | Deployment, alerting, recovery, performance and incremental limitations |
| `docs/mapping.md` | Full source-to-target mapping and expected output |

## Assumptions and contracts

- Source tables retain all records needed to rebuild the lifetime summary. Removing source history also removes its contribution on refresh. Actual deletes must delete all historical versions of a business key; deleting only the newest version intentionally exposes the next version. There is no tombstone flag in this contract.
- `event_ts` is a source revision timestamp; `transaction_ts` is business occurrence time; `ingested_at` is stable ingestion time assigned upstream. All are UTC; strings require ISO-compatible formats and explicit offsets if non-UTC. Naive input times are interpreted as UTC. Source producers must not fabricate timestamps on retry.
- Sources can be typed as the provided DDL or contain castable primitive strings. Missing columns and normalized-name collisions fail analysis. Invalid casts become NULL and are quarantined where required. Extra columns are ignored. Complex physical types instead of primitives are contract-breaking and may fail analysis.
- Version winner: descending revision timestamp, ingestion timestamp, then SHA-256 of the full source payload. Exact duplicates are interchangeable. Conflicting timestamp ties use deterministic payload order, not business priority; producers should supply unambiguous revision timestamps. Losers are quarantined as `superseded_duplicate`. Ranking precedes quality filtering to prevent resurrection of stale valid versions.
- Accepted statuses: transactions POSTED/PENDING/REVERSED; accounts OPEN/CLOSED/SUSPENDED; product categories PAYMENTS/SAVINGS/CREDIT. Only POSTED contributes to Gold. REVERSED removes that transaction's prior contribution; refunds are separate negative POSTED records.
- `reference_data` exclusively contains daily currency-to-USD rates. There is no forward-fill or implicit rate of 1, even for USD. Currency strings are three letters; country strings two letters. This validates format, not membership in authoritative ISO registries.
- `products.risk_policy` is a recursive JSON rule tree with `tag`, `not`, `all`, `any`. Tags arrive in `transactions.tags_json`, a JSON string array. Invalid policies quarantine associated posted transactions.
- This risk rule interpreter is the sole Python UDF. Arbitrary nested heterogeneous Boolean trees cannot be cleanly represented by a fixed Spark schema and finite sequence of higher-order expressions. JSON recursion requires traversal; depth, node and byte limits bound its cost. Everything else uses native Spark expressions. For fixed-depth policies, replace the UDF with native expressions. No external services or nondeterministic libraries run on executors.
- `record_created_at` means earliest contributing transaction ingestion time; `record_updated_at` means latest contributing transaction/dimension revision or transaction ingestion time. They are deterministic business provenance, **not** first physical insertion or last refresh timestamps. Deletes can cause these values to move backward. `validation_timestamp` captures the logical run time separately.
- `pipeline_run_id` is a caller-supplied logical batch identifier, not an undocumented Spark configuration for the platform update ID. Persist the mapping to the actual update ID from the event log in orchestration logs. Reuse batch context on retry.

## Data quality

Rules treat SQL NULL as failure. Warnings retain rows with `data_quality_status=WARNING` and `warning_reasons`. Quarantine rows carry source/table stage, JSON payload, rejection-reason array, batch ID and validation time. Gold includes PASS and WARNING only.

| Rules | Severity / action |
|---|---|
| Source required fields, casts/ranges, formats, accepted values, source timestamps | Quarantine |
| Duplicate source versions | Quarantine loser; latest valid winner contributes |
| Missing account/customer/product/rate, invalid policy, conversion overflow, transaction before account opening | Quarantine transaction |
| Gold key completeness/uniqueness, attributes, formats, numeric/date ranges, cross-column equations | Quarantine summary |
| Missing/invalid email, stale customer/product group, closed/suspended account activity | Warning |
| Reconciliation mismatch, rejected-fact percentage, email NULL percentage, minimum volume, baseline volume band | Failure |

Failure rules operate on one-row aggregate controls, including for an empty source. Their results therefore count **control evaluations** (0/1), not failed business rows. Other rule counts count rows at the named stage. Empty row-level datasets return zero counts and 0% failures; the separate minimum-volume control prevents silent empty success. Thresholds use inclusive bounds.

The rejected-fact threshold denominator is latest transaction versions; numerator is invalid source winners plus valid posted transactions rejected during enrichment. Historical duplicate losers and dimension-only invalid rows do not count toward this threshold, but appear in quarantine and results. Gold-level invalid summaries are quarantined; reconciliation operates on candidates so intentional summary quarantine does not masquerade as source loss. The results table identifies those exclusions explicitly.

Reconciliation verifies global deduplicated source POSTED count/amount = pre-publication candidate count/amount + rejected posted count/amount. A second comparison checks accepted-fact count/amount per full business key against candidates. Global native-currency amount is only an arithmetic control, never an economic cross-currency metric. USD output uses decimal arithmetic; these controls do not independently certify external FX accuracy. Raw invalid amounts cannot participate in monetary reconciliation and are covered by source-quality counts/thresholds.

`data_quality_results` and quarantine are **current snapshots**, not append-only audit history. Rule results contain rule name, table name, pass/fail count, failure percentage, severity, batch ID and validation timestamp. Snapshot history outside the pipeline using the example SQL. Do not read a results target back into its own definition.

## Quick start

1. Use Python 3.11+ and Java 17 for local Spark tests:
   ```sh
   python3.11 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt
   PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
   ```
2. Follow [deployment and operations](docs/operations.md). Create fresh dev source/target schemas with `sql/01_sources.sql`, then load `tests/sample_data.py` using `tests/load_sample.py` on Databricks.
3. Set sample context `run_id=sample-001`, `as_of=2026-09-01 00:00:00`, `baseline_posted_rows=4`, **max_quarantine_pct=30**. The sample deliberately rejects one of five latest transactions (20%); the default 5% production threshold must fail this sample. Historical duplicate T1 is not part of that percentage.
4. Run the bundle Job and `sql/02_integration_assertions.sql`. Expected Gold: one row, count 3, total USD/native 90, average 30. Expected quarantine: old T1 and orphan T3. See [mapping and expected outputs](docs/mapping.md).

## Configurable parameters

| Parameter | Default / requirement |
|---|---|
| Bundle catalog | Required existing UC catalog; replace placeholder via `--var` |
| source_schema / gold_schema | Separate names per target in YAML |
| run_id / as_of | Required per logical run; UTC timestamp string |
| gold.max_quarantine_pct | 5; use bundle override 30 for sample |
| gold.max_email_null_pct | 20; edit configuration to business SLA |
| gold.min_posted_rows | 1 |
| baseline_posted_rows | 4 fixture default; **replace for real source scope** |
| gold.min_volume_ratio / max_volume_ratio | 0.5 / 2.0 of approved baseline |
| gold.freshness_days | 30, warning per summary key |
| workspace host / run identity / notifications | Environment-specific, must configure before production |

`as_of` validates an input snapshot's upper time bound; this code does not time-travel sources to reconstruct a historical cutoff. Freeze upstream writes during validation or orchestrate a consistent upstream release. The five independent Delta source commits do not provide a shared multi-table snapshot transaction.

## API references

Verified against official documentation on 2026-09-06. Uses `from pyspark import pipelines as dp`, `@dp.materialized_view`, and expectation decorators; no legacy `dlt` APIs. Serverless incremental refresh is best-effort; partitioned windows and joins have support, but actual query eligibility must be inspected. The optional Python refresh-policy argument is documented as Beta, so the runnable default deliberately uses the stable automatic behavior.

- [Materialized view Python API](https://docs.databricks.com/aws/en/ldp/developer/ldp-python-ref-materialized-view)
- [Incremental refresh support and limitations](https://docs.databricks.com/aws/en/ldp/incremental-refresh)
- [Expectations and failure behavior](https://docs.databricks.com/aws/en/ldp/expectations)
- [Declarative Automation Bundle resources](https://docs.databricks.com/aws/en/dev-tools/bundles/resources)
