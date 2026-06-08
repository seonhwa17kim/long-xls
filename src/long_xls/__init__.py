"""long-xls: Recover data from XLS files that exceed the 65,536-row limit."""

__version__ = "0.1.1"

from long_xls.parser import parse, parse_to_dataframe, scan
from long_xls.export import to_xlsx, to_csv, to_parquet, schema_json

__all__ = [
    "parse",
    "parse_to_dataframe",
    "scan",
    "to_xlsx",
    "to_csv",
    "to_parquet",
    "schema_json",
]
