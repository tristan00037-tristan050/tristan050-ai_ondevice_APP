"""Strict manifest helpers for AC-25 R6 v4.1 delivery artifacts."""
from __future__ import annotations

from pathlib import Path

from . import strict_receipt as sr


DELIVERY_REQUIRED = frozenset(
    {
        "README.md", "START_HEAD", "TARGET_HEAD", "TARGET_TREE",
        "candidate.bundle", "cumulative.patch", "changed_paths.json",
        "changed_paths.nul", "DIGESTS.sha256",
    }
)


def changed_paths_from_nul(raw: bytes) -> tuple[str, ...]:
    if not raw or not raw.endswith(b"\0"):
        if raw == b"":
            return ()
        raise sr.StrictReceiptError("CHANGED_PATH_NUL_TERMINATOR_MISSING")
    fields = raw[:-1].split(b"\0")
    try:
        paths = tuple(field.decode("utf-8", "strict") for field in fields)
    except UnicodeDecodeError as exc:
        raise sr.StrictReceiptError("CHANGED_PATH_NOT_UTF8") from exc
    sr.validate_unique_paths(paths)
    if paths != tuple(sorted(paths, key=lambda value: value.encode("utf-8"))):
        raise sr.StrictReceiptError("CHANGED_PATHS_NOT_SORTED")
    return paths


def changed_paths_document(raw: bytes, *, base: str, head: str) -> dict:
    if sr.OID_RE.fullmatch(base or "") is None or sr.OID_RE.fullmatch(head or "") is None:
        raise sr.StrictReceiptError("CHANGED_PATH_COORDINATE_INVALID")
    return {"base": base, "head": head, "paths": list(changed_paths_from_nul(raw))}


def verify_delivery_layout(root: Path, *, allow_missing_digests: bool = False) -> tuple[str, ...]:
    files = sr._all_files(root)
    top = {path for path in files if "/" not in path}
    expected = DELIVERY_REQUIRED - ({"DIGESTS.sha256"} if allow_missing_digests else set())
    if top != expected:
        raise sr.StrictReceiptError("DELIVERY_LAYOUT_INVALID")
    if not any(path.startswith("AC25_R6_CLOSE_RECEIPT/") for path in files):
        raise sr.StrictReceiptError("DELIVERY_RECEIPT_MISSING")
    for path in files:
        name = Path(path).name
        if name.startswith("._") or name == ".DS_Store" or "__MACOSX" in Path(path).parts:
            raise sr.StrictReceiptError("APPLEDOUBLE_NOT_ALLOWED")
    return files


def build_delivery_digests(root: Path) -> bytes:
    verify_delivery_layout(root, allow_missing_digests=True)
    return sr.build_digest_manifest(root)


def verify_delivery_digests(root: Path) -> None:
    verify_delivery_layout(root)
    sr.verify_digest_manifest(root)
