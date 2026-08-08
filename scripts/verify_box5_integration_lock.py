#!/usr/bin/env python3
"""Verify the Box5 integration lock from Git objects, never caller claims."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "integration_lock.json"
REPOSITORY = "github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP"
APPROVED_BASE_COMMIT = "de3dd4ebaf5b3935a142b988dd61e6198aa9536d"
APPROVED_BASE_TREE = "8c3509db047145714d2a1a84dfc76fb0a4c0fec9"
_OID = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_CRITICAL_PATHS = frozenset(
    {
        ".github/workflows/box5-stage3.yml",
        "butler-desktop/src-tauri/build.rs",
        "butler-desktop/src-tauri/capabilities/box5-authority.json",
        "butler-desktop/src-tauri/native/box5_user_authority_launcher.swift",
        "butler-desktop/src-tauri/native/box5_user_authority_protocol.swift",
        "butler-desktop/src-tauri/permissions/box5-authority.toml",
        "butler-desktop/src-tauri/src/lib.rs",
        "butler-desktop/src/lib/accounting_review/client.ts",
        "butler-desktop/src/lib/accounting_review/nativeAuthorizedRequest.ts",
        "butler-desktop/src/lib/accounting_review/nativeAuthorizedRequest.test.ts",
        "butler_pc_core/accounting/assignment/adapters.py",
        "butler_pc_core/accounting/assignment/authorization.py",
        "butler_pc_core/accounting/assignment/authorization_replay.py",
        "butler_pc_core/accounting/assignment/contracts/action_nonce_response.schema.json",
        "butler_pc_core/accounting/assignment/contracts/authority-bound-event-v2.schema.json",
        "butler_pc_core/accounting/assignment/contracts/authorization-decision-v2.schema.json",
        "butler_pc_core/accounting/assignment/contracts/authorization-replay-v2.sql",
        "butler_pc_core/accounting/assignment/contracts/integration_lock.schema.json",
        "butler_pc_core/accounting/assignment/contracts/native-authority-request-v2.schema.json",
        "butler_pc_core/accounting/assignment/contracts/protected-header-v2.schema.json",
        "butler_pc_core/accounting/assignment/contracts/trust-policy-v2.schema.json",
        "butler_pc_core/accounting/assignment/contracts/user-assertion-v2.schema.json",
        "butler_pc_core/accounting/assignment/domain.py",
        "butler_pc_core/accounting/assignment/router.py",
        "butler_pc_core/accounting/assignment/runtime.py",
        "butler_pc_core/accounting/assignment/stage3_store_schema_v3.py",
        "butler_pc_core/accounting/assignment/store.py",
        "butler_pc_core/accounting/assignment/contracts/authorization-audit-v2.schema.json",
        "butler_pc_core/auth/capability_token.py",
        "butler_pc_core/company_policy/admin_auth.py",
        "butler_pc_core/company_policy/contracts.py",
        "butler_pc_core/company_policy/role_registry.py",
        "butler_sidecar.py",
        "scripts/ci/trusted_parse_junit_xml.py",
        "scripts/ci/trusted_firstscreen_mutations.mjs",
        "scripts/ci/verify_box5_junit_evidence.py",
        "scripts/audit/reproduce_box5_ac11_schema_constraints_v1.py",
        "scripts/build_box5_user_authority_helper_macos.sh",
        "scripts/build_complete_app.sh",
        "scripts/verify_box5_authorization_audit.py",
        "scripts/verify_box5_integration_lock.py",
        "scripts/write_build_info.py",
        "schemas/candidate-artifact-identity-v1.schema.json",
        "tools/ac23/archive_safety.py",
        "tools/ac23/build_candidate_artifact_identity.py",
        "tools/ac23/collect_ac23_evidence.py",
        "tools/ac23/collect_final_package_matrix.py",
        "tools/ac23/evidence_policy_v3.json",
        "tools/ac23/junit_closed_profile.py",
        "tools/ac23/package_ac23.sh",
        "tools/ac23/run_ac23_mutations.py",
        "tools/ac23/strict_json.py",
        "tools/ac23/verify_external_test_evidence.py",
        "tools/ac23/verify_candidate_artifact_identity.py",
        "tests/ac23/test_candidate_artifact_identity.py",
        "tests/ac23/test_evidence_semantics.py",
        "tests/ac23/test_junit_closed_profile.py",
        "tests/ac23/test_verifier_purity.py",
        "tests/accounting/assignment/test_authorization_product_route.py",
        "tests/accounting/assignment/test_ac11_schema_matrix_verifier.py",
        "tests/accounting/assignment/test_authorization_replay_round3.py",
        "tests/accounting/assignment/test_authorization_wire_round3.py",
        "tests/accounting/assignment/authorization_testkit.py",
        "tests/accounting/assignment/test_box5_integration_lock_v2.py",
        "tests/firstscreen_trusted/test_trusted_junit_semantics_box5.py",
        "tests/fixtures/box5_ua2_golden_v1.json",
        "tests/fixtures/box5_ac11_schema_mutations_v1.json",
        "tests/test_write_build_info.py",
    }
)
APPROVED_ALLOWED_PATTERNS = (
    ".github/workflows/box5-stage3.yml",
    "butler-desktop/src-tauri/build.rs",
    "butler-desktop/src-tauri/capabilities/box5-authority.json",
    "butler-desktop/src-tauri/native/box5_user_authority_*.swift",
    "butler-desktop/src-tauri/permissions/box5-authority.toml",
    "butler-desktop/src-tauri/src/lib.rs",
    "butler-desktop/src/lib/accounting_review/**",
    "butler-desktop/src/components/accounting_review/**",
    "butler-desktop/src/__tests__/AccountingReviewPage.test.tsx",
    "butler_pc_core/accounting/assignment/**",
    "butler_pc_core/accounting/classify/**",
    "butler_pc_core/auth/capability_token.py",
    "butler_pc_core/company_policy/middleware.py",
    "butler_sidecar.py",
    "integration_lock.json",
    "schemas/candidate-artifact-identity-v1.schema.json",
    "scripts/audit/reproduce_box5_contract_forgery_v2.py",
    "scripts/audit/reproduce_box5_ac11_schema_constraints_v1.py",
    "scripts/build_box5_user_authority_helper_macos.sh",
    "scripts/build_complete_app.sh",
    "scripts/ci/parse_junit_xml.py",
    "scripts/ci/trusted_parse_junit_xml.py",
    "scripts/ci/trusted_firstscreen_mutations.mjs",
    "scripts/ci/verify_box5_junit_evidence.py",
    "scripts/verify_box5_authorization_audit.py",
    "scripts/verify_box5_integration_lock.py",
    "scripts/write_build_info.py",
    "tools/ac23/**",
    "tests/ac23/**",
    "tests/accounting/assignment/**",
    "tests/accounting/classify/**",
    "tests/auth/test_capability_token.py",
    "tests/firstscreen_trusted/test_parser_isolation_differential.py",
    "tests/firstscreen_trusted/test_trusted_junit_semantics_box5.py",
    "tests/fixtures/box5_ua2_golden_v1.json",
    "tests/fixtures/box5_ac11_schema_mutations_v1.json",
    "tests/test_write_build_info.py",
)
REQUIRED_SOURCE_PACKAGE_SHA256 = frozenset(
    {
        "3433df7ca733ea641f001c5c0f6c27ab11a09456b492a8309cc5df22fd27c8e5",
        "2c65cb6c7260857ba69317d1e59d0f0f2d5917a5a091c27410cba0c0d0a69047",
        "08c558a1192d37804531212ee5a9e881166b7795288804959e707462c1080f01",
    }
)


def _git(*arguments: str, input_text: str | None = None) -> str:
    return subprocess.check_output(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        input=input_text,
        stderr=subprocess.DEVNULL,
    ).strip()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _changed_paths(base: str, *, worktree: bool) -> set[str]:
    arguments = ["diff", "--name-only", "--diff-filter=ACMRTUXB"]
    arguments += [base] if worktree else [f"{base}..HEAD"]
    changed = {line for line in _git(*arguments).splitlines() if line}
    if worktree:
        changed.update(
            line
            for line in _git("ls-files", "--others", "--exclude-standard").splitlines()
            if line
        )
    return changed


def _canonical_remote(value: str) -> str:
    normalized = value.removesuffix(".git").replace("git@github.com:", "github.com/")
    normalized = normalized.replace("ssh://git@github.com/", "github.com/")
    normalized = normalized.replace("https://github.com/", "github.com/")
    return normalized


def _observed_remote_identity() -> str:
    value = _git("remote", "get-url", "origin")
    local_mirror = Path(value)
    if local_mirror.is_dir():
        value = subprocess.check_output(
            ["git", "-C", str(local_mirror.resolve()), "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    return _canonical_remote(value)


def refresh_candidate_lock() -> dict[str, object]:
    """Mechanically refresh the unsigned candidate lock from local bytes.

    This never creates an approval signature and therefore cannot turn a
    candidate into a release. It exists to prevent hand-edited path/digest
    drift before independent attestation.
    """

    if _observed_remote_identity() != REPOSITORY:
        raise RuntimeError("REMOTE_IDENTITY_MISMATCH")
    if _git("show", "-s", "--format=%T", APPROVED_BASE_COMMIT) != APPROVED_BASE_TREE:
        raise RuntimeError("BASE_TREE_MISMATCH")
    _git("merge-base", "--is-ancestor", APPROVED_BASE_COMMIT, "HEAD")
    critical: dict[str, dict[str, object]] = {}
    for relative in sorted(REQUIRED_CRITICAL_PATHS):
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("CRITICAL_FILE_INVALID")
        raw = path.read_bytes()
        critical[relative] = {
            "mode": "100755" if os.access(path, os.X_OK) else "100644",
            "blob_oid": _git("hash-object", "--", relative),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        }
    now = datetime.now(timezone.utc).replace(microsecond=0)
    document: dict[str, object] = {
        "schema_version": "butler.integration_lock.v2",
        "repository": REPOSITORY,
        "approved_base_commit": APPROVED_BASE_COMMIT,
        "approved_base_tree": APPROVED_BASE_TREE,
        "critical_files": critical,
        "critical_manifest_sha256": hashlib.sha256(_canonical(critical)).hexdigest(),
        "source_package_sha256": sorted(REQUIRED_SOURCE_PACKAGE_SHA256),
        "allowed_paths": list(APPROVED_ALLOWED_PATTERNS),
        "owner": "알고리즘 개발팀12(온디바이스)",
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(days=7)).isoformat().replace("+00:00", "Z"),
    }
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            dir=ROOT, prefix=".integration_lock.", suffix=".tmp"
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, LOCK_PATH)
        temporary = None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return document


def verify(
    *,
    allow_worktree_base: bool = False,
    expected_head: str | None = None,
) -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    if lock.get("schema_version") != "butler.integration_lock.v2":
        failures.append("LOCK_SCHEMA_INVALID")
    if lock.get("repository") != REPOSITORY:
        failures.append("REPOSITORY_IDENTITY_MISMATCH")
    try:
        if _observed_remote_identity() != REPOSITORY:
            failures.append("REMOTE_IDENTITY_MISMATCH")
    except (OSError, subprocess.CalledProcessError):
        failures.append("REMOTE_IDENTITY_UNAVAILABLE")
    base = str(lock.get("approved_base_commit", ""))
    base_tree = str(lock.get("approved_base_tree", ""))
    if not _OID.fullmatch(base) or not _OID.fullmatch(base_tree):
        failures.append("BASE_IDENTITY_INVALID")
    else:
        try:
            if _git("show", "-s", "--format=%T", base) != base_tree:
                failures.append("BASE_TREE_MISMATCH")
            _git("merge-base", "--is-ancestor", base, "HEAD")
        except (OSError, subprocess.CalledProcessError):
            failures.append("BASE_ANCESTRY_INVALID")

    head = _git("rev-parse", "HEAD")
    head_tree = _git("show", "-s", "--format=%T", "HEAD")
    if expected_head is not None and (
        not _OID.fullmatch(expected_head) or expected_head != head
    ):
        failures.append("EXACT_HEAD_MISMATCH")
    worktree = bool(_git("status", "--porcelain"))
    if worktree and not allow_worktree_base:
        failures.append("WORKTREE_NOT_CLEAN")

    critical = lock.get("critical_files")
    if not isinstance(critical, dict) or set(critical) != REQUIRED_CRITICAL_PATHS:
        failures.append("CRITICAL_PATH_SET_MISMATCH")
        critical = {}
    for relative in sorted(REQUIRED_CRITICAL_PATHS):
        expected = critical.get(relative)
        path = ROOT / relative
        if not isinstance(expected, dict) or not path.is_file() or path.is_symlink():
            failures.append("CRITICAL_FILE_INVALID")
            continue
        raw = path.read_bytes()
        observed_sha = hashlib.sha256(raw).hexdigest()
        observed_blob = _git("hash-object", "--", relative)
        observed_mode = "100755" if os.access(path, os.X_OK) else "100644"
        if (
            not _DIGEST.fullmatch(str(expected.get("sha256", "")))
            or not _OID.fullmatch(str(expected.get("blob_oid", "")))
            or expected.get("size") != len(raw)
            or expected.get("sha256") != observed_sha
            or expected.get("blob_oid") != observed_blob
            or expected.get("mode") != observed_mode
        ):
            failures.append("CRITICAL_FILE_IDENTITY_MISMATCH")
        if not worktree:
            try:
                tree_entry = _git("ls-tree", "HEAD", "--", relative).split()
            except (OSError, subprocess.CalledProcessError):
                failures.append("CRITICAL_GIT_OBJECT_MISSING")
            else:
                if (
                    len(tree_entry) != 4
                    or tree_entry[0] != observed_mode
                    or tree_entry[2] != observed_blob
                ):
                    failures.append("CRITICAL_GIT_OBJECT_MISMATCH")

    manifest_digest = hashlib.sha256(_canonical(critical)).hexdigest()
    if lock.get("critical_manifest_sha256") != manifest_digest:
        failures.append("CRITICAL_MANIFEST_DIGEST_MISMATCH")
    source_digests = lock.get("source_package_sha256")
    if (
        not isinstance(source_digests, list)
        or set(source_digests) != REQUIRED_SOURCE_PACKAGE_SHA256
        or len(source_digests) != len(set(source_digests))
        or any(not _DIGEST.fullmatch(str(value)) for value in source_digests)
    ):
        failures.append("SOURCE_PACKAGE_DIGEST_INVALID")

    allowed = lock.get("allowed_paths")
    if not isinstance(allowed, list) or tuple(allowed) != APPROVED_ALLOWED_PATTERNS:
        failures.append("ALLOWED_PATHS_INVALID")
        allowed = list(APPROVED_ALLOWED_PATTERNS)
    try:
        changed = _changed_paths(base, worktree=worktree)
    except (OSError, subprocess.CalledProcessError):
        failures.append("CHANGED_PATHS_UNAVAILABLE")
        changed = set()
    if any(not any(fnmatch.fnmatch(path, pattern) for pattern in allowed) for path in changed):
        failures.append("CHANGED_PATH_OUTSIDE_ALLOWLIST")

    try:
        created = datetime.fromisoformat(str(lock["created_at"]).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(lock["expires_at"]).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if not created < now < expires:
            failures.append("LOCK_VALIDITY_INVALID")
    except (KeyError, TypeError, ValueError):
        failures.append("LOCK_TIME_INVALID")

    if failures:
        raise RuntimeError(";".join(sorted(set(failures))))
    return {
        "schema_version": "butler.integration_lock.verification.v2",
        "repository": REPOSITORY,
        "base_commit": base,
        "base_tree": base_tree,
        "head_commit": head,
        "head_tree": head_tree,
        "critical_manifest_sha256": manifest_digest,
        "changed_path_count": len(changed),
        "candidate_only": worktree,
        # Compatibility keys remain derived observations, never lock claims.
        "route_inventory_digest": hashlib.sha256(
            (ROOT / "butler_pc_core/accounting/assignment/router.py").read_bytes()
        ).hexdigest(),
        "contract_closure_digest": hashlib.sha256(
            _canonical(sorted(
                path.name
                for path in (ROOT / "butler_pc_core/accounting/assignment/contracts").glob("*.json")
            ))
        ).hexdigest(),
        "ui_tokens_digest": hashlib.sha256(
            (ROOT / "butler-desktop/src/lib/accounting_review/client.ts").read_bytes()
        ).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-candidate-lock", action="store_true")
    parser.add_argument("--allow-worktree-base", action="store_true")
    parser.add_argument("--expected-head", default=os.environ.get("GITHUB_SHA"))
    args = parser.parse_args()
    if args.refresh_candidate_lock:
        try:
            lock = refresh_candidate_lock()
        except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
            print("STATUS=BLOCK")
            print(f"ERROR_CODE={str(exc) if str(exc).isascii() else 'LOCK_REFRESH_FAILED'}")
            return 1
        print("STATUS=CANDIDATE_LOCK_REFRESHED")
        print(f"CRITICAL_MANIFEST_SHA256={lock['critical_manifest_sha256']}")
        return 0
    try:
        result = verify(
            allow_worktree_base=args.allow_worktree_base,
            expected_head=args.expected_head,
        )
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        code = str(exc)
        if not code.isascii() or len(code) > 160:
            code = "INTEGRATION_LOCK_VERIFICATION_FAILED"
        print("STATUS=BLOCK")
        print(f"ERROR_CODE={code}")
        return 1
    print("STATUS=CANDIDATE" if result["candidate_only"] else "STATUS=PASS")
    print(f"HEAD_COMMIT={result['head_commit']}")
    print(f"HEAD_TREE={result['head_tree']}")
    print(f"CRITICAL_MANIFEST_SHA256={result['critical_manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
