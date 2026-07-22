from __future__ import annotations

import json
from pathlib import Path

from scripts.ci.classify_a4_repository_failures import classify


def _baseline(
    path: Path, failures: dict[str, str], *, platform_overlay: bool = False
) -> Path:
    owners = {owner: "owned outside A4" for owner in set(failures.values())}
    document = {
        "schema_version": "butler.box5.a4.repository_failure_baseline.v5.5",
        "owner_notes": owners,
        "failures": failures,
    }
    if platform_overlay:
        document["baseline_role"] = "platform_overlay"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _junit(path: Path, classname: str, name: str) -> Path:
    path.write_text(
        f'<testsuites><testsuite><testcase classname="{classname}" name="{name}">'
        '<failure message="redacted"/></testcase></testsuite></testsuites>',
        encoding="utf-8",
    )
    return path


def test_real_baseline_contains_42_non_a4_owned_failures() -> None:
    root = Path(__file__).resolve().parents[3]
    baseline = json.loads(
        (root / "docs/ops/A4_V55_REPOSITORY_FAILURE_BASELINE.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(baseline["failures"]) == 42
    assert not any(nodeid.startswith("tests.accounting.classify.test_a4_") for nodeid in baseline["failures"])


def test_ubuntu_ci_overlay_contains_27_truthfully_classified_optional_dependency_failures() -> None:
    root = Path(__file__).resolve().parents[3]
    overlay = json.loads(
        (root / "docs/ops/A4_V55_REPOSITORY_FAILURE_BASELINE_UBUNTU_CI_OVERLAY.json").read_text(
            encoding="utf-8"
        )
    )
    assert overlay["baseline_role"] == "platform_overlay"
    assert overlay["environment_marker"]["llama_cpp_importable"] is False
    assert len(overlay["failures"]) == 27
    assert set(overlay["failures"].values()) == {"box4-box6-json-grammar"}
    assert not any(nodeid.startswith("tests.accounting.classify.test_a4_") for nodeid in overlay["failures"])


def test_classifier_accepts_only_an_exact_external_baseline_failure(tmp_path: Path) -> None:
    nodeid = "tests.external.test_feature::test_known"
    report = classify(
        junit_path=_junit(tmp_path / "junit.xml", "tests.external.test_feature", "test_known"),
        baseline_path=_baseline(tmp_path / "baseline.json", {nodeid: "external"}),
        pytest_exit_code=1,
    )
    assert report["status"] == "PASS_WITH_CLASSIFIED_EXTERNAL_FAILURES"
    assert report["unknown_failure_count"] == 0


def test_classifier_blocks_new_or_a4_owned_failures(tmp_path: Path) -> None:
    report = classify(
        junit_path=_junit(
            tmp_path / "junit.xml",
            "tests.accounting.classify.test_a4_new",
            "test_regression",
        ),
        baseline_path=_baseline(
            tmp_path / "baseline.json",
            {"tests.external.test_feature::test_known": "external"},
        ),
        pytest_exit_code=1,
    )
    assert report["status"] == "BLOCKED"
    assert report["a4_owned_failure_count"] == 1
    assert report["unknown_failure_count"] == 1


def test_classifier_combines_an_exact_platform_overlay_without_hiding_new_failures(
    tmp_path: Path,
) -> None:
    nodeid = "tests.external.test_platform::test_known"
    base = _baseline(
        tmp_path / "baseline.json",
        {"tests.external.test_base::test_known": "base-owner"},
    )
    overlay = _baseline(
        tmp_path / "overlay.json",
        {nodeid: "platform-owner"},
        platform_overlay=True,
    )
    report = classify(
        junit_path=_junit(
            tmp_path / "junit.xml", "tests.external.test_platform", "test_known"
        ),
        baseline_path=base,
        overlay_paths=(overlay,),
        pytest_exit_code=1,
    )
    assert report["status"] == "PASS_WITH_CLASSIFIED_EXTERNAL_FAILURES"
    assert report["baseline_failure_count"] == 2
    assert report["resolved_baseline_nodeids"] == [
        "tests.external.test_base::test_known"
    ]


def test_classifier_rejects_duplicate_or_unmarked_overlays(tmp_path: Path) -> None:
    nodeid = "tests.external.test_feature::test_known"
    base = _baseline(tmp_path / "baseline.json", {nodeid: "external"})
    duplicate = _baseline(
        tmp_path / "duplicate.json",
        {nodeid: "external"},
        platform_overlay=True,
    )
    junit = _junit(
        tmp_path / "junit.xml", "tests.external.test_feature", "test_known"
    )
    try:
        classify(
            junit_path=junit,
            baseline_path=base,
            overlay_paths=(duplicate,),
            pytest_exit_code=1,
        )
    except ValueError as exc:
        assert "duplicate nodeids" in str(exc)
    else:
        raise AssertionError("duplicate overlay was accepted")

    unmarked = _baseline(
        tmp_path / "unmarked.json",
        {"tests.external.test_other::test_known": "external"},
    )
    try:
        classify(
            junit_path=junit,
            baseline_path=base,
            overlay_paths=(unmarked,),
            pytest_exit_code=1,
        )
    except ValueError as exc:
        assert "overlay role" in str(exc)
    else:
        raise AssertionError("unmarked overlay was accepted")
