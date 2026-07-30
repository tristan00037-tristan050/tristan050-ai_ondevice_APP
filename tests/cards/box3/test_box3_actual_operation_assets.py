from __future__ import annotations

from pathlib import Path

from butler_pc_core.cards.box3.actual_runner_assets import (
    ActualRunnerAssetConfig,
    sha256_file,
    verify_base_model_asset,
)
from butler_pc_core.cards.box3.helper_component_guard import build_example_component_use_guard, verify_helper_component_use_guard


def test_missing_product_asset_authority_returns_blocked():
    verdict = verify_base_model_asset(ActualRunnerAssetConfig())
    assert verdict.status == "ASSET_AUTHORITY_BLOCKED"
    assert verdict.allowed is False


def test_explicit_test_asset_sha_can_be_verified_without_real_claim(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"test-model")
    sha = sha256_file(model)
    verdict = verify_base_model_asset(
        ActualRunnerAssetConfig(
            expected_base_sha256_full=sha,
            allow_test_asset=True,
            test_asset_path=model,
            readonly_required=False,
        )
    )
    # Engine may be partial if llama_cpp is not installed; SHA itself must be measured.
    assert verdict.sha256_full == sha
    assert verdict.path_digest and verdict.path_digest.startswith("sha256:")


def test_helper_component_use_guard_blocks_when_not_allowed():
    guard = build_example_component_use_guard(allow=False, stack_supported=True)
    verdict = verify_helper_component_use_guard(guard)
    assert verdict.allowed is False
    assert verdict.fail_class == "BLOCK_HELPER_REAL_USE_GUARD_PENDING"


def test_helper_component_use_guard_passes_only_when_allowed_and_stack_supported():
    guard = build_example_component_use_guard(allow=True, stack_supported=True, sdk_call_supported=True, embedder_provider="helper2_sdk")
    verdict = verify_helper_component_use_guard(guard)
    assert verdict.allowed is True
    assert verdict.fail_class is None
