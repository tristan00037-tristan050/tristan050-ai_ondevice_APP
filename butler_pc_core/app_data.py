from __future__ import annotations

import os
from pathlib import Path


class AppDataPathError(RuntimeError):
    pass


def product_data_root(component: str, *, legacy_name: str) -> Path:
    """Return a device-local persistent root without accepting relative app data."""

    if (
        not component
        or component in {".", ".."}
        or "/" in component
        or "\\" in component
    ):
        raise AppDataPathError("APP_DATA_COMPONENT_INVALID")
    configured = os.environ.get("BUTLER_APP_DATA_DIR", "").strip()
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            raise AppDataPathError("APP_DATA_DIR_NOT_ABSOLUTE")
        return root / component
    raise AppDataPathError("NATIVE_APP_DATA_DIR_UNAVAILABLE")
