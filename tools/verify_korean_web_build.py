#!/usr/bin/env python3
"""Verify the files produced by the Korean Godot Web export."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


HANGUL_RE = re.compile(r"[가-힣]")
UNRESOLVED_TEMPLATE_RE = re.compile(r"\$GODOT_[A-Z_]+|%url%")
MAX_RECOMMENDED_FILE_SIZE = 25 * 1024 * 1024
REQUIRED_OUTPUT_FILES = (
    "LICENSE",
    "NotoSansKR-LICENSE.txt",
    "KOREAN-EDITION.md",
)


class HtmlReferenceParser(HTMLParser):
    """Collect local asset references from an exported HTML entrypoint."""

    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.references.append(value)


def _is_remote_reference(value: str) -> bool:
    scheme = urlsplit(value).scheme.lower()
    return scheme in {
        "data",
        "http",
        "https",
        "mailto",
        "javascript",
    } or value.startswith("//")


def _check_local_references(build_dir: Path, references: list[str]) -> list[str]:
    errors: list[str] = []
    for reference in references:
        if _is_remote_reference(reference) or reference.startswith("#"):
            continue

        if reference.startswith("/"):
            errors.append(
                f"root-relative asset reference is not portable: {reference}"
            )
            continue

        relative_path = unquote(urlsplit(reference).path)
        candidate = (build_dir / relative_path).resolve()
        try:
            candidate.relative_to(build_dir.resolve())
        except ValueError:
            errors.append(f"asset reference escapes the build directory: {reference}")
            continue
        if not candidate.is_file():
            errors.append(f"missing local asset: {reference}")
    return errors


def _file_inventory(build_dir: Path) -> tuple[list[dict[str, int | str]], list[str]]:
    files: list[dict[str, int | str]] = []
    warnings: list[str] = []
    for path in sorted(build_dir.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        relative = path.relative_to(build_dir).as_posix()
        files.append({"path": relative, "bytes": size})
        if size > MAX_RECOMMENDED_FILE_SIZE:
            warnings.append(
                f"{relative} is larger than 25 MiB ({size / 1024 / 1024:.1f} MiB)"
            )
    return files, warnings


def _configured_godot_version() -> str:
    version = os.environ.get("GODOT_VERSION", "")
    if version:
        return version
    env_path = Path(".env")
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "GODOT_VERSION":
            return value.strip().strip('"').strip("'")
    return ""


def verify(build_dir: Path, source_commit: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    index_path = build_dir / "index.html"

    if not index_path.is_file():
        errors.append("index.html is missing")
        if build_dir.is_dir():
            files, inventory_warnings = _file_inventory(build_dir)
        else:
            files, inventory_warnings = [], []
    else:
        html = index_path.read_text(encoding="utf-8")
        parser = HtmlReferenceParser()
        parser.feed(html)
        errors.extend(_check_local_references(build_dir, parser.references))
        if 'lang="ko"' not in html and "lang='ko'" not in html:
            errors.append("index.html does not declare lang=ko")
        if not HANGUL_RE.search(html):
            errors.append("index.html does not contain Korean user-facing text")
        unresolved = UNRESOLVED_TEMPLATE_RE.findall(html)
        if unresolved:
            errors.append(f"unresolved export template tokens: {sorted(set(unresolved))}")
        if "GDQUEST_ENVIRONMENT = {};" in html:
            errors.append("GDQUEST_ENVIRONMENT was not populated by the export")
        files, inventory_warnings = _file_inventory(build_dir)

        bootstrap_path = build_dir / "bootstrap.js"
        if bootstrap_path.is_file():
            bootstrap = bootstrap_path.read_text(encoding="utf-8")
            if "WebGL을 사용할 수 없습니다" not in bootstrap:
                errors.append("bootstrap.js does not contain the Korean WebGL notice")

    warnings.extend(inventory_warnings)
    for required_file in REQUIRED_OUTPUT_FILES:
        if not (build_dir / required_file).is_file():
            errors.append(f"required attribution file is missing: {required_file}")
    suffixes = {path.suffix for path in build_dir.rglob("*") if path.is_file()}
    for suffix in (".js", ".wasm", ".pck"):
        if suffix not in suffixes:
            errors.append(f"exported Web build has no {suffix} file")

    total_bytes = sum(int(item["bytes"]) for item in files)
    return {
        "ok": not errors,
        "language": "ko",
        "source_commit": source_commit,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "godot_version": _configured_godot_version(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--report-json", type=Path, default=None)
    args = parser.parse_args()

    report = verify(args.build_dir, args.source_commit)
    build_info_path = args.build_dir / "build-info.json"
    if args.build_dir.is_dir():
        build_info_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    for warning in report["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in report["errors"]:
        print(f"ERROR: {error}", file=sys.stderr)
    if report["ok"]:
        print(
            f"Korean Web build verified: {report['file_count']} files, "
            f"{report['total_bytes'] / 1024 / 1024:.1f} MiB"
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
