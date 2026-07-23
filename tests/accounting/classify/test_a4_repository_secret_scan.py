from __future__ import annotations

import hashlib
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


# --------------------------------------------------------------------------- #
# Baseline suppression + protected approval manifest pinning.
# --------------------------------------------------------------------------- #


def _baseline_document(finding: scanner.Finding, *, source_head: str) -> dict[str, object]:
    return {
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
        "source_head": source_head,
    }


def test_baseline_suppresses_only_the_exact_audited_line(tmp_path: Path) -> None:
    token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    finding = scanner.scan_payload(
        scope="tracked", object_id="blob", path="tests/fixture.txt", payload=token.encode()
    )[0]
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(_baseline_document(finding, source_head="0" * 40)), encoding="utf-8")
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


def _write_baseline_with_manifest(
    tmp_path: Path, finding: scanner.Finding, *, source_head: str, manifest_head: str | None = None
) -> tuple[Path, Path]:
    baseline = tmp_path / "baseline.json"
    payload = json.dumps(_baseline_document(finding, source_head=source_head)).encode("utf-8")
    baseline.write_bytes(payload)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "butler.box5.a4.secret_scan_baseline_manifest.v5.6",
                "approved_source_head": manifest_head or source_head,
                "baseline_sha256": hashlib.sha256(payload).hexdigest(),
                "entry_count": 1,
            }
        ),
        encoding="utf-8",
    )
    return baseline, manifest


def test_baseline_manifest_accepts_pinned_baseline(tmp_path: Path) -> None:
    token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    finding = scanner.scan_payload(
        scope="tracked", object_id="blob", path="tests/fixture.txt", payload=token.encode()
    )[0]
    baseline, manifest = _write_baseline_with_manifest(tmp_path, finding, source_head="a" * 40)
    suppressed = scanner.apply_baseline(
        scanner.ScanSummary(1, 0, (finding,), ()), baseline, manifest_path=manifest
    )
    assert suppressed.ok is True
    assert suppressed.baseline_suppressed == 1


def test_baseline_manifest_blocks_entry_tampering(tmp_path: Path) -> None:
    token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    finding = scanner.scan_payload(
        scope="tracked", object_id="blob", path="tests/fixture.txt", payload=token.encode()
    )[0]
    baseline, manifest = _write_baseline_with_manifest(tmp_path, finding, source_head="a" * 40)
    # Silently append a byte to the baseline without updating the protected manifest.
    baseline.write_bytes(baseline.read_bytes() + b" ")
    with pytest.raises(ValueError):
        scanner.apply_baseline(
            scanner.ScanSummary(1, 0, (finding,), ()), baseline, manifest_path=manifest
        )


def test_baseline_manifest_blocks_source_head_drift(tmp_path: Path) -> None:
    token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    finding = scanner.scan_payload(
        scope="tracked", object_id="blob", path="tests/fixture.txt", payload=token.encode()
    )[0]
    # Manifest approves head 'b'*40 but the baseline was generated at 'a'*40.
    baseline, manifest = _write_baseline_with_manifest(
        tmp_path, finding, source_head="a" * 40, manifest_head="b" * 40
    )
    with pytest.raises(ValueError):
        scanner.apply_baseline(
            scanner.ScanSummary(1, 0, (finding,), ()), baseline, manifest_path=manifest
        )


# --------------------------------------------------------------------------- #
# Rotation evidence: real, network-backed verification only.
# --------------------------------------------------------------------------- #

_EVIDENCE_BODY = b"A4 rotation evidence canonical body\n"
_EVIDENCE_SHA = hashlib.sha256(_EVIDENCE_BODY).hexdigest()
_EVIDENCE_AUTHOR = "tristan00037-tristan050"


def _fetcher(body: bytes = _EVIDENCE_BODY, author: str = _EVIDENCE_AUTHOR):
    def fetch(repo: str, comment_id: str, *, token: object) -> scanner.FetchedComment:
        return scanner.FetchedComment(body, author)

    return fetch


def _raising_fetcher(exc: Exception):
    def fetch(repo: str, comment_id: str, *, token: object) -> scanner.FetchedComment:
        raise exc

    return fetch


def _forbidden_fetcher():
    def fetch(repo: str, comment_id: str, *, token: object) -> scanner.FetchedComment:
        raise AssertionError("evidence must not be fetched on this path")

    return fetch


