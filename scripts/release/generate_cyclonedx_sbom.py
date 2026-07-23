#!/usr/bin/env python3
"""Generate a deterministic CycloneDX inventory from checked-in lock files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from butler_pc_core.firstscreen_trust import build_context_digest, strict_json_loads, validate_build_context


def _npm_purl(name: str, version: str) -> str:
    return f"pkg:npm/{name.replace('@', '%40')}@{version}"


def _resolve_npm_dependency(packages: dict[str, dict[str, object]], package_path: str, name: str) -> str | None:
    cursor = package_path
    while True:
        candidate = f"{cursor}/node_modules/{name}" if cursor else f"node_modules/{name}"
        if candidate in packages:
            return candidate
        marker = cursor.rfind("/node_modules/")
        if marker < 0:
            cursor = ""
        else:
            cursor = cursor[:marker]
        if not cursor:
            candidate = f"node_modules/{name}"
            return candidate if candidate in packages else None


def npm_inventory(lock_path: Path) -> tuple[list[dict[str, object]], dict[str, set[str]], set[str]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("packages", {})
    if not isinstance(packages, dict) or "" not in packages:
        raise ValueError("NPM_LOCK_PACKAGES_MISSING")
    result: dict[str, dict[str, object]] = {}
    graph: dict[str, set[str]] = defaultdict(set)
    path_refs: dict[str, str] = {}
    for package_path, package in sorted(packages.items()):
        if not package_path or not package_path.startswith("node_modules/"):
            continue
        if not isinstance(package, dict):
            raise ValueError("NPM_LOCK_PACKAGE_INVALID")
        name = package.get("name") or package_path.removeprefix("node_modules/")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str) or not version:
            continue
        purl = _npm_purl(name, version)
        path_refs[package_path] = purl
        component: dict[str, object] = {
            "type": "library",
            "name": name,
            "version": version,
            "bom-ref": purl,
            "purl": purl,
        }
        license_name = package.get("license")
        if isinstance(license_name, str) and license_name:
            component["licenses"] = [{"license": {"name": license_name}}]
        result[purl] = component
    for package_path, package in sorted(packages.items()):
        parent_ref = path_refs.get(package_path)
        if parent_ref is None or not isinstance(package, dict):
            continue
        declared: dict[str, object] = {}
        for key in ("dependencies", "optionalDependencies", "peerDependencies"):
            value = package.get(key, {})
            if isinstance(value, dict):
                declared.update(value)
        for name in sorted(declared):
            resolved_path = _resolve_npm_dependency(packages, package_path, name)
            if resolved_path is not None and resolved_path in path_refs:
                graph[parent_ref].add(path_refs[resolved_path])
    root_refs: set[str] = set()
    root_package = packages[""]
    if isinstance(root_package, dict):
        declared = {}
        for key in ("dependencies", "devDependencies", "optionalDependencies"):
            value = root_package.get(key, {})
            if isinstance(value, dict):
                declared.update(value)
        for name in sorted(declared):
            resolved_path = _resolve_npm_dependency(packages, "", name)
            if resolved_path is not None and resolved_path in path_refs:
                root_refs.add(path_refs[resolved_path])
    return [result[key] for key in sorted(result)], graph, root_refs


def _normalize_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_inventory(paths: list[Path]) -> tuple[list[dict[str, object]], dict[str, set[str]], set[str]]:
    components: dict[str, dict[str, object]] = {}
    graph: dict[str, set[str]] = defaultdict(set)
    root_refs: set[str] = set()
    pattern = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        blocks: list[tuple[str, str, list[str]]] = []
        current: tuple[str, str, list[str]] | None = None
        via_mode = False
        for raw in lines + ["__END__"]:
            match = pattern.match(raw.strip())
            if match:
                if current is not None:
                    blocks.append(current)
                current = (match.group(1), match.group(2), [])
                via_mode = False
                continue
            if current is None:
                continue
            stripped = raw.strip()
            if stripped.startswith("# via"):
                via_mode = True
                inline = stripped.removeprefix("# via").strip()
                if inline:
                    current[2].append(inline)
            elif via_mode and stripped.startswith("#   "):
                current[2].append(stripped.removeprefix("#   ").strip())
            elif stripped and not stripped.startswith("--hash") and not stripped.startswith("\\") and not stripped.startswith("#"):
                via_mode = False
        if current is not None:
            blocks.append(current)
        refs_by_name: dict[str, str] = {}
        for name, version, _parents in blocks:
            normalized = _normalize_python_name(name)
            purl = f"pkg:pypi/{normalized}@{version}"
            refs_by_name[normalized] = purl
            components[purl] = {
                "type": "library", "name": name, "version": version, "bom-ref": purl, "purl": purl,
                "properties": [{"name": "butler:hash_locked", "value": "true"}],
            }
        for name, _version, parents in blocks:
            child_ref = refs_by_name[_normalize_python_name(name)]
            for parent in parents:
                if parent.startswith("-r "):
                    root_refs.add(child_ref)
                    continue
                parent_ref = refs_by_name.get(_normalize_python_name(parent))
                if parent_ref is not None:
                    graph[parent_ref].add(child_ref)
    return [components[key] for key in sorted(components)], graph, root_refs


def dependency_entries(all_refs: Iterable[str], graph: dict[str, set[str]]) -> list[dict[str, object]]:
    return [
        {"ref": ref, "dependsOn": sorted(graph.get(ref, set()))}
        for ref in sorted(set(all_refs))
    ]


def _valid_oid(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def _metadata_identity(build_info_path: Path, manifest_path: Path) -> tuple[str, str]:
    build = json.loads(build_info_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(build, dict) or not isinstance(manifest, dict):
        raise ValueError("SOURCE_IDENTITY_METADATA_INVALID")
    commit = build.get("build_base_commit_oid")
    tree = build.get("build_tree_oid")
    if (
        manifest.get("schema_version") != "butler.safe-source-manifest.v2"
        or not _valid_oid(commit)
        or not _valid_oid(tree)
        or manifest.get("commit") != commit
        or manifest.get("tree") != tree
        or manifest.get("build_stamp", {}).get("commit") != commit
        or manifest.get("build_stamp", {}).get("tree") != tree
    ):
        raise ValueError("SOURCE_IDENTITY_METADATA_INVALID")
    return commit, tree


def _source_identity(
    commit_reference: str,
    build_info_path: Path | None,
    manifest_path: Path | None,
) -> tuple[str, str, str]:
    metadata: tuple[str, str] | None = None
    if build_info_path is not None or manifest_path is not None:
        if build_info_path is None or manifest_path is None:
            raise ValueError("SOURCE_IDENTITY_METADATA_INCOMPLETE")
        metadata = _metadata_identity(build_info_path, manifest_path)
    try:
        commit = subprocess.run(
            ["git", "rev-parse", f"{commit_reference}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "rev-parse", f"{commit}^{{tree}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        if not _valid_oid(commit) or not _valid_oid(tree):
            raise ValueError("GIT_SOURCE_IDENTITY_INVALID")
        if metadata is not None and metadata != (commit, tree):
            raise ValueError("SOURCE_IDENTITY_AUTHORITY_MISMATCH")
        return commit, tree, "GIT_AND_METADATA" if metadata else "GIT"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if metadata is None:
            raise ValueError("SOURCE_IDENTITY_UNAVAILABLE")
        commit, tree = metadata
        if commit_reference != "HEAD" and commit_reference != commit:
            raise ValueError("SOURCE_COMMIT_REFERENCE_MISMATCH")
        return commit, tree, "BUILD_INFO_AND_SOURCE_MANIFEST"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--npm-lock", type=Path, required=True)
    parser.add_argument("--python-requirements", type=Path, action="append", default=[])
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--build-info", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--build-context", type=Path)
    arguments = parser.parse_args()
    build_info = arguments.build_info
    source_manifest = arguments.source_manifest
    if build_info is None and source_manifest is None:
        automatic_build = Path("BUILD_INFO.json")
        automatic_manifest = Path("../SOURCE_ARCHIVE_MANIFEST.json")
        if automatic_build.is_file() and automatic_manifest.is_file():
            build_info = automatic_build
            source_manifest = automatic_manifest
    commit, tree, identity_authority = _source_identity(arguments.commit, build_info, source_manifest)
    context_digest: str | None = None
    if arguments.build_context is not None:
        context = strict_json_loads(arguments.build_context.read_bytes(), maximum=64 * 1024)
        validate_build_context(context)
        if context["commit_oid"] != commit or context["tree_oid"] != tree:
            raise ValueError("BUILD_CONTEXT_SOURCE_IDENTITY_MISMATCH")
        context_digest = build_context_digest(context)
    npm_components, npm_graph, npm_roots = npm_inventory(arguments.npm_lock)
    python_components, python_graph, python_roots = python_inventory(arguments.python_requirements)
    components = npm_components + python_components
    unique = {str(component["purl"]): component for component in components}
    ordered = [unique[key] for key in sorted(unique)]
    root_ref = "pkg:generic/butler-desktop@0.9.0"
    graph: dict[str, set[str]] = defaultdict(set)
    for source in (npm_graph, python_graph):
        for parent, children in source.items():
            graph[parent].update(children)
    graph[root_ref].update(npm_roots | python_roots)
    serial_seed = (
        commit
        + "\n"
        + tree
        + "\n"
        + (context_digest or "UNBOUND_BUILD_CONTEXT")
        + "\n"
        + "\n".join(str(component["purl"]) for component in ordered)
    ).encode()
    serial = hashlib.sha256(serial_seed).hexdigest()[:32]
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial[0:8]}-{serial[8:12]}-4{serial[13:16]}-8{serial[17:20]}-{serial[20:32]}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application", "name": "Butler Desktop", "version": "0.9.0",
                "bom-ref": root_ref, "purl": root_ref,
                "properties": [
                    {"name": "butler:git_commit_oid", "value": commit},
                    {"name": "butler:git_tree_oid", "value": tree},
                    {"name": "butler:source_identity_authority", "value": identity_authority},
                    *(
                        [{"name": "butler:build_context_digest", "value": context_digest}]
                        if context_digest is not None
                        else []
                    ),
                ],
            },
            "properties": [
                {"name": "butler:subject", "value": f"git+commit:{commit}"},
                {"name": "butler:tree", "value": tree},
            ],
        },
        "components": ordered,
        "dependencies": dependency_entries([root_ref, *unique], graph),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "components": len(ordered), "dependency_nodes": len(document["dependencies"]), "sha256": hashlib.sha256(arguments.output.read_bytes()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
