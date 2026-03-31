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
    ["data/source_a.sas7bdat", "data/source_b.sas7bdat"],
    meta_path="data/source.meta",
    header="true",
)
```

The reader uses the Spark SAS format
`com.github.saurfang.sas.spark`, so that JAR still needs to be available when
you run `spark-submit`.

## Metadata file

If `meta_path` is provided, the reader treats it as a `;`-separated schema
file and reads it through Spark's CSV reader.

Example:

```text
s.no;columnname;datatype;nullable
1;customer_id;long;false
2;signup_dt;timestamp;true
3;is_active;boolean;true
```

## Notes

- The implementation reads SAS data through `spark.read.format(...).load(...)`.
- Supported metadata headers include `columnname`/`columname`, `datatype`,
  and optional `nullable`.
- `datatype` can be a simple Spark type like `string` or a parameterized type
  like `decimal(20,4)`.
- Any extra keyword arguments passed to `read_sas_with_metadata(...)` are sent
  to `spark.read.options(...)`.
- Multiple SAS paths can be passed in, and the helper unions them together
  after adding `source_file_name` and `source_file_name_with_path`.
