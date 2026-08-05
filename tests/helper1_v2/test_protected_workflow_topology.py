from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / ".github/workflows/helper1-v2-evidence.yml"
TRUSTED = ROOT / ".github/workflows/helper1-v2-trusted-verifier.yml"
POLICY = ROOT / "contracts/helper1/trusted-verifier-policy-v1.json"
VERIFIER = ROOT / "scripts/ci/helper1_trusted_verifier.py"
SUBJECT_BINDING = ROOT / "scripts/ci/helper1_subject_binding.py"
SEMANTICS = ROOT / "scripts/ci/helper1_evidence_semantics.py"
PUBLISHER = ROOT / "scripts/ci/publish_helper1_subject_check.py"
PACKAGE_VERIFIER = ROOT / "scripts/verify_helper1_v51_package.py"
PRODUCER_PACKAGE = ROOT / "scripts/ci/helper1_producer_package.py"
POSTGRES_PROBE = ROOT / "scripts/ci/helper1_postgresql_replay_probe.py"
PRODUCT_APPROVAL_BUNDLE = ROOT / "scripts/ci/helper1_product_approval_bundle.py"
APPROVAL_CLOSURE = ROOT / "butler_pc_core/helper1/approval_closure.py"
CANONICAL_JSON = ROOT / "butler_pc_core/helper1/canonical_json.py"
EXECUTION = ROOT / "butler_pc_core/helper1/execution.py"
REPLAY_STORE = ROOT / "butler_pc_core/helper1/replay_store.py"
RETRIEVAL_POLICY = ROOT / "butler_pc_core/helper1/retrieval_policy.py"
CODEOWNERS = ROOT / ".github/CODEOWNERS"
PROTECTED_SURFACE = ROOT / "scripts/ci/helper1_protected_surface.py"


