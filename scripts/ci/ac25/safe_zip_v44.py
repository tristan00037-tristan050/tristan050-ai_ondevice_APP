"""Bounded, extraction-free ZIP reader for untrusted AC-25 artifacts."""
from __future__ import annotations

import hashlib
import io
import stat
import unicodedata
import zipfile
from dataclasses import dataclass

from .strict_receipt import StrictReceiptError, validate_path


ARTIFACT_ARCHIVE_UNSAFE = "ARTIFACT_ARCHIVE_UNSAFE"
ARTIFACT_DIGEST_MISMATCH = "ARTIFACT_DIGEST_MISMATCH"


@dataclass(frozen=True)
class ValidatedArchive:
    """An immutable validation result retaining the exact archive bytes."""

    archive_bytes: bytes
    names: tuple[str, ...]
    sizes: tuple[tuple[str, int], ...]
    archive_sha256: str

    def read_exact(self, path: str, *, max_bytes: int) -> bytes:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
            raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
        try:
            validate_path(path)
        except StrictReceiptError as exc:
            raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE) from exc
        declared = dict(self.sizes)
        if path not in declared or declared[path] > max_bytes:
            raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
        try:
            with zipfile.ZipFile(io.BytesIO(self.archive_bytes), "r") as archive:
                raw = archive.read(path)
        except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
            raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE) from exc
        if len(raw) != declared[path] or len(raw) > max_bytes:
            raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
        return raw


class SafeZipReader:
    """Validate central-directory metadata before reading any entry bytes."""

    MAX_FILES = 64
    MAX_SINGLE_FILE = 16 * 1024 * 1024
    MAX_TOTAL_UNCOMPRESSED = 64 * 1024 * 1024
    MAX_COMPRESSION_RATIO = 100
    _SUPPORTED_COMPRESSION = frozenset((zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED))

    def validate(self, archive_bytes: bytes) -> ValidatedArchive:
        if not isinstance(archive_bytes, bytes) or not archive_bytes:
            raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes), "r")
            infos = archive.infolist()
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE) from exc
        with archive:
            if not infos or len(infos) > self.MAX_FILES:
                raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
            raw_names: set[str] = set()
            nfc_names: set[str] = set()
            folded_names: set[str] = set()
            sizes: list[tuple[str, int]] = []
            total = 0
            for info in infos:
                name = info.filename
                try:
                    validate_path(name)
                except StrictReceiptError as exc:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE) from exc
                normalized = unicodedata.normalize("NFC", name)
                folded = normalized.casefold()
                if name in raw_names or normalized in nfc_names or folded in folded_names:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
                raw_names.add(name)
                nfc_names.add(normalized)
                folded_names.add(folded)
                if info.flag_bits & 0x1 or info.compress_type not in self._SUPPORTED_COMPRESSION:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if unix_mode and not stat.S_ISREG(unix_mode):
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
                if info.is_dir() or info.file_size < 0 or info.compress_size < 0:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
                if info.file_size > self.MAX_SINGLE_FILE:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
                total += info.file_size
                if total > self.MAX_TOTAL_UNCOMPRESSED:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
                if info.file_size and info.compress_size == 0:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
                if info.compress_size and info.file_size > info.compress_size * self.MAX_COMPRESSION_RATIO:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
                sizes.append((name, info.file_size))
            # Opening every bounded member forces CRC and decompressor validation.
            for name, expected_size in sizes:
                try:
                    raw = archive.read(name)
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE) from exc
                if len(raw) != expected_size:
                    raise StrictReceiptError(ARTIFACT_ARCHIVE_UNSAFE)
        return ValidatedArchive(
            archive_bytes=archive_bytes,
            names=tuple(name for name, _size in sizes),
            sizes=tuple(sizes),
            archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        )


__all__ = ["ARTIFACT_ARCHIVE_UNSAFE", "ARTIFACT_DIGEST_MISMATCH", "SafeZipReader", "ValidatedArchive"]
