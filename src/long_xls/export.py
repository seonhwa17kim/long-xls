"""Export helpers: xlsx (default), csv, parquet, and JSON schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from long_xls.parser import SheetData, _OPCODE_NAME


# -- Schema ----------------------------------------------------------------

def schema_json(sheet: SheetData) -> dict[str, Any]:
    """Return a JSON-serialisable dict describing the file structure.

    Includes column names, inferred types, row/wrap counts, and record stats.
    """
    col_types: list[dict[str, Any]] = []
    for c in range(sheet.num_columns):
        vals = sheet.columns.get(c, [])
        sample = next((v for v in vals if v is not None), None)
        if isinstance(sample, str):
            dtype = "string"
        elif isinstance(sample, int):
            dtype = "integer"
        elif isinstance(sample, float):
            dtype = "float"
        else:
            dtype = "unknown"
        col_types.append({
            "index": c,
            "name": sheet.headers[c],
            "type": dtype,
            "non_null_count": sum(1 for v in vals if v is not None),
        })

    return {
        "file": sheet.path,
        "file_size": sheet.file_size,
        "encoding": sheet.encoding,
        "num_columns": sheet.num_columns,
        "num_data_rows": sheet.num_data_rows,
        "row_limit_exceeded": any(w > 0 for w in sheet.wraps_per_col.values()),
        "wraps": dict(sheet.wraps_per_col),
        "columns": col_types,
        "record_types": {
            _OPCODE_NAME.get(op, f"0x{op:04X}"): cnt
            for op, cnt in sorted(sheet.record_counts.items())
        },
        "warnings": sheet.warnings,
    }


def write_schema(sheet: SheetData, dest: str | Path) -> Path:
    """Write schema JSON to a file."""
    dest = Path(dest)
    dest.write_text(
        json.dumps(schema_json(sheet), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dest


# -- DataFrame helper (lazy import) ---------------------------------------

def _to_df(sheet: SheetData):
    import pandas as pd
    data = {
        sheet.headers[c]: sheet.columns.get(c, [None] * sheet.num_data_rows)
        for c in range(sheet.num_columns)
    }
    return pd.DataFrame(data)


# -- Exporters -------------------------------------------------------------

def to_xlsx(sheet: SheetData, dest: str | Path) -> Path:
    """Write to XLSX (default format).  Requires openpyxl."""
    dest = Path(dest)
    df = _to_df(sheet)
    df.to_excel(str(dest), index=False, engine="openpyxl")
    return dest


def to_csv(sheet: SheetData, dest: str | Path) -> Path:
    """Write to CSV with UTF-8 BOM."""
    dest = Path(dest)
    df = _to_df(sheet)
    df.to_csv(str(dest), index=False, encoding="utf-8-sig")
    return dest


def to_parquet(sheet: SheetData, dest: str | Path) -> Path:
    """Write to Parquet.  Requires pyarrow."""
    dest = Path(dest)
    df = _to_df(sheet)
    df.to_parquet(str(dest), index=False, engine="pyarrow")
    return dest


FORMATS = {
    "xlsx": to_xlsx,
    "csv": to_csv,
    "parquet": to_parquet,
}
