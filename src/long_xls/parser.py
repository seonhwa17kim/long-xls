"""BIFF record parser for overflowed XLS files.

Handles standalone BIFF streams (no OLE2 container) where row indices
wrap around at 65,536.  This is the format produced by programs that
dump cell records without respecting the XLS row limit.

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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

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

# struct format caches for hot path
_UNPACK_HH = struct.Struct("<HH").unpack_from
_UNPACK_D  = struct.Struct("<d").unpack_from
_UNPACK_H  = struct.Struct("<H").unpack_from


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


# -- Progress callback type ------------------------------------------------

ProgressFn = Callable[[int, int], None]
"""progress(current_bytes, total_bytes)"""


def _null_progress(cur: int, total: int) -> None:
    pass


# -- Low-level record iteration --------------------------------------------

def _iter_records(data: bytes) -> Iterator[tuple[int, bytes, int]]:
    """Yield (opcode, payload, offset) for each BIFF record."""
    pos = 0
    end = len(data)
    unpack = _UNPACK_HH
    while pos + 4 <= end:
        opcode, length = unpack(data, pos)
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


# -- Public API -------------------------------------------------------------

def parse(
    path: str | Path,
    encoding: str = "cp949",
    progress: ProgressFn | None = None,
) -> SheetData:
    """Parse a BIFF XLS file and return structured data.

    Parameters
    ----------
    path : file path
    encoding : primary encoding to try for strings (default cp949).
        Falls back through euc-kr, utf-8, latin-1 automatically.
    progress : optional callback(current_bytes, total_bytes) for UI.

    Returns
    -------
    SheetData with headers, column data, and metadata.
    """
    path = Path(path)
    data = path.read_bytes()
    file_size = len(data)
    on_progress = progress or _null_progress

    # Build deduped encoding list
    enc_order: list[str] = []
    seen: set[str] = set()
    for e in (encoding, "cp949", "euc-kr", "utf-8", "latin-1"):
        if e not in seen:
            seen.add(e)
            enc_order.append(e)
    # The "hot" encoding (first successful) will be moved to front
    hot_enc: str | None = None

    # ---- Single-pass parse ------------------------------------------------
    record_counts: dict[int, int] = {}
    headers: dict[int, str] = {}
    col_data: dict[int, list[Any]] = {}
    wraps_per_col: dict[int, int] = {}
    last_raw: dict[int, int] = {}
    actual_encoding = encoding
    header_done = False

    # Local aliases for hot-path speed
    unpack_hh = _UNPACK_HH
    unpack_d = _UNPACK_D
    unpack_h = _UNPACK_H

    pos = 0
    end = file_size
    progress_interval = max(file_size // 50, 65536)  # ~50 updates
    next_progress = progress_interval

    while pos + 4 <= end:
        opcode, length = unpack_hh(data, pos)
        if opcode == 0 and length == 0:
            break
        payload_start = pos + 4
        payload_end = payload_start + length
        if payload_end > end:
            break

        # Count every record type
        record_counts[opcode] = record_counts.get(opcode, 0) + 1

        # Progress callback
        if pos >= next_progress:
            on_progress(pos, file_size)
            next_progress = pos + progress_interval

        # Skip non-cell records
        if opcode not in CELL_OPCODES or length < 7:
            pos = payload_end
            continue

        raw_row, col = unpack_hh(data, payload_start)

        # Wrap-around detection
        prev = last_raw.get(col)
        if prev is not None and raw_row < prev:
            wraps_per_col[col] = wraps_per_col.get(col, 0) + 1
        last_raw[col] = raw_row

        # Decode value
        val: Any = None
        enc_used = ""

        if opcode == LABEL:
            str_len = data[payload_start + 7]
            raw_str = data[payload_start + 8: payload_start + 8 + str_len]
            # Hot encoding path: try last successful encoding first
            if hot_enc:
                try:
                    val = raw_str.decode(hot_enc)
                    enc_used = hot_enc
                except (UnicodeDecodeError, LookupError):
                    val, enc_used = _try_decode(raw_str, tuple(enc_order))
                    hot_enc = enc_used
            else:
                val, enc_used = _try_decode(raw_str, tuple(enc_order))
                hot_enc = enc_used

        elif opcode == NUMBER:
            if length < 15:
                pos = payload_end
                continue
            val = unpack_d(data, payload_start + 7)[0]
            if math.isfinite(val) and val == int(val) and abs(val) < 2**53:
                val = int(val)

        elif opcode == INTEGER:
            if length < 9:
                pos = payload_end
                continue
            val = unpack_h(data, payload_start + 7)[0]

        # Header vs data
        if not header_done and raw_row == 0 and wraps_per_col.get(col, 0) == 0:
            headers[col] = str(val) if val is not None else f"col{col}"
        else:
            if not header_done:
                header_done = True
            col_data.setdefault(col, []).append(val)

        pos = payload_end

    # Final progress
    on_progress(file_size, file_size)

    # ---- Assemble result --------------------------------------------------
    num_cols = max(len(headers), len(col_data), 0)
    if num_cols == 0:
        return SheetData(
            path=str(path), file_size=file_size, headers=[], columns={},
            num_data_rows=0, num_columns=0, wraps_per_col={},
            record_counts=record_counts, encoding=actual_encoding,
            warnings=["No cell data found"],
        )

    if enc_used:
        actual_encoding = enc_used

    header_list = [headers.get(c, f"col{c}") for c in range(num_cols)]

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


def parse_to_dataframe(
    path: str | Path,
    encoding: str = "cp949",
    progress: ProgressFn | None = None,
):
    """Parse and return a pandas DataFrame directly."""
    import pandas as pd

    sheet = parse(path, encoding, progress=progress)
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
            raw_row = _UNPACK_H(payload, 0)[0]
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
