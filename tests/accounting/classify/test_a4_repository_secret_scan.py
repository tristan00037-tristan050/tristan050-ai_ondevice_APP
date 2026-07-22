from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.ci import a4_repository_secret_scan as scanner


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "A4 Test")
    _git(repo, "config", "user.email", "a4-test@example.invalid")
    return repo


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def test_scanner_blocks_direct_and_encoded_secrets_without_echoing_values(tmp_path: Path) -> None:
    github_token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    bearer = "Bear" + "er " + "m7Qv2Kx9Lp4Rw8Hs6Yt3Bc5D"
    encoded = __import__("base64").b64encode(bearer.encode()).decode()
    repo = _repo(tmp_path)
    (repo / "settings.txt").write_text(github_token + "\n" + encoded + "\n", encoding="utf-8")
    _commit(repo, "seed")

    summary = scanner.scan_repository(repo)

    rules = {item.rule_id for item in summary.findings}
    assert "GITHUB_TOKEN" in rules
    assert "BASE64_ENCODED_GENERIC_BEARER" in rules
    rendered = "\n".join(f"{item.rule_id}:{item.path_digest}" for item in summary.findings)
    assert github_token not in rendered
    assert bearer not in rendered


def test_scanner_inspects_deleted_history_blobs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    token = "xox" + "b-" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5"
    secret = repo / "deleted.txt"
    secret.write_text(token + "\n", encoding="utf-8")
    _commit(repo, "secret")
    secret.unlink()
    _commit(repo, "delete")

    summary = scanner.scan_repository(repo)

    assert not any(item.scope == "tracked" for item in summary.findings)
    assert any(item.scope == "history" and item.rule_id == "SLACK_TOKEN" for item in summary.findings)


def test_scanner_fails_closed_for_oversized_blobs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "large.bin").write_bytes(b"x" * 65)
    _commit(repo, "large")

    summary = scanner.scan_repository(repo, max_blob_bytes=64)

    assert summary.ok is False
    assert {item.error_code for item in summary.errors} == {
        "OVERSIZED_TRACKED_FILE",
        "OVERSIZED_HISTORY_BLOB",
    }


def test_baseline_suppresses_only_the_exact_audited_line(tmp_path: Path) -> None:
    token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    finding = scanner.scan_payload(
        scope="tracked", object_id="blob", path="tests/fixture.txt", payload=token.encode()
    )[0]
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": "butler.box5.a4.secret_scan_baseline.v5.5",
                "entries": [
                    {
                        "scope": finding.scope,
                        "rule_id": finding.rule_id,
                        "path_digest": finding.path_digest,
                        "line_digest": finding.line_digest,
                        "reason": "AUDITED_NON_SECRET_FIXTURE_OR_PLACEHOLDER",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    summary = scanner.ScanSummary(1, 0, (finding,), ())
    suppressed = scanner.apply_baseline(summary, baseline)
    assert suppressed.ok is True
    assert suppressed.baseline_suppressed == 1

    changed = scanner.scan_payload(
        scope="tracked",
        object_id="blob-2",
        path="tests/fixture.txt",
        payload=(token + "Z").encode(),
    )[0]
    unsuppressed = scanner.apply_baseline(
        scanner.ScanSummary(1, 0, (changed,), ()), baseline
    )
    assert unsuppressed.ok is False


def _rotation_document(finding: scanner.Finding, *, complete: bool) -> dict[str, object]:
    evidence = {
        "status": "ROTATED",
        "revoked_at_utc": "2026-07-23T00:00:00Z",
        "rotated_at_utc": "2026-07-23T00:01:00Z",
        "rotated_by": "finance-security@example.invalid",
        "evidence_url": "https://evidence.example.invalid/a4/rotation",
        "evidence_sha256": "a" * 64,
    } if complete else {
        "status": "ROTATION_EVIDENCE_REQUIRED",
        "revoked_at_utc": None,
        "rotated_at_utc": None,
        "rotated_by": None,
        "evidence_url": None,
        "evidence_sha256": None,
    }
    return {
        "schema_version": "butler.box5.a4.secret_rotation_status.v5.5",
        "status": "COMPLETE" if complete else "BLOCKED_EXTERNAL",
        "raw_values_included": False,
        "raw_paths_included": False,
        "exposure_scope": finding.scope,
        "exposure_blob_oid": finding.object_id,
        "source_path_digest": finding.path_digest,
        "finding_rule_id": finding.rule_id,
        "finding_line_digest": finding.line_digest,
        "credentials": [
            {"credential_id": credential_id, **evidence}
            for credential_id in ("DATABASE_URL", "EXPORT_SIGN_SECRET")
        ],
        "merge_gate": (
            "ROTATION_EVIDENCE_COMPLETE_PENDING_SECRET_SCAN"
            if complete
            else "BLOCKED_UNTIL_ALL_ROTATION_EVIDENCE_IS_PRESENT"
        ),
    }


def test_rotation_status_releases_only_the_exact_finding_after_complete_proof(tmp_path: Path) -> None:
    token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    finding = scanner.scan_payload(
        scope="history", object_id="a" * 40, path="deleted.env", payload=token.encode()
    )[0]
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    blocked_path = tmp_path / "blocked.json"
    blocked_path.write_text(json.dumps(_rotation_document(finding, complete=False)), encoding="utf-8")

    blocked = scanner.apply_rotation_evidence(summary, blocked_path)
    assert blocked.ok is False
    assert blocked.rotation_suppressed == 0
    assert blocked.rotation_evidence_status == "BLOCKED_EXTERNAL"

    completed_path = tmp_path / "complete.json"
    completed_path.write_text(json.dumps(_rotation_document(finding, complete=True)), encoding="utf-8")
    completed = scanner.apply_rotation_evidence(summary, completed_path)
    assert completed.ok is True
    assert completed.rotation_suppressed == 1
    assert completed.rotation_evidence_status == "COMPLETE_VERIFIED"

    changed = scanner.Finding(
        finding.scope,
        "GITHUB_TOKEN",
        finding.object_id,
        finding.path_digest,
        finding.line_number,
        "b" * 64,
        finding.encoding,
    )
    mismatch = scanner.apply_rotation_evidence(
        scanner.ScanSummary(0, 1, (changed,), ()), completed_path
    )
    assert mismatch.ok is False
    assert mismatch.rotation_suppressed == 0


def test_rotation_status_rejects_partial_or_unbound_evidence(tmp_path: Path) -> None:
    token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    finding = scanner.scan_payload(
        scope="history", object_id="a" * 40, path="deleted.env", payload=token.encode()
    )[0]
    document = _rotation_document(finding, complete=True)
    document["credentials"][0]["evidence_sha256"] = None  # type: ignore[index]
    status_path = tmp_path / "forged.json"
    status_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError):
        scanner.apply_rotation_evidence(
            scanner.ScanSummary(0, 1, (finding,), ()), status_path
        )
