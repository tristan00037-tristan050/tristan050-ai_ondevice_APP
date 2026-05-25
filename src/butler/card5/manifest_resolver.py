from __future__ import annotations

import os
from pathlib import Path


class ManifestResolutionError(RuntimeError):
    pass


def _as_root_path(repo_root: Path | str | None) -> Path:
    if repo_root is None:
        return Path.cwd().resolve()
    return Path(repo_root).expanduser().resolve()


def _resolve_candidate(path: Path | str, root: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def resolve_option_d_manifest(
    repo_root: Path | str | None = None,
    explicit_path: str | Path | None = None,
) -> Path:
    root = _as_root_path(repo_root)
    ordered_candidates: list[Path] = []

    if explicit_path:
        ordered_candidates.append(_resolve_candidate(explicit_path, root))

    env_path = os.environ.get("BUTLER_CARD5_OPTION_D_MANIFEST")
    if env_path:
        ordered_candidates.append(_resolve_candidate(env_path, root))

    for relative in (
        "evidence/card5_lora_v3_3/option_d_manifest_v5.json",
        "evidence/card5_lora_v3_3/option_d_manifest_v3.json",
        "evidence/card5_lora_v3_3/option_d_manifest_v2.json",
    ):
        ordered_candidates.append((root / relative).resolve())

    package_manifest = (Path(__file__).resolve().parents[3] / "manifest.json").resolve()
    ordered_candidates.append(package_manifest)

    for target in ordered_candidates:
        if target.exists():
            return target

    raise ManifestResolutionError("CARD5_OPTION_D_MANIFEST_NOT_FOUND")
