[한국어](README.ko.md) | **English**

# long-xls

**Recover data from XLS files that exceed the 65,536-row limit.**

Some programs — stock trading platforms, industrial data loggers, legacy
reporting tools — write BIFF cell records past the XLS row limit without
switching to XLSX.  The data is *physically present* in the file, but
every standard tool (Excel, pandas, xlrd) either truncates it or crashes.

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

Excel shows 65,536 rows.  **long-xls recovers all 370,000.**

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
| `long-xls scan data.xls` | Quick file scan (record counts, no full parse) |

### Options

| Option | Default | Description |
|---|---|---|
| `-f`, `--format` | `xlsx` | Output format: `xlsx`, `csv`, `parquet` |
| `-o`, `--output-dir` | same as input | Output directory |
| `-e`, `--encoding` | `cp949` | Text encoding for string cells |
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

## What It Handles

| Feature | Status |
|---|---|
| BIFF2 LABEL (string cells) | Supported |
| BIFF2 NUMBER (float cells) | Supported |
| BIFF2 INTEGER (int cells) | Supported |
| Row wrap-around at 65,536 | Auto-detected |
| Column-major storage order | Auto-detected |
| Multiple encodings (CP949 / EUC-KR / UTF-8) | Auto-fallback |
| Standalone BIFF stream (no OLE2 container) | Supported |
| OLE2 compound files | Not yet |

## How It Works

Standard XLS (BIFF) format limits sheets to 65,536 rows.  Some programs
ignore this limit and keep writing cell records.  The row index, stored
as a 16-bit unsigned integer, wraps around to 0 at the boundary.

long-xls tracks the wrap count per column and reconstructs logical row
numbers:

```
logical_row = raw_row + (wrap_count * 65536)
```

The data in these files is stored in **column-major order** — all values
for column 0, then all values for column 1, etc.  long-xls handles this
transparently.

## Building a Standalone Executable

```bash
pip install pyinstaller
python build_exe.py          # produces dist/long-xls.exe (Windows)
```

## License

[MIT](LICENSE)
