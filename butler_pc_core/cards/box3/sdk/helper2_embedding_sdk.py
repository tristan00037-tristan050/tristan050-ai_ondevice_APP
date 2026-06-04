from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Helper2Embedder:
    implementation: str = "helper2_sdk"

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[:8]]