def _blocked_document(finding: scanner.Finding) -> dict[str, object]:
    empty = {
        "status": "ROTATION_EVIDENCE_REQUIRED",
        "revoked_at_utc": None,
        "rotated_at_utc": None,
        "rotated_by": None,
        "evidence_url": None,
        "evidence_sha256": None,
    }
    return {
        "schema_version": "butler.box5.a4.secret_rotation_status.v5.5",
        "status": "BLOCKED_EXTERNAL",
        "raw_values_included": False,
        "raw_paths_included": False,
        "exposure_scope": finding.scope,
        "exposure_blob_oid": finding.object_id,
        "source_path_digest": finding.path_digest,
        "finding_rule_id": finding.rule_id,
        "finding_line_digest": finding.line_digest,
        "credentials": [
            {"credential_id": credential_id, **empty}
            for credential_id in ("DATABASE_URL", "EXPORT_SIGN_SECRET")
        ],
        "merge_gate": "BLOCKED_UNTIL_ALL_ROTATION_EVIDENCE_IS_PRESENT",
    }


def _completion_document(
    finding: scanner.Finding,
    *,
    status: str = "COMPLETE_VERIFIED",
    evidence_url: str | None = None,
    evidence_sha256: str | None = None,
    rotated_by: str = _EVIDENCE_AUTHOR,
) -> dict[str, object]:
    evidence = {
        "status": "ROTATED",
        "revoked_at_utc": "2026-07-23T00:00:00Z",
        "rotated_at_utc": "2026-07-23T00:01:00Z",
        "rotated_by": rotated_by,
        "evidence_url": evidence_url or scanner._EVIDENCE_CANONICAL_URL,
        "evidence_sha256": evidence_sha256 or _EVIDENCE_SHA,
    }
    return {
        "schema_version": "butler.box5.a4.secret_rotation_status.v5.5",
        "status": status,
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
        "merge_gate": scanner._ROTATION_COMPLETION_GATES[status],
    }


def _history_finding() -> scanner.Finding:
    token = "gh" + "p_" + "Qz7mN2Vk9Lp4Rw8Hs6Yt3Bc5Df1Gj0Xa"
    return scanner.scan_payload(
        scope="history", object_id="a" * 40, path="deleted.env", payload=token.encode()
    )[0]


def _write(tmp_path: Path, name: str, document: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_rotation_verified_releases_only_the_exact_finding_after_network_proof(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())

    # Blocked evidence keeps the finding and never passes.
    blocked_path = _write(tmp_path, "blocked.json", _blocked_document(finding))
    blocked = scanner.apply_rotation_evidence(
        summary, blocked_path, evidence_fetcher=_forbidden_fetcher(), token="t"
    )
    assert blocked.ok is False
    assert blocked.rotation_suppressed == 0
    assert blocked.rotation_evidence_status == "BLOCKED_EXTERNAL"

    # Real, verified proof releases exactly the bound finding.
    verified_path = _write(tmp_path, "verified.json", _completion_document(finding))
    verified = scanner.apply_rotation_evidence(
        summary, verified_path, evidence_fetcher=_fetcher(), token="t"
    )
    assert verified.ok is True
    assert verified.rotation_suppressed == 1
    assert verified.rotation_evidence_status == "COMPLETE_VERIFIED"

    # A different finding (different line digest) is not the bound target.
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
        scanner.ScanSummary(0, 1, (changed,), ()),
        verified_path,
        evidence_fetcher=_fetcher(),
        token="t",
    )
    assert mismatch.ok is False
    assert mismatch.rotation_suppressed == 0


