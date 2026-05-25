from __future__ import annotations

import os
from pathlib import Path


class ManifestResolutionError(RuntimeError):
    pass


def resolve_option_d_manifest(
    repo_root: Path | None = None,
    explicit_path: str | None = None,
) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    env_path = os.environ.get("BUTLER_CARD5_OPTION_D_MANIFEST")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            root / "evidence/card5_lora_v3_3/option_d_manifest_v5.json",
            root / "evidence/card5_lora_v3_3/option_d_manifest_v3.json",
            root / "evidence/card5_lora_v3_3/option_d_manifest_v2.json",
            Path(__file__).resolve().parents[3] / "manifest.json",
        ]
    )
    for candidate in candidates:
        target = candidate if candidate.is_absolute() else root / candidate
        if target.exists():
            return target
    raise ManifestResolutionError("CARD5_OPTION_D_MANIFEST_NOT_FOUND")

