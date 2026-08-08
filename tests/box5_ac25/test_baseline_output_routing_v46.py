from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest


REPOSITORY = Path(__file__).resolve().parents[2]
GENERATOR = REPOSITORY / "scripts/ops/gen_autodecision_v1.mjs"
VERIFY_AUTODECISION = (
    REPOSITORY / "scripts/verify/verify_autodecision_from_reports_v1.sh"
)
VERIFY_RUNTIME_SHADOW = REPOSITORY / "scripts/verify/verify_runtime_shadow.sh"


def run_generator(
    *, input_root: Path, output_root: Path | None, evidence_root: Path
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "AC25_EVIDENCE_ROOT": str(evidence_root),
            "AUTODECISION_INPUT_REPORTS_ROOT": str(input_root),
        }
    )
    if output_root is not None:
        environment["AUTODECISION_OUTPUT_REPORTS_ROOT"] = str(output_root)
    else:
        environment.pop("AUTODECISION_OUTPUT_REPORTS_ROOT", None)
    return subprocess.run(
        ["node", str(GENERATOR)],
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def external_roots(tmp_path: Path) -> tuple[Path, Path]:
    input_root = tmp_path / "input"
    evidence_root = tmp_path / "evidence"
    input_root.mkdir(mode=0o700)
    evidence_root.mkdir(mode=0o700)
    return input_root, evidence_root


def copy_canonical_inputs(input_root: Path) -> None:
    source = REPOSITORY / "docs/ops/reports"
    for filename in ("repo_contracts_latest.json", "ai_smoke_latest.json"):
        (input_root / filename).write_bytes((source / filename).read_bytes())


def test_actionlint_declares_only_required_custom_label() -> None:
    config = (REPOSITORY / ".github/actionlint.yaml").read_text(encoding="utf-8")
    assert config.splitlines() == [
        "self-hosted-runner:",
        "  labels:",
        "    - helper1-quality",
    ]


def test_ac25_generator_writes_json_and_markdown_outside_repository(
    external_roots,
) -> None:
    input_root, evidence_root = external_roots
    copy_canonical_inputs(input_root)
    output_root = evidence_root / "autodecision"
    output_root.mkdir(mode=0o700)

    completed = run_generator(
        input_root=input_root,
        output_root=output_root,
        evidence_root=evidence_root,
    )

    assert completed.returncode == 0, completed.stdout
    assert completed.stderr == ""
    assert completed.stdout.splitlines() == [
        "AUTODECISION_GENERATED=1",
        "ERROR_CODE=NONE",
    ]
    for filename in ("autodecision_latest.json", "autodecision_latest.md"):
        output = output_root / filename
        observed = output.stat()
        assert output.is_file()
        assert stat.S_IMODE(observed.st_mode) == 0o600
        assert observed.st_nlink == 1
    parsed = json.loads((output_root / "autodecision_latest.json").read_text())
    assert parsed["schema"] == "autodecision_v1"
    serialized = (output_root / "autodecision_latest.json").read_text()
    markdown = (output_root / "autodecision_latest.md").read_text()
    assert str(input_root) not in serialized
    assert str(input_root) not in markdown
    assert str(evidence_root) not in serialized
    assert str(evidence_root) not in markdown


def test_ac25_generator_requires_explicit_output_root(external_roots) -> None:
    input_root, evidence_root = external_roots
    copy_canonical_inputs(input_root)
    completed = run_generator(
        input_root=input_root,
        output_root=None,
        evidence_root=evidence_root,
    )
    assert completed.returncode == 1
    assert completed.stderr == ""
    assert completed.stdout.splitlines() == [
        "AUTODECISION_GENERATED=0",
        "ERROR_CODE=AUTODECISION_GENERATION_FAILED",
    ]


@pytest.mark.parametrize(
    "missing_filename", ["repo_contracts_latest.json", "ai_smoke_latest.json"]
)
def test_ac25_generator_never_falls_back_to_repository_inputs(
    external_roots, missing_filename: str
) -> None:
    input_root, evidence_root = external_roots
    copy_canonical_inputs(input_root)
    (input_root / missing_filename).unlink()
    output_root = evidence_root / "autodecision"
    output_root.mkdir(mode=0o700)
    completed = run_generator(
        input_root=input_root,
        output_root=output_root,
        evidence_root=evidence_root,
    )
    assert completed.returncode == 1
    assert completed.stderr == ""
    assert not (output_root / "autodecision_latest.json").exists()
    assert not (output_root / "autodecision_latest.md").exists()


def test_ac25_generator_rejects_output_inside_repository(external_roots) -> None:
    input_root, evidence_root = external_roots
    copy_canonical_inputs(input_root)
    completed = run_generator(
        input_root=input_root,
        output_root=REPOSITORY / "out/ac25-v46-forbidden",
        evidence_root=evidence_root,
    )
    assert completed.returncode == 1
    assert completed.stderr == ""


def test_verify_script_passes_distinct_input_output_and_evidence_roots() -> None:
    source = VERIFY_AUTODECISION.read_text(encoding="utf-8")
    assert 'AUTODECISION_INPUT_REPORTS_ROOT="$INPUT_REPORTS_ROOT"' in source
    assert 'AUTODECISION_OUTPUT_REPORTS_ROOT="$OUTPUT_REPORTS_ROOT"' in source
    assert 'AC25_EVIDENCE_ROOT="$EVIDENCE_ROOT"' in source
    assert "AUTODECISION_OUTPUT_ROOT_REQUIRED" in source


def test_runtime_shadow_proof_uses_shared_descriptor_writer_only() -> None:
    source = VERIFY_RUNTIME_SHADOW.read_text(encoding="utf-8")
    assert 'PROOF_DIR="docs/ops/PROOFS"' not in source
    assert "scripts/ops/external_atomic_io.py" in source
    assert "--evidence-root \"$EVIDENCE_ROOT\"" in source
    assert "--output \"$PROOF_DIR/2026-01-29_runtime_shadow.md\"" in source
    assert "cat > \"$PROOF_DIR" not in source
    assert "BLOCK:" not in source
    assert "Full Response" not in source
    assert "RawResponsePersisted: NO" in source


def test_json_and_markdown_route_through_one_external_writer_function() -> None:
    source = GENERATOR.read_text(encoding="utf-8")
    external_branch = source.split("if (evidenceRoot) {", 1)[1].split("return;", 1)[0]
    assert external_branch.count("writeExternalBytes({") == 2
    assert "outJson" in external_branch
    assert "outMd" in external_branch
