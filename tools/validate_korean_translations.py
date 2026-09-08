#!/usr/bin/env python3
"""Validate the private Korean PO catalogs against the checked-out source catalogs.

The validator intentionally has no default write target. A CI job can opt into
materializing the validated catalogs into a disposable checkout with
prepare_korean_translations.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


CATALOG_NAMES = ("application.po", "course.po", "supplementary.po")
HANGUL_RE = re.compile(r"[가-힣]")
TAG_RE = re.compile(r"\[[^\[\]]+\]")
CODE_BLOCK_RE = re.compile(r"\[code\](.*?)\[/code\]", re.DOTALL)
PLACEHOLDER_RE = re.compile(r"%(?:\d+\$)?[a-zA-Z]")
BRACED_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_.-]*\}")
GLOSSARY_TERM_RE = re.compile(r'\[glossary\s+term="([^"]+)"\]')
URL_TARGET_RE = re.compile(r"\[url=([^\]]+)\]")
TECHNICAL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z_][A-Za-z0-9_]+_[A-Za-z0-9_]+|"
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\([^()\n]*\))"
    r"(?![A-Za-z0-9_])"
)
CODEISH_RE = re.compile(r"^[\sA-Za-z0-9_.,:()=+*/<>\[\]-]+$")


@dataclass(frozen=True)
class Message:
    context: str
    msgid: str
    msgstr: str
    flags: frozenset[str]

    @property
    def key(self) -> tuple[str, str]:
        return self.context, self.msgid


def _message_id(message_id: object) -> str:
    """Return the singular message id for Babel and polib message objects."""
    if isinstance(message_id, tuple):
        return str(message_id[0])
    return str(message_id)


def _load_with_babel(path: Path) -> list[Message]:
    from babel.messages.pofile import read_po

    with path.open("rb") as handle:
        catalog = read_po(handle, locale="ko")

    messages: list[Message] = []
    for message in catalog:
        msgid = _message_id(message.id)
        if not msgid:
            continue
        value = message.string
        if isinstance(value, tuple):
            value = value[0]
        messages.append(
            Message(
                context=message.context or "",
                msgid=msgid,
                msgstr=str(value or ""),
                flags=frozenset(message.flags),
            )
        )
    return messages


def _load_with_polib(path: Path) -> list[Message]:
    import polib

    messages: list[Message] = []
    for message in polib.pofile(str(path)):
        if not message.msgid:
            continue
        messages.append(
            Message(
                context=message.msgctxt or "",
                msgid=message.msgid,
                msgstr=message.msgstr or "",
                flags=frozenset(message.flags),
            )
        )
    return messages


def load_catalog(path: Path) -> dict[tuple[str, str], Message]:
    """Parse one catalog, preferring Babel as required by the project."""
    try:
        messages = _load_with_babel(path)
    except ImportError:
        try:
            messages = _load_with_polib(path)
        except ImportError as error:
            raise RuntimeError(
                "Babel is required to validate PO files. Install requirements.txt."
            ) from error
    except Exception as error:
        raise RuntimeError(f"Could not parse {path}: {error}") from error

    return {message.key: message for message in messages}


def load_preserved_strings(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")

    preserved: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict) or "msgid" not in item:
            raise ValueError(f"{path} contains an invalid preserved string")
        preserved.add((str(item.get("msgctxt", "")), str(item["msgid"])))
    return preserved


def _signature(text: str) -> dict[str, Counter[str]]:
    text_without_code_blocks = CODE_BLOCK_RE.sub("", text)
    return {
        "tags": Counter(TAG_RE.findall(text)),
        "code": Counter(CODE_BLOCK_RE.findall(text)),
        "placeholders": Counter(PLACEHOLDER_RE.findall(text)),
        "braced_placeholders": Counter(BRACED_PLACEHOLDER_RE.findall(text)),
        "glossary_terms": Counter(GLOSSARY_TERM_RE.findall(text)),
        "url_targets": Counter(URL_TARGET_RE.findall(text)),
        "technical_tokens": Counter(
            TECHNICAL_TOKEN_RE.findall(text_without_code_blocks)
        ),
    }


def _structure_errors(source: str, translation: str) -> list[str]:
    source_signature = _signature(source)
    translation_signature = _signature(translation)
    errors: list[str] = []
    for name, expected in source_signature.items():
        actual = translation_signature[name]
        if actual != expected:
            errors.append(f"{name} changed (expected {expected!r}, got {actual!r})")
    return errors


def _requires_hangul(msgid: str) -> bool:
    """Identify ordinary prose without rejecting code, punctuation, or URLs."""
    if not re.search(r"[A-Za-z]{2,}", msgid):
        return False
    if CODEISH_RE.fullmatch(msgid):
        return False
    if msgid.startswith("[code]") and msgid.endswith("[/code]"):
        return False
    if "\n" in msgid and not re.search(r"[.!?]\s", msgid):
        return False
    return True


def validate_catalogs(
    source_dir: Path,
    reference_dir: Path,
    preserved_path: Path,
    *,
    allow_incomplete: bool = False,
) -> dict:
    preserved = load_preserved_strings(preserved_path)
    errors: list[str] = []
    warnings: list[str] = []
    files: dict[str, dict] = {}

    for name in CATALOG_NAMES:
        source_path = source_dir / name
        reference_path = reference_dir / name
        if not source_path.exists():
            errors.append(f"Missing private catalog: {source_path}")
            continue
        if not reference_path.exists():
            errors.append(f"Missing reference catalog: {reference_path}")
            continue

        source = load_catalog(source_path)
        reference = load_catalog(reference_path)
        missing = sorted(set(reference) - set(source))
        extra = sorted(set(source) - set(reference))
        if missing:
            errors.append(f"{name}: {len(missing)} message(s) missing from private catalog")
        if extra:
            errors.append(f"{name}: {len(extra)} message(s) are not in the reference catalog")

        translated = 0
        empty = 0
        fuzzy = 0
        structure_failures = 0
        no_hangul: list[str] = []
        for key, reference_message in reference.items():
            message = source.get(key)
            if message is None:
                continue
            if message.msgstr:
                translated += 1
            is_fuzzy = "fuzzy" in message.flags
            if not message.msgstr:
                empty += 1
                if not allow_incomplete and key not in preserved:
                    errors.append(f"{name}: empty translation: {message.msgid[:120]!r}")
            if is_fuzzy:
                fuzzy += 1
                if not allow_incomplete:
                    errors.append(f"{name}: fuzzy translation: {message.msgid[:120]!r}")
            if message.msgstr:
                structure_errors = _structure_errors(
                    reference_message.msgid, message.msgstr
                )
                if structure_errors:
                    structure_failures += 1
                    errors.append(
                        f"{name}: {message.msgid[:100]!r}: "
                        + "; ".join(structure_errors)
                    )
            if (
                message.msgstr
                and key not in preserved
                and _requires_hangul(message.msgid)
                and not HANGUL_RE.search(message.msgstr)
            ):
                no_hangul.append(message.msgid[:120])

        if no_hangul:
            warnings.append(
                f"{name}: {len(no_hangul)} translated message(s) contain no Hangul; "
                "check names, code, and brand strings."
            )
        files[name] = {
            "reference_messages": len(reference),
            "private_messages": len(source),
            "translated": translated,
            "empty": empty,
            "fuzzy": fuzzy,
            "structure_failures": structure_failures,
            "completeness": translated / len(reference) if reference else 1.0,
            "no_hangul_examples": no_hangul[:10],
        }

    total_reference = sum(item["reference_messages"] for item in files.values())
    total_translated = sum(item["translated"] for item in files.values())
    return {
        "files": files,
        "total_reference_messages": total_reference,
        "total_translated": total_translated,
        "completeness": total_translated / total_reference if total_reference else 1.0,
        "errors": errors,
        "warnings": warnings,
        "preserved_strings": len(preserved),
    }


def print_report(report: dict) -> None:
    for name, stats in report["files"].items():
        print(
            f"{name}: {stats['translated']}/{stats['reference_messages']} translated, "
            f"{stats['empty']} empty, {stats['fuzzy']} fuzzy, "
            f"{stats['structure_failures']} structural failures"
        )
    print(
        "Total: "
        f"{report['total_translated']}/{report['total_reference_messages']} "
        f"({report['completeness'] * 100:.1f}%)"
    )
    for warning in report["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in report["errors"]:
        print(f"ERROR: {error}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("localization/ko"))
    parser.add_argument("--reference-dir", type=Path, default=Path("i18n/ko"))
    parser.add_argument(
        "--preserved-strings",
        type=Path,
        default=None,
        help="JSON list of intentionally untranslated code/brand strings.",
    )
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Report empty and fuzzy messages without failing.",
    )
    args = parser.parse_args()

    preserved_path = args.preserved_strings or args.source_dir.parent / "preserved-strings.json"
    try:
        report = validate_catalogs(
            args.source_dir,
            args.reference_dir,
            preserved_path,
            allow_incomplete=args.allow_incomplete,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print_report(report)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
