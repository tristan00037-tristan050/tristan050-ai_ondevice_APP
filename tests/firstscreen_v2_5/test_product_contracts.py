from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from butler_pc_core.firstscreen_trust import TrustVerificationError, build_context_digest, validate_build_context
from scripts.release.verify_firstscreen_product_bundle import ProductBundleVerificationError, _safe_name
from scripts.release.firstscreen_source_contracts import PROTECTED_PATHS


pytestmark = pytest.mark.no_sidecar_token
ROOT = Path(__file__).resolve().parents[2]


def _context() -> dict[str, object]:
    return {
        "schema_version": "butler.firstscreen.build-context.v1",
        "mode": "production",
        "repository": "atlink/butler",
        "commit_oid": "1" * 40,
        "tree_oid": "2" * 40,
        "source_manifest_digest": "3" * 64,
        "python_lock_digest": "4" * 64,
        "npm_lock_digest": "5" * 64,
        "cargo_lock_digest": "6" * 64,
        "toolchain_identity": "python=3.12.13;node=24.14.0;rust=1.97.1",
        "workflow_identity": "atlink/butler/.github/workflows/firstscreen-v2-5.yml@refs/heads/main",
        "created_at_utc": "2026-07-21T00:00:00Z",
    }


@pytest.mark.parametrize(
    "attack,field,value",
    [
        ("BI-003-context-mode", "mode", "development"),
        ("BI-004-short-commit", "commit_oid", "1" * 12),
        ("BI-004-short-tree", "tree_oid", "2" * 12),
        ("BI-005-dev-fallback", "commit_oid", "dev"),
        ("BI-005-unknown-fallback", "tree_oid", "unknown"),
        ("BI-007-repository", "repository", "attacker"),
        ("BI-007-workflow", "workflow_identity", "short"),
        ("BI-lock-digest", "npm_lock_digest", "0" * 63),
    ],
)
def test_build_context_attack_contract(attack: str, field: str, value: object) -> None:
    document = _context()
    document[field] = value
    with pytest.raises(TrustVerificationError):
        validate_build_context(document)


def test_build_context_digest_is_order_independent() -> None:
    document = _context()
    reversed_document = dict(reversed(list(document.items())))
    assert build_context_digest(document) == build_context_digest(reversed_document)


@pytest.mark.parametrize(
    "attack,required,forbidden",
    [
        ("EX-001", "EXPORT_EXTENSION_MISMATCH", "set_extension"),
        ("EX-002", "ReplaceFileW", "remove_file(path)"),
        ("EX-003", "EXPORT_ATOMIC_REPLACE_FAILED", "EXPORT_REPLACE_FAILED"),
        ("EX-004", "sync_all", "SystemTime::now"),
        ("EX-005", "EXPORT_DIRECTORY_SYNC_FAILED", "EXPORT_PUBLISH_FAILED"),
        ("EX-006", "is_reparse_or_symlink", "canonicalize()"),
        ("EX-007", "EXPORT_TARGET_INVALID", "EXPORT_PARENT_INVALID"),
        ("EX-008", "EXPORT_WRITE_FAILED", "format!(\"EXPORT_WRITE_FAILED"),
        ("EX-009", "snapshot_unchanged", "MOVEFILE_REPLACE_EXISTING"),
        ("EX-010-N", "MAX_EXPORT_BYTES", "64 * 1024 * 1024 + 1;"),
        ("EX-CSPRNG", "BCryptGenRandom", "UNIX_EPOCH"),
        ("EX-NO-REPLACE", "libc::linkat", "path.set_extension"),
        ("EX-DIRFD-PIN", "libc::openat", "libc::open("),
        ("EX-NOFOLLOW", "libc::O_NOFOLLOW", "canonicalize()"),
        ("EX-HANDLE-RENAME", "renameatx_np", "fs::rename(temporary, target)"),
        ("EX-ATOMIC-CAS", "RENAME_SWAP", "RENAME_NOREPLACE"),
    ],
)
def test_native_export_source_contract(attack: str, required: str, forbidden: str) -> None:
    source = (ROOT / "butler-desktop/src-tauri/src/export.rs").read_text(encoding="utf-8")
    assert required in source, attack
    assert forbidden not in source, attack


