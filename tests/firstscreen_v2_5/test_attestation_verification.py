"""FirstScreen SBOM attestation 검증 계약 — 실물 bundle 로 고정한다.

기존 시험은 워크플로 파일에 명령 문자열이 들어 있는지만 봤다. 그러면 값이 틀려도
'정본'으로 굳는다. 여기서는 ★실제 actions/attest 가 만든 bundle(고정 fixture)에서
인증서 확장값을 직접 읽어, 워크플로가 넘기는 인자가 그 값과 맞는지 비교한다.

fixture 출처: main push 로 성공한 실행
  commit  65c93d9e675fbd7781185169ba994a9ac57d206e
  run     https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/30183247122
  subject source.zip sha256:dc0cc81511a91473bed318c50e87087feb181bd00d18d1d72f608f8fcedd4cd4
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import NoReturn

import pytest

pytestmark = pytest.mark.no_sidecar_token

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "firstscreen" / "attestation_bundle_65c93d9e.json"
WORKFLOW = ROOT / ".github" / "workflows" / "product-verify-supplychain.yml"

ATTESTED_COMMIT = "65c93d9e675fbd7781185169ba994a9ac57d206e"
ATTESTED_SUBJECT_SHA256 = "dc0cc81511a91473bed318c50e87087feb181bd00d18d1d72f608f8fcedd4cd4"
REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
SIGNER_WORKFLOW = f"{REPOSITORY}/.github/workflows/product-verify-supplychain.yml"
PREDICATE_TYPE = "https://cyclonedx.org/bom"
NON_GATING_LOCAL_ENV = "BUTLER_ATTESTATION_NON_GATING"

ERROR_GH_CLI_UNAVAILABLE = "ATTESTATION_GH_CLI_UNAVAILABLE"
ERROR_ARTIFACT_REGENERATION_FAILED = "ATTESTATION_ARTIFACT_REGENERATION_FAILED"
ERROR_BASELINE_VERIFICATION_FAILED = "ATTESTATION_BASELINE_VERIFICATION_FAILED"
ERROR_EXPECTED_ACCEPTANCE_FAILED = "ATTESTATION_EXPECTED_ACCEPTANCE_FAILED"
ERROR_EXPECTED_REJECTION_FAILED = "ATTESTATION_EXPECTED_REJECTION_FAILED"

# Fulcio(GitHub) 인증서 확장 OID
OID_SOURCE_REPOSITORY_DIGEST = "1.3.6.1.4.1.57264.1.13"
OID_SOURCE_REPOSITORY_REF = "1.3.6.1.4.1.57264.1.14"


def _bundle() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _certificate_extension(oid: str) -> str:
    """인증서에서 확장값을 꺼낸다. 값은 DER UTF8String 로 감싸여 있다."""
    raw = base64.b64decode(_bundle()["verificationMaterial"]["certificate"]["rawBytes"])
    marker = bytes(int(part) for part in _oid_der(oid))
    index = raw.find(marker)
    assert index != -1, f"인증서에 {oid} 확장이 없다"
    cursor = index + len(marker)
    assert raw[cursor] == 0x04, "OCTET STRING 이 아니다"
    cursor += 1
    outer_length, cursor = _der_length(raw, cursor)
    end = cursor + outer_length
    assert raw[cursor] == 0x0C, "UTF8String 이 아니다"
    cursor += 1
    inner_length, cursor = _der_length(raw, cursor)
    value = raw[cursor : cursor + inner_length].decode("utf-8")
    assert cursor + inner_length <= end
    return value


def _oid_der(oid: str) -> list[int]:
    parts = [int(part) for part in oid.split(".")]
    body = [parts[0] * 40 + parts[1]]
    for part in parts[2:]:
        chunk = [part & 0x7F]
        part >>= 7
        while part:
            chunk.append((part & 0x7F) | 0x80)
            part >>= 7
        body.extend(reversed(chunk))
    return [0x06, len(body), *body]


def _der_length(raw: bytes, cursor: int) -> tuple[int, int]:
    first = raw[cursor]
    cursor += 1
    if first < 0x80:
        return first, cursor
    count = first & 0x7F
    value = int.from_bytes(raw[cursor : cursor + count], "big")
    return value, cursor + count


def _verify_step_command() -> str:
    """검증 스텝 하나만 잘라 낸다(다음 `- name:` 직전까지)."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    start = workflow.index("Verify FirstScreen attestation signer and subject")
    remainder = workflow[start:]
    next_step = remainder.find("\n      - name:")
    step = remainder if next_step == -1 else remainder[:next_step]
    assert "gh attestation verify" in step, "검증 스텝을 잘라 내지 못했다"
    return step


