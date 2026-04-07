# Data Stack Processor - Complete Checklist & Implementation Guide

## ✅ Implementation Checklist

### Core Components
- ✅ **stack_processor.py** (450+ lines)
  - ✅ JoinConfig dataclass
  - ✅ FileEntry dataclass with glob expansion
  - ✅ ConfigReader with environment support
  - ✅ DataStackProcessor with join/union logic
  - ✅ create_data_stack() main function

### Documentation
- ✅ **DATA_STACK_ARCHITECTURE.md** - Full architecture
- ✅ **STACK_PROCESSOR_QUICKREF.md** - Quick reference
- ✅ **VISUAL_DIAGRAMS.md** - Flow diagrams
- ✅ **IMPLEMENTATION_SUMMARY.md** - Complete summary
- ✅ **conf.example.json** - Example configurations

### Examples & Tests
- ✅ **example_usage.py** - Usage examples
- ✅ **test_stack_processor.py** - Unit tests

---

## 🚀 Integration Steps

### Step 1: Copy Module
```bash
cp /Users/naveen/Desktop/github/mlproject/src/mlproject/stack_processor.py \
   /your/project/path/src/
```

### Step 2: Install Dependencies
```bash
pip install pyspark
```

### Step 3: Create Configuration
```bash
# Copy example and customize
cp conf.example.json conf.json

# Edit with your actual file paths
# Update file paths, metadata paths, join keys
```

### Step 4: Use in Your Code
```python
from pyspark.sql import SparkSession
from src.mlproject.stack_processor import create_data_stack

spark = SparkSession.builder.appName("MyApp").getOrCreate()

# Process data stack
df = create_data_stack(spark, "conf.json", env="uat")

# Use result
df.show()
df.write.parquet("output/")
```

### Step 5: Run Tests
```bash
pytest tests/test_stack_processor.py -v
```

---

## 📋 Feature Breakdown

### Feature 1: Environment-based Configuration ✅
```python
# Load UAT config
df_uat = create_data_stack(spark, "conf.json", env="uat")

# Load PROD config
df_prod = create_data_stack(spark, "conf.json", env="prod")

# Use environment variable
export MLPROJECT_ENV=prod
df = create_data_stack(spark, "conf.json")  # Uses prod
```

### Feature 2: Base File Selection ✅
```json
{
  "file": "base.sas",
  "basefile": true  // Exactly one per environment
}
```
- Processor finds and loads this first
- All subsequent operations build on this
- Can be a glob pattern with multiple files

### Feature 3: Glob Pattern Expansion ✅
```json
{
  "file": "data_*.sas",  // Expands to: data_1.sas, data_2.sas, ...
  "basefile": true
}
```
- Automatic expansion using shell glob
- Sorted alphabetically
- Works with base files and join entries

### Feature 4: Automatic Union ✅
```json
{
  "file": "kb*.sas",     // 3 files matched
  "basefile": true,
  "union": true
}
```
Processing:
1. Find kb1.sas, kb2.sas, kb3.sas
2. Load all three
3. UNION them together
4. Result becomes the base

### Feature 5: Join Operations ✅
```json
{
  "file": "extend.sas",
  "join": {
    "type": "inner",       // inner|left|right|outer|cross
    "keys": ["acct_id"]    // One or more columns
  }
}
```
- Inner join (default)
- Left join (keep all left rows)
- Right join (keep all right rows)
- Outer join (keep all rows)
- Cross join (cartesian product)

### Feature 6: Union Before Join ✅
```json
{
  "file": "data*.sas",
  "union": true,
  "join": {
    "choose name": "union",
    "type": "inner",
    "keys": ["id"]
  }
}
```
Processing:
1. Expand data*.sas (multiple files)
2. UNION all files
3. JOIN result with previous data

### Feature 7: Metadata Support ✅
```json
{
  "file": "data.sas",
  "metadata": "data.metadata"  // Optional schema
}
```
- Reads schema from metadata file
- Applies to SAS files via pyspark_sas module
- Optional - works without metadata too

### Feature 8: Detailed Logging ✅
```
2024-04-07 14:30:15 Processing stack for environment: uat
2024-04-07 14:30:15 Starting copy of data and metadata files
2024-04-07 14:30:16 [BASE] Loading 1 file(s): ['/nas/test/kb1.sas']
2024-04-07 14:30:17 Union completed: 95 rows
2024-04-07 14:30:17 Join operation: type=inner, keys=['acct_id']
2024-04-07 14:30:18 Join completed: 70 rows
2024-04-07 14:30:18 Data stack processing completed
```

---

## 🧪 Testing Checklist

### Unit Tests Included
- ✅ JoinConfig creation and defaults
- ✅ FileEntry from dict parsing
- ✅ Glob pattern expansion
- ✅ ConfigReader loading
- ✅ Environment validation
- ✅ Base file validation
- ✅ Join configuration
- ✅ DataStackProcessor initialization
- ✅ Entry processing
- ✅ Join application

### Manual Testing
```bash
# 1. Test configuration loading
python -c "
from stack_processor import ConfigReader
config = ConfigReader('conf.json', env='uat')
entries = config.get_entries()
print(f'Found {len(entries)} entries')
"

# 2. Test glob expansion
python -c "
from stack_processor import FileEntry
entry = FileEntry(file_pattern='/nas/test/kb*.sas')
files = entry.expand_files()
print(f'Glob expanded to {len(files)} files')
"

# 3. Test full processing
python -c "
from pyspark.sql import SparkSession
from stack_processor import create_data_stack
spark = SparkSession.builder.appName('Test').getOrCreate()
df = create_data_stack(spark, 'conf.json')
print(f'Result: {df.count()} rows')
"
```

