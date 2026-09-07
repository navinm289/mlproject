-- Run using Databricks SQL named parameters catalog, source_schema, gold_schema.
-- Catalog must already exist with managed storage. Use a dedicated sandbox for sample data.
CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog || '.' || :source_schema);
CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog || '.' || :gold_schema);
CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :source_schema || '.customers') (
 customer_id STRING, customer_name STRING, email STRING, country STRING, event_ts TIMESTAMP, ingested_at TIMESTAMP
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true','delta.enableRowTracking'='true','delta.enableDeletionVectors'='true');
CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :source_schema || '.accounts') (
 account_id STRING, customer_id STRING, account_status STRING, opened_date DATE, event_ts TIMESTAMP, ingested_at TIMESTAMP
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true','delta.enableRowTracking'='true','delta.enableDeletionVectors'='true');
CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :source_schema || '.products') (
 product_id STRING, product_name STRING, category STRING, risk_policy STRING, event_ts TIMESTAMP, ingested_at TIMESTAMP
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true','delta.enableRowTracking'='true','delta.enableDeletionVectors'='true');
CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :source_schema || '.reference_data') (
 currency STRING, rate_date DATE, usd_rate DECIMAL(18,8), event_ts TIMESTAMP, ingested_at TIMESTAMP
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true','delta.enableRowTracking'='true','delta.enableDeletionVectors'='true');
CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :source_schema || '.transactions') (
 transaction_id STRING, account_id STRING, product_id STRING, currency STRING, amount DECIMAL(18,2), transaction_ts TIMESTAMP,
 status STRING, tags_json STRING, event_ts TIMESTAMP, ingested_at TIMESTAMP
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed'='true','delta.enableRowTracking'='true','delta.enableDeletionVectors'='true');
-- Pipeline decorators are the authoritative UC materialized-view definitions for outputs.
-- Do not CREATE TABLE the pipeline-owned targets. Column schemas derive from explicit casts
-- and aggregations. Primary keys are checked in code; UC PK/FK declarations are not enforcement.
-- Grant run identity USE CATALOG, USE SCHEMA, SELECT on sources;
-- USE SCHEMA, CREATE TABLE, CREATE MATERIALIZED VIEW on target schema as needed.
-- Restrict quarantine and private intermediate access because payloads contain customer PII.
