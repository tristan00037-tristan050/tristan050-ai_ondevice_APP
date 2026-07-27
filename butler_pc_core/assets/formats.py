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

from .checked import checked_add, checked_mul
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
MAX_TENSOR_DIMENSIONS = 16
MAX_GGUF_STRING_BYTES = 16 * 1024 * 1024
MAX_GGUF_ARRAY_ITEMS = 2_000_000
MAX_GGUF_METADATA = 1_000_000
MAX_GGUF_TENSORS = 1_000_000
MAX_GGUF_RECURSION = 4
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_SAFETENSORS_ITEM_BITS = {
    "BOOL": 8,
    "U8": 8,
    "I8": 8,
    "F8_E4M3": 8,
    "F8_E5M2": 8,
    "I16": 16,
    "U16": 16,
    "F16": 16,
    "BF16": 16,
    "I32": 32,
    "U32": 32,
    "F32": 32,
    "F64": 64,
    "I64": 64,
    "U64": 64,
}
# GGML type -> (elements per block, bytes per block). This deliberately
# supports only the audited legacy/K-quant set used by Butler packages.
_GGML_BLOCKS = {
    0: (1, 4),     # F32
    1: (1, 2),     # F16
    2: (32, 18),   # Q4_0
    3: (32, 20),   # Q4_1
    6: (32, 22),   # Q5_0
    7: (32, 24),   # Q5_1
    8: (32, 34),   # Q8_0
    9: (32, 40),   # Q8_1
    10: (256, 84),  # Q2_K
    11: (256, 110), # Q3_K
    12: (256, 144), # Q4_K
    13: (256, 176), # Q5_K
    14: (256, 210), # Q6_K
    15: (256, 292), # Q8_K
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
    handle.seek(0, io.SEEK_END)
    file_size = handle.tell()
    header_end = checked_add(8, header_length)
    if header_end > file_size:
        raise block("BLOCK_FORMAT_INVALID")
    handle.seek(8)
    raw_header = handle.read(header_length)
    if len(raw_header) != header_length:
        raise block("BLOCK_FORMAT_INVALID")
    header = _strict_json(raw_header, maximum=MAX_SAFETENSORS_HEADER)
    if not isinstance(header, dict):
        raise block("BLOCK_FORMAT_INVALID")
    payload_size = file_size - header_end
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
            dtype not in _SAFETENSORS_ITEM_BITS
            or not isinstance(shape, list)
            or len(shape) > MAX_TENSOR_DIMENSIONS
            or not all(type(item) is int and item >= 0 for item in shape)
            or not isinstance(offsets, list)
            or len(offsets) != 2
            or not all(type(item) is int and item >= 0 for item in offsets)
        ):
            raise block("FORMAT_SCHEMA_INVALID")
        start, end = offsets
        elements = checked_mul(*shape, limit=MAX_ARRAY_ELEMENTS) if shape else 1
        expected_bits = checked_mul(
            elements,
            _SAFETENSORS_ITEM_BITS[dtype],
            limit=checked_mul(payload_size, 8),
        )
        expected_bytes = (checked_add(expected_bits, 7)) // 8
        if (
            start > end
            or end > payload_size
            or end - start != expected_bytes
        ):
            raise block("BLOCK_FORMAT_INVALID")
        ranges.append((start, end))
    ordered = sorted(ranges)
    cursor = 0
    for start, end in ordered:
        if start != cursor:
            raise block("BLOCK_FORMAT_INVALID")
        cursor = end
    if cursor != payload_size:
        raise block("BLOCK_FORMAT_INVALID")


class _GGUFReader:
    def __init__(self, handle: BinaryIO, size: int) -> None:
        self.handle = handle
        self.size = size
        self.offset = 0
        self.budget = min(size, 512 * 1024 * 1024)

    def read(self, length: int) -> bytes:
        end = checked_add(self.offset, length)
        if end > self.size or length > self.budget:
            raise block("BLOCK_FORMAT_INVALID")
        raw = self.handle.read(length)
        if len(raw) != length:
            raise block("BLOCK_FORMAT_INVALID")
        self.offset = end
        self.budget -= length
        return raw

    def scalar(self, fmt: str) -> int | float | bool:
        size = struct.calcsize(fmt)
        value = struct.unpack(fmt, self.read(size))[0]
        return value

    def string(self) -> str:
        length = self.scalar("<Q")
        if type(length) is not int or length > MAX_GGUF_STRING_BYTES:
            raise block("BLOCK_FORMAT_INVALID")
        try:
            text = self.read(length).decode("utf-8")
        except UnicodeError as exc:
            raise block("BLOCK_FORMAT_INVALID") from exc
        if "\x00" in text:
            raise block("BLOCK_FORMAT_INVALID")
        return text

    def value(self, value_type: int, *, depth: int = 0) -> object:
        if depth > MAX_GGUF_RECURSION:
            raise block("BLOCK_FORMAT_INVALID")
        formats = {
            0: "<B",
            1: "<b",
            2: "<H",
            3: "<h",
            4: "<I",
            5: "<i",
            6: "<f",
            10: "<Q",
            11: "<q",
            12: "<d",
        }
        if value_type in formats:
            return self.scalar(formats[value_type])
        if value_type == 7:
            raw = self.scalar("<B")
            if raw not in {0, 1}:
                raise block("BLOCK_FORMAT_INVALID")
            return bool(raw)
        if value_type == 8:
            return self.string()
        if value_type == 9:
            subtype = self.scalar("<I")
            count = self.scalar("<Q")
            if (
                type(subtype) is not int
                or subtype == 9
                or type(count) is not int
                or count > MAX_GGUF_ARRAY_ITEMS
            ):
                raise block("BLOCK_FORMAT_INVALID")
            return [self.value(subtype, depth=depth + 1) for _ in range(count)]
        raise block("BLOCK_FORMAT_INVALID")


