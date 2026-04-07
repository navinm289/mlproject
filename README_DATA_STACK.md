# Data Stack Processor - Complete Solution

## Overview

The **Data Stack Processor** is a complete Python solution for orchestrating complex PySpark data transformations based on JSON configuration files. It handles file reading, joining, and unioning with support for glob patterns and environment-specific configurations.

## What You Get

### 📦 Core Implementation
- **`src/mlproject/stack_processor.py`** (450+ lines)
  - Production-ready code with full error handling
  - Support for environment-based configurations
  - Glob pattern expansion
  - Join and union operations
  - Comprehensive logging

### 📚 Documentation (5 comprehensive guides)
1. **`DATA_STACK_ARCHITECTURE.md`** - Full technical architecture
2. **`STACK_PROCESSOR_QUICKREF.md`** - Quick reference guide
3. **`VISUAL_DIAGRAMS.md`** - Flow diagrams and visual explanations
4. **`IMPLEMENTATION_SUMMARY.md`** - Complete implementation details
5. **`COMPLETE_CHECKLIST.md`** - Integration and deployment guide

### 💡 Examples & Tests
- **`src/mlproject/example_usage.py`** - Real-world usage examples
- **`tests/test_stack_processor.py`** - Comprehensive unit tests
- **`conf.example.json`** - Example configurations with comments

---

## Quick Start

### 1️⃣ Your Use Case
```
You have 10 SAS files with relationships:
- 1 base file (customer data)
- Several files to join (account, transaction, etc.)
- Some files with multiple pieces (daily_*.sas) to union first
```

### 2️⃣ Configuration (JSON)
```json
{
  "uat": [
    { "file": "customer.sas", "basefile": true },
    { "file": "account.sas", "join": {"type": "inner", "keys": ["cust_id"]} },
    { "file": "daily_*.sas", "union": true }
  ]
}
```

### 3️⃣ Python Code
```python
from pyspark.sql import SparkSession
from mlproject.stack_processor import create_data_stack

spark = SparkSession.builder.appName("DataProcessing").getOrCreate()

# Load and process
df = create_data_stack(spark, "conf.json", env="uat")

# Use result
df.show()
df.write.parquet("output/processed_data")
```

### 4️⃣ That's It!
The processor:
1. ✅ Loads customer.sas as base
2. ✅ Joins account.sas on cust_id
3. ✅ Finds all daily_*.sas files, unions them, and processes
4. ✅ Returns final DataFrame ready to use

---

## Key Features

### 🌍 Environment-based Configuration
```python
df_uat = create_data_stack(spark, "conf.json", env="uat")
df_prod = create_data_stack(spark, "conf.json", env="prod")
```

### 📁 Glob Pattern Support
```json
{ "file": "data_*.sas" }  // Automatically expands to all matches
```

### 🔗 Join Operations
```json
{
  "join": {
    "type": "inner|left|right|outer|cross",
    "keys": ["column1", "column2"]
  }
}
```

### 🔀 Union Before Join
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

### 📊 Metadata Support
```json
{
  "file": "data.sas",
  "metadata": "data.metadata"  // Optional schema
}
```

### 📝 Detailed Logging
```
2024-04-07 14:30:15 Processing UAT environment
2024-04-07 14:30:15 [BASE] Loading 1 file(s)
2024-04-07 14:30:16 Join operation: type=inner, keys=['acct_id']
2024-04-07 14:30:17 Join completed: 50000 rows
...
```

---

## File Structure

```
mlproject/
├── src/mlproject/
│   ├── stack_processor.py              ← Core implementation
│   ├── pyspark_sas.py                  ← SAS reading utilities
│   ├── example_usage.py                ← Usage examples
│   └── conf.json                       ← Your configuration
│
├── tests/
│   └── test_stack_processor.py         ← Unit tests
│
├── Documentation/
│   ├── DATA_STACK_ARCHITECTURE.md      ← Full architecture
│   ├── STACK_PROCESSOR_QUICKREF.md     ← Quick reference
│   ├── VISUAL_DIAGRAMS.md              ← Flow diagrams
│   ├── IMPLEMENTATION_SUMMARY.md       ← Complete details
│   └── COMPLETE_CHECKLIST.md           ← Integration guide
│
├── conf.example.json                   ← Example configurations
├── README_DATA_STACK.md                ← This file
└── ... other project files
```

