from __future__ import annotations

import os
from pathlib import Path


class AppDataPathError(RuntimeError):
    pass


def product_data_root(component: str, *, legacy_name: str) -> Path:
    """Return a device-local persistent root without accepting relative app data."""

    configured = os.environ.get("BUTLER_APP_DATA_DIR", "").strip()
    if not configured:
        raise AppDataPathError("APP_DATA_DIR_REQUIRED")
    root = Path(configured).expanduser()
    if not root.is_absolute():
        raise AppDataPathError("APP_DATA_DIR_NOT_ABSOLUTE")
    if component in {"", ".", ".."} or "/" in component or "\\" in component:
        raise AppDataPathError("APP_DATA_COMPONENT_INVALID")
    # legacy_name remains in the signature to avoid a parallel call contract,
    # but production never falls back to CWD or a legacy relative directory.
    del legacy_name
    return root / component
