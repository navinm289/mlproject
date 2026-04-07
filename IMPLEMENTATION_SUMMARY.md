# Data Stack Processor - Complete Implementation

## Files Created

### Core Module
- **`src/mlproject/stack_processor.py`** (450+ lines)
  - `JoinConfig`: Dataclass for join configuration
  - `FileEntry`: Dataclass for file entries with glob support
  - `ConfigReader`: Reads JSON config based on environment
  - `DataStackProcessor`: Orchestrates the data loading and transformations
  - `create_data_stack()`: Main entry function

### Documentation
- **`DATA_STACK_ARCHITECTURE.md`**: Full architecture explanation
- **`STACK_PROCESSOR_QUICKREF.md`**: Quick reference guide
- **`conf.example.json`**: Example configuration with all scenarios

### Examples & Tests
- **`src/mlproject/example_usage.py`**: Usage examples
- **`tests/test_stack_processor.py`**: Unit tests

---

## What It Does - In Plain English

You have 10 SAS files and want to combine them intelligently:

### Traditional Approach ❌
```python
# Manual loading - prone to errors
df1 = read_sas("file1.sas")
df2 = read_sas("file2.sas")
df_combined = df1.join(df2, on="id")
# ... repeat 8 more times
```

### Using Data Stack Processor ✓
```python
# Configuration-driven - clean and maintainable
df = create_data_stack(spark, "conf.json", env="uat")
```

---

## How It Works

### Step 1: Configuration
Define your file stack in JSON:
```json
{
  "uat": [
    { "file": "base.sas", "basefile": true },
    { "file": "file2.sas", "join": {"type": "inner", "keys": ["id"]} },
    { "file": "file3*.sas", "union": true }
  ]
}
```

### Step 2: Load Base
Processor finds the base file and loads it:
```
abc.sas → DataFrame[100 rows]
```

### Step 3: Process in Order
For each remaining file:
- **If union=true**: Union with accumulated data
- **If join exists**: Join with accumulated data
- **If glob pattern**: Expand and handle all matches

### Step 4: Result
Final DataFrame with all transformations applied:
```
base → join file2 → union file3* → Final DataFrame[X rows]
```

---

## Key Features

### ✅ Glob Pattern Support
```json
{ "file": "data_*.sas" }  // Expands to: data_1.sas, data_2.sas, ...
```

### ✅ Environment-based Config
```python
df_uat = create_data_stack(spark, "conf.json", env="uat")
df_prod = create_data_stack(spark, "conf.json", env="prod")
```

### ✅ Multiple Join Types
```json
{
  "join": {
    "type": "inner|left|right|outer|cross",
    "keys": ["col1", "col2"]
  }
}
```

### ✅ Union Before Join
```json
{
  "file": "files*.sas",
  "union": true,
  "join": {
    "choose name": "union",
    "type": "inner",
    "keys": ["id"]
  }
}
```
Unions all matching files first, then joins with previous data.

### ✅ Metadata Support
```json
{
  "file": "data.sas",
  "metadata": "data.metadata"  // Optional schema specification
}
```

### ✅ Detailed Logging
```
2024-04-07 14:30:15 Processing UAT environment
2024-04-07 14:30:15 [BASE] Loading 1 file(s)
2024-04-07 14:30:16 Base file(s) loaded successfully
2024-04-07 14:30:16 Processing entry 1/3: pattern=/nas/test/ebf.sas
2024-04-07 14:30:17 Join operation: type=inner, keys=['acct_id']
2024-04-07 14:30:17 Join completed: 50000 rows
...
```

---

## Use Cases

### Case 1: Sequential Joins
```
Load base → JOIN file2 → JOIN file3 → Result
```

### Case 2: Glob-based Union
```
Find kb*.sas (3 files) → UNION all → Result
```

### Case 3: Complex Stack
```
Load base → JOIN file2 → UNION file3* → JOIN file4 → Result
```

### Case 4: Multi-file Base
```
Find base*.sas (5 files) → UNION all as base → JOIN file2 → Result
```

---

## Quick Start

### 1. Create Configuration
```json
{
  "uat": [
    {
      "file": "/path/to/base.sas",
      "metadata": "/path/to/base.metadata",
      "basefile": true
    },
    {
      "file": "/path/to/extend.sas",
      "join": {
        "type": "inner",
        "keys": ["account_id"]
      }
    }
  ]
}
```

### 2. Use in Python
```python
from pyspark.sql import SparkSession
from mlproject.stack_processor import create_data_stack

spark = SparkSession.builder.appName("MyApp").getOrCreate()

# Load and process
df = create_data_stack(spark, "src/mlproject/conf.json")

# Use the DataFrame
df.show()
df.write.parquet("output/result")
```

### 3. Run with Different Environment
```python
df_prod = create_data_stack(spark, "src/mlproject/conf.json", env="prod")
```

---

## File Structure

```
mlproject/
├── src/mlproject/
│   ├── stack_processor.py          ← Main implementation
│   ├── pyspark_sas.py              ← SAS reading utilities
│   ├── example_usage.py            ← Usage examples
│   └── conf.json                   ← Your configuration
├── tests/
│   └── test_stack_processor.py     ← Unit tests
├── conf.example.json               ← Example config
├── DATA_STACK_ARCHITECTURE.md      ← Full documentation
├── STACK_PROCESSOR_QUICKREF.md     ← Quick reference
└── README.md
```

---

## Processing Order Matters!

The processor reads entries **in the order specified**:

```json
[
  { "file": "abc.sas", "basefile": true },        // 1st: Load as base
  { "file": "def.sas", "join": {...} },           // 2nd: Join with #1
  { "file": "ghi*.sas", "union": true }           // 3rd: Union with #2
]
```

**Results in**:
```
base (abc) → join (def) → union (ghi*)
```

If you reverse the order, you get different results!

---

## Error Handling

### Config Validation
✓ File must exist
✓ Exactly one base file
✓ Environment must exist in config
✓ Join keys must be specified

### Runtime Errors
✓ File not found → Error with path
✓ Invalid join type → Error with type name
✓ Missing join keys → Error with column names

---

## Performance Considerations

1. **Base file size**: Impacts overall performance
2. **Join keys**: Index columns if possible
3. **Glob patterns**: Minimize number of files if possible
4. **Union operations**: Unionizing large number of files can be slow

---

## Next Steps

1. **Copy module** to your project: `cp src/mlproject/stack_processor.py <your-project>/`
2. **Update conf.json** with your actual file paths
3. **Install PySpark** if not already: `pip install pyspark`
4. **Run example**: `python src/mlproject/example_usage.py`
5. **Integrate** into your data pipeline

---

## Troubleshooting

### "Environment not found"
- Check environment name in config
- Use `env` parameter: `create_data_stack(spark, config, env="prod")`

### "Must have exactly one base file"
- Check config has exactly one `"basefile": true`
- Only one entry can have this flag

### "File not found"
- Check file paths are correct
- Check glob patterns match actual files
- Use absolute paths if possible

### "Join keys not found"
- Ensure join keys exist in both DataFrames
- Check column name spelling (case-sensitive in PySpark)

---

## Support

For questions or issues:
1. Check `DATA_STACK_ARCHITECTURE.md` for detailed docs
2. Check `STACK_PROCESSOR_QUICKREF.md` for quick answers
3. Review `conf.example.json` for configuration examples
4. Check unit tests in `tests/test_stack_processor.py` for usage patterns