---

## Configuration Examples

### Example 1: Base + Sequential Joins
```json
{
  "uat": [
    { "file": "customer.sas", "basefile": true },
    { "file": "account.sas", "join": {"type": "inner", "keys": ["cust_id"]} },
    { "file": "transaction.sas", "join": {"type": "left", "keys": ["acct_id"]} }
  ]
}
```

**Result**: customer ← JOIN account ← LEFT JOIN transaction

---

### Example 2: Glob Pattern as Base
```json
{
  "uat": [
    { "file": "daily_*.sas", "basefile": true, "union": true },
    { "file": "summary.sas", "join": {"type": "inner", "keys": ["date"]} }
  ]
}
```

**Result**: UNION(daily_1, daily_2, ...) ← JOIN summary

---

### Example 3: Union Before Join
```json
{
  "uat": [
    { "file": "base.sas", "basefile": true },
    {
      "file": "extension_*.sas",
      "union": true,
      "join": {
        "choose name": "union",
        "type": "inner",
        "keys": ["id"]
      }
    }
  ]
}
```

**Result**: base ← JOIN UNION(extension_1, extension_2, ...)

---

## Processing Flow

```
┌─────────────────────────────────────────┐
│  Configuration (JSON)                   │
│  Select Environment                     │
└──────────────┬──────────────────────────┘
               │
               ├─ Find base file (basefile: true)
               ├─ Load base (may have glob pattern)
               │
               ├─ For each remaining entry:
               │  ├─ Expand glob patterns
               │  ├─ Load file(s)
               │  ├─ Apply union if needed
               │  ├─ Apply join if configured
               │
               └─ Return final DataFrame
```

---

## API Usage

### Basic Usage
```python
from pyspark.sql import SparkSession
from mlproject.stack_processor import create_data_stack

spark = SparkSession.builder.appName("App").getOrCreate()

# Process with default environment (uat)
df = create_data_stack(spark, "src/mlproject/conf.json")

# Process with specific environment
df_prod = create_data_stack(spark, "src/mlproject/conf.json", env="prod")

# Process using environment variable
import os
os.environ["MLPROJECT_ENV"] = "prod"
df = create_data_stack(spark, "src/mlproject/conf.json")
```

### Advanced Usage
```python
from mlproject.stack_processor import ConfigReader, DataStackProcessor

# Read config
config_reader = ConfigReader("conf.json", env="uat")

# Validate
entries = config_reader.get_entries()
config_reader.validate_entries(entries)

# Process
processor = DataStackProcessor(spark, config_reader)
df = processor.process()

# Get entries for inspection
for entry in entries:
    print(f"File: {entry.file_pattern}")
    print(f"Base: {entry.is_base}")
    print(f"Union: {entry.is_union}")
    if entry.join_config:
        print(f"Join type: {entry.join_config.type}")
        print(f"Join keys: {entry.join_config.keys}")
```

---

## Environment Variables

```bash
# Set default environment
export MLPROJECT_ENV=prod

# Set logging level
export LOG_LEVEL=DEBUG

# Run your script (will use prod environment)
python your_script.py
```

---

## Error Handling

The processor validates:
- ✅ Configuration file exists
- ✅ Environment exists in config
- ✅ Exactly one base file is marked
- ✅ Join keys are specified
- ✅ Files can be found or expanded
- ✅ Metadata files exist (if specified)

Example error handling:
```python
try:
    df = create_data_stack(spark, "conf.json", env="prod")
except FileNotFoundError as e:
    print(f"Configuration file not found: {e}")
except ValueError as e:
    print(f"Configuration validation error: {e}")
```

---

## Testing

### Run Unit Tests
```bash
pytest tests/test_stack_processor.py -v
```

