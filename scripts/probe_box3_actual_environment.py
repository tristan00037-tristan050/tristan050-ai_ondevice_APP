#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.cards.box3.actual_runner_assets import ActualRunnerAssetConfig, verify_base_model_asset, BASE_MODEL_SHA256_FULL
from butler_pc_core.cards.box3.engine_compat import check_engine_model_compatibility


def main() -> int:
    cfg = ActualRunnerAssetConfig.from_env()
    asset = verify_base_model_asset(cfg)
    engine = check_engine_model_compatibility(asset.model_format if asset.model_format in {"GGUF", "MLX"} else "unknown")
    print(json.dumps({
        "schema_version": "box3.actual_environment_probe.v1",
        "canonical_base_model_sha256_full": BASE_MODEL_SHA256_FULL,
        "asset": asset.to_dict(),
        "engine": engine.to_dict(),
        "real_runtime_pass_claim_allowed": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
