from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class AssetError(RuntimeError):
    """Stable, path-free failure raised across the asset trust boundary."""

    code: str

    def __str__(self) -> str:
        return self.code


def block(code: str) -> AssetError:
    return AssetError(code)
