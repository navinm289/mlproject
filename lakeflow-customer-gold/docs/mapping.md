# Source-to-target mapping

| Gold column | Source / derivation |
|---|---|
| customer_id | accounts.customer_id → customers.customer_id |
| account_id | transactions.account_id → accounts.account_id |
| product_id | transactions.product_id → products.product_id |
| currency | trimmed uppercase transactions.currency; part of grain |
| customer_name, email, country | latest customers; trim; lowercase email; uppercase country |
| account_status, opened_date | latest accounts; uppercase status; date cast |
| product_name, category | latest products; uppercase category |
| total_transaction_amount | SUM posted accepted transactions.amount, DECIMAL(28,2) |
| transaction_count | COUNT accepted transactions, BIGINT |
| average_transaction_amount | AVG DECIMAL(18,2), Spark DECIMAL(22,6) |
| total_amount_usd | SUM per-transaction amount × reference_data.usd_rate rounded to DECIMAL(28,2), aggregate DECIMAL(38,2) |
| first_transaction_ts, latest_transaction_ts | MIN/MAX transactions.transaction_ts, UTC TIMESTAMP |
| risk_transaction_count | count matched product policy against normalized transaction tags |
| summary_id | SHA-256 JSON struct of the four ordered grain columns |
| customer_segment | HIGH_VALUE if net USD >= 10000 for this customer/account/product/currency group, otherwise STANDARD |
| product_segment | category + REVIEW if any risk match, otherwise NORMAL |
| data_quality_status, warning_reasons | PASS/WARNING from row rules; ARRAY<STRING> reasons |
| record_created_at | MIN contributing transactions.ingested_at |
| record_updated_at | MAX contributing revision/ingestion and dimension revision timestamps |
| pipeline_run_id, validation_timestamp | immutable orchestration batch context |
| publication_gate_status | PASSED after aggregate critical checks |

The segment is group-specific, not a customer-wide lifetime classification across all accounts. Enriched tags are lowercase, trimmed, deduplicated, sorted and NULL/empty elements removed through native higher-order array expressions. Source raw payload is retained only in internal/quarantine paths.

## Sample expected outputs

The sample has six physical transactions, five latest business keys, four valid latest POSTED transactions, three accepted POSTED facts. T5 is PENDING and excluded by business scope.

| customer_id | account_id | product_id | currency | total_transaction_amount | transaction_count | average_transaction_amount | total_amount_usd |
|---|---|---|---|---:|---:|---:|---:|
| C1 | A1 | P1 | USD | 90.00 | 3 | 30.000000 | 90.00 |

Other values: Alice, alice@example.com, US, OPEN, 2020-01-01, Payments, PAYMENTS; first=2026-08-30 10:00 UTC, latest=2026-08-30 11:30 UTC; risk count=1; STANDARD; PAYMENTS_REVIEW; PASS; warning_reasons=[]; created/updated=2026-08-30 12:00 UTC; run=sample-001; validation=2026-09-01 00:00 UTC; gate=PASSED. `summary_id` is generated deterministically from the stated key.

| Quarantine source_table | Payload ID | Reasons |
|---|---|---|
| transactions | T1 amount 90, older event_ts | superseded_duplicate |
| joined_transactions | T3 account MISSING | account_fk, customer_fk, opened_before_transaction |

Source POSTED count=4 and amount=140; candidate count=3 and amount=90; rejected count=1 and amount=50. Latest transaction rows=5; rejected percentage=20%; null-email percentage=0%. With the sample threshold 30%, all five critical rules pass. `duplicate_version` for transactions has pass_count=5, fail_count=1 and failure_percentage=16.666... . Join account_fk/customer_fk/opened_before_transaction each have 3 passes, 1 failure, 25%. Other row rules pass.
