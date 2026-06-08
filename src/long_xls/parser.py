"""BIFF record parser for overflowed XLS files.

Handles standalone BIFF streams (no OLE2 container) where row indices
wrap around at 65,536.  This is the format produced by programs like
Kiwoom HTS that dump cell records without respecting the XLS row limit.

Binary layout observed
----------------------
- BOF  0x0809  (6 bytes payload)
- DIMENSIONS 0x0200
- Cell records in **column-major** order:
    header row (row 0, all columns) -> col 0 data -> col 1 data -> ...
- Each column's data wraps row index at 65,536 boundaries.
- LABEL 0x0004: row(2) col(2) attr(3) strlen(1) bytes(n)
- NUMBER 0x0003: row(2) col(2) attr(3) double(8)
- INTEGER 0x0002: row(2) col(2) attr(3) uint16(2)
- EOF 0x000A
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# -- BIFF opcodes ----------------------------------------------------------

BOF       = 0x0809
EOF       = 0x000A
DIMENSIONS = 0x0200
LABEL     = 0x0004  # BIFF2 string
NUMBER    = 0x0003  # BIFF2 IEEE-754 double
INTEGER   = 0x0002  # BIFF2 16-bit unsigned int

_OPCODE_NAME = {
    BOF: "BOF", EOF: "EOF", DIMENSIONS: "DIMENSIONS",
    LABEL: "LABEL", NUMBER: "NUMBER", INTEGER: "INTEGER",
}

CELL_OPCODES = frozenset({LABEL, NUMBER, INTEGER})

ROW_LIMIT = 65_536  # wrap boundary


# -- Data containers -------------------------------------------------------

@dataclass(frozen=True)
class Cell:
    """One decoded cell with its logical (unwrapped) row index."""
    logical_row: int
    col: int
    value: Any          # str | int | float | None
    opcode: int


@dataclass
class SheetData:
    """Complete parsed result for one sheet / file."""
    path: str
    file_size: int
    headers: list[str]
    columns: dict[int, list[Any]]   # col_index -> [values]
    num_data_rows: int
    num_columns: int
    wraps_per_col: dict[int, int]   # col_index -> wrap count
    record_counts: dict[int, int]   # opcode -> count
    encoding: str
    warnings: list[str] = field(default_factory=list)


# -- Low-level record iteration --------------------------------------------

def _iter_records(data: bytes) -> Iterator[tuple[int, bytes, int]]:
    """Yield (opcode, payload, offset) for each BIFF record."""
    pos = 0
    end = len(data)
    while pos + 4 <= end:
        opcode, length = struct.unpack_from("<HH", data, pos)
        if opcode == 0 and length == 0:
            break
        payload_end = pos + 4 + length
        if payload_end > end:
            yield opcode, data[pos + 4:end], pos
            break
        yield opcode, data[pos + 4:payload_end], pos
        pos = payload_end


def _try_decode(raw: bytes, encodings: tuple[str, ...]) -> tuple[str, str]:
    """Try decoding *raw* with each encoding; return (text, encoding_used)."""
    for enc in encodings:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.hex(), "hex"


# -- Cell iteration with wrap tracking -------------------------------------

def _iter_cells(
    data: bytes,
    encodings: tuple[str, ...] = ("cp949", "euc-kr", "utf-8", "latin-1"),
) -> Iterator[tuple[Cell, str]]:
    """Yield (Cell, encoding_used) with logical rows that account for wraps."""
    last_raw: dict[int, int] = {}     # col -> last raw row seen
    wraps: dict[int, int] = {}        # col -> wrap count

    for opcode, payload, _offset in _iter_records(data):
        if opcode not in CELL_OPCODES or len(payload) < 7:
            continue

        raw_row, col = struct.unpack_from("<HH", payload, 0)

        # Detect wrap-around
        prev = last_raw.get(col)
        if prev is not None and raw_row < prev:
            wraps[col] = wraps.get(col, 0) + 1
        last_raw[col] = raw_row

        logical_row = raw_row + wraps.get(col, 0) * ROW_LIMIT

        enc_used = ""
        if opcode == LABEL:
            str_len = payload[7]
            text, enc_used = _try_decode(payload[8:8 + str_len], encodings)
            yield Cell(logical_row, col, text, opcode), enc_used

        elif opcode == NUMBER:
            if len(payload) < 15:
                continue
            val = struct.unpack_from("<d", payload, 7)[0]
            if math.isfinite(val) and val == int(val) and abs(val) < 2**53:
                val = int(val)
            yield Cell(logical_row, col, val, opcode), ""

        elif opcode == INTEGER:
            if len(payload) < 9:
                continue
            val = struct.unpack_from("<H", payload, 7)[0]
            yield Cell(logical_row, col, val, opcode), ""


# -- Public API -------------------------------------------------------------

def parse(
    path: str | Path,
    encoding: str = "cp949",
) -> SheetData:
    """Parse a BIFF XLS file and return structured data.

    Parameters
    ----------
    path : file path
    encoding : primary encoding to try for strings (default cp949).
        Falls back through euc-kr, utf-8, latin-1 automatically.

    Returns
    -------
    SheetData with headers, column data, and metadata.
    """
    path = Path(path)
    data = path.read_bytes()
    file_size = len(data)

    encodings = (encoding, "cp949", "euc-kr", "utf-8", "latin-1")
    # deduplicate while keeping order
    seen: set[str] = set()
    enc_list: list[str] = []
    for e in encodings:
        if e not in seen:
            seen.add(e)
            enc_list.append(e)
    enc_tuple = tuple(enc_list)

    # Count records
    record_counts: dict[int, int] = {}
    for opcode, _payload, _off in _iter_records(data):
        record_counts[opcode] = record_counts.get(opcode, 0) + 1

    # Parse cells
    headers: dict[int, str] = {}
    col_data: dict[int, list[Any]] = {}
    wraps_per_col: dict[int, int] = {}
    last_raw: dict[int, int] = {}
    actual_encoding = encoding
    header_done = False

    for cell, enc_used in _iter_cells(data, enc_tuple):
        if enc_used:
            actual_encoding = enc_used

        if not header_done and cell.logical_row == 0:
            headers[cell.col] = str(cell.value) if cell.value is not None else f"col{cell.col}"
            continue

        if not header_done and cell.logical_row != 0:
            header_done = True

        col_data.setdefault(cell.col, []).append(cell.value)

        # Track wraps
        raw_row = cell.logical_row % ROW_LIMIT
        prev = last_raw.get(cell.col)
        if prev is not None and raw_row < prev:
            wraps_per_col[cell.col] = wraps_per_col.get(cell.col, 0) + 1
        last_raw[cell.col] = raw_row

    num_cols = max(len(headers), len(col_data), 0)
    if num_cols == 0:
        return SheetData(
            path=str(path), file_size=file_size, headers=[], columns={},
            num_data_rows=0, num_columns=0, wraps_per_col={},
            record_counts=record_counts, encoding=actual_encoding,
            warnings=["No cell data found"],
        )

    # Ensure headers list is ordered
    header_list = [headers.get(c, f"col{c}") for c in range(num_cols)]

    # Align column lengths
    warnings: list[str] = []
    lengths = {c: len(v) for c, v in col_data.items()}
    max_len = max(lengths.values()) if lengths else 0
    if len(set(lengths.values())) > 1:
        warnings.append(f"Column length mismatch: {lengths}")
        for c in col_data:
            if len(col_data[c]) < max_len:
                col_data[c].extend([None] * (max_len - len(col_data[c])))

    return SheetData(
        path=str(path),
        file_size=file_size,
        headers=header_list,
        columns=col_data,
        num_data_rows=max_len,
        num_columns=num_cols,
        wraps_per_col=wraps_per_col,
        record_counts=record_counts,
        encoding=actual_encoding,
        warnings=warnings,
    )


def parse_to_dataframe(path: str | Path, encoding: str = "cp949"):
    """Parse and return a pandas DataFrame directly."""
    import pandas as pd

    sheet = parse(path, encoding)
    data = {
        sheet.headers[c]: sheet.columns.get(c, [None] * sheet.num_data_rows)
        for c in range(sheet.num_columns)
    }
    return pd.DataFrame(data), sheet


def scan(path: str | Path) -> dict[str, Any]:
    """Quick scan: return file metadata without building full column data."""
    path = Path(path)
    data = path.read_bytes()

    record_counts: dict[int, int] = {}
    row_range: dict[int, tuple[int, int, int]] = {}  # opcode -> (min, max, count)

    for opcode, payload, _off in _iter_records(data):
        record_counts[opcode] = record_counts.get(opcode, 0) + 1
        if opcode in CELL_OPCODES and len(payload) >= 4:
            raw_row = struct.unpack_from("<H", payload, 0)[0]
            if opcode in row_range:
                lo, hi, cnt = row_range[opcode]
                row_range[opcode] = (min(lo, raw_row), max(hi, raw_row), cnt + 1)
            else:
                row_range[opcode] = (raw_row, raw_row, 1)

    return {
        "path": str(path),
        "size": len(data),
        "records_total": sum(record_counts.values()),
        "record_types": {
            _OPCODE_NAME.get(op, f"0x{op:04X}"): cnt
            for op, cnt in sorted(record_counts.items())
        },
        "cell_ranges": {
            _OPCODE_NAME.get(op, f"0x{op:04X}"): {
                "raw_row_min": lo, "raw_row_max": hi, "count": cnt,
            }
            for op, (lo, hi, cnt) in sorted(row_range.items())
        },
    }
