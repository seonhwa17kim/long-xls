"""Tests for long-xls parser using generated synthetic XLS files."""

import math
from pathlib import Path

import pytest

from long_xls.parser import parse, scan

FIXTURES = Path(__file__).parent / "fixtures"


# -- Helpers ---------------------------------------------------------------

def _ensure_fixtures():
    """Generate test fixtures if they don't exist."""
    if not (FIXTURES / "test_100k_rows.xls").exists():
        from tests.generate_test_xls import generate_long_xls, generate_encodings_test
        generate_long_xls(FIXTURES / "test_100k_rows.xls", num_rows=100_000)
        generate_long_xls(FIXTURES / "test_200k_rows.xls", num_rows=200_000)
        generate_encodings_test(FIXTURES / "test_70k_cp949.xls")


@pytest.fixture(autouse=True, scope="session")
def fixtures():
    _ensure_fixtures()


# -- Tests -----------------------------------------------------------------

class TestParse100k:
    def test_row_count(self):
        sheet = parse(FIXTURES / "test_100k_rows.xls", encoding="utf-8")
        assert sheet.num_data_rows == 100_000

    def test_column_count(self):
        sheet = parse(FIXTURES / "test_100k_rows.xls", encoding="utf-8")
        assert sheet.num_columns == 3

    def test_headers(self):
        sheet = parse(FIXTURES / "test_100k_rows.xls", encoding="utf-8")
        assert sheet.headers == ["id", "name", "value"]

    def test_wraps(self):
        sheet = parse(FIXTURES / "test_100k_rows.xls", encoding="utf-8")
        assert any(w > 0 for w in sheet.wraps_per_col.values())

    def test_first_row(self):
        sheet = parse(FIXTURES / "test_100k_rows.xls", encoding="utf-8")
        assert sheet.columns[0][0] == 1        # id
        assert sheet.columns[1][0] == "row_00001"  # name
        assert sheet.columns[2][0] == 1.5       # value

    def test_last_row(self):
        sheet = parse(FIXTURES / "test_100k_rows.xls", encoding="utf-8")
        assert sheet.columns[0][-1] == 100_000
        assert sheet.columns[1][-1] == "row_100000"
        assert math.isclose(sheet.columns[2][-1], 150_000.0)

    def test_wrap_boundary(self):
        """Row 65536 (index 65535) should be correctly recovered."""
        sheet = parse(FIXTURES / "test_100k_rows.xls", encoding="utf-8")
        idx = 65536 - 1  # data row 65536 = index 65535
        assert sheet.columns[0][idx] == 65536
        assert sheet.columns[1][idx] == "row_65536"

    def test_no_warnings(self):
        sheet = parse(FIXTURES / "test_100k_rows.xls", encoding="utf-8")
        assert sheet.warnings == []


class TestParse200k:
    def test_row_count(self):
        sheet = parse(FIXTURES / "test_200k_rows.xls", encoding="utf-8")
        assert sheet.num_data_rows == 200_000

    def test_three_wraps(self):
        sheet = parse(FIXTURES / "test_200k_rows.xls", encoding="utf-8")
        # 200000 rows -> wraps at 65536, 131072, 196608
        assert max(sheet.wraps_per_col.values()) == 3


class TestParse70kCP949:
    def test_row_count(self):
        sheet = parse(FIXTURES / "test_70k_cp949.xls", encoding="cp949")
        assert sheet.num_data_rows == 70_000

    def test_one_wrap(self):
        sheet = parse(FIXTURES / "test_70k_cp949.xls", encoding="cp949")
        assert max(sheet.wraps_per_col.values()) == 1


class TestScan:
    def test_scan_100k(self):
        info = scan(FIXTURES / "test_100k_rows.xls")
        assert info["records_total"] > 0
        assert "LABEL" in info["record_types"]
        assert "NUMBER" in info["record_types"]
