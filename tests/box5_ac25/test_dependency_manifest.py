"""§15 M-1 — dependency manifest 시험.

감사가 잡은 것: 두 레인이 `-r requirements.txt` 를 불렀는데 그 파일은 없다.
그런데 CI 57개가 초록이었다. 다른 job 이 먼저 lock 을 깔아 우연히 넘어간 것이다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from ac25 import dependency_manifest as dm

pytestmark = pytest.mark.no_sidecar_token

REPO_ROOT = Path(__file__).resolve().parents[2]

GOOD = (
    "pytest==9.1.1 \\\n    --hash=sha256:" + "1" * 64 + "\n"
    "PyYAML==6.0.3 \\\n    --hash=sha256:" + "2" * 64 + "\n"
)


def _tests(tmp_path: Path, source: str = "import pytest\nimport yaml\n") -> Path:
    root = tmp_path / "tests" / "box5_ac25"
    root.mkdir(parents=True)
    (root / "test_sample.py").write_text(source, encoding="utf-8")
    return root


def _repo(tmp_path: Path, manifest: str | None = GOOD, name: str = "requirements-firstscreen-ci.lock"):
    root = tmp_path / "repo"
    root.mkdir()
    if manifest is not None:
        (root / name).write_text(manifest, encoding="utf-8")
    return root


# ══ 실재하는 manifest 를 실제로 해석한다 ═══════════════════════════════
def test_the_repository_manifest_resolves():
    """★합성이 아니라 저장소의 실물 lock 을 읽는다."""
    resolved = dm.resolve_manifest(
        repo_root=REPO_ROOT, test_root=REPO_ROOT / "tests" / "box5_ac25"
    )
    assert resolved.relative_path == "requirements-firstscreen-ci.lock"
    assert resolved.hash_pinned is True
    assert len(resolved.sha256) == 64
    assert resolved.missing_distributions == frozenset()
    assert {"pytest", "pyyaml"} <= resolved.distributions


def test_requirements_txt_is_not_a_candidate():
    """감사가 지목한 그 파일은 후보 목록에 없다."""
    assert "requirements.txt" not in dm.MANIFEST_CANDIDATES


def test_repository_has_no_root_requirements_txt():
    assert not (REPO_ROOT / "requirements.txt").exists()


def test_real_tests_need_exactly_pytest_and_yaml():
    assert dm.external_imports(REPO_ROOT / "tests" / "box5_ac25") == frozenset(
        {"pytest", "yaml"}
    )


# ══ manifest 없음·중복 ═════════════════════════════════════════════════
def test_missing_manifest_is_rejected(tmp_path):
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.resolve_manifest(repo_root=_repo(tmp_path, None), test_root=_tests(tmp_path))
    assert caught.value.code == dm.STAGE_B_DEPENDENCY_MANIFEST_NOT_FOUND


def test_ambiguous_manifest_is_rejected(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    (root / "requirements-second.lock").write_text(GOOD, encoding="utf-8")
    monkeypatch.setattr(
        dm, "MANIFEST_CANDIDATES",
        ("requirements-firstscreen-ci.lock", "requirements-second.lock"),
    )
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.resolve_manifest(repo_root=root, test_root=_tests(tmp_path))
    assert caught.value.code == dm.STAGE_B_DEPENDENCY_MANIFEST_AMBIGUOUS


# ══ hash·version 누락 ══════════════════════════════════════════════════
def test_missing_hash_is_rejected():
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.parse_manifest("pytest==9.1.1\n")
    assert caught.value.code == dm.STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED


@pytest.mark.parametrize("requirement", ["pytest", "pytest>=9.0", "pytest~=9.1", "pytest!=9.0"])
def test_unpinned_version_is_rejected(requirement):
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.parse_manifest(f"{requirement} \\\n    --hash=sha256:{'1' * 64}\n")
    assert caught.value.code == dm.STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED


# ══ URL·VCS·local path·확장 지시자 ═════════════════════════════════════
@pytest.mark.parametrize(
    "line",
    [
        "https://example.invalid/pkg-1.0-py3-none-any.whl",
        "git+https://example.invalid/pkg.git#egg=pkg",
        "-e .",
        "--editable .",
        "--extra-index-url https://example.invalid/simple",
        "--find-links ./wheels",
        "-r other-requirements.txt",
        "--requirement other.txt",
        "./local/pkg-1.0.tar.gz",
        "file:///tmp/pkg-1.0.tar.gz",
    ],
)
def test_non_pinned_forms_are_rejected(line):
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.parse_manifest(line + "\n")
    assert caught.value.code == dm.STAGE_B_DEPENDENCY_MANIFEST_NOT_PINNED


# ══ 필수 배포 누락 ═════════════════════════════════════════════════════
def test_missing_required_distribution_is_rejected(tmp_path):
    only_pytest = "pytest==9.1.1 \\\n    --hash=sha256:" + "1" * 64 + "\n"
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.resolve_manifest(
            repo_root=_repo(tmp_path, only_pytest), test_root=_tests(tmp_path)
        )
    assert caught.value.code == dm.STAGE_B_DEPENDENCY_MANIFEST_INCOMPLETE
    assert "pyyaml" in caught.value.detail


# ══ import mapping 누락 ════════════════════════════════════════════════
def test_unmapped_import_is_rejected(tmp_path):
    root = _tests(tmp_path, "import pytest\nimport numpy\n")
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.required_distributions(root)
    assert caught.value.code == dm.STAGE_B_IMPORT_DISTRIBUTION_UNMAPPED
    assert "numpy" in caught.value.detail


def test_yaml_maps_to_pyyaml():
    """★유추할 수 없는 대응이다. 표에 없으면 닫힌다."""
    assert dm.IMPORT_TO_DISTRIBUTION["yaml"] == "PyYAML"
    assert dm.normalize("PyYAML") == "pyyaml"


def test_stdlib_and_internal_imports_are_not_distributions(tmp_path):
    root = _tests(tmp_path, "import json\nimport hashlib\nfrom ac25 import anchors\n")
    assert dm.external_imports(root) == frozenset()


def test_relative_import_is_internal(tmp_path):
    root = _tests(tmp_path, "from . import helper\n")
    assert dm.external_imports(root) == frozenset()


# ══ comment·continuation·marker 파싱 ═══════════════════════════════════
def test_comment_and_continuation_and_marker_are_handled():
    text = (
        "# 주석 줄\n"
        "pytest==9.1.1 \\\n"
        "    --hash=sha256:" + "1" * 64 + " \\\n"
        "    --hash=sha256:" + "3" * 64 + "\n"
        "    # via something\n"
        "PyYAML==6.0.3 ; python_version >= '3.9' \\\n"
        "    --hash=sha256:" + "2" * 64 + "\n"
    )
    distributions, pinned = dm.parse_manifest(text)
    assert distributions == frozenset({"pytest", "pyyaml"})
    assert pinned is True


def test_normalization_follows_pep503():
    assert dm.normalize("Foo.Bar_baz") == "foo-bar-baz"
    distributions, _ = dm.parse_manifest(
        "Zope.Interface==5.0 \\\n    --hash=sha256:" + "4" * 64 + "\n"
    )
    assert distributions == frozenset({"zope-interface"})


def test_empty_manifest_is_rejected():
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.parse_manifest("# 주석만 있다\n\n")
    assert caught.value.code == dm.STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED


def test_non_utf8_manifest_is_rejected(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "requirements-firstscreen-ci.lock").write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(dm.DependencyManifestError) as caught:
        dm.resolve_manifest(repo_root=root, test_root=_tests(tmp_path))
    assert caught.value.code == dm.STAGE_B_DEPENDENCY_MANIFEST_PARSE_FAILED
