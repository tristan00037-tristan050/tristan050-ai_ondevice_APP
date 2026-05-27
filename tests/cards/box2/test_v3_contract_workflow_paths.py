"""Regression guard for Codex P2 #2 (PR #755).

The box2-helper3-v3-contract workflow runs scripts/run_box2_helper3_v3_contract_tests.sh
(and that script is also wrapped by scripts/run_box2_helper3_v3_real_macbook.sh).
GitHub matches pull_request.paths against the changed files in the PR,
so if those script paths are not listed, a PR that only edits the
harness or its wrapper will skip this gate — letting the gate logic
drift without the gate ever executing.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github/workflows/box2_helper3_v3_contract.yml"


def _load_paths() -> list[str]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 parses bare 'on:' as boolean True; tolerate both forms.
    on_section = data.get(True) if True in data else data.get("on")
    assert on_section is not None, "workflow has no 'on:' section"
    return list(on_section.get("pull_request", {}).get("paths", []))


def test_workflow_paths_include_contract_script():
    paths = _load_paths()
    assert "scripts/run_box2_helper3_v3_contract_tests.sh" in paths, (
        f"contract harness script missing from pull_request.paths: {paths}"
    )


def test_workflow_paths_include_real_macbook_wrapper():
    paths = _load_paths()
    assert "scripts/run_box2_helper3_v3_real_macbook.sh" in paths, (
        f"real-MacBook wrapper missing from pull_request.paths: {paths}"
    )


def test_workflow_paths_do_not_use_broad_scripts_glob():
    """A broad 'scripts/**' would over-trigger this workflow on unrelated
    script changes. The fix must list the specific harness + wrapper only."""
    paths = _load_paths()
    assert "scripts/**" not in paths, (
        f"paths use broad 'scripts/**' which over-triggers the workflow: {paths}"
    )
    assert "scripts/*" not in paths


def test_workflow_paths_keep_existing_entries():
    """Original entries must remain so the workflow still triggers on
    src/test/data/evidence/requirements changes."""
    paths = _load_paths()
    for required in (
        "butler_pc_core/cards/box2/**",
        "tests/cards/box2/**",
        "data/box2_helper3_eval/**",
        "evidence/box2_helper3/**",
        "requirements-box2-helper3.txt",
        "install_runtime.sh",
        ".github/workflows/box2_helper3_v3_contract.yml",
    ):
        assert required in paths, f"required entry dropped: {required}"


def test_contract_script_actually_invoked_by_workflow():
    """Tie the gate-script entry to actual execution: the workflow must
    contain a 'run:' step that invokes the contract harness script."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/run_box2_helper3_v3_contract_tests.sh" in text
    # The script should appear in a run step, not only the paths list.
    body_without_paths = text.split("workflow_dispatch:", 1)[-1]
    assert "scripts/run_box2_helper3_v3_contract_tests.sh" in body_without_paths


def test_real_macbook_wrapper_actually_calls_contract_script():
    """Lock the wrapper -> harness invocation so the paths entry stays
    semantically correct."""
    wrapper = REPO_ROOT / "scripts/run_box2_helper3_v3_real_macbook.sh"
    assert wrapper.exists(), f"wrapper script missing: {wrapper}"
    assert "scripts/run_box2_helper3_v3_contract_tests.sh" in wrapper.read_text(
        encoding="utf-8"
    ), "real-MacBook wrapper no longer invokes the contract harness"
