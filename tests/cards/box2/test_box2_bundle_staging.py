from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.stage_box2_adapter import StageError, stage_box2_adapter


def _source_adapter(root: Path, weights: bytes = b"sealed-box2-weights") -> tuple[Path, str]:
    source = root / "box2_adapter"
    adapter = source / "rewrite/adapter/box2b_v5_rewrite"
    adapter.mkdir(parents=True)
    (adapter / "adapter_model.safetensors").write_bytes(weights)
    (adapter / "adapter_config.json").write_text(
        json.dumps(
            {
                "peft_type": "LORA",
                "task_type": "CAUSAL_LM",
                "inference_mode": True,
                "target_modules": ["q_proj", "v_proj"],
            }
        ),
        encoding="utf-8",
    )
    (source / "tool_call").mkdir()
    (source / "tool_call" / "receipt.json").write_text("{}", encoding="utf-8")
    return source, hashlib.sha256(weights).hexdigest()


def test_stager_copies_full_asset_and_seals_runtime_weight(tmp_path):
    source, expected_sha256 = _source_adapter(tmp_path / "source")
    destination = tmp_path / "bundle/models/box2/box2_adapter"

    receipt = stage_box2_adapter(
        source,
        destination,
        expected_weight_sha256=expected_sha256,
    )

    assert receipt.file_count == 3
    assert receipt.total_bytes > 0
    assert len(receipt.manifest_sha256) == 64
    assert receipt.rewrite_weight_sha256 == expected_sha256
    assert (
        destination
        / "rewrite/adapter/box2b_v5_rewrite/adapter_model.safetensors"
    ).read_bytes() == b"sealed-box2-weights"
    assert (destination / "tool_call/receipt.json").is_file()


def test_stager_fails_closed_when_source_is_missing(tmp_path):
    with pytest.raises(StageError, match="BOX2_ADAPTER_SOURCE_MISSING"):
        stage_box2_adapter(
            tmp_path / "missing",
            tmp_path / "destination",
            expected_weight_sha256="0" * 64,
        )


def test_stager_rejects_weight_digest_mismatch(tmp_path):
    source, _ = _source_adapter(tmp_path / "source")

    with pytest.raises(StageError, match="BOX2_ADAPTER_WEIGHT_SHA_MISMATCH"):
        stage_box2_adapter(
            source,
            tmp_path / "destination",
            expected_weight_sha256="0" * 64,
        )


def test_stager_rejects_symlinked_asset_entry(tmp_path):
    source, expected_sha256 = _source_adapter(tmp_path / "source")
    (source / "unsafe-link").symlink_to(
        source / "rewrite/adapter/box2b_v5_rewrite/adapter_model.safetensors"
    )

    with pytest.raises(StageError, match="BOX2_ADAPTER_UNSAFE_ENTRY"):
        stage_box2_adapter(
            source,
            tmp_path / "destination",
            expected_weight_sha256=expected_sha256,
        )


def test_stager_replaces_previous_bundle_atomically(tmp_path):
    source, expected_sha256 = _source_adapter(tmp_path / "source")
    destination = tmp_path / "bundle/models/box2/box2_adapter"
    destination.mkdir(parents=True)
    (destination / "stale.txt").write_text("stale", encoding="utf-8")

    stage_box2_adapter(
        source,
        destination,
        expected_weight_sha256=expected_sha256,
    )

    assert not (destination / "stale.txt").exists()
    assert (
        destination
        / "rewrite/adapter/box2b_v5_rewrite/adapter_model.safetensors"
    ).is_file()


def test_complete_app_build_requires_box2_stage():
    root = Path(__file__).resolve().parents[3]
    build_script = (root / "scripts/build_complete_app.sh").read_text(
        encoding="utf-8"
    )

    assert "scripts/stage_box2_adapter.py" in build_script
    assert "BUTLER_BOX2_ADAPTER_SRC" in build_script
    assert "BOX2_ADAPTER_STAGE_FAILED" in build_script
    assert "BUTLER_ALLOW_MISSING_BOX2" not in build_script