# ── 오프라인: 실물 인증서 확장값과 워크플로 인자를 대조한다 ──────────────


def test_fixture_is_the_attested_cyclonedx_bundle() -> None:
    bundle = _bundle()
    payload = json.loads(base64.b64decode(bundle["dsseEnvelope"]["payload"]))
    assert payload["predicateType"] == PREDICATE_TYPE
    subjects = {item["name"]: item["digest"]["sha256"] for item in payload["subject"]}
    assert subjects == {"source.zip": ATTESTED_SUBJECT_SHA256}


def test_source_digest_flag_matches_the_certificate_value() -> None:
    """★#883 지적 지점. 인증서에 실제로 뭐가 들어 있는지로 판정한다."""
    certificate_value = _certificate_extension(OID_SOURCE_REPOSITORY_DIGEST)

    # GitHub 이 발급한 인증서는 알고리즘 접두 없는 commit sha1 을 담는다.
    assert certificate_value == ATTESTED_COMMIT

    # gh attestation verify 는 --source-digest 값을 이 확장값과 ★그대로 비교한다.
    # 따라서 워크플로는 접두 없는 ${GITHUB_SHA} 를 넘겨야 한다.
    command = _verify_step_command()
    assert '--source-digest "${GITHUB_SHA}"' in command

    # 접두를 붙이면 인증서 값과 달라져 main 게이트가 항상 실패한다. 되돌림 방지로 고정한다.
    assert f"sha1:{ATTESTED_COMMIT}" != certificate_value
    assert '--source-digest "sha1:${GITHUB_SHA}"' not in command


def test_source_ref_flag_matches_the_certificate_value() -> None:
    assert _certificate_extension(OID_SOURCE_REPOSITORY_REF) == "refs/heads/main"
    assert '--source-ref "${GITHUB_REF}"' in _verify_step_command()


def test_verify_step_binds_bundle_predicate_and_signer() -> None:
    command = _verify_step_command()
    assert '--bundle "${FIRSTSCREEN_ATTESTATION_BUNDLE}"' in command
    assert f'--predicate-type "{PREDICATE_TYPE}"' in command
    assert '--signer-workflow "${GITHUB_WORKFLOW_REF%%@*}"' in command
    assert "ATTESTATION_BUNDLE_UNAVAILABLE" in command
    # 색인 지연 재시도 우회는 제거된 상태여야 한다.
    assert "ATTESTATION_VERIFY_RETRY" not in WORKFLOW.read_text(encoding="utf-8")


# ── 통합: 실물 bundle 로 gh attestation verify 를 실제 실행한다 ──────────


