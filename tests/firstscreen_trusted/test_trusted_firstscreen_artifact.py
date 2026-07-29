from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import zipfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_sidecar_token

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ci" / "trusted_firstscreen_artifact.py"
SPEC = importlib.util.spec_from_file_location("trusted_firstscreen_artifact", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


def _valid_outer(
    tmp_path: Path,
    protected_manifest: Path,
) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source.zip"
    _write_zip(source, {"README.txt": b"trusted source fixture\n"})
    protected_action_pins = tmp_path / "action-pins.v1.json"
    protected_action_pins.write_text(
        '{"schema_version":1}\n',
        encoding="utf-8",
    )
    protected_index_schema = tmp_path / "evidence-index.schema.json"
    protected_index_schema.write_text('{"type":"object"}\n', encoding="utf-8")
    head = "a" * 40
    tree = "b" * 40
    metadata_value = {
        "schema_version": 1,
        "repository": "tristan00037-tristan050/tristan050-ai_ondevice_APP",
        "event_name": "pull_request",
        "pull_request": 886,
        "subject_head": head,
        "tree_oid": {"algorithm": "sha1", "hex": tree},
        "producer": {
            "workflow_id": 1,
            "workflow_name": "firstscreen-v2-5-product-gate",
            "workflow_path": ".github/workflows/firstscreen-v2-5.yml",
            "workflow_ref": (
                "tristan00037-tristan050/tristan050-ai_ondevice_APP/"
                ".github/workflows/firstscreen-v2-5.yml@refs/pull/886/merge"
            ),
            "run_id": "123",
            "run_attempt": 1,
        },
        "artifact": {
            "id": 456,
            "name": f"firstscreen-v9-evidence-{head}",
            "sha256": "",
        },
        "trusted_verifier": {
            "head": "c" * 40,
            "tree": "d" * 40,
            "workflow_ref": "trusted",
        },
    }
    report_files = {
        name: f"report:{name}\n".encode()
        for name in MODULE.REPORT_NAMES
    }
    context_files = {
        name: f'{{"context":"{name}"}}\n'.encode()
        for name in MODULE.CONTEXT_NAMES
    }
    assert len(report_files) == len(context_files)
    runs = []
    for report_name, context_name in zip(
        sorted(MODULE.REPORT_NAMES),
        sorted(MODULE.CONTEXT_NAMES),
    ):
        runs.append(
            {
                "runner": "node",
                "command": "test",
                "tool_versions": {"node": "test"},
                "exit_code": 0,
                "started_at": "2026-07-29T00:00:00Z",
                "finished_at": "2026-07-29T00:00:01Z",
                "os": "Linux",
                "arch": "X64",
                "execution_oid": {"algorithm": "sha1", "hex": head},
                "tree_oid": {"algorithm": "sha1", "hex": tree},
                "raw_result_path": report_name,
                "raw_result_sha256": hashlib.sha256(
                    report_files[report_name]
                ).hexdigest(),
                "context_path": context_name,
                "context_sha256": hashlib.sha256(
                    context_files[context_name]
                ).hexdigest(),
            }
        )
    index = {
        "schema_version": 1,
        "subject": {
            "repository": metadata_value["repository"],
            "pull_request": 886,
            "head_oid": {"algorithm": "sha1", "hex": head},
            "tree_oid": {"algorithm": "sha1", "hex": tree},
        },
        "workflow": {
            "runner_kind": "github-hosted",
            "run_id": "123",
            "run_attempt": 1,
            "workflow_ref": metadata_value["producer"]["workflow_ref"],
        },
        "runs": runs,
    }
    package_files = {
        "manifests/required-tests.v3.json": protected_manifest.read_bytes(),
        "manifests/action-pins.v1.json": protected_action_pins.read_bytes(),
        "manifests/evidence-index.schema.json": protected_index_schema.read_bytes(),
        "source/source.zip": source.read_bytes(),
        "source/git-ls-tree.txt": b"tree\n",
        "source/correction.patch": b"patch\n",
        "EVIDENCE_INDEX.json": (
            json.dumps(index, separators=(",", ":")) + "\n"
        ).encode(),
        **report_files,
        **context_files,
    }
    checksums = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
        for name, payload in sorted(package_files.items())
    ).encode()
    inner = tmp_path / MODULE.INNER_ARCHIVE
    _write_zip(
        inner,
        {
            **{
                f"{MODULE.PACKAGE_ROOT}/{name}": payload
                for name, payload in package_files.items()
            },
            f"{MODULE.PACKAGE_ROOT}/SHA256SUMS.txt": checksums,
        },
    )
    outer = tmp_path / "artifact.zip"
    _write_zip(
        outer,
        {
            MODULE.INNER_ARCHIVE: inner.read_bytes(),
            MODULE.DETACHED_DIGEST: (
                f"{_sha256(inner)}  {MODULE.INNER_ARCHIVE}\n".encode()
            ),
        },
    )
    metadata_value["artifact"]["sha256"] = _sha256(outer)
    metadata = tmp_path / "trusted-metadata.json"
    metadata.write_text(
        json.dumps(metadata_value, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return outer, metadata, protected_action_pins, protected_index_schema


def test_trusted_artifact_preflight_binds_all_digest_layers(tmp_path: Path) -> None:
    protected = tmp_path / "required-tests.v3.json"
    protected.write_text(
        json.dumps({"schema_version": 3, "tests": []}) + "\n",
        encoding="utf-8",
    )
    outer, metadata, action_pins, index_schema = _valid_outer(tmp_path, protected)
    output = tmp_path / "result.json"
    MODULE.verify(
        outer,
        tmp_path / "extract",
        protected,
        action_pins,
        index_schema,
        metadata,
        output,
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["schema_version"] == 1
    assert result["upload_artifact_sha256"] == _sha256(outer)
    assert result["protected_manifest_sha256"] == _sha256(protected)
    assert result["checksum_count"] == len(MODULE.PACKAGE_FILES) - 1
    assert not Path(result["package_relative"]).is_absolute()


@pytest.mark.parametrize(
    "entry",
    [
        "../escape.txt",
        "package/name:stream",
        "package/CON.txt",
        "package/trailing. ",
        "package\\mixed.txt",
        "package/e\u0301.txt",
    ],
)
def test_archive_preflight_rejects_cross_platform_paths(
    tmp_path: Path,
    entry: str,
) -> None:
    archive_path = tmp_path / "attack.zip"
    _write_zip(archive_path, {entry: b"x"})
    with archive_path.open("rb") as stream:
        with pytest.raises(MODULE.ArtifactError):
            MODULE._preflight(stream)


def test_archive_preflight_rejects_symlink_entry(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target")
    with archive_path.open("rb") as stream:
        with pytest.raises(MODULE.ArtifactError, match="ARCHIVE_FILE_TYPE_INVALID"):
            MODULE._preflight(stream)


def test_archive_preflight_rejects_casefold_collision(tmp_path: Path) -> None:
    archive_path = tmp_path / "collision.zip"
    _write_zip(archive_path, {"A.txt": b"a", "a.TXT": b"b"})
    with archive_path.open("rb") as stream:
        with pytest.raises(MODULE.ArtifactError, match="ARCHIVE_PATH_COLLISION"):
            MODULE._preflight(stream)


def test_detached_digest_must_not_contain_runner_path(tmp_path: Path) -> None:
    detached = tmp_path / MODULE.DETACHED_DIGEST
    detached.write_text(
        f"{'a' * 64}  /home/runner/work/{MODULE.INNER_ARCHIVE}\n",
        encoding="ascii",
    )
    with pytest.raises(MODULE.ArtifactError, match="DETACHED_DIGEST_INVALID"):
        MODULE._strict_detached(detached)


def test_protected_manifest_mismatch_blocks_package(tmp_path: Path) -> None:
    protected = tmp_path / "required-tests.v3.json"
    protected.write_text('{"schema_version":3}\n', encoding="utf-8")
    outer, metadata, action_pins, index_schema = _valid_outer(tmp_path, protected)
    protected.write_text('{"schema_version":3,"changed":true}\n', encoding="utf-8")
    with pytest.raises(MODULE.ArtifactError, match="PROTECTED_MANIFEST_MISMATCH"):
        MODULE.verify(
            outer,
            tmp_path / "extract",
            protected,
            action_pins,
            index_schema,
            metadata,
            tmp_path / "result.json",
        )
