from __future__ import annotations

import ast
import io
import json
import math
import re
import struct
import unicodedata
import zipfile
from typing import BinaryIO

from .contracts import AssetEntry
from .errors import block
from .path_policy import validate_relative_path

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_JSONL_LINE_BYTES = 2 * 1024 * 1024
MAX_JSONL_LINES = 1_000_000
MAX_SAFETENSORS_HEADER = 16 * 1024 * 1024
MAX_NPY_HEADER = 64 * 1024
MAX_ARRAY_ELEMENTS = 1_000_000_000
MAX_ARCHIVE_MEMBERS = 10_000
MAX_COMPRESSION_RATIO = 1_000
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_SAFETENSORS_ITEM_BYTES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "I16": 2,
    "U16": 2,
    "F16": 2,
    "BF16": 2,
    "I32": 4,
    "U32": 4,
    "F32": 4,
    "F64": 8,
    "I64": 8,
    "U64": 8,
}


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise block("FORMAT_SCHEMA_INVALID")
        result[key] = value
    return result


def _reject_control_strings(value: object) -> None:
    if isinstance(value, str):
        if _CONTROL_RE.search(value) or value != unicodedata.normalize("NFC", value):
            raise block("FORMAT_SCHEMA_INVALID")
        return
    if isinstance(value, list):
        for item in value:
            _reject_control_strings(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_control_strings(key)
            _reject_control_strings(item)


def _strict_json(raw: bytes, *, maximum: int = MAX_JSON_BYTES) -> object:
    if len(raw) > maximum or raw.startswith(b"\xef\xbb\xbf"):
        raise block("RESOURCE_LIMIT_EXCEEDED")
    try:
        text = raw.decode("utf-8")
        if text != unicodedata.normalize("NFC", text):
            raise block("FORMAT_SCHEMA_INVALID")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                block("FORMAT_SCHEMA_INVALID")
            ),
        )
        _reject_control_strings(value)
        return value
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise block("FORMAT_SCHEMA_INVALID") from exc


def _read_bounded(handle: BinaryIO, maximum: int) -> bytes:
    handle.seek(0)
    raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise block("RESOURCE_LIMIT_EXCEEDED")
    return raw


def _validate_json(handle: BinaryIO) -> None:
    _strict_json(_read_bounded(handle, MAX_JSON_BYTES))


def _validate_jsonl(handle: BinaryIO) -> None:
    handle.seek(0)
    count = 0
    while True:
        line = handle.readline(MAX_JSONL_LINE_BYTES + 1)
        if not line:
            break
        count += 1
        if count > MAX_JSONL_LINES or len(line) > MAX_JSONL_LINE_BYTES:
            raise block("RESOURCE_LIMIT_EXCEEDED")
        if not line.endswith(b"\n"):
            raise block("FORMAT_SCHEMA_INVALID")
        _strict_json(line[:-1], maximum=MAX_JSONL_LINE_BYTES)


def _validate_npy(handle: BinaryIO) -> None:
    handle.seek(0)
    if handle.read(6) != b"\x93NUMPY":
        raise block("FORMAT_SCHEMA_INVALID")
    version = handle.read(2)
    if version not in {b"\x01\x00", b"\x02\x00", b"\x03\x00"}:
        raise block("UNSUPPORTED_FORMAT")
    length_size = 2 if version == b"\x01\x00" else 4
    length_raw = handle.read(length_size)
    if len(length_raw) != length_size:
        raise block("FORMAT_SCHEMA_INVALID")
    header_length = int.from_bytes(length_raw, "little")
    if not 1 <= header_length <= MAX_NPY_HEADER:
        raise block("RESOURCE_LIMIT_EXCEEDED")
    header = handle.read(header_length)
    if len(header) != header_length:
        raise block("FORMAT_SCHEMA_INVALID")
    try:
        encoding = "utf-8" if version == b"\x03\x00" else "latin1"
        parsed = ast.literal_eval(header.decode(encoding).strip())
        if (
            not isinstance(parsed, dict)
            or set(parsed) != {"descr", "fortran_order", "shape"}
            or type(parsed["fortran_order"]) is not bool
            or not isinstance(parsed["shape"], tuple)
            or not all(type(item) is int and item >= 0 for item in parsed["shape"])
        ):
            raise ValueError
        import numpy as np

        dtype = np.dtype(parsed["descr"])
        shape = parsed["shape"]
    except Exception as exc:
        raise block("FORMAT_SCHEMA_INVALID") from exc
    if getattr(dtype, "hasobject", True):
        raise block("UNSAFE_SERIALIZATION")
    elements = math.prod(shape) if shape else 1
    if elements < 0 or elements > MAX_ARRAY_ELEMENTS:
        raise block("RESOURCE_LIMIT_EXCEEDED")
    expected_data_bytes = elements * int(dtype.itemsize)
    data_start = 8 + length_size + header_length
    handle.seek(0, io.SEEK_END)
    if handle.tell() != data_start + expected_data_bytes:
        raise block("FORMAT_SCHEMA_INVALID")