def _align(value: int, alignment: int) -> int:
    if alignment <= 0 or alignment > 4096 or alignment & (alignment - 1):
        raise block("BLOCK_FORMAT_INVALID")
    return checked_mul((checked_add(value, alignment - 1)) // alignment, alignment)


def _validate_gguf(handle: BinaryIO) -> None:
    handle.seek(0, io.SEEK_END)
    file_size = handle.tell()
    if file_size < 24:
        raise block("BLOCK_FORMAT_INVALID")
    handle.seek(0)
    reader = _GGUFReader(handle, file_size)
    if reader.read(4) != b"GGUF":
        raise block("BLOCK_FORMAT_INVALID")
    version = reader.scalar("<I")
    tensor_count = reader.scalar("<Q")
    metadata_count = reader.scalar("<Q")
    if (
        version not in {2, 3}
        or type(tensor_count) is not int
        or tensor_count > MAX_GGUF_TENSORS
        or type(metadata_count) is not int
        or metadata_count > MAX_GGUF_METADATA
    ):
        raise block("BLOCK_FORMAT_INVALID")

    metadata: dict[str, object] = {}
    for _ in range(metadata_count):
        key = reader.string()
        if not key or key in metadata:
            raise block("BLOCK_FORMAT_INVALID")
        value_type = reader.scalar("<I")
        if type(value_type) is not int:
            raise block("BLOCK_FORMAT_INVALID")
        metadata[key] = reader.value(value_type)

    tensor_rows: list[tuple[str, int, int, int]] = []
    tensor_names: set[str] = set()
    for _ in range(tensor_count):
        name = reader.string()
        dimensions_count = reader.scalar("<I")
        if (
            not name
            or name in tensor_names
            or type(dimensions_count) is not int
            or not 1 <= dimensions_count <= MAX_TENSOR_DIMENSIONS
        ):
            raise block("BLOCK_FORMAT_INVALID")
        tensor_names.add(name)
        dimensions = [reader.scalar("<Q") for _ in range(dimensions_count)]
        if not all(type(item) is int and item > 0 for item in dimensions):
            raise block("BLOCK_FORMAT_INVALID")
        elements = checked_mul(*dimensions, limit=MAX_ARRAY_ELEMENTS)
        ggml_type = reader.scalar("<I")
        offset = reader.scalar("<Q")
        if ggml_type not in _GGML_BLOCKS or type(offset) is not int:
            raise block("BLOCK_FORMAT_INVALID")
        block_elements, block_bytes = _GGML_BLOCKS[ggml_type]
        if elements % block_elements:
            raise block("BLOCK_FORMAT_INVALID")
        byte_size = checked_mul(elements // block_elements, block_bytes)
        tensor_rows.append((name, offset, byte_size, ggml_type))

    alignment_value = metadata.get("general.alignment", 32)
    if type(alignment_value) is not int:
        raise block("BLOCK_FORMAT_INVALID")
    data_start = _align(reader.offset, alignment_value)
    if data_start > file_size:
        raise block("BLOCK_FORMAT_INVALID")
    handle.seek(reader.offset)
    padding = handle.read(data_start - reader.offset)
    if any(padding):
        raise block("BLOCK_FORMAT_INVALID")

    ranges: list[tuple[int, int]] = []
    for _name, relative_offset, byte_size, _ggml_type in tensor_rows:
        if relative_offset % alignment_value:
            raise block("BLOCK_FORMAT_INVALID")
        start = checked_add(data_start, relative_offset)
        end = checked_add(start, byte_size)
        if end > file_size:
            raise block("BLOCK_FORMAT_INVALID")
        ranges.append((start, end))
    ordered = sorted(ranges)
    cursor = data_start
    for start, end in ordered:
        expected = _align(cursor, alignment_value)
        if start != expected or start < cursor:
            raise block("BLOCK_FORMAT_INVALID")
        handle.seek(cursor)
        if any(handle.read(start - cursor)):
            raise block("BLOCK_FORMAT_INVALID")
        cursor = end
    if cursor != file_size:
        raise block("BLOCK_FORMAT_INVALID")

    tokens = metadata.get("tokenizer.ggml.tokens")
    if tokens is not None:
        if not isinstance(tokens, list):
            raise block("BLOCK_FORMAT_INVALID")
        vocabulary_size = len(tokens)
        for key, value in metadata.items():
            if key.endswith("_token_id"):
                if type(value) is not int or not 0 <= value < vocabulary_size:
                    raise block("BLOCK_FORMAT_INVALID")


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
