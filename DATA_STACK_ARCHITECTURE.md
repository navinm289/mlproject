# Data Stack Processor - Architecture & Usage

## Overview

The Data Stack Processor is a Python module that reads configuration files and orchestrates the loading, joining, and unioning of SAS files using PySpark.

## Key Components

### 1. `ConfigReader` - Environment-based Configuration
- Reads JSON/YAML configuration files
- Loads entries based on environment (e.g., 'uat', 'prod', 'dev')
- Validates configuration
- Environment selection:
  - Command-line argument: `env` parameter
  - Environment variable: `MLPROJECT_ENV`
  - Default: `'uat'`

### 2. `FileEntry` - Individual File Configuration
Represents a single entry in the configuration stack with:
- **file_pattern**: Path to file(s) - supports glob patterns (e.g., `kb*.sas`)
- **metadata_path**: Optional metadata file for schema
- **basefile**: Boolean - marks the base file(s)
- **union**: Boolean - indicates this should be unioned with previous data
- **join**: Join configuration if applicable

### 3. `JoinConfig` - Join Operation Configuration
- **type**: Join type (`inner`, `left`, `right`, `outer`, `cross`)
- **keys**: List of column names to join on
- **choose name**: Optional union name for multi-file union before join

### 4. `DataStackProcessor` - Orchestration Engine
Processes the data stack in order:
1. Load base file(s) - can include glob patterns
2. Process remaining entries sequentially
3. Apply joins/unions as configured

## Processing Flow

```
┌─────────────────────────────────────────┐
│  Load Configuration (JSON)              │
│  Select Environment (uat/prod/dev)      │
└──────────────┬──────────────────────────┘
               │
               v
┌─────────────────────────────────────────┐
│  Find & Load BASE FILE(s)               │
│  - Can be single file or glob pattern   │
│  - If glob, union all matching files    │
└──────────────┬──────────────────────────┘
               │
               v
┌─────────────────────────────────────────┐
│  Process Remaining Entries in Order     │
│  For Each Entry:                        │
│  ├─ If union=true → UNION with current  │
│  └─ If join exists → JOIN with current  │
└──────────────┬──────────────────────────┘
               │
               v
┌─────────────────────────────────────────┐
│  Return Final DataFrame                 │
└─────────────────────────────────────────┘
```

## Configuration Format

```json
{
  "uat": [
    {
      "file": "/nas/test/abc.sas",
      "metadata": "/nas/test/abc.metadata",
      "basefile": true
    },
    {
      "file": "/nas/test/ebf.sas",
      "metadata": "/nas/test/ebf.metadata",
      "join": {
        "type": "inner",
        "keys": ["acct_id"]
      }
    },
    {
      "file": "/nas/test/kb*.sas",
      "metadata": "/nas/test/kd.metadata",
      "union": true,
      "join": {
        "type": "inner",
        "keys": ["acct_id"]
      }
    },
    {
      "file": "/nas/test/ki*.sas",
      "metadata": "/nas/test/ki.metadata",
      "union": true,
      "join": {
        "choose name": "union",
        "type": "inner",
        "keys": ["acct_id"]
      }
    }
  ],
  "prod": [
    ...
  ]
}
```

## Use Cases Explained

### Case 1: Base File + Join
```json
[
  {
    "file": "/nas/test/abc.sas",
    "basefile": true
  },
  {
    "file": "/nas/test/ebf.sas",
    "join": {
      "type": "inner",
      "keys": ["acct_id"]
    }
  }
]
```
**Processing**: Load abc.sas → JOIN with ebf.sas on acct_id

### Case 2: Base File with Glob + Join
```json
[
  {
    "file": "/nas/test/kb*.sas",
    "basefile": true,
    "union": true
  },
  {
    "file": "/nas/test/ebf.sas",
    "join": {
      "type": "inner",
      "keys": ["acct_id"]
    }
  }
]
```
**Processing**: 
1. Find all files matching `kb*.sas` (e.g., kb1.sas, kb2.sas, kb3.sas)
2. UNION all kb*.sas files together
3. JOIN result with ebf.sas on acct_id

### Case 3: Union Before Join
```json
[
  {
    "file": "/nas/test/abc.sas",
    "basefile": true
  },
  {
    "file": "/nas/test/ki*.sas",
    "union": true,
    "join": {
      "choose name": "union",
      "type": "inner",
      "keys": ["acct_id"]
    }
  }
]
```
**Processing**:
1. Load abc.sas as base
2. Find all files matching `ki*.sas`
3. UNION all ki*.sas files together
4. JOIN the unioned result with abc.sas on acct_id

## Python API Usage

### Basic Usage
```python
from pyspark.sql import SparkSession
from mlproject.stack_processor import create_data_stack

spark = SparkSession.builder.appName("DataProcessor").getOrCreate()

# Process with default environment (uat)
df = create_data_stack(spark, "src/mlproject/conf.json")

# Process with specific environment
df_prod = create_data_stack(spark, "src/mlproject/conf.json", env="prod")
```

### Advanced Usage with ConfigReader
```python
from mlproject.stack_processor import ConfigReader, DataStackProcessor

# Read configuration
config_reader = ConfigReader("src/mlproject/conf.json", env="uat")

# Validate
config_reader.validate_entries(config_reader.get_entries())

# Process
processor = DataStackProcessor(spark, config_reader)
df = processor.process()

# Use the DataFrame
df.show()
df.write.parquet("output/processed_data")
```

## Environment Variables

- **MLPROJECT_ENV**: Set the default environment
  ```bash
  export MLPROJECT_ENV=prod
  python your_script.py
  ```

## Error Handling

The processor validates:
- ✓ Configuration file exists
- ✓ Environment exists in config
- ✓ Exactly one base file is marked
- ✓ Join keys are specified for joins
- ✓ Files can be found or expanded

## Logging

Enable detailed logging:
```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Features

✓ Multi-environment support
✓ Glob pattern expansion (e.g., `kb*.sas`)
✓ Automatic union of glob-matched files
✓ Configurable join types and keys
✓ Metadata schema support
✓ Detailed logging
✓ Error validation
✓ Preserves column order and data types
