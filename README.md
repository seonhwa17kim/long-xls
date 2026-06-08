# long-xls

Recover data from XLS files that exceed the 65,536-row limit.

Some programs (e.g. Kiwoom HTS, legacy data exporters) write BIFF records
past the XLS row limit without switching to XLSX.  Standard tools like
Excel, pandas, and xlrd either truncate the data or refuse to open the file.

**long-xls** reads the raw BIFF binary stream, detects row-index
wrap-arounds at the 65,536 boundary, and reconstructs the full dataset.

## Install

```bash
pip install long-xls            # xlsx output (default)
pip install long-xls[parquet]   # + parquet support
pip install long-xls[all]       # everything
```

Or download a standalone executable from
[Releases](https://github.com/seonhwa/long-xls/releases) — no Python needed.

## Usage

```bash
# Convert to xlsx (default)
long-xls data.xls

# Convert to csv
long-xls data.xls -f csv

# Convert to parquet
long-xls data.xls -f parquet

# Convert with schema sidecar
long-xls data.xls --schema

# Print schema to stdout
long-xls schema data.xls

# Quick file scan (no full parse)
long-xls scan data.xls

# Multiple files
long-xls *.xls -f csv -o output/

# Specify encoding (default: cp949)
long-xls data.xls -e utf-8
```

## Python API

```python
from long_xls import parse, parse_to_dataframe, schema_json

# Low-level: get structured data
sheet = parse("data.xls")
print(sheet.num_data_rows)   # 371700

# DataFrame
df, sheet = parse_to_dataframe("data.xls")

# Schema
import json
print(json.dumps(schema_json(sheet), indent=2))
```

## What it handles

| Feature | Status |
|---|---|
| BIFF2 LABEL (string cells) | Supported |
| BIFF2 NUMBER (float cells) | Supported |
| BIFF2 INTEGER (int cells) | Supported |
| Row wrap-around at 65,536 | Auto-detected |
| Column-major storage order | Auto-detected |
| EUC-KR / CP949 / UTF-8 encoding | Auto-fallback |
| OLE2 compound files (.xls) | Not yet — standalone BIFF only |

## How it works

Standard XLS (BIFF) format limits sheets to 65,536 rows.  Some programs
ignore this limit and keep appending cell records with row indices that
wrap around to 0.  long-xls tracks the wrap count per column and
reconstructs logical row numbers:

```
logical_row = raw_row + (wrap_count * 65536)
```

## License

MIT
