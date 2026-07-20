"""Secure source snapshot and deterministic row closure for Box5 A4 v2.1.

The product opens the uploaded bank file exactly once, copies and hashes from
that descriptor, verifies the descriptor a second time, then unlinks the
private snapshot after opening independent producer and verifier descriptors.
No path is reopened after the owner boundary.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import stat
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .reconciliation_v2 import A4ContractError, digest_object


MAX_SOURCE_BYTES = 512 * 1024 * 1024
_ALLOWED_SUFFIXES = frozenset({".csv", ".xls", ".xlsx"})


def _fingerprint(value: os.stat_result) -> dict[str, int]:
    return {
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "mode": int(value.st_mode),
        "uid": int(value.st_uid),
        "gid": int(value.st_gid),
        "size": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
        "ctime_ns": int(value.st_ctime_ns),
    }


def _hash_fd(fd: int) -> tuple[str, int]:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    size = 0
    while True:
        block = os.read(fd, 1024 * 1024)
        if not block:
            break
        digest.update(block)
        size += len(block)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest(), size


@dataclass(slots=True)
class SourceSnapshot:
    """Unlinked immutable snapshot with separate product/verifier descriptors."""

    producer_fd: int
    verifier_fd: int
    suffix: str
    receipt: dict[str, Any]
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for fd in (self.producer_fd, self.verifier_fd):
            try:
                os.close(fd)
            except OSError:
                pass

    def __enter__(self) -> SourceSnapshot:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def secure_source_snapshot(path: str | Path) -> SourceSnapshot:
    """Create a verified, unlinked snapshot or fail closed without partial output."""

    source_path = Path(path)
    suffix = source_path.suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise A4ContractError("BLOCK_FILE_TYPE")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    cloexec = getattr(os, "O_CLOEXEC", None)
    if nofollow is None or cloexec is None:
        raise A4ContractError("BLOCK_PLATFORM_CAPABILITY")
    source_fd = -1
    staging_fd = -1
    producer_fd = -1
    verifier_fd = -1
    staging_path: Path | None = None
    try:
        source_fd = os.open(source_path, os.O_RDONLY | cloexec | nofollow)
        pre = os.fstat(source_fd)
        if (
            not stat.S_ISREG(pre.st_mode)
            or pre.st_size <= 0
            or pre.st_size > MAX_SOURCE_BYTES
            or pre.st_uid != os.geteuid()
            or pre.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise A4ContractError("BLOCK_FILE_TYPE")
        staging_fd, raw_staging = tempfile.mkstemp(
            prefix="butler-a4-source-", suffix=suffix
        )
        staging_path = Path(raw_staging)
        os.set_inheritable(staging_fd, False)
        os.fchmod(staging_fd, 0o600)
        os.lseek(source_fd, 0, os.SEEK_SET)
        first_digest = hashlib.sha256()
        copied = 0
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            first_digest.update(block)
            copied += len(block)
            view = memoryview(block)
            while view:
                written = os.write(staging_fd, view)
                if written <= 0:
                    raise A4ContractError("BLOCK_INPUT_CLOSURE")
                view = view[written:]
        os.fsync(staging_fd)
        staging_dir_fd = os.open(
            staging_path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | cloexec,
        )
        try:
            os.fsync(staging_dir_fd)
        finally:
            os.close(staging_dir_fd)
        first_sha = first_digest.hexdigest()
        second_sha, second_size = _hash_fd(source_fd)
        post = os.fstat(source_fd)
        snapshot_sha, snapshot_size = _hash_fd(staging_fd)
        if (
            _fingerprint(pre) != _fingerprint(post)
            or copied != pre.st_size
            or second_size != copied
            or snapshot_size != copied
            or first_sha != second_sha
            or first_sha != snapshot_sha
        ):
            raise A4ContractError("BLOCK_INPUT_CHANGED")
        pre_digest = digest_object(_fingerprint(pre))
        post_digest = digest_object(_fingerprint(post))
        os.close(staging_fd)
        staging_fd = -1
        producer_fd = os.open(staging_path, os.O_RDONLY | cloexec | nofollow)
        verifier_fd = os.open(staging_path, os.O_RDONLY | cloexec | nofollow)
        staging_path.unlink()
        staging_dir_fd = os.open(
            staging_path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | cloexec,
        )
        try:
            os.fsync(staging_dir_fd)
        finally:
            os.close(staging_dir_fd)
        staging_path = None
        snapshot = SourceSnapshot(
            producer_fd=producer_fd,
            verifier_fd=verifier_fd,
            suffix=suffix,
            receipt={
                "schema_version": "2.1.0",
                "source_file_sha256": first_sha,
                "source_file_size": copied,
                "pre_fstat_digest": pre_digest,
                "post_fstat_digest": post_digest,
                "snapshot_sha256": snapshot_sha,
                "producer_verifier_fd_separated": producer_fd != verifier_fd,
                "snapshot_path_unlinked": True,
            },
        )
        producer_fd = -1
        verifier_fd = -1
        return snapshot
    except A4ContractError:
        raise
    except (OSError, OverflowError) as exc:
        raise A4ContractError("BLOCK_INPUT_CLOSURE") from exc
    finally:
        for fd in (source_fd, staging_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if staging_path is not None:
            try:
                staging_path.unlink()
            except OSError:
                pass
        for fd in (producer_fd, verifier_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass


def _normalized_cell(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).strip()
    if len(text.encode("utf-8")) > 1_024:
        raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    return text


def row_closure(frame: Any, *, fee_column: str = "거래유형") -> dict[str, Any]:
    """Create an ordered, exhaustive disposition manifest over parsed data rows."""

    columns = tuple(str(column) for column in frame.columns)
    rows: list[dict[str, Any]] = []
    ordered = hashlib.sha256()
    for ordinal, (_, row) in enumerate(frame.iterrows()):
        cells = [[column, _normalized_cell(row.get(column))] for column in columns]
        row_digest = digest_object(
            {"domain": "BUTLER_A4_PARSED_ROW_V2_1", "ordinal": ordinal, "cells": cells}
        )
        disposition = (
            "FEE"
            if _normalized_cell(row.get(fee_column)).upper() in {"FEE", "수수료"}
            else "PRINCIPAL"
        )
        ordered.update(bytes.fromhex(row_digest))
        rows.append(
            {
                "ordinal": ordinal,
                "row_digest": row_digest,
                "disposition": disposition,
            }
        )
    return {
        "schema_version": "2.1.0",
        "ordered_row_root": ordered.hexdigest(),
        "row_count": len(rows),
        "disposition_counts": {
            name: sum(item["disposition"] == name for item in rows)
            for name in ("PRINCIPAL", "FEE", "HEADER", "QUARANTINED", "REJECTED")
        },
        "rows": rows,
    }


def _physical_rows(fd: int, suffix: str) -> list[list[object]]:
    """Read physical source records from the already-owned descriptor."""

    duplicate = os.dup(fd)
    try:
        os.lseek(duplicate, 0, os.SEEK_SET)
        with os.fdopen(duplicate, "rb", closefd=True) as handle:
            raw = handle.read(MAX_SOURCE_BYTES + 1)
        duplicate = -1
    finally:
        if duplicate >= 0:
            os.close(duplicate)
    if len(raw) > MAX_SOURCE_BYTES:
        raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    if suffix == ".csv":
        decoded: str | None = None
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                decoded = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise A4ContractError("BLOCK_INPUT_CLOSURE")
        try:
            return [list(row) for row in csv.reader(io.StringIO(decoded, newline=""))]
        except csv.Error as exc:
            raise A4ContractError("BLOCK_INPUT_CLOSURE") from exc
    if suffix == ".xlsx":
        workbook = None
        try:
            import openpyxl

            workbook = openpyxl.load_workbook(
                io.BytesIO(raw), read_only=True, data_only=False, keep_links=True
            )
            if len(workbook.worksheets) != 1:
                raise A4ContractError("BLOCK_ADAPTER_POLICY")
            worksheet = workbook.worksheets[0]
            if worksheet.sheet_state != "visible" or getattr(
                workbook, "_external_links", ()
            ):
                raise A4ContractError("BLOCK_ADAPTER_POLICY")
            rows: list[list[object]] = []
            for record in worksheet.iter_rows():
                if any(cell.data_type == "f" for cell in record):
                    raise A4ContractError("BLOCK_ADAPTER_POLICY")
                rows.append([cell.value for cell in record])
            return rows
        except A4ContractError:
            raise
        except Exception as exc:
            raise A4ContractError("BLOCK_INPUT_CLOSURE") from exc
        finally:
            if workbook is not None:
                workbook.close()
    if suffix == ".xls":
        try:
            import xlrd

            workbook = xlrd.open_workbook(file_contents=raw, on_demand=True)
            if workbook.nsheets != 1:
                raise A4ContractError("BLOCK_ADAPTER_POLICY")
            sheet = workbook.sheet_by_index(0)
            if getattr(sheet, "visibility", 0) != 0:
                raise A4ContractError("BLOCK_ADAPTER_POLICY")
            return [sheet.row_values(index) for index in range(sheet.nrows)]
        except A4ContractError:
            raise
        except Exception as exc:
            raise A4ContractError("BLOCK_INPUT_CLOSURE") from exc
    raise A4ContractError("BLOCK_UNSUPPORTED_SOURCE_FORMAT")


def physical_row_closure(
    fd: int,
    suffix: str,
    *,
    source_sha256: str,
    adapter: Any,
) -> dict[str, Any]:
    """Bind every physical source record before dataframe normalization."""

    physical = _physical_rows(fd, suffix)
    if not physical or len(physical) > 100_001:
        raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    required = (
        str(adapter.source_account),
        str(adapter.bank_code),
        str(adapter.booking_date),
        str(adapter.withdrawal),
        str(adapter.deposit),
    )
    normalized_rows: list[list[str]] = []
    header_index: int | None = None
    for index, raw_row in enumerate(physical):
        if len(raw_row) > 256:
            raise A4ContractError("BLOCK_RESOURCE_LIMIT")
        row = [_normalized_cell(value) for value in raw_row]
        normalized_rows.append(row)
        if header_index is None and all(row.count(name) == 1 for name in required):
            header_index = index
    if header_index is None:
        raise A4ContractError("BLOCK_ADAPTER_POLICY")
    headers = normalized_rows[header_index]
    if len(headers) != len(set(headers)):
        raise A4ContractError("BLOCK_AMBIGUOUS_COLUMN")
    fee_index = (
        headers.index(str(adapter.fee_type))
        if adapter.fee_type is not None and str(adapter.fee_type) in headers
        else None
    )
    rows: list[dict[str, Any]] = []
    ordered = hashlib.sha256()
    transaction_ordinal = 0
    for ordinal, cells in enumerate(normalized_rows):
        if ordinal <= header_index:
            disposition, txn_ordinal = "HEADER", None
        elif not any(cells):
            disposition, txn_ordinal = "BLANK", None
        else:
            fee = (
                cells[fee_index].upper()
                if fee_index is not None and fee_index < len(cells)
                else ""
            )
            disposition = "FEE" if fee in {"FEE", "수수료"} else "PRINCIPAL"
            txn_ordinal = transaction_ordinal
            transaction_ordinal += 1
        locator = digest_object(
            {
                "domain": "BUTLER/A4/ROW_LOCATOR/V3.1",
                "source_sha256": source_sha256,
                "sheet_id": "sheet-0001",
                "row_ordinal": ordinal,
            }
        )
        cell_digest = digest_object(
            {
                "domain": "BUTLER/A4/CELL_VECTOR/V3.1",
                "row_ordinal": ordinal,
                "cells": cells,
            }
        )
        for value in (locator, cell_digest, disposition):
            encoded = value.encode("utf-8")
            ordered.update(len(encoded).to_bytes(4, "big"))
            ordered.update(encoded)
        rows.append(
            {
                "row_locator": locator,
                "sheet_id": "sheet-0001",
                "row_ordinal": ordinal,
                "disposition": disposition,
                "cell_vector_digest": cell_digest,
                "transaction_ordinal": txn_ordinal,
            }
        )
    names = ("PRINCIPAL", "FEE", "HEADER", "BLANK", "QUARANTINED", "REJECTED")
    return {
        "schema_version": "3.1.0",
        "ordered_row_root": ordered.hexdigest(),
        "row_count": len(rows),
        "transaction_row_count": transaction_ordinal,
        "disposition_counts": {
            name: sum(item["disposition"] == name for item in rows) for name in names
        },
        "rows": rows,
    }
