# Data Stack Processor - Visual Flow Diagrams

## Overall Processing Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    Configuration (JSON)                       │
│  {                                                            │
│    "uat": [                                                   │
│      { "file": "base.sas", "basefile": true },              │
│      { "file": "ext.sas", "join": {...} },                  │
│      { "file": "data*.sas", "union": true }                 │
│    ]                                                         │
│  }                                                           │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   v
        ┌─────────────────────┐
        │  ConfigReader       │
        │  env = "uat"        │
        │  Validate entries   │
        └─────────┬───────────┘
                  │
                  v
      ┌───────────────────────────┐
      │ DataStackProcessor.process()│
      │ Orchestrate operations     │
      └───────────┬───────────────┘
                  │
        ┌─────────┴────────┐
        │                  │
        v                  v
    ┌────────────┐     ┌─────────────────┐
    │ Load Base  │     │ Process Entries │
    │ abc.sas    │────▶│ in Order        │
    │ 100 rows   │     │                 │
    └────────────┘     └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    v            v            v
                ┌─────┐     ┌───────┐    ┌─────────┐
                │JOIN │     │ UNION │    │  UNION  │
                │ext  │     │ data* │    │ & JOIN  │
                └─────┘     └───────┘    └─────────┘
                    │            │            │
                    └────────────┼────────────┘
                                 v
                       ┌──────────────────┐
                       │  Final DataFrame │
                       │  Rows: X         │
                       │  Columns: Y      │
                       └──────────────────┘
```

---

## Scenario 1: Base + Simple Join

**Configuration:**
```json
[
  { "file": "abc.sas", "basefile": true },
  { "file": "def.sas", "join": {"type": "inner", "keys": ["id"]} }
]
```

**Flow:**
```
┌──────────┐
│ abc.sas  │
│100 rows  │ ── Read ──┐
└──────────┘           │
                       v
                   ┌─────────┐
                   │ DataFrame│
                   │(base)   │
                   └────┬────┘
                        │
                   ┌────v────────┐
                   │ JOIN        │
                   │on: id       │
                   │type: inner  │
                   └────┬────────┘
                        │
┌──────────┐            │
│ def.sas  │ ── Read ──┤
│ 50 rows  │           │
└──────────┘           │
                       v
                  ┌─────────────┐
                  │   RESULT    │
                  │  70 rows    │
                  └─────────────┘
```

---

## Scenario 2: Glob Pattern Union (Multiple Files as Base)

**Configuration:**
```json
[
  { "file": "kb*.sas", "basefile": true, "union": true },
  { "file": "ext.sas", "join": {"type": "inner", "keys": ["id"]} }
]
```

**Flow:**
```
Glob Expansion: kb*.sas
    │
    ├─ kb1.sas (30 rows)
    ├─ kb2.sas (40 rows)
    └─ kb3.sas (25 rows)

    ┌────────────┐ ┌────────────┐ ┌────────────┐
    │ kb1: 30    │ │ kb2: 40    │ │ kb3: 25    │
    │ DF1        │ │ DF2        │ │ DF3        │
    └────────────┘ └────────────┘ └────────────┘
         │               │               │
         └───────────────┼───────────────┘
                         v
              ┌──────────────────────┐
              │ UNION (kb1+kb2+kb3)  │
              │ 95 rows total        │
              └──────┬───────────────┘
                     │
                     │ (This becomes base)
                     │
         ┌───────────v──────────┐
         │ JOIN                 │
         │ on: id               │
         │ type: inner          │
         │ with: ext.sas        │
         └───────────┬──────────┘
                     │
            ┌────────v─────────┐
            │    RESULT        │
            │  70 rows         │
            └──────────────────┘
```

---

## Scenario 3: Union Before Join

**Configuration:**
```json
[
  { "file": "abc.sas", "basefile": true },
  { 
    "file": "ki*.sas", 
    "union": true,
    "join": {
      "choose name": "union",
      "type": "inner", 
      "keys": ["id"]
    }
  }
]
```

**Flow:**
```
Step 1: Load Base
┌──────────┐
│ abc.sas  │
│ 100 rows │ ──▶ DF_BASE
└──────────┘

Step 2: Glob & Union
Glob Expansion: ki*.sas
    │
    ├─ ki1.sas (20 rows)
    ├─ ki2.sas (30 rows)
    └─ ki3.sas (15 rows)

    ┌────────────┐ ┌────────────┐ ┌────────────┐
    │ ki1: 20    │ │ ki2: 30    │ │ ki3: 15    │
    └────────────┘ └────────────┘ └────────────┘
         │               │               │
         └───────────────┼───────────────┘
                         v
              ┌──────────────────────┐
              │ UNION (ki1+ki2+ki3)  │
              │ 65 rows total        │
              └─────┬────────────────┘
                    │
                    v (DF_UNIONED)

Step 3: Join with Base
┌──────────────────────┐
│ DF_BASE              │
│ 100 rows             │
└─────────┬────────────┘
          │
          │ JOIN on: id
          │ type: inner
          │
┌─────────v─────────────┐
│ DF_UNIONED            │
│ 65 rows               │
└──────────────────────┘
          │
          v
      ┌────────────┐
      │  RESULT    │
      │  80 rows   │
      └────────────┘
