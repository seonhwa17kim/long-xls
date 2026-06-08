#!/usr/bin/env python3
"""Generate synthetic long-XLS test files for testing long-xls.

Creates BIFF2-style standalone XLS files with more than 65,536 rows,
mimicking the behaviour of programs that write past the row limit.

The generated files use column-major order (all col0, then all col1, ...)
with row indices wrapping at 65,536 — exactly the structure long-xls
is designed to recover.
"""

import struct
from pathlib import Path

# BIFF opcodes
BOF       = 0x0809
EOF       = 0x000A
DIMENSIONS = 0x0200
LABEL     = 0x0004
NUMBER    = 0x0003


def _write_record(f, opcode: int, payload: bytes):
    f.write(struct.pack("<HH", opcode, len(payload)))
    f.write(payload)


def _write_bof(f):
    # BOF: version=0x0200, type=0x0010 (worksheet)
    _write_record(f, BOF, b"\x00\x02\x10\x00\x00\x00")


def _write_dimensions(f):
    # DIMENSIONS placeholder (10 bytes of zeros — not actually read by long-xls)
    _write_record(f, DIMENSIONS, b"\x00" * 10)


def _write_eof(f):
    _write_record(f, EOF, b"")


def _write_label(f, row: int, col: int, text: str, encoding: str = "utf-8"):
    raw = text.encode(encoding)
    # BIFF2 LABEL: row(2) + col(2) + attr(3) + strlen(1) + string
    payload = struct.pack("<HH3sB", row & 0xFFFF, col, b"\x00\x00\x00", len(raw))
    payload += raw
    _write_record(f, LABEL, payload)


def _write_number(f, row: int, col: int, value: float):
    # BIFF2 NUMBER: row(2) + col(2) + attr(3) + double(8)
    payload = struct.pack("<HH3sd", row & 0xFFFF, col, b"\x00\x00\x00", value)
    _write_record(f, NUMBER, payload)


def generate_long_xls(
    path: str | Path,
    num_rows: int = 100_000,
    encoding: str = "utf-8",
):
    """Generate a test XLS file with column-major BIFF2 records.

    Schema: id (int), name (string), value (float)
    Storage order: header row → col0 all rows → col1 all rows → col2 all rows
    Row indices wrap at 65536 just like real-world long XLS files.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    headers = ["id", "name", "value"]

    with open(path, "wb") as f:
        _write_bof(f)
        _write_dimensions(f)

        # Header row (row 0, all columns)
        for col_idx, name in enumerate(headers):
            _write_label(f, 0, col_idx, name, encoding)

        # Column 0: id (NUMBER) — sequential integer
        for i in range(1, num_rows + 1):
            _write_number(f, i, 0, float(i))

        # Column 1: name (LABEL) — "row_NNNNN"
        for i in range(1, num_rows + 1):
            _write_label(f, i, 1, f"row_{i:05d}", encoding)

        # Column 2: value (NUMBER) — i * 1.5
        for i in range(1, num_rows + 1):
            _write_number(f, i, 2, i * 1.5)

        _write_eof(f)

    print(f"Generated: {path} ({path.stat().st_size:,} bytes)")
    print(f"  {num_rows:,} data rows, {len(headers)} columns")
    print(f"  Wraps: {num_rows // 65536}")
    return path


def generate_encodings_test(path: str | Path):
    """Generate a small long-XLS with CP949-encoded strings."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "wb") as f:
        _write_bof(f)
        _write_dimensions(f)

        # Headers in Korean
        headers_kr = ["번호", "이름", "값"]
        for col_idx, name in enumerate(headers_kr):
            _write_label(f, 0, col_idx, name, "cp949")

        num_rows = 70_000  # just over 1 wrap
        for i in range(1, num_rows + 1):
            _write_number(f, i, 0, float(i))
        for i in range(1, num_rows + 1):
            _write_label(f, i, 1, f"항목_{i}", "cp949")
        for i in range(1, num_rows + 1):
            _write_number(f, i, 2, i * 0.01)

        _write_eof(f)

    print(f"Generated: {path} ({path.stat().st_size:,} bytes)")
    print(f"  {num_rows:,} data rows (CP949 encoding)")


if __name__ == "__main__":
    out_dir = Path(__file__).parent / "fixtures"

    # Test 1: 100k rows, UTF-8
    generate_long_xls(out_dir / "test_100k_rows.xls", num_rows=100_000)

    # Test 2: 200k rows
    generate_long_xls(out_dir / "test_200k_rows.xls", num_rows=200_000)

    # Test 3: CP949 encoded, 70k rows (just over 1 wrap)
    generate_encodings_test(out_dir / "test_70k_cp949.xls")

    print("\nAll test fixtures generated.")
