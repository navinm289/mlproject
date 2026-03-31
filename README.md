# mlproject

This project now includes a small PySpark helper for reading SAS files.

## Install

```bash
pip install -e .
```

## Usage

```python
from pyspark.sql import SparkSession
from mlproject import read_sas_with_metadata

spark = SparkSession.builder.getOrCreate()

df = read_sas_with_metadata(
    spark,
    "data/source.sas7bdat",
    meta_path="data/source.meta.json",
)
```

## Metadata file

If `meta_path` is provided, the reader uses it automatically. JSON is supported
out of the box, and YAML is supported when `PyYAML` is installed.

Example:

```json
{
  "read_options": {
    "format": "sas7bdat",
    "encoding": "utf-8"
  },
  "column_names": ["customer_id", "signup_dt", "is_active"],
  "schema": [
    {"name": "customer_id", "type": "long", "nullable": false},
    {"name": "signup_dt", "type": "timestamp", "nullable": true},
    {"name": "is_active", "type": "boolean", "nullable": true}
  ],
  "rename_columns": {
    "signup_dt": "signup_at"
  },
  "casts": {
    "signup_at": "timestamp"
  }
}
```

## Notes

- The implementation uses `pandas.read_sas(...)` first, then converts the
  result to a PySpark DataFrame.
- Direct function keyword arguments override `read_options` found in metadata.