def _load_producer_package_module():
    spec = importlib.util.spec_from_file_location(
        "helper1_producer_package_fixture", PRODUCER_PACKAGE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_trusted_verifier_module():
    spec = importlib.util.spec_from_file_location(
        "helper1_trusted_verifier_fixture", VERIFIER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(VERIFIER.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _quality_fixture(root: Path, *, commit: str, tree: str, run_id: str) -> Path:
    from butler_pc_core.helper1.quality_evidence import (
        MANIFEST_NAME,
        QUALITY_FILES,
        build_manifest,
    )

    payloads: dict[str, bytes] = {}
    for name in QUALITY_FILES:
        raw = b"observer" if name.endswith("observer.bin") else b"{}\n"
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        payloads[name] = raw
    (root / MANIFEST_NAME).write_bytes(
        build_manifest(
            payloads,
            source_commit=commit,
            source_tree=tree,
            evaluation_run_id=run_id,
            evaluation_run_attempt=1,
            producer_run_id=run_id,
            producer_run_attempt=1,
            workflow_id=1,
            workflow_ref=f"owner/repo/.github/workflows/helper1-v2-evidence.yml@{commit}",
            workflow_sha256="a" * 64,
        )
    )
    return root


def _producer_artifact(tmp_path: Path):
    module = _load_producer_package_module()
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    tree = subprocess.run(
        ("git", "rev-parse", "HEAD^{tree}"),
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    artifact = tmp_path / "helper1-producer-artifact"
    inputs = tmp_path / "inputs"
    evidence = inputs / "test-evidence"
    evidence.mkdir(parents=True)
    subject = {
        "schema_version": "butler.helper1.canonical-subject.v1",
        "repository_full_name": "tristan00037-tristan050/tristan050-ai_ondevice_APP",
        "subject_sha": commit,
    }
    subject_path = inputs / "CANONICAL_SUBJECT.json"
    subject_path.write_bytes(_canonical(subject) + b"\n")
    submission = {
        "schema_version": "butler.helper1.untrusted-submission.v1",
        "run_id": "fixture:1",
        "subject_commit": commit,
        "canonical_subject_sha256": hashlib.sha256(_canonical(subject)).hexdigest(),
        "product_evidence_present": True,
    }
    submission_path = inputs / "SUBMISSION.json"
    submission_path.write_bytes(_canonical(submission) + b"\n")
    index = {
        "schema_version": "butler.helper1.test-evidence-index.v1",
        "source_tree": tree,
        "lanes": [
            {"lane_id": lane, "status": status}
            for lane, status in sorted(module.EXPECTED_LANES.items())
        ],
        "checks": [
            {"check_id": check, "status": "PASSED"}
            for check in sorted(module.EXPECTED_CHECKS)
        ],
        "required_lanes_blocked": 1,
        "all_required_lanes_passed": False,
        "all_required_checks_passed": True,
    }
    (evidence / "TEST_EVIDENCE_INDEX.v1.json").write_bytes(_canonical(index))
    product = inputs / "product-approval"
    legacy = product / "legacy"
    approval = product / "approval"
    objects = product / "objects"
    legacy.mkdir(parents=True)
    approval.mkdir()
    objects.mkdir()
    bundle_module = sys.modules[module.load_product_approval_bundle.__module__]
    for name in bundle_module.LEGACY_FILES:
        (legacy / name).write_bytes(_canonical({"fixture": name}))
    for name in bundle_module.APPROVAL_FILES:
        (approval / name).write_bytes(_canonical({"fixture": name}))
    object_raw = b"product-approval-object"
    (objects / hashlib.sha256(object_raw).hexdigest()).write_bytes(object_raw)
    product_files = {
        f"legacy/{item.name}": item.read_bytes() for item in legacy.iterdir()
    }
    product_files.update(
        {f"approval/{item.name}": item.read_bytes() for item in approval.iterdir()}
    )
    product_files.update(
        {f"objects/{item.name}": item.read_bytes() for item in objects.iterdir()}
    )
    product_manifest = bundle_module.build_manifest(
        product_files,
        subject_commit=commit,
        subject_tree=tree,
        producer_run="fixture:1",
    )
    (product / "MANIFEST.json").write_bytes(_canonical(product_manifest) + b"\n")
    quality = _quality_fixture(inputs / "quality", commit=commit, tree=tree, run_id="fixture:1")
    approval_input = inputs / "approval-input.zip"
    approval_input.write_bytes(b"fixture-approval-input")
    provenance = inputs / "APPROVAL_INPUT_PROVENANCE.v2.json"
    provenance.write_bytes(_canonical({
        "schema_version": "butler.helper1.approval-input-provenance.v2",
        "mode": "ARTIFACT",
        "repository_id": 1,
        "repository_name": subject["repository_full_name"],
        "subject_commit": commit,
        "subject_tree": tree,
        "producer_workflow_ref": f'{subject["repository_full_name"]}/.github/workflows/helper1-v2-approval-evidence.yml@{commit}',
        "producer_workflow_id": 1,
        "producer_workflow_sha256": "a" * 64,
        "run_id": 1,
        "run_attempt": 1,
        "event_name": "workflow_dispatch",
        "artifact_id": 1,
        "artifact_name": "fixture-approval",
        "artifact_sha256": hashlib.sha256(approval_input.read_bytes()).hexdigest(),
        "inventory_sha256": "b" * 64,
        "canonical_subject_sha256": hashlib.sha256(_canonical(subject)).hexdigest(),
    }) + b"\n")
    module.verify_approval_input_bytes = lambda *_args, **_kwargs: None
    descriptor = module.build(
        artifact, subject_path, submission_path, evidence, product, quality,
        approval_input, provenance,
    )
    return module, artifact, subject_path, descriptor


def test_trusted_verifier_runs_from_protected_default_branch_only():
    producer = PRODUCER.read_text(encoding="utf-8")
    trusted = TRUSTED.read_text(encoding="utf-8")

    assert "workflow_run:" in trusted
    assert "workflows: [helper1-v2-evidence-producer]" in trusted
    assert "ref: ${{ github.sha }}" in trusted
    assert "persist-credentials: false" in trusted
    assert "checks: write" in trusted
    assert "environment: helper1-production-verifier" in trusted
    assert "HELPER1_APPROVAL_REPLAY_DSN: ${{ secrets.HELPER1_APPROVAL_REPLAY_DSN }}" in trusted
    assert "python scripts/ci/helper1_postgresql_replay_probe.py" in trusted
    assert "HELPER1_REPLAY_PROBE_RUN_ID: ${{ github.run_id }}-${{ github.run_attempt }}" in trusted
    assert "HELPER1_REPLAY_PROBE_OUTCOME: ${{ steps.replay-store-probe.outcome }}" in trusted
    assert "REPLAY_PROBE_OUTCOME: ${{ steps.replay-store-probe.outcome }}" in trusted
    assert "HELPER1_APPROVAL_REPLAY_DB" not in trusted
    assert "python scripts/ci/helper1_subject_binding.py" in trusted
    assert '--fetch-event "${GITHUB_EVENT_PATH}"' in trusted
    assert '--subject "${RUNNER_TEMP}/helper1/CANONICAL_SUBJECT.json"' in trusted
    assert '--producer-package "${RUNNER_TEMP}/helper1/input/package/helper1-v51.zip"' in trusted
    assert "--evidence-dir" not in trusted
    assert "--artifact-root" not in trusted
    assert "checkout" not in trusted.split(
        "Recompute canonical subject and fetch exact Git object without checkout", 1
    )[1]
    assert "ref: ${{ github.event.workflow_run.head_sha }}" not in trusted
    assert "persist-credentials: false" in producer


def test_producer_execution_creates_required_fixed_path_package(tmp_path: Path) -> None:
    module, artifact, _subject, descriptor = _producer_artifact(tmp_path)

    assert (artifact / module.PACKAGE_RELATIVE).is_file()
    assert (artifact / module.DESCRIPTOR_RELATIVE).is_file()
    assert descriptor["package_relative_path"] == "package/helper1-v51.zip"
    workflow = PRODUCER.read_text(encoding="utf-8")
    assert "python scripts/ci/helper1_producer_package.py build" in workflow
    assert "python scripts/ci/helper1_product_approval_bundle.py" in workflow
    assert "helper1-producer-artifact/artifacts/objects" not in workflow
    assert workflow.index("helper1_product_approval_bundle.py") < workflow.index(
        "helper1_producer_package.py build"
    ) < workflow.index("actions/upload-artifact")
    assert "helper1-producer-artifact/package/helper1-v51.zip" in workflow
    assert "helper1-producer-artifact/package/helper1-v51.candidate.json" in workflow
    assert "path: helper1-producer-artifact/" in workflow
    assert "--previous-result-package" not in workflow
    assert "--rollback-predecessor-package" not in workflow


def test_producer_package_fingerprint_matches_candidate_descriptor(tmp_path: Path) -> None:
    module, artifact, _subject, descriptor = _producer_artifact(tmp_path)
    package = artifact / module.PACKAGE_RELATIVE
    persisted = json.loads((artifact / module.DESCRIPTOR_RELATIVE).read_bytes())

    observed = hashlib.sha256(package.read_bytes()).hexdigest()
    assert descriptor["package_sha256"] == observed
    assert persisted["package_sha256"] == observed
    assert persisted["immediate_predecessor"] != persisted["rollback_record"]


def test_uploaded_artifact_roundtrip_preserves_exact_verifier_path(tmp_path: Path) -> None:
    module, artifact, _subject, descriptor = _producer_artifact(tmp_path / "source")
    transport = shutil.make_archive(
        str(tmp_path / "uploaded-artifact"), "zip", root_dir=artifact
    )
    downloaded = tmp_path / "downloaded"
    shutil.unpack_archive(transport, downloaded)

    policy_raw = POLICY.read_bytes()
    loaded = module.load_verified_package(
        downloaded / "package/helper1-v51.zip",
        policy=json.loads(policy_raw),
        policy_raw=policy_raw,
        require_authority=False,
    )
    assert loaded.package_sha256 == descriptor["package_sha256"]
    assert (downloaded / "package/helper1-v51.zip").is_file()


def test_missing_renamed_or_substituted_package_blocks_final_gate(tmp_path: Path) -> None:
    module, artifact, _subject, _descriptor = _producer_artifact(tmp_path / "source")
    policy_raw = POLICY.read_bytes()
    policy = json.loads(policy_raw)

    missing = tmp_path / "missing"
    shutil.copytree(artifact, missing)
    (missing / module.PACKAGE_RELATIVE).unlink()
    with pytest.raises(module.ProducerPackageError):
        module.load_verified_package(
            missing / module.PACKAGE_RELATIVE,
            policy=policy,
            policy_raw=policy_raw,
            require_authority=False,
        )

    renamed = tmp_path / "renamed"
    shutil.copytree(artifact, renamed)
    package = renamed / module.PACKAGE_RELATIVE
    package.rename(package.with_name("helper1-v51-renamed.zip"))
    with pytest.raises(module.ProducerPackageError):
        module.load_verified_package(
            renamed / module.PACKAGE_RELATIVE,
            policy=policy,
            policy_raw=policy_raw,
            require_authority=False,
        )

    substituted = tmp_path / "substituted"
    shutil.copytree(artifact, substituted)
    package = substituted / module.PACKAGE_RELATIVE
    mutated = bytearray(package.read_bytes())
    mutated[len(mutated) // 2] ^= 1
    package.write_bytes(mutated)
    with pytest.raises(module.ProducerPackageError):
        module.load_verified_package(
            substituted / module.PACKAGE_RELATIVE,
            policy=policy,
            policy_raw=policy_raw,
            require_authority=False,
        )

    trusted = TRUSTED.read_text(encoding="utf-8")
    assert "LINEAGE_OUTCOME: ${{ steps.verify-lineage.outcome }}" in trusted
    assert 'test "${outcome}" = success' in trusted


def test_handoff_chain_authority_is_fixed_outside_the_candidate_package() -> None:
    trusted = TRUSTED.read_text(encoding="utf-8")
    verifier = PACKAGE_VERIFIER.read_text(encoding="utf-8")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    authority = policy["handoff_chain_authority"]

    assert "--chain-anchor" not in verifier
    assert "PROTECTED_POLICY_PATH" in verifier
    assert "helper1-v51-a4-closure" in verifier
    assert authority == {
        "schema_version": "butler.helper1.handoff-chain-authority.v1",
        "chain_id": "helper1-v51-a4-closure",
        "authority_mode": "PROTECTED_WORKFLOW_SIGNED_CHAIN",
        "approved_public_key_b64": None,
        "approved_public_key_sha256": None,
        "required_environment": "helper1-production-verifier",
        "required_check_name": "helper1-v2/protected-verdict",
    }
    assert "HELPER1_HANDOFF_CHAIN_AUTHORITY_B64: ${{ secrets.HELPER1_HANDOFF_CHAIN_AUTHORITY_B64 }}" in trusted
    assert "python scripts/ci/helper1_producer_package.py verify" in trusted
    assert "HELPER1_LINEAGE_OUTCOME: ${{ steps.verify-lineage.outcome }}" in trusted
    assert "LINEAGE_OUTCOME: ${{ steps.verify-lineage.outcome }}" in trusted


def test_package_and_self_selected_authority_joint_mutation_is_rejected() -> None:
    import base64
    import copy
    import hashlib
    import importlib.util

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    spec = importlib.util.spec_from_file_location("helper1_package_verifier_fixture", PACKAGE_VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CHAIN_GENERATIONS == (13, 14, 15)

    trusted_key = Ed25519PrivateKey.generate()
    trusted_public = base64.b64encode(
        trusted_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")

    descriptors: list[dict[str, object]] = []
    previous: str | None = None
    for generation, marker in ((13, "a"), (14, "b"), (15, "c")):
        descriptor = {
            "schema_version": "butler.helper1.handoff-chain-descriptor.v1",
            "chain_id": "helper1-v51-a4-closure",
            "generation": generation,
            "package_sha256": marker * 64,
            "result_tree": marker * 40,
            "previous_descriptor_sha256": previous,
        }
        descriptors.append(descriptor)
        previous = hashlib.sha256(module._canonical_authority_value(descriptor)).hexdigest()

    def signed_bundle(items: list[dict[str, object]], key: Ed25519PrivateKey) -> bytes:
        return module._canonical_authority_value(
            {
                "schema_version": "butler.helper1.signed-handoff-chain.v1",
                "chain_id": "helper1-v51-a4-closure",
                "descriptors": items,
                "signatures_b64": [
                    base64.b64encode(
                        key.sign(module._canonical_authority_value(item))
                    ).decode("ascii")
                    for item in items
                ],
            }
        )

    assert module._verify_signed_chain_authority(
        signed_bundle(descriptors, trusted_key), trusted_public
    ) is not None

    forged = copy.deepcopy(descriptors)
    forged[1]["package_sha256"] = forged[0]["package_sha256"]
    forged[1]["result_tree"] = forged[0]["result_tree"]
    forged[2]["package_sha256"] = "d" * 64
    forged[2]["previous_descriptor_sha256"] = hashlib.sha256(
        module._canonical_authority_value(forged[1])
    ).hexdigest()
    attacker_key = Ed25519PrivateKey.generate()
    assert module._verify_signed_chain_authority(
        signed_bundle(forged, attacker_key), trusted_public
    ) is None

    wrong_chain = copy.deepcopy(descriptors)
    wrong_chain[2]["chain_id"] = "attacker-selected-chain"
    assert module._verify_signed_chain_authority(
        signed_bundle(wrong_chain, trusted_key), trusted_public
    ) is None

    gapped = copy.deepcopy(descriptors)
    gapped[1]["generation"] = 15
    gapped[2]["generation"] = 16
    gapped[2]["previous_descriptor_sha256"] = hashlib.sha256(
        module._canonical_authority_value(gapped[1])
    ).hexdigest()
    assert module._verify_signed_chain_authority(
        signed_bundle(gapped, trusted_key), trusted_public
    ) is None

    duplicate = copy.deepcopy(descriptors)
    duplicate[1]["package_sha256"] = duplicate[0]["package_sha256"]
    duplicate[1]["result_tree"] = duplicate[0]["result_tree"]
    duplicate[2]["previous_descriptor_sha256"] = hashlib.sha256(
        module._canonical_authority_value(duplicate[1])
    ).hexdigest()
    assert module._verify_signed_chain_authority(
        signed_bundle(duplicate, trusted_key), trusted_public
    ) is None


def test_submission_is_downloaded_from_same_repository_but_never_executed():
    trusted = TRUSTED.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")

    assert '--repo "${GITHUB_REPOSITORY}"' in trusted
    assert '--name "helper1-v2-evidence-${PRODUCER_RUN_ID}-${PRODUCER_RUN_ATTEMPT}"' in trusted
    assert "${RUNNER_TEMP}/helper1/input/evidence" not in trusted
    assert "${RUNNER_TEMP}/helper1/input/artifacts" not in trusted
    assert '${RUNNER_TEMP}/helper1/input/package/helper1-v51.zip' in trusted
    assert "python ${RUNNER_TEMP}" not in trusted
    assert "repository.get(\"full_name\") != policy[\"repository\"]" in verifier
    assert "value.get(\"subject_commit\") != expected_commit" in verifier
    assert "verify_artifact_object(objects, digest)" in verifier
    assert "load_verified_package(" in verifier
    assert "expected_tree=subject_tree" in verifier
    assert "resolve_commit_tree(ROOT, subject_commit)" in verifier


def test_protected_verifier_fingerprint_is_exactly_pinned():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    observed = "sha256:" + hashlib.sha256(VERIFIER.read_bytes()).hexdigest()
    tree = ast.parse(PROTECTED_SURFACE.read_text(encoding="utf-8"))
    assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "PROTECTED_COMPONENT_PATHS" for target in node.targets)
    )
    component_paths = ast.literal_eval(assignment.value)
    expected = {
        path: "sha256:" + hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in component_paths
    }

    assert policy["protected_verifier_sha256"] == observed
    assert policy["protected_components_sha256"] == expected
    assert policy["policy_epoch"] == 2
    assert policy["enabled"] is False
    assert policy["approved_public_key_b64"] is None
    assert policy["approved_verdict_public_key_b64"] is None
    assert policy["approval_policy_sha256"] is None
    assert policy["approved_activation_public_key_b64"] is None


def test_transitive_dependency_omission_is_detected_automatically() -> None:
    module = _load_trusted_verifier_module()
    omitted = "butler_pc_core/helper1/failure_codes.py"
    module.PROTECTED_COMPONENTS = {
        name: path
        for name, path in module.PROTECTED_COMPONENTS.items()
        if name != omitted
    }

    assert omitted in module._missing_transitive_components()
    with pytest.raises(module.VerificationError, match="PROTECTED_TRANSITIVE_COMPONENT_MISSING"):
        module.verify_protected_components({"protected_components_sha256": {}})


def test_protected_success_path_invokes_a4_closure_before_verdict() -> None:
    source = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "verify_approval_closure"
    ]
    assert len(calls) == 1
    verdict_lines = [
        node.lineno
        for node in ast.walk(main)
        if isinstance(node, ast.Constant) and node.value == "CODE_PASS=1"
    ]
    assert len(verdict_lines) == 1
    assert calls[0].lineno < verdict_lines[0]


def test_existing_helper1_codeowners_rules_are_preserved_and_a4_is_owned() -> None:
    owners = CODEOWNERS.read_text(encoding="utf-8")
    preserved = (
        "/contracts/helper1/trusted-verifier-policy-v1.json",
        "/scripts/ci/helper1_trusted_verifier.py",
        "/scripts/verify_helper1_v2.py",
        "/scripts/verify_helper1_v51_package.py",
        "/.github/workflows/helper1-v2-evidence.yml",
        "/.github/workflows/helper1-v2-trusted-verifier.yml",
        "/tests/helper1_v2/test_self_selected_trust_regression.py",
        "/scripts/ci/helper1_subject_binding.py",
        "/scripts/ci/helper1_evidence_semantics.py",
        "/scripts/ci/publish_helper1_subject_check.py",
        "/scripts/ci/helper1_postgresql_replay_probe.py",
        "/scripts/ci/helper1_product_approval_bundle.py",
        "/scripts/ci/helper1_producer_package.py",
        "/tests/helper1_v2/test_protected_workflow_topology.py",
    )
    added = (
        "/butler_pc_core/helper1/approval_closure.py",
        "/butler_pc_core/helper1/canonical_json.py",
        "/butler_pc_core/helper1/execution.py",
        "/butler_pc_core/helper1/retrieval_policy.py",
        "/butler_pc_core/helper1/replay_store.py",
        "/contracts/helper1/retrieval-approval-trust-policy-v1.json",
        "/tests/helper1_v2/vectors/**",
    )
    assert all(owners.count(path) == 1 for path in (*preserved, *added))
    assert "/butler_pc_core/helper1/**" in owners
    assert "/scripts/ci/helper1_*" in owners
    assert "/contracts/helper1-*" in owners


def test_postgresql_probe_fails_closed_without_protected_dsn() -> None:
    environment = dict(os.environ)
    environment.pop("HELPER1_APPROVAL_REPLAY_DSN", None)
    environment["HELPER1_REPLAY_PROBE_RUN_ID"] = "fixture-1"
    completed = subprocess.run(
        [sys.executable, str(POSTGRES_PROBE)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout.splitlines() == [
        "HELPER1_POSTGRES_REPLAY_PROBE_OK=0",
        "ERROR_CODE=APPROVAL_REPLAY_STORE_UNAVAILABLE",
    ]
    assert completed.stderr == ""



def test_subject_check_is_published_after_verdict_preservation() -> None:
    trusted = TRUSTED.read_text(encoding="utf-8")
    preserve = trusted.index("Preserve immutable subject-bound verdict")
    publish = trusted.index("Publish fixed check on exact subject SHA")
    enforce = trusted.index("Enforce protected subject gate")

    assert preserve < publish < enforce
    assert "helper1-v2-protected-verdict-${{ github.event.workflow_run.head_sha }}" in trusted
    assert "--publish" in trusted
    assert "HELPER1_PRESERVE_OUTCOME" in trusted
    assert "PUBLISH_OUTCOME" in trusted
    assert "continue-on-error: true" in trusted


def test_fixed_required_check_identity_is_declared_but_activation_stays_disabled() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    publisher = PUBLISHER.read_text(encoding="utf-8")

    assert policy["subject_check_name"] == "helper1-v2/protected-verdict"
    assert policy["subject_check_app_slug"] == "github-actions"
    assert policy["subject_check_required"] is True
    assert policy["enabled"] is False
    assert "head_sha" in publisher
    assert "resolve_commit_tree(ROOT, subject)" in publisher
    assert "PROTECTED_PREREQUISITE_FAILED" in publisher


def test_subject_fetch_supports_push_merge_queue_and_base_pull_ref_without_checkout() -> None:
    binding = SUBJECT_BINDING.read_text(encoding="utf-8")

    assert "fetch_subject_object" in binding
    assert "--no-tags" in binding
    assert "--depth=1" in binding
    assert "refs/pull/{pull_number}/head" in binding
    assert "FETCH_HEAD^{commit}" in binding
    assert "observed != subject" in binding
    assert "[\"checkout\"" not in binding
