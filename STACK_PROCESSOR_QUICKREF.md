# Data Stack Processor - Quick Reference

## What It Does

The Data Stack Processor reads a JSON configuration and:
1. **Picks the base file** based on `"basefile": true`
2. **Reads files in order** - subsequent entries are joined/unioned with previous data
3. **Handles glob patterns** - e.g., `kb*.sas` expands to all matching files
4. **Supports 4 operations**:
   - Single file read
   - Union of multiple files (when glob matches multiple files)
   - Join (with configurable type and keys)
   - Union → Join (union glob files first, then join with accumulated data)

## Configuration Rules

### Every Config Must Have:
- ✓ Exactly ONE `"basefile": true` entry
- ✓ At least one environment (e.g., "uat", "prod")

### Operations:
```json
{
  "file": "path/to/file.sas",
  "metadata": "path/to/file.metadata",          // Optional
  "basefile": true/false,                       // Mark the base file
  "union": true/false,                          // Union with previous data
  "join": {                                     // Optional join config
    "type": "inner|left|right|outer|cross",    // Join type
    "keys": ["col1", "col2"],                   // Join columns
    "choose name": "union"                      // Optional: union files first
  }
}
```

## Processing Examples

### Example 1: Base + Join
```json
[
  { "file": "abc.sas", "basefile": true },
  { "file": "def.sas", "join": {"type": "inner", "keys": ["id"]} }
]
```
**Steps**: Load abc.sas → JOIN def.sas on id

---

### Example 2: Glob Pattern as Base
```json
[
  { "file": "kb*.sas", "basefile": true, "union": true },
  { "file": "def.sas", "join": {"type": "inner", "keys": ["id"]} }
]
```
**Steps**: 
1. Find kb1.sas, kb2.sas, kb3.sas
2. UNION all kb files
3. JOIN with def.sas

---

### Example 3: Union Glob then Join
```json
[
  { "file": "abc.sas", "basefile": true },
  { "file": "ki*.sas", "union": true, 
    "join": {"choose name": "union", "type": "inner", "keys": ["id"]} }
]
```
**Steps**:
1. Load abc.sas
2. Find ki1.sas, ki2.sas
3. UNION ki1.sas + ki2.sas together
4. JOIN unioned result with abc.sas

## Python Usage

```python
from pyspark.sql import SparkSession
from mlproject.stack_processor import create_data_stack

spark = SparkSession.builder.appName("App").getOrCreate()

# Default environment (uat)
df = create_data_stack(spark, "src/mlproject/conf.json")

# Specific environment
df = create_data_stack(spark, "src/mlproject/conf.json", env="prod")

# Or use environment variable
# export MLPROJECT_ENV=prod
# df = create_data_stack(spark, "src/mlproject/conf.json")
```

## Column Handling

- **Column Order**: Preserved from base file
- **New Columns**: From joined/unioned files are appended
- **Duplicates**: Join operations add columns from right table
- **Source Tracking**: Two columns added:
  - `source_file_name`: Just the filename
  - `source_file_name_with_path`: Full path

## Join Types

| Type | Behavior |
|------|----------|
| **inner** | Only matching rows from both tables |
| **left** | All rows from left, matching from right |
| **right** | All rows from right, matching from left |
| **outer** | All rows from both tables |
| **cross** | Cartesian product (use with caution!) |

## Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Environment not found" | Env not in config | Add env to config or specify correct env |
| "Must have exactly one base file" | 0 or 2+ basefile=true | Fix to have exactly 1 |
| "Join configuration must specify keys" | Join without keys | Add keys array to join config |
| "Config file not found" | Wrong path | Check file path exists |

## Glob Pattern Examples

```
kb*.sas          → kb1.sas, kb2.sas, kb3.sas ...
data_*.parquet   → data_20240101.parquet, data_20240102.parquet ...
*/test/*.sas     → any/test/*.sas, all/test/*.sas ...
file[abc].sas    → filea.sas, fileb.sas, filec.sas
```

## File Count Behavior

- **1 match**: Single file loaded
- **2+ matches**: Auto-unioned together
- **0 matches**: Error (file not found)

## Logging

Enable info logs:
```python
import logging
logging.basicConfig(level=logging.INFO)
```

See operation count, join types, file expansions in logs.
