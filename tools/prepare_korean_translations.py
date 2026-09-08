#!/usr/bin/env python3
"""Validate and materialize the private Korean catalogs into a CI checkout."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from validate_korean_translations import (
    CATALOG_NAMES,
    print_report,
    validate_catalogs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("localization/ko"))
    parser.add_argument("--reference-dir", type=Path, default=Path("i18n/ko"))
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=None,
        help="Disposable checkout directory to receive validated PO files.",
    )
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    preserved_path = args.source_dir.parent / "preserved-strings.json"
    report = validate_catalogs(
        args.source_dir,
        args.reference_dir,
        preserved_path,
    )
    print_report(report)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if report["errors"]:
        print("Private Korean catalogs were not materialized.", file=sys.stderr)
        return 1
    if args.target_dir is None:
        print("Validation passed; no target directory was requested.")
        return 0
    if args.target_dir.resolve() == args.source_dir.resolve():
        print("ERROR: target directory must differ from source directory.", file=sys.stderr)
        return 2

    args.target_dir.mkdir(parents=True, exist_ok=True)
    for name in CATALOG_NAMES:
        target = args.target_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.source_dir / name, target)
    print(f"Materialized {len(CATALOG_NAMES)} Korean catalogs into {args.target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