---

## 🔍 Validation Checklist

### Before Running
- ✅ All file paths in conf.json exist
- ✅ Metadata files exist (if specified)
- ✅ Exactly one entry has `"basefile": true`
- ✅ Join keys exist in both tables
- ✅ PySpark is installed
- ✅ Environment variable MLPROJECT_ENV is set (optional)

### During Execution
- ✅ Check logs for file expansions
- ✅ Verify row counts at each step
- ✅ Monitor memory usage (large files)
- ✅ Check for join key mismatches

### After Execution
- ✅ Result DataFrame has expected row count
- ✅ Column names are correct
- ✅ Data types are as expected
- ✅ No duplicate columns

---

## 📊 Example Scenarios

### Scenario 1: Simple Stack (3 files)
```json
{
  "uat": [
    { "file": "customer.sas", "basefile": true },
    { "file": "account.sas", "join": {"type": "inner", "keys": ["cust_id"]} },
    { "file": "transaction.sas", "join": {"type": "left", "keys": ["acct_id"]} }
  ]
}
```

Expected output:
- Load customer (e.g., 1000 rows)
- Join account on cust_id (e.g., 1200 rows)
- Left join transaction on acct_id (e.g., 5000 rows)

### Scenario 2: Glob-based Stack (5 files)
```json
{
  "uat": [
    { "file": "daily_*.sas", "basefile": true, "union": true },
    { "file": "summary.sas", "join": {"type": "inner", "keys": ["date"]} }
  ]
}
```

Expected output:
- Find daily_20240101.sas, daily_20240102.sas, ... (5 files)
- Union all (e.g., 5000 rows)
- Join with summary (e.g., 4500 rows)

### Scenario 3: Complex Stack (10 files)
```json
{
  "uat": [
    { "file": "base.sas", "basefile": true },
    { "file": "ext_a.sas", "join": {"type": "inner", "keys": ["id"]} },
    { "file": "ext_b*.sas", "union": true, "join": {"choose name": "union", "type": "inner", "keys": ["id"]} },
    { "file": "ext_c.sas", "join": {"type": "left", "keys": ["ref_id"]} },
    { "file": "ext_d*.sas", "union": true, "join": {"type": "right", "keys": ["key"]} },
    { "file": "lookup.sas", "join": {"type": "inner", "keys": ["code"]} }
  ]
}
```

Flow: base → join ext_a → union+join ext_b* → join ext_c → union+join ext_d* → join lookup

---

## 🛠️ Troubleshooting

### Issue: "Environment 'prod' not found"
**Solution**: Add prod section to conf.json:
```json
{
  "uat": [...],
  "prod": [...]
}
```

### Issue: "Must have exactly one base file"
**Solution**: Check conf.json has exactly one `"basefile": true`

### Issue: "File not found: /path/to/file.sas"
**Solution**: Verify file paths:
```bash
ls /path/to/file.sas
# If using glob: ls /path/to/kb*.sas
```

### Issue: "Join key 'acct_id' not found"
**Solution**: Verify column names:
```python
df.columns  # Check column names
```
Column names are case-sensitive!

### Issue: "Join produced 0 rows"
**Solution**: Check join keys:
- Do values actually match?
- Check data types (int vs string)
- Consider using LEFT join to debug

### Issue: OutOfMemoryError
**Solution**: 
- Increase Spark memory: `--driver-memory 4g --executor-memory 4g`
- Process fewer files at once
- Pre-filter data

---

## 📈 Performance Tips

1. **Reduce glob matches**: Use specific patterns
   ```json
   { "file": "data_2024*.sas" }  // Better than data_*
   ```

2. **Optimize join keys**: Use indexed columns
   ```json
   { "join": {"keys": ["primary_key"]} }
   ```

3. **Order matters**: Put large tables later
   ```json
   [
     { "file": "small_base.sas", "basefile": true },
     { "file": "large_extend.sas", "join": {...} }
   ]
   ```

4. **Use appropriate join type**:
   - `inner`: Smallest result, fastest
   - `left`/`right`: Medium result
   - `outer`: Largest result, slowest

5. **Partition if possible**: For very large files

---

## 🎯 Success Criteria

Your implementation is successful when:

- ✅ Configuration loads without errors
- ✅ Base file is identified correctly
- ✅ Glob patterns expand to actual files
- ✅ Files are read in correct order
- ✅ Joins produce expected row counts
- ✅ Unions combine files correctly
- ✅ Final DataFrame has all expected columns
- ✅ No data loss during transformations
- ✅ Logging shows all operations
- ✅ Can process different environments

---

## 📞 Quick Reference

```python
# Import
from mlproject.stack_processor import create_data_stack

# Usage
df = create_data_stack(spark, "conf.json")
df = create_data_stack(spark, "conf.json", env="prod")

# Check result
df.show()
df.printSchema()
df.count()
df.columns
```

---

## 🚢 Deployment Checklist

- ✅ Module copied to project
- ✅ Dependencies installed (PySpark)
- ✅ Configuration file created and validated
- ✅ All file paths verified
- ✅ Environment variables set (if using)
- ✅ Unit tests passing
- ✅ Manual tests passing
- ✅ Documentation reviewed
- ✅ Error handling tested
- ✅ Ready for production

---

**Version**: 1.0  
**Last Updated**: April 7, 2026  
**Status**: ✅ Complete and Ready for Use