### Manual Testing
```python
# Test 1: Configuration loading
from mlproject.stack_processor import ConfigReader
config = ConfigReader("conf.json", env="uat")
entries = config.get_entries()
print(f"Loaded {len(entries)} entries")

# Test 2: Glob expansion
from mlproject.stack_processor import FileEntry
entry = FileEntry(file_pattern="/nas/test/kb*.sas")
files = entry.expand_files()
print(f"Glob expanded to {len(files)} files: {files}")

# Test 3: Full processing
from pyspark.sql import SparkSession
spark = SparkSession.builder.appName("Test").getOrCreate()
df = create_data_stack(spark, "conf.json")
print(f"Result: {df.count()} rows, {len(df.columns)} columns")
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Environment not found" | Add environment section to conf.json |
| "Must have exactly one base file" | Ensure exactly one `"basefile": true` |
| "File not found" | Check file paths exist in conf.json |
| "Join key not found" | Verify column names (case-sensitive) |
| "Join produced 0 rows" | Check join keys have matching values |
| OutOfMemoryError | Increase Spark memory allocation |

---

## Performance Tips

1. **Use specific glob patterns**
   ```json
   { "file": "data_2024*.sas" }  // Better than data_*
   ```

2. **Order files by size** - Put smaller tables first for joins
   ```json
   [
     { "file": "small.sas", "basefile": true },
     { "file": "large.sas", "join": {...} }
   ]
   ```

3. **Use appropriate join type**
   - `inner`: Smallest result, fastest
   - `left`/`right`: Medium result
   - `outer`: Largest result, slowest

4. **Optimize join keys** - Use indexed columns

---

## Next Steps

1. **Review**: Read `DATA_STACK_ARCHITECTURE.md` for full details
2. **Setup**: Copy `stack_processor.py` to your project
3. **Configure**: Create `conf.json` with your file paths
4. **Test**: Run examples in `example_usage.py`
5. **Deploy**: Use in your data pipeline

---

## Documentation Map

| Document | Purpose | Best For |
|----------|---------|----------|
| **DATA_STACK_ARCHITECTURE.md** | Complete technical details | Deep understanding |
| **STACK_PROCESSOR_QUICKREF.md** | Quick lookup guide | Fast answers |
| **VISUAL_DIAGRAMS.md** | Flow diagrams and examples | Visual learners |
| **IMPLEMENTATION_SUMMARY.md** | Feature overview | Getting started |
| **COMPLETE_CHECKLIST.md** | Integration guide | Implementation |
| **conf.example.json** | Configuration examples | Configuration help |
| **example_usage.py** | Code examples | Using the module |

---

## Requirements

- Python 3.7+
- PySpark 3.0+
- Hadoop (for HDFS operations, optional)

### Installation
```bash
pip install pyspark>=3.0
```

---

## Module Structure

```python
# Main function
create_data_stack(spark, config_path, env=None) -> DataFrame

# Classes
ConfigReader          # Reads and validates configuration
FileEntry            # Represents a file in the stack
JoinConfig           # Join configuration
DataStackProcessor   # Orchestrates the transformation
```

---

## Support & Questions

1. Check the appropriate documentation file
2. Review examples in `example_usage.py`
3. Check configuration examples in `conf.example.json`
4. Run unit tests to verify installation

---

## Version History

- **v1.0** (April 7, 2026)
  - Initial release
  - Full environment support
  - Glob pattern expansion
  - Join and union operations
  - Comprehensive documentation

---

## License

Part of mlproject repository

---

## Summary

You now have a **complete, production-ready solution** for orchestrating complex PySpark data transformations:

✅ Core module (stack_processor.py)  
✅ Comprehensive documentation (5 guides)  
✅ Working examples  
✅ Unit tests  
✅ Example configurations  
✅ Integration guide  

**Ready to use immediately!**

Start with `DATA_STACK_ARCHITECTURE.md` for full details or jump to `STACK_PROCESSOR_QUICKREF.md` for quick answers.
