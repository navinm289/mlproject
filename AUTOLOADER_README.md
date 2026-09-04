# Serverless Auto Loader: CSV + control file to Bronze

This POC ingests CSV files from AWS S3 into **one Unity Catalog Bronze Delta
table**. A matching control file in the same landing directory supplies the
expected filename, logical CSV row count, checksum, and file creation time.
Validation results are written back to technical columns in that same Bronze
table. No Silver table is created.

## Delivery contract

Upload the data file first and the control file last:

```text
s3://company-bucket/orders/landing/orders_20260904.csv
s3://company-bucket/orders/landing/orders_20260904.control.json
```

```json
{
  "data_file": "orders_20260904.csv",
  "record_count": 125000,
  "checksum_algorithm": "SHA-256",
  "checksum": "<lowercase-or-uppercase-sha256>",
  "file_creation_time": "2026-09-04T06:30:00Z"
}
```

`record_count` means the number of logical CSV data rows parsed by Spark; the
header is not counted. The POC supports SHA-256. Do not substitute the S3 ETag,
because multipart or encrypted objects do not always have a full-object MD5
ETag.

## Execution flow

1. A Databricks file-arrival trigger monitors the shared landing directory.
2. A 120-second quiet period debounces the CSV and control-file arrivals.
3. Serverless Auto Loader selects only `*.csv` and runs with `AvailableNow`.
4. CSV rows are appended to the Bronze table with `WAITING_FOR_CONTROL`.
5. Batch validation reads `*.control.json`, computes row count and SHA-256,
   compares the file timestamp, and updates the same Bronze rows.
6. Processing stops at Bronze with `VALID` or a rejection status.

The file-arrival trigger can still run before a pair is complete. That is safe:
the CSV remains `WAITING_FOR_CONTROL`, and the later arrival starts another
idempotent run.

## Validation statuses

- `WAITING_FOR_CONTROL`
- `VALID`
- `DATA_NOT_INGESTED`
- `UNSUPPORTED_CHECKSUM`
- `COUNT_MISMATCH`
- `CHECKSUM_MISMATCH`
- `CREATION_TIME_MISMATCH`

## Checkpoint ownership

The standalone application supplies and reuses one checkpoint for this CSV
stream. Unity Catalog governs access to its Volume/external location, while
Spark and Auto Loader maintain the checkpoint contents. Never share this path
with another stream, put it inside the landing directory, edit it, or attach a
storage lifecycle policy that deletes it.

The schema location is separate from the streaming checkpoint and stores Auto
Loader schema evolution state.

## Deploy as a serverless Databricks Asset Bundle

Prerequisites:

- A Unity Catalog-enabled Databricks workspace.
- The S3 prefix registered as a UC external location or Volume.
- Read access to the landing location and write access to checkpoint/schema
  locations and the Bronze schema.
- Managed file events enabled on the external location. If unavailable, pass
  `--disable-managed-file-events` and use directory listing for the POC.

Validate and deploy:

```bash
databricks bundle validate \
  --var='landing_path=s3://company-bucket/orders/landing' \
  --var='checkpoint_path=/Volumes/main/ops/checkpoints/orders' \
  --var='schema_path=/Volumes/main/ops/schemas/orders' \
  --var='bronze_table=main.bronze.orders'

databricks bundle deploy \
  --var='landing_path=s3://company-bucket/orders/landing' \
  --var='checkpoint_path=/Volumes/main/ops/checkpoints/orders' \
  --var='schema_path=/Volumes/main/ops/schemas/orders' \
  --var='bronze_table=main.bronze.orders'
```

## Production notes

- Treat landing files as immutable; do not overwrite a filename.
- A byte-level checksum requires reading the complete object and has a compute
  cost. For very large files, prefer an S3-stored checksum supplied and
  validated during upload when the producer can support it.
- S3 exposes last-modified time rather than a general creation-time attribute.
  The POC compares the control timestamp with the Auto Loader file modification
  time using a five-minute tolerance.
- The same Bronze table can hold multiple deliveries, but each feed/table must
  have its own checkpoint and schema location.
