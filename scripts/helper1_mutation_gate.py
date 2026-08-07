#!/usr/bin/env python3
"""Prove approval and replay-routing mutants are killed by acceptance tests."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.test_evidence import parse_junit  # noqa: E402


@dataclass(frozen=True, slots=True)
class Mutant:
    mutant_id: str
    relative_path: str
    old: str
    new: str
    test_node: str


MUTANTS = (
    Mutant(
        "REQUIRED_ROLE_REMOVED",
        "butler_pc_core/helper1/approval_closure.py",
        "for role in (*REQUIRED_EVIDENCE_ROLES, THRESHOLD_POLICY_ROLE):",
        "for role in (THRESHOLD_POLICY_ROLE,):",
        "tests/helper1_v2/test_a4_closure_v51.py::test_each_missing_a4_receipt_has_the_specific_missing_code",
    ),
    Mutant(
        "PAYLOAD_DIGEST_CHECK_REMOVED",
        "butler_pc_core/helper1/approval_closure.py",
        'if not hmac.compare_digest(item.payload_digest, signed["payload_sha256"]):',
        "if False:",
        "tests/helper1_v2/test_evidence_envelope_v51.py::test_payload_is_detached_and_one_byte_change_breaks_digest",
    ),
    Mutant(
        "SIGNATURE_VERIFY_REMOVED",
        "butler_pc_core/helper1/retrieval_policy.py",
        "        key_role = THRESHOLD_POLICY_SIGNER if role == \"A4_RETRIEVAL_THRESHOLD_POLICY\" else EVIDENCE_SIGNER\n",
        "        return\n",
        "tests/helper1_v2/test_policy_authority_v51.py::test_deterministic_fake_signatures_are_all_blocked[1]",
    ),
    Mutant(
        "SUBJECT_COMPARE_REMOVED",
        "butler_pc_core/helper1/approval_closure.py",
        "if subject is not None and (\n",
        "if False and subject is not None and (\n",
        "tests/helper1_v2/test_evidence_envelope_v51.py::test_resigned_wrong_subject_is_rejected",
    ),
    Mutant(
        "REPLAY_RESERVATION_REMOVED",
        "butler_pc_core/helper1/approval_closure.py",
        "            authority.reserve(reservations, now)\n",
        "            pass  # deliberate replay mutant\n",
        "tests/helper1_v2/test_policy_authority_v51.py::test_missing_duplicate_and_replayed_roles_fail_closed",
    ),
    Mutant(
        "THRESHOLD_COMPARE_REMOVED",
        "butler_pc_core/helper1/approval_closure.py",
        "            if metrics.get(metric, -1) < minimum:\n",
        "            if False:\n",
        "tests/helper1_v2/test_a4_closure_v51.py::test_signed_threshold_metric_minimum_is_actually_enforced",
    ),
    Mutant(
        "DNS_HOSTADDR_PINNING_REMOVED",
        "butler_pc_core/helper1/replay_store.py",
        '        connection_values["hostaddr"] = ",".join(item[1] for item in endpoints)\n',
        '        connection_values.pop("hostaddr", None)\n',
        "tests/helper1_v2/test_replay_store_v51.py::test_postgresql_pins_every_resolved_host_port_and_address",
    ),
    Mutant(
        "ROUTING_ENV_GUARD_REMOVED",
        "butler_pc_core/helper1/replay_store.py",
        "        self._validate_routing_environment()\n",
        "        pass  # deliberate routing environment mutant\n",
        "tests/helper1_v2/test_replay_store_v51.py::test_postgresql_routing_environment_is_rejected_before_connecting",
    ),
)

PROTECTED_MUTANT = Mutant(
    "PROTECTED_A4_INVOCATION_REMOVED",
    "scripts/ci/helper1_trusted_verifier.py",
    "approval_closure_digest, approval_file_digests = verify_approval_closure(",
    "approval_closure_digest, approval_file_digests = bypass_approval_closure(",
    "tests/helper1_v2/test_protected_workflow_topology.py::test_protected_success_path_invokes_a4_closure_before_verdict",
)


def _apply_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise RuntimeError("MUTATION_TARGET_AMBIGUOUS")
    path.write_text(source.replace(old, new), encoding="utf-8")


def _run(mutant: Mutant, temporary: Path) -> bool:
    work = temporary / mutant.mutant_id.lower()
    shutil.copytree(ROOT / "butler_pc_core", work / "butler_pc_core")
    shutil.copytree(ROOT / "tests" / "helper1_v2", work / "tests" / "helper1_v2")
    _apply_once(work / mutant.relative_path, mutant.old, mutant.new)
    report = work / "mutation.junit.xml"
    environment = dict(os.environ)
    environment.update({"PYTHONPATH": str(work), "PYTHONHASHSEED": "0"})
    completed = subprocess.run(
        (sys.executable, "-m", "pytest", "-q", mutant.test_node, f"--junitxml={report}"),
        cwd=work,
        env=environment,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )
    try:
        collected, _passed, failed, errors, _skipped = parse_junit(report)
    except Exception:
        return False
    return completed.returncode == 1 and collected >= 1 and failed >= 1 and errors == 0


def _run_protected_mutant(temporary: Path) -> bool:
    work = temporary / "protected_a4_invocation_removed"
    for source, destination in (
        (ROOT / ".github" / "CODEOWNERS", work / ".github" / "CODEOWNERS"),
        (ROOT / ".github" / "workflows", work / ".github" / "workflows"),
        (ROOT / "scripts" / "ci", work / "scripts" / "ci"),
        (ROOT / "contracts" / "helper1", work / "contracts" / "helper1"),
        (ROOT / "butler_pc_core" / "helper1", work / "butler_pc_core" / "helper1"),
    ):
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    test_path = work / PROTECTED_MUTANT.test_node.split("::", 1)[0]
    test_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / PROTECTED_MUTANT.test_node.split("::", 1)[0], test_path)
    _apply_once(
        work / PROTECTED_MUTANT.relative_path,
        PROTECTED_MUTANT.old,
        PROTECTED_MUTANT.new,
    )
    report = work / "protected-mutation.junit.xml"
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            PROTECTED_MUTANT.test_node,
            f"--junitxml={report}",
        ),
        cwd=work,
        env={**os.environ, "PYTHONPATH": str(work), "PYTHONHASHSEED": "0"},
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )
    try:
        collected, _passed, failed, errors, _skipped = parse_junit(report)
    except Exception:
        return False
    return completed.returncode == 1 and collected == 1 and failed == 1 and errors == 0


def main() -> int:
    outcomes: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="helper1-v51-mutation-") as name:
        root = Path(name)
        for mutant in MUTANTS:
            try:
                killed = _run(mutant, root)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                killed = False
            outcomes.append((mutant.mutant_id, killed))
        try:
            protected_killed = _run_protected_mutant(root)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            protected_killed = False
    for mutant_id, killed in outcomes:
        print(f"MUTATION_{mutant_id}_KILLED={int(killed)}")
    all_killed = all(killed for _, killed in outcomes)
    print(f"MUTATION_{PROTECTED_MUTANT.mutant_id}_KILLED={int(protected_killed)}")
    print(f"HELPER1_CORE_SOURCE_MUTATION_COUNT={len(outcomes)}")
    all_killed = all_killed and protected_killed
    print(f"HELPER1_MUTATION_GATE_OK={int(all_killed)}")
    print("ERROR_CODE=NONE" if all_killed else "ERROR_CODE=HELPER1_MUTATION_SURVIVED")
    return 0 if all_killed else 1


if __name__ == "__main__":
    raise SystemExit(main())