def _regenerate_attested_artifact(destination: Path) -> None:
    subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "release" / "build_safe_source_archive.py"),
            "--commit",
            ATTESTED_COMMIT,
            "--scope-baseline",
            f"{ATTESTED_COMMIT}^",
            "--output",
            str(destination),
            "--manifest",
            str(destination.with_suffix(".manifest.json")),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def _gh_verify(artifact: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    arguments = {
        "--repo": REPOSITORY,
        "--bundle": str(FIXTURE),
        "--predicate-type": PREDICATE_TYPE,
        "--signer-workflow": SIGNER_WORKFLOW,
        "--source-digest": ATTESTED_COMMIT,
        "--source-ref": "refs/heads/main",
    }
    arguments.update(overrides)
    command = ["gh", "attestation", "verify", str(artifact)]
    for flag, value in arguments.items():
        command.extend([flag, value])
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _is_gating_ci() -> bool:
    return os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


def _fail_or_skip_non_gating(error_code: str) -> NoReturn:
    """CI는 항상 실패하고, 명시적으로 비게이팅인 로컬 실행만 건너뛴다."""
    if not _is_gating_ci() and os.environ.get(NON_GATING_LOCAL_ENV) == "1":
        pytest.skip(error_code)
    pytest.fail(error_code, pytrace=False)


def _assert_verification_succeeds(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        pytest.fail(ERROR_EXPECTED_ACCEPTANCE_FAILED, pytrace=False)


def _assert_verification_rejects(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode == 0:
        pytest.fail(ERROR_EXPECTED_REJECTION_FAILED, pytrace=False)


@pytest.fixture(scope="module")
def attested_artifact(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("gh") is None:
        _fail_or_skip_non_gating(ERROR_GH_CLI_UNAVAILABLE)
    artifact = tmp_path_factory.mktemp("attestation") / "source.zip"
    try:
        _regenerate_attested_artifact(artifact)
    except subprocess.CalledProcessError:  # pragma: no cover - 환경 의존
        _fail_or_skip_non_gating(ERROR_ARTIFACT_REGENERATION_FAILED)

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert digest == ATTESTED_SUBJECT_SHA256, "재생성한 산출물이 attested subject 와 다르다"

    baseline = _gh_verify(artifact)
    if baseline.returncode != 0:
        _fail_or_skip_non_gating(ERROR_BASELINE_VERIFICATION_FAILED)
    return artifact


def test_integration_correct_subject_and_digest_passes(attested_artifact: Path) -> None:
    _assert_verification_succeeds(_gh_verify(attested_artifact))


def test_integration_algorithm_prefixed_digest_fails(attested_artifact: Path) -> None:
    """지시된 'sha1:' 접두 형식은 실제로는 실패한다 — 되돌림 방지."""
    result = _gh_verify(attested_artifact, **{"--source-digest": f"sha1:{ATTESTED_COMMIT}"})
    _assert_verification_rejects(result)


def test_integration_other_commit_fails(attested_artifact: Path) -> None:
    result = _gh_verify(attested_artifact, **{"--source-digest": "0" * 40})
    _assert_verification_rejects(result)


def test_integration_other_source_ref_fails(attested_artifact: Path) -> None:
    result = _gh_verify(attested_artifact, **{"--source-ref": "refs/heads/not-main"})
    _assert_verification_rejects(result)


def test_integration_other_signer_workflow_fails(attested_artifact: Path) -> None:
    result = _gh_verify(
        attested_artifact,
        **{"--signer-workflow": f"{REPOSITORY}/.github/workflows/firstscreen-v2-5.yml"},
    )
    _assert_verification_rejects(result)


def test_integration_environment_is_reported(attested_artifact: Path) -> None:
    """이 시험이 실제로 돌았는지 로그로 남긴다(조용한 skip 방지)."""
    assert os.path.getsize(attested_artifact) > 0


@pytest.mark.parametrize("ci_variable", ["CI", "GITHUB_ACTIONS"])
def test_gating_ci_cannot_enable_attestation_skip(
    monkeypatch: pytest.MonkeyPatch,
    ci_variable: str,
) -> None:
    monkeypatch.setenv(ci_variable, "true")
    monkeypatch.setenv(NON_GATING_LOCAL_ENV, "1")
    with pytest.raises(pytest.fail.Exception, match=f"^{ERROR_BASELINE_VERIFICATION_FAILED}$"):
        _fail_or_skip_non_gating(ERROR_BASELINE_VERIFICATION_FAILED)


def test_local_attestation_skip_requires_explicit_non_gating_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv(NON_GATING_LOCAL_ENV, raising=False)
    with pytest.raises(pytest.fail.Exception, match=f"^{ERROR_BASELINE_VERIFICATION_FAILED}$"):
        _fail_or_skip_non_gating(ERROR_BASELINE_VERIFICATION_FAILED)


def test_explicit_non_gating_local_environment_uses_bounded_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv(NON_GATING_LOCAL_ENV, "1")
    with pytest.raises(pytest.skip.Exception, match=f"^{ERROR_BASELINE_VERIFICATION_FAILED}$"):
        _fail_or_skip_non_gating(ERROR_BASELINE_VERIFICATION_FAILED)


def test_failure_reporting_does_not_embed_verifier_output() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert "baseline" + ".stderr" not in source
    assert "baseline" + ".stdout" not in source
    assert "error" + ".stderr" not in source


def test_verification_failure_omits_captured_diagnostics() -> None:
    result = subprocess.CompletedProcess(
        args=["gh", "attestation", "verify"],
        returncode=1,
        stdout="RAW_STDOUT_MUST_NOT_PERSIST",
        stderr="RAW_STDERR_MUST_NOT_PERSIST",
    )
    with pytest.raises(pytest.fail.Exception, match=f"^{ERROR_EXPECTED_ACCEPTANCE_FAILED}$") as caught:
        _assert_verification_succeeds(result)
    report = str(caught.value)
    assert "RAW_STDOUT" not in report
    assert "RAW_STDERR" not in report
