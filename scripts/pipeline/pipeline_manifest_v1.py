from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def get_git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL)
            .strip()[:12]
        )
    except Exception:
        return "unknown"


def get_config_digest(config: dict) -> str:
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def create_manifest(source_dir: str, output_dir: str, config: dict, stats: dict) -> dict:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": get_git_sha(),
        "config_digest": get_config_digest(config),
        "source_dir": source_dir,
        "output_dir": output_dir,
        "stage_counts": {
            stage: stats.get("stages", {}).get(stage, {})
            for stage in [
                "collect",
                "clean",
                "quality",
                "format",
                "split",
                "quarantine",
            ]
        },
        "elapsed_seconds": stats.get("elapsed_seconds", -1),
    }


def save_manifest(manifest: dict, output_dir: str) -> Path:
    out_path = Path(output_dir) / "pipeline_manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
