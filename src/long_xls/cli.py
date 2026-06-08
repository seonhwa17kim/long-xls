"""Command-line interface for long-xls."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from long_xls import __version__
from long_xls.parser import parse, scan
from long_xls.export import FORMATS, schema_json, write_schema


def _size_str(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    else:
        return f"{n / (1024 * 1024):.1f} MB"


# -- Progress bar ----------------------------------------------------------

_BAR_WIDTH = 30


def _make_progress(label: str, t0: float):
    """Return a progress callback that draws a bar to stderr."""
    last_pct = [-1]  # mutable closure

    def _progress(cur: int, total: int) -> None:
        if total == 0:
            return
        pct = min(cur * 100 // total, 100)
        if pct == last_pct[0]:
            return
        last_pct[0] = pct
        filled = _BAR_WIDTH * pct // 100
        bar = "#" * filled + "-" * (_BAR_WIDTH - filled)
        elapsed = time.perf_counter() - t0
        sys.stderr.write(f"\r  {label} [{bar}] {pct:3d}%  {elapsed:.1f}s")
        sys.stderr.flush()
        if pct >= 100:
            sys.stderr.write("\n")
            sys.stderr.flush()

    return _progress


# -- File conflict resolution ----------------------------------------------

def _resolve_output_path(out_path: Path, force: bool) -> Path | None:
    """Handle existing output file.

    Returns the path to write to, or None to skip.
    With --force, always overwrites without asking.
    """
    if not out_path.exists():
        return out_path

    if force:
        return out_path

    # Interactive prompt
    print(f"\n  File already exists: {out_path}")
    print(f"    [o] Overwrite")
    print(f"    [r] Rename (add number suffix)")
    print(f"    [s] Skip")
    while True:
        try:
            choice = input("  Choice [o/r/s]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if choice == "o":
            return out_path
        elif choice == "r":
            return _numbered_path(out_path)
        elif choice == "s":
            return None
        else:
            print("    Please enter o, r, or s.")


def _numbered_path(p: Path) -> Path:
    """Return path with (2), (3), ... suffix before extension."""
    stem = p.stem
    ext = p.suffix
    parent = p.parent
    n = 2
    while True:
        candidate = parent / f"{stem} ({n}){ext}"
        if not candidate.exists():
            return candidate
        n += 1


# -- Commands --------------------------------------------------------------

def _run_convert(args: argparse.Namespace) -> int:
    files = args.files
    if not files:
        print("Error: no input files", file=sys.stderr)
        return 1

    fmt = args.format
    exporter = FORMATS.get(fmt)
    if exporter is None:
        print(f"Error: unknown format '{fmt}'", file=sys.stderr)
        return 1

    force = getattr(args, "force", False)

    for fpath in files:
        p = Path(fpath)
        if not p.is_file():
            print(f"Error: not a file: {p}", file=sys.stderr)
            continue

        print(f"Parsing {p.name} ({_size_str(p.stat().st_size)}) ...")
        t0 = time.perf_counter()
        progress_read = _make_progress("Reading", t0)
        sheet = parse(p, encoding=args.encoding, progress=progress_read)

        # Overflow info
        max_wraps = max(sheet.wraps_per_col.values()) if sheet.wraps_per_col else 0
        if max_wraps > 0:
            print(f"  Row overflow detected: {max_wraps} wrap(s) recovered")
        print(f"  {sheet.num_data_rows:,} rows x {sheet.num_columns} columns")

        # Output directory
        out_dir = Path(args.output_dir) if args.output_dir else p.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        # Schema
        if args.schema:
            schema_dest = out_dir / f"{p.stem}.schema.json"
            schema_dest = _resolve_output_path(schema_dest, force)
            if schema_dest:
                write_schema(sheet, schema_dest)
                print(f"  -> {schema_dest} ({_size_str(schema_dest.stat().st_size)})")

        # Export
        out_path = out_dir / f"{p.stem}.{fmt}"
        out_path = _resolve_output_path(out_path, force)
        if out_path is None:
            print("  Skipped.")
            continue

        t_write = time.perf_counter()
        progress_write = _make_progress(f"Writing {fmt.upper()}", t_write)
        exporter(sheet, out_path, progress=progress_write)
        elapsed_total = time.perf_counter() - t0
        print(f"  -> {out_path} ({_size_str(out_path.stat().st_size)})  [{elapsed_total:.1f}s total]")

        if sheet.warnings:
            for w in sheet.warnings:
                print(f"  Warning: {w}")

    return 0


def _run_schema(args: argparse.Namespace) -> int:
    for fpath in args.files:
        p = Path(fpath)
        if not p.is_file():
            print(f"Error: not a file: {p}", file=sys.stderr)
            continue
        sheet = parse(p, encoding=args.encoding)
        print(json.dumps(schema_json(sheet), ensure_ascii=False, indent=2))
    return 0


def _run_scan(args: argparse.Namespace) -> int:
    for fpath in args.files:
        p = Path(fpath)
        if not p.is_file():
            print(f"Error: not a file: {p}", file=sys.stderr)
            continue
        info = scan(p)
        print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="long-xls",
        description="Recover data from XLS files that exceed the 65,536-row limit.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    # -- convert (default) --
    p_conv = sub.add_parser(
        "convert", help="Convert XLS to xlsx/csv/parquet (default command)",
    )
    p_conv.add_argument("files", nargs="+", help="Input .xls file(s)")
    p_conv.add_argument(
        "-f", "--format", default="xlsx",
        choices=sorted(FORMATS),
        help="Output format (default: xlsx)",
    )
    p_conv.add_argument("-o", "--output-dir", help="Output directory (default: same as input)")
    p_conv.add_argument("-e", "--encoding", default="cp949", help="Text encoding (default: cp949)")
    p_conv.add_argument(
        "--schema", action="store_true",
        help="Also write a .schema.json file alongside the output",
    )
    p_conv.add_argument(
        "-y", "--force", action="store_true",
        help="Overwrite existing files without asking",
    )
    p_conv.set_defaults(func=_run_convert)

    # -- schema --
    p_schema = sub.add_parser("schema", help="Print JSON schema to stdout")
    p_schema.add_argument("files", nargs="+", help="Input .xls file(s)")
    p_schema.add_argument("-e", "--encoding", default="cp949")
    p_schema.set_defaults(func=_run_schema)

    # -- scan --
    p_scan = sub.add_parser("scan", help="Quick file scan (record counts, no full parse)")
    p_scan.add_argument("files", nargs="+", help="Input .xls file(s)")
    p_scan.set_defaults(func=_run_scan)

    # If first arg looks like a file (not a known subcommand), inject "convert"
    raw_argv = argv if argv is not None else sys.argv[1:]
    known_commands = {"convert", "schema", "scan"}
    if raw_argv and raw_argv[0] not in known_commands and not raw_argv[0].startswith("-"):
        raw_argv = ["convert"] + list(raw_argv)

    args = parser.parse_args(raw_argv)

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