```

---

## Data Flow: Multi-Step Stack

**Configuration with 4 entries:**
```json
[
  { "file": "base.sas", "basefile": true },           // Step 1
  { "file": "ext1.sas", "join": {...} },             // Step 2
  { "file": "ext2*.sas", "union": true },            // Step 3
  { "file": "ext3.sas", "join": {...} }              // Step 4
]
```

**Visual Stack:**
```
                            ┌─────────────┐
                            │ base.sas    │
                            │ 100 rows    │
                            └──────┬──────┘
                                   │
                         ┌─────────v────────┐
                         │ JOIN ext1.sas    │
                         │ on: acct_id      │
                         │ 150 rows         │
                         └─────────┬────────┘
                                   │
                     ┌─────────────v──────────┐
                     │ UNION ext2*.sas        │
                     │ (5 files unioned)      │
                     │ 180 rows               │
                     └─────────────┬──────────┘
                                   │
                         ┌─────────v────────┐
                         │ JOIN ext3.sas    │
                         │ on: customer_id  │
                         │ 200 rows         │
                         └─────────┬────────┘
                                   │
                                   v
                          ┌────────────────┐
                          │   FINAL DF     │
                          │   200 rows     │
                          │   (15 columns) │
                          └────────────────┘
```

---

## Class Relationships

```
┌───────────────────────────────────────────────────────┐
│                   ConfigReader                        │
├───────────────────────────────────────────────────────┤
│ - config_path: Path                                   │
│ - env: str                                            │
│ - config: dict                                        │
├───────────────────────────────────────────────────────┤
│ + load_config()                                       │
│ + get_entries() → List[FileEntry]                    │
│ + validate_entries(entries)                          │
└────────────────────┬────────────────────────────────┘
                     │ uses
                     │
                     v
         ┌──────────────────────────┐
         │     FileEntry            │
         ├──────────────────────────┤
         │ - file_pattern: str      │
         │ - metadata_path: str     │
         │ - is_base: bool          │
         │ - is_union: bool         │
         │ - join_config: JoinConf  │
         ├──────────────────────────┤
         │ + from_dict()            │
         │ + expand_files()         │
         └────────────┬─────────────┘
                      │ contains
                      │
                      v
              ┌─────────────────┐
              │  JoinConfig     │
              ├─────────────────┤
              │ - type: str     │
              │ - keys: List    │
              ├─────────────────┤
              │ + from_dict()   │
              └─────────────────┘

┌──────────────────────────────────────────────────────┐
│         DataStackProcessor                           │
├──────────────────────────────────────────────────────┤
│ - spark: SparkSession                                │
│ - config_reader: ConfigReader                        │
├──────────────────────────────────────────────────────┤
│ + process() → DataFrame                              │
│ - _process_entry(entry) → DataFrame                  │
│ - _apply_entry(df, entry) → DataFrame                │
│ - _apply_union(df, entry) → DataFrame                │
│ - _apply_join(df, entry) → DataFrame                 │
└──────────────────────────────────────────────────────┘
         │ uses
         ├────────────────────────────────┐
         v                                v
    ConfigReader              read_sas_with_metadata()
                             (from pyspark_sas.py)
```

---

## Decision Tree: Processing Entry

```
┌─ Entry to process
│
├─ Is this base file?
│  ├─ YES → Load and return
│  │
│  └─ NO → Next question
│
├─ Does it have "union": true?
│  ├─ YES → Does it have glob pattern?
│  │         ├─ YES → Expand glob → Load each → Union → Next
│  │         └─ NO  → Load single file → Union → Next
│  │
│  └─ NO → Next question
│
├─ Does it have "join" config?
│  ├─ YES → Does it have glob pattern?
│  │         ├─ YES → Expand glob → Load each → Union → Join → Next
│  │         └─ NO  → Load single file → Join → Next
│  │
│  └─ NO → Just load and return
│
└─ END
```

---

## Memory/Data Flow

```
Original Files (on disk)
    │
    ├─ base.sas (100MB)
    ├─ ext1.sas (50MB)
    ├─ ext2_1.sas (30MB)
    ├─ ext2_2.sas (30MB)
    ├─ ext2_3.sas (40MB)
    └─ ext3.sas (60MB)

    │
    │ Read into Spark
    v
RDD/DataFrame (in memory)
    │
    ├─ DF_BASE (100 rows) ────┐
    ├─ DF_EXT1 (50 rows)  ────┤
    ├─ DF_EXT2_1,2,3      ────┤
    └─ DF_EXT3 (60 rows)  ────┘
    │
    │ Transform
    v
Processing Stack
    ├─ STEP 1: Load BASE ───────────────────────────── (100 rows)
    │
    ├─ STEP 2: JOIN EXT1 ────────────────────────────  (150 rows)
    │
    ├─ STEP 3: UNION EXT2_1,2,3 ─────────────────────  (180 rows)
    │
    └─ STEP 4: JOIN EXT3 ────────────────────────────  (200 rows)
    
    │
    │ Result
    v
FINAL DataFrame (200 rows, multiple columns)
```

---

## Configuration Validation Logic

```
┌────────────────────┐
│ Load config.json   │
└─────────┬──────────┘
          │
          v
┌────────────────────────────┐
│ Validate JSON structure    │
│ - Valid JSON?              │
│ - Has environment key?     │
│ - Is value a list?         │
└─────────┬──────────────────┘
          │
          v
┌────────────────────────────┐
│ Validate entries           │
│ - Exactly 1 basefile=true? │
│ - All files have patterns? │
│ - Join keys specified?     │
└─────────┬──────────────────┘
          │
    ┌─────┴─────┐
    │           │
    v           v
 VALID     INVALID
  │           │
  │           └─ Raise ValueError
  │              with details
  │
  v
┌──────────────────────┐
│ Proceed with         │
│ processing           │
└──────────────────────┘
```
