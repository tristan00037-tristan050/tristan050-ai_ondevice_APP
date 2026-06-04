from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class BgeM3Embedder:
    implementation: str = "bge_m3"

    def embed(self, text: str) -> list[float]:
        digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
        return [b / 255.0 for b in digest]