def _validate_npz(handle: BinaryIO) -> None:
    handle.seek(0)
    try:
        with zipfile.ZipFile(handle) as archive:
            names = archive.namelist()
            if (
                not names
                or len(names) > MAX_ARCHIVE_MEMBERS
                or len(names) != len(set(names))
            ):
                raise block("FORMAT_SCHEMA_INVALID")
            for info in archive.infolist():
                try:
                    member_path = validate_relative_path(info.filename)
                except Exception as exc:
                    raise block("FORMAT_SCHEMA_INVALID") from exc
                if (
                    info.is_dir()
                    or not member_path.endswith(".npy")
                    or info.file_size > MAX_JSON_BYTES * 64
                    or (
                        info.compress_size == 0
                        and info.file_size > 0
                    )
                    or (
                        info.compress_size > 0
                        and info.file_size > info.compress_size * MAX_COMPRESSION_RATIO
                    )
                ):
                    raise block("FORMAT_SCHEMA_INVALID")
                with archive.open(info) as member:
                    raw = member.read(info.file_size + 1)
                    if len(raw) != info.file_size:
                        raise block("FORMAT_SCHEMA_INVALID")
                    _validate_npy(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise block("FORMAT_SCHEMA_INVALID") from exc


def _validate_safetensors(handle: BinaryIO) -> None:
    handle.seek(0)
    raw_length = handle.read(8)
    if len(raw_length) != 8:
        raise block("FORMAT_SCHEMA_INVALID")
    header_length = struct.unpack("<Q", raw_length)[0]
    if not 2 <= header_length <= MAX_SAFETENSORS_HEADER:
        raise block("RESOURCE_LIMIT_EXCEEDED")
    header = _strict_json(handle.read(header_length), maximum=MAX_SAFETENSORS_HEADER)
    if not isinstance(header, dict):
        raise block("FORMAT_SCHEMA_INVALID")
    handle.seek(0, io.SEEK_END)
    payload_size = handle.tell() - 8 - header_length
    ranges: list[tuple[int, int]] = []
    for name, descriptor in header.items():
        if name == "__metadata__":
            if not isinstance(descriptor, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in descriptor.items()
            ):
                raise block("FORMAT_SCHEMA_INVALID")
            continue
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(descriptor, dict)
            or set(descriptor) != {"dtype", "shape", "data_offsets"}
        ):
            raise block("FORMAT_SCHEMA_INVALID")
        dtype = descriptor["dtype"]
        shape = descriptor["shape"]
        offsets = descriptor["data_offsets"]
        if (
            dtype not in _SAFETENSORS_ITEM_BYTES
            or not isinstance(shape, list)
            or not all(type(item) is int and item >= 0 for item in shape)
            or not isinstance(offsets, list)
            or len(offsets) != 2
            or not all(type(item) is int and item >= 0 for item in offsets)
        ):
            raise block("FORMAT_SCHEMA_INVALID")
        start, end = offsets
        elements = math.prod(shape) if shape else 1
        if (
            elements > MAX_ARRAY_ELEMENTS
            or start > end
            or end > payload_size
            or end - start != elements * _SAFETENSORS_ITEM_BYTES[dtype]
        ):
            raise block("FORMAT_SCHEMA_INVALID")
        ranges.append((start, end))
    ordered = sorted(ranges)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise block("FORMAT_SCHEMA_INVALID")


def _validate_gguf(handle: BinaryIO) -> None:
    handle.seek(0)
    header = handle.read(24)
    if len(header) < 24 or header[:4] != b"GGUF":
        raise block("FORMAT_SCHEMA_INVALID")
    version = int.from_bytes(header[4:8], "little")
    tensor_count = int.from_bytes(header[8:16], "little")
    metadata_count = int.from_bytes(header[16:24], "little")
    if version not in {2, 3} or tensor_count > 1_000_000 or metadata_count > 1_000_000:
        raise block("UNSUPPORTED_FORMAT")


def _validate_text(handle: BinaryIO) -> None:
    raw = _read_bounded(handle, MAX_JSON_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise block("FORMAT_SCHEMA_INVALID") from exc
    if text != unicodedata.normalize("NFC", text) or "\x00" in text:
        raise block("FORMAT_SCHEMA_INVALID")


def validate_format(handle: BinaryIO, entry: AssetEntry) -> None:
    validators = {
        "json": _validate_json,
        "jsonl": _validate_jsonl,
        "npy": _validate_npy,
        "npz": _validate_npz,
        "safetensors": _validate_safetensors,
        "gguf": _validate_gguf,
        "utf8_text": _validate_text,
        "opaque": lambda _handle: None,
    }
    validator = validators.get(entry.validator)
    if validator is None:
        raise block("UNSUPPORTED_FORMAT")
    validator(handle)
