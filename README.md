[한국어](README.ko.md) | **English**

# long-xls

**A simple tool to recover data from XLS files that exceed the 65,536-row limit.**

The XLS format is structurally limited to 65,536 rows per sheet.  However,
some programs — legacy reporting utils, converting tools, stock trading
platform exporters, etc. — keep writing BIFF cell records past this limit.
The data is physically present in the file, but most programs and libraries
(Excel, pandas, xlrd) either silently truncate it or throw an error, leaving
no way to read the stored data.

**long-xls** reads the raw BIFF binary stream, detects row-index
wrap-arounds at the 65,536 boundary, and reconstructs the full dataset.

## The Problem

```
┌─────────────────────────────────────────────────────┐
│  Your XLS file (e.g. 370,000 rows of trade data)    │
│                                                     │
│  Row 1 ............ ✓ visible in Excel              │
│  Row 65,536 ....... ✓ visible in Excel              │
│  Row 65,537 ....... ✗ INVISIBLE — data is there     │
│  Row 370,000 ...... ✗ INVISIBLE — but recoverable!  │
└─────────────────────────────────────────────────────┘
```

## Install

```bash
pip install long-xls              # xlsx output (default)
pip install "long-xls[parquet]"   # + parquet support
pip install "long-xls[all]"       # everything
```

Or download a **standalone executable** from
[Releases](https://github.com/seonhwa17kim/long-xls/releases) — no
Python required.

## Quick Start

```bash
# Convert to xlsx (default)
long-xls data.xls

# Convert to csv
long-xls data.xls -f csv

# Convert to parquet
long-xls data.xls -f parquet

# Include a JSON schema sidecar file
long-xls data.xls --schema

# Multiple files at once
long-xls *.xls -f csv -o output/
```

## Commands

| Command | Description |
|---|---|
| `long-xls data.xls` | Convert to xlsx (default) |
| `long-xls data.xls -f csv` | Convert to csv |
| `long-xls data.xls -f parquet` | Convert to parquet |
| `long-xls data.xls --schema` | Also write `.schema.json` |
| `long-xls schema data.xls` | Print JSON schema to stdout |
| `long-xls scan data.xls` | Quick file scan (record counts only) |

### Options

| Option | Default | Description |
|---|---|---|
| `-f`, `--format` | `xlsx` | Output format: `xlsx`, `csv`, `parquet` |
| `-o`, `--output-dir` | same as input | Output directory |
| `-e`, `--encoding` | `cp949` | Text encoding for string cells |
| `-y`, `--force` | off | Overwrite existing files without asking |
| `--schema` | off | Write a `.schema.json` alongside output |

## Python API

```python
from long_xls import parse, parse_to_dataframe, schema_json

# Parse and inspect
sheet = parse("data.xls")
print(f"{sheet.num_data_rows:,} rows recovered")

# Get a pandas DataFrame
df, sheet = parse_to_dataframe("data.xls")

# Export schema as JSON
import json
print(json.dumps(schema_json(sheet), indent=2))
```

## Schema Output Example

```json
{
  "file": "data.xls",
  "file_size": 29736094,
  "encoding": "cp949",
  "num_columns": 4,
  "num_data_rows": 371700,
  "row_limit_exceeded": true,
  "wraps": {"0": 5, "1": 5, "2": 5, "3": 5},
  "columns": [
    {"index": 0, "name": "date", "type": "string", "non_null_count": 371700},
    {"index": 1, "name": "time", "type": "string", "non_null_count": 371700},
    {"index": 2, "name": "price", "type": "float", "non_null_count": 371700},
    {"index": 3, "name": "volume", "type": "integer", "non_null_count": 371700}
  ]
}
```

## Test Files

### Synthetic test files (generator included)

Run `tests/generate_test_xls.py` to generate long-XLS test files of
various sizes.  It writes raw BIFF2 records to reproduce the row
wrap-around behaviour.

```bash
python tests/generate_test_xls.py
```

| File | Rows | Wraps | Encoding | Purpose |
|---|---|---|---|---|
| `test_100k_rows.xls` | 100,000 | 1 | UTF-8 | Basic recovery verification |
| `test_200k_rows.xls` | 200,000 | 3 | UTF-8 | Multi-wrap verification |
| `test_70k_cp949.xls` | 70,000 | 1 | CP949 | Korean encoding verification |

### Real-world example: Kiwoom Securities HTS chart data

Futures tick chart data exported from Kiwoom Securities HTS.  Contains
371,700 rows, but Excel only shows up to 65,535.  long-xls recovers
the entire dataset.

- `20240808_KOSPI200_Tick_Kiwoom.xls` — 371,700 rows (5 wraps), 29.7 MB

## Building a Standalone Executable

```bash
pip install pyinstaller
python build_exe.py          # produces dist/long-xls.exe (Windows)
```

## Author

seonhwa17kim (with help from GPT-5.5, Gemini 3.5, Claude Opus 4.8)

## License

[MIT](LICENSE) Copyright (c) 2026 seonhwa17kim