def test_accounting_review_is_not_part_of_firstscreen_change_scope() -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("requires Git context; no-git scope is verified from the source manifest")
    changed = __import__("subprocess").run(
        ["git", "diff", "--name-only", "HEAD^", "HEAD", "--", *PROTECTED_PATHS],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert changed == ""


def test_protected_scope_contract_blocks_real_product_path_mutation(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    protected = repository / PROTECTED_PATHS[1] / "contracts.ts"
    protected.parent.mkdir(parents=True)
    protected.write_text("export const protectedValue = 1;\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "contract-test"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "contract-test@invalid"], cwd=repository, check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)
    baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    protected.write_text("export const protectedValue = 2;\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "attack"], cwd=repository, check=True)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/release/firstscreen_source_contracts.py"), "--check-unchanged", baseline, "HEAD"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert str(PROTECTED_PATHS[1]) in result.stdout


def test_build_context_uses_the_same_protected_scope_authority() -> None:
    source = (ROOT / "scripts/release/build_with_git.py").read_text(encoding="utf-8")
    assert "from scripts.release.firstscreen_source_contracts import changed_protected_paths" in source
    assert "changed_protected_paths(baseline, commit" in source
    assert '"accounting_review", root=root' not in source


def test_native_release_binary_requires_and_embeds_build_context_digest() -> None:
    build_script = (ROOT / "butler-desktop/src-tauri/build.rs").read_text(encoding="utf-8")
    build_gate = (ROOT / "butler-desktop/src-tauri/build_gate.rs").read_text(encoding="utf-8")
    identity = (ROOT / "butler-desktop/src-tauri/src/build_identity.rs").read_text(encoding="utf-8")
    assert "BUILD_CONTEXT_DIGEST_REQUIRED" in build_script
    assert "mod build_gate;" in build_script
    assert "build_gate::evaluate_build_gate(" in build_script
    assert 'Err("BUILD_CONTEXT_DIGEST_INVALID")' in build_gate
    assert "cargo:rustc-env=BUTLER_BUILD_CONTEXT_DIGEST" in build_script
    assert 'env!("BUTLER_BUILD_CONTEXT_DIGEST")' in identity


def test_handoff_regression_runs_on_macos_and_blocks_the_gate() -> None:
    """인계 권한복구는 macOS 전용 스크립트다. 회귀가 실제 대상 OS 에서 돌아야 한다.

    ubuntu job 에서만 돌면 plutil 분기가 CI 에서 한 번도 실행되지 않는다.
    """
    workflow = (ROOT / ".github/workflows/firstscreen-v2-5.yml").read_text(encoding="utf-8")
    assert "handoff-macos:" in workflow
    macos_job = workflow[workflow.index("handoff-macos:") : workflow.index("\n  gate:")]
    assert "runs-on: macos-15" in macos_job
    assert "command -v plutil" in macos_job
    assert "tests/test_handoff_restore_permissions.py" in macos_job
    # skip 은 실행되지 않은 것과 같다 — 게이트가 skip 을 통과시키면 안 된다.
    assert "skipped cases" in macos_job
    assert "HANDOFF_MACOS_GATE_FAILED" in macos_job

    gate_job = workflow[workflow.index("\n  gate:") :]
    assert "handoff-macos" in gate_job, "집계 gate 가 macOS job 을 기다려야 한다"
    assert 'test "${HANDOFF_MACOS}" = success' in gate_job


def test_repository_python_gate_uses_documented_collection_exclusions() -> None:
    workflow = (ROOT / ".github/workflows/firstscreen-v2-5.yml").read_text(encoding="utf-8")
    repository_commands = [
        line.strip()
        for line in workflow.splitlines()
        if "python -m pytest tests/" in line
        and ("--collect-only" in line or "repository-junit.xml" in line)
    ]
    assert len(repository_commands) == 2
    for command in repository_commands:
        assert "--import-mode=importlib" not in command
        assert "--ignore=tests/turboq/" in command
        assert "--ignore=tests/eval/test_eval_hardcase.py" in command
        assert "--ignore=tests/eval/test_eval_judge_v3.py" in command


def test_firstscreen_sbom_attestation_verification_is_bound_and_index_independent() -> None:
    """배선(어느 스텝의 bundle 을 쓰는가)만 본다.

    ★인자 '값'이 맞는지는 여기서 판정하지 않는다. 문자열 존재 검사는 값이 틀려도 그대로
    정본으로 굳기 때문이다. --source-digest·--source-ref 의 값 판정은
    tests/firstscreen_v2_5/test_attestation_verification.py 가 ★실물 attestation 인증서
    확장값과 대조해서, 그리고 gh attestation verify 를 실제로 실행해서 수행한다.
    """
    workflow = (ROOT / ".github/workflows/product-verify-supplychain.yml").read_text(encoding="utf-8")
    assert "id: attest_firstscreen_sbom" in workflow
    assert (
        "FIRSTSCREEN_ATTESTATION_BUNDLE: \"${{ steps.attest_firstscreen_sbom.outputs['bundle-path'] }}\""
        in workflow
    )
    assert '--bundle "${FIRSTSCREEN_ATTESTATION_BUNDLE}"' in workflow
    assert "ATTESTATION_BUNDLE_UNAVAILABLE" in workflow
    # 색인 지연을 재시도로 넘기던 우회는 제거된 상태여야 한다.
    assert "ATTESTATION_VERIFY_RETRY" not in workflow


def test_outer_bundle_is_ascii_but_nested_git_source_accepts_safe_utf8() -> None:
    with pytest.raises(ProductBundleVerificationError, match="PATH_NOT_ASCII"):
        _safe_name("source/한글.txt")
    assert _safe_name("source/한글.txt", ascii_only=False) == "source/한글.txt"
    with pytest.raises(ProductBundleVerificationError, match="PATH_INVALID"):
        _safe_name("source/../escape.txt", ascii_only=False)
