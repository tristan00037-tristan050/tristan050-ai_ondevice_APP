from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from butler_pc_core.assets import get_asset_service
from butler_pc_core.assets.errors import block

MAX_CHUNKS = 1_000_000
MAX_DIMENSIONS = 16_384
MAX_QUERY_BYTES = 16 * 1024


@dataclass(frozen=True)
class _Chunk:
    chunk_id: str
    text: str


def _load_chunks(handle: Any) -> list[_Chunk]:
    chunks: list[_Chunk] = []
    seen: set[str] = set()
    for line in handle:
        if len(chunks) >= MAX_CHUNKS:
            raise block("RESOURCE_LIMIT_EXCEEDED")
        try:
            row = json.loads(line)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise block("FORMAT_SCHEMA_INVALID") from exc
        if not isinstance(row, dict) or set(row) != {"chunk_id", "text"}:
            raise block("FORMAT_SCHEMA_INVALID")
        chunk_id, text = row["chunk_id"], row["text"]
        if (
            not isinstance(chunk_id, str)
            or not chunk_id
            or chunk_id in seen
            or not isinstance(text, str)
            or not text
        ):
            raise block("FORMAT_SCHEMA_INVALID")
        seen.add(chunk_id)
        chunks.append(_Chunk(chunk_id, text))
    if not chunks:
        raise block("FORMAT_SCHEMA_INVALID")
    return chunks


def _load_embeddings(handle: Any, expected_rows: int):
    try:
        import numpy as np

        matrix = np.load(handle, allow_pickle=False)
    except Exception as exc:
        raise block("FORMAT_SCHEMA_INVALID") from exc
    if (
        not isinstance(matrix, np.ndarray)
        or matrix.dtype not in {np.dtype("float16"), np.dtype("float32")}
        or matrix.ndim != 2
        or matrix.shape[0] != expected_rows
        or not 1 <= matrix.shape[1] <= MAX_DIMENSIONS
        or not np.isfinite(matrix).all()
    ):
        raise block("FORMAT_SCHEMA_INVALID")
    return matrix.astype(np.float32, copy=False)


def _query_vector(query: str, dimensions: int):
    """Deterministic local feature hashing used by the safe retrieval baseline."""

    if not query or len(query.encode("utf-8")) > MAX_QUERY_BYTES:
        raise block("QUERY_INVALID")
    import numpy as np

    vector = np.zeros(dimensions, dtype=np.float32)
    normalized = " ".join(query.casefold().split())
    grams = [normalized[index : index + 3] for index in range(max(1, len(normalized) - 2))]
    for gram in grams:
        raw = hashlib.sha256(gram.encode("utf-8")).digest()
        index = int.from_bytes(raw[:8], "little") % dimensions
        vector[index] += -1.0 if raw[8] & 1 else 1.0
    norm = float(np.linalg.norm(vector))
    if norm:
        vector /= norm
    return vector


def find(query: str, top_k: int) -> list[dict[str, object]]:
    if type(top_k) is not int or not 1 <= top_k <= 50:
        raise block("QUERY_INVALID")
    with get_asset_service().require_capability("helper1.search") as lease:
        with lease.require("chunks_jsonl").open() as chunks_handle:
            chunks = _load_chunks(chunks_handle)
        with lease.require("embeddings_npy").open() as embeddings_handle:
            embeddings = _load_embeddings(embeddings_handle, len(chunks))

    import numpy as np

    norms = np.linalg.norm(embeddings, axis=1)
    safe_norms = np.where(norms > 0, norms, 1.0)
    scores = (embeddings @ _query_vector(query, embeddings.shape[1])) / safe_norms
    indices = np.argsort(-scores, kind="stable")[: min(top_k, len(chunks))]
    return [
        {
            "chunk_id": chunks[int(index)].chunk_id,
            "text": chunks[int(index)].text,
            "score": float(scores[int(index)]),
        }
        for index in indices
    ]


def ask(_query: str) -> dict[str, object]:
    # Search is production-ready. Generative ask remains unavailable until its
    # GGUF loader consumes the verified descriptor without reopening a path.
    raise block("REQUIRED_ASSET_MISSING")