def test_self_attested_completion_never_passes_and_never_fetches(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    path = _write(
        tmp_path, "self.json", _completion_document(finding, status="COMPLETE_SELF_ATTESTED")
    )
    # A forbidden fetcher proves the self-attested path performs no network release.
    result = scanner.apply_rotation_evidence(
        summary, path, evidence_fetcher=_forbidden_fetcher(), token="t"
    )
    assert result.ok is False
    assert result.rotation_suppressed == 0
    assert result.rotation_evidence_status == "COMPLETE_SELF_ATTESTED"
    assert result.findings == (finding,)


def test_fake_evidence_url_is_blocked(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    path = _write(
        tmp_path,
        "fake_url.json",
        _completion_document(finding, evidence_url="https://evidence.example.invalid/a4/rotation"),
    )
    with pytest.raises(scanner.RotationEvidenceError):
        scanner.apply_rotation_evidence(summary, path, evidence_fetcher=_fetcher(), token="t")


def test_arbitrary_sha_without_matching_body_is_blocked(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    path = _write(
        tmp_path, "arb_hash.json", _completion_document(finding, evidence_sha256="a" * 64)
    )
    with pytest.raises(scanner.RotationEvidenceError):
        scanner.apply_rotation_evidence(summary, path, evidence_fetcher=_fetcher(), token="t")


def test_one_byte_body_tamper_is_blocked(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    path = _write(tmp_path, "tamper.json", _completion_document(finding))
    tampered = scanner.apply_rotation_evidence
    with pytest.raises(scanner.RotationEvidenceError):
        tampered(summary, path, evidence_fetcher=_fetcher(body=_EVIDENCE_BODY + b"x"), token="t")


def test_other_repository_comment_is_blocked(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    other = "https://api.github.com/repos/attacker/evil/issues/comments/5053048876"
    path = _write(tmp_path, "other_repo.json", _completion_document(finding, evidence_url=other))
    with pytest.raises(scanner.RotationEvidenceError):
        scanner.apply_rotation_evidence(summary, path, evidence_fetcher=_fetcher(), token="t")


def test_other_comment_id_is_blocked(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    other = (
        "https://api.github.com/repos/tristan00037-tristan050/"
        "tristan050-ai_ondevice_APP/issues/comments/999999999"
    )
    path = _write(tmp_path, "other_id.json", _completion_document(finding, evidence_url=other))
    with pytest.raises(scanner.RotationEvidenceError):
        scanner.apply_rotation_evidence(summary, path, evidence_fetcher=_fetcher(), token="t")


def test_rotated_by_actor_mismatch_is_blocked(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    path = _write(
        tmp_path, "actor.json", _completion_document(finding, rotated_by="impersonator")
    )
    with pytest.raises(scanner.RotationEvidenceError):
        scanner.apply_rotation_evidence(summary, path, evidence_fetcher=_fetcher(), token="t")


def test_api_failure_or_timeout_is_blocked(tmp_path: Path) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    path = _write(tmp_path, "verified.json", _completion_document(finding))
    for exc in (
        scanner.RotationEvidenceError("fetch failed"),
        TimeoutError("timed out"),
    ):
        with pytest.raises(Exception):
            scanner.apply_rotation_evidence(
                summary, path, evidence_fetcher=_raising_fetcher(exc), token="t"
            )


def test_missing_token_fails_closed_via_default_fetcher(tmp_path: Path, monkeypatch) -> None:
    finding = _history_finding()
    summary = scanner.ScanSummary(0, 1, (finding,), ())
    path = _write(tmp_path, "verified.json", _completion_document(finding))
    for name in scanner._EVIDENCE_TOKEN_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Default fetcher + no token in the environment must never reach a network pass.
    with pytest.raises(scanner.RotationEvidenceError):
        scanner.apply_rotation_evidence(summary, path)


def test_blocked_rotation_cannot_be_bypassed_by_baseline_or_history_rewrite(tmp_path: Path) -> None:
    finding = _history_finding()
    blocked_path = _write(tmp_path, "blocked.json", _blocked_document(finding))
    no_reachable_finding = scanner.ScanSummary(0, 0, (), ())
    blocked = scanner.apply_rotation_evidence(
        no_reachable_finding, blocked_path, evidence_fetcher=_forbidden_fetcher(), token="t"
    )
    assert blocked.findings == ()
    assert blocked.rotation_evidence_status == "BLOCKED_EXTERNAL"
    assert blocked.ok is False


def test_self_attested_cannot_pass_even_with_no_reachable_finding(tmp_path: Path) -> None:
    finding = _history_finding()
    path = _write(
        tmp_path, "self.json", _completion_document(finding, status="COMPLETE_SELF_ATTESTED")
    )
    # Even if the blob were rewritten out of history, self-attestation must not pass.
    result = scanner.apply_rotation_evidence(
        scanner.ScanSummary(0, 0, (), ()), path, evidence_fetcher=_forbidden_fetcher(), token="t"
    )
    assert result.ok is False
    assert result.rotation_evidence_status == "COMPLETE_SELF_ATTESTED"


def test_rotation_status_rejects_partial_or_unbound_evidence(tmp_path: Path) -> None:
    finding = _history_finding()
    document = _completion_document(finding)
    document["credentials"][0]["evidence_sha256"] = None  # type: ignore[index]
    path = _write(tmp_path, "forged.json", document)
    with pytest.raises(ValueError):
        scanner.apply_rotation_evidence(
            scanner.ScanSummary(0, 1, (finding,), ()), path, evidence_fetcher=_fetcher(), token="t"
        )
