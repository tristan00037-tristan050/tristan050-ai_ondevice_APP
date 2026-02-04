#!/usr/bin/env python3
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError


@dataclass(frozen=True)
class LintError:
    file: str
    line: int
    col: int
    reason_code: str
    job: str = "-"
    step: str = "-"


def repo_root() -> Path:
    # scripts/ci/workflow_lint_gate.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def workflow_files(root: Path) -> List[Path]:
    wdir = root / ".github" / "workflows"
    files: List[Path] = []
    if wdir.is_dir():
        files += sorted(wdir.glob("*.yml"))
        files += sorted(wdir.glob("*.yaml"))
    return files


def lc_line_col(obj) -> tuple[int, int]:
    try:
        line = int(getattr(obj.lc, "line", 0)) + 1
        col = int(getattr(obj.lc, "col", 0)) + 1
        return line, col
    except Exception:
        return 0, 0


def main() -> int:
    root = repo_root()
    files = workflow_files(root)

    yaml = YAML(typ="rt")
    # Fail-Closed: duplicate keys must fail (e.g., duplicated "run:" in the same mapping)
    yaml.allow_duplicate_keys = False

    errors: List[LintError] = []

    for p in files:
        rel = str(p.relative_to(root))
        try:
            data = yaml.load(p.read_text(encoding="utf-8"))
        except DuplicateKeyError as e:
            mark = getattr(e, "problem_mark", None)
            line = int(getattr(mark, "line", -1)) + 1 if mark else 0
            col = int(getattr(mark, "column", -1)) + 1 if mark else 0
            errors.append(LintError(rel, line, col, "WORKFLOW_DUPLICATE_KEY"))
            continue
        except Exception:
            errors.append(LintError(rel, 0, 0, "WORKFLOW_YAML_PARSE_ERROR"))
            continue

        if not isinstance(data, dict):
            errors.append(LintError(rel, 0, 0, "WORKFLOW_INVALID_TOPLEVEL"))
            continue

        jobs = data.get("jobs")
        if not isinstance(jobs, dict):
            errors.append(LintError(rel, 0, 0, "WORKFLOW_JOBS_MISSING"))
            continue

        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps")
            if steps is None:
                continue
            if not isinstance(steps, list):
                errors.append(LintError(rel, 0, 0, "WORKFLOW_STEPS_NOT_LIST", job=str(job_id)))
                continue

            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                has_run = "run" in step
                has_uses = "uses" in step
                if not (has_run or has_uses):
                    line, col = lc_line_col(step)
                    errors.append(LintError(rel, line, col, "WORKFLOW_EMPTY_STEP", job=str(job_id), step=str(idx)))

    ok = 1 if not errors else 0
    print(f"WORKFLOW_LINT_OK={ok}")
    print(f"WORKFLOW_LINT_ERROR_COUNT={len(errors)}")

    for e in errors[:50]:
        print(f"WORKFLOW_LINT_ERROR={e.file}:{e.line}:{e.col} reason_code={e.reason_code} job={e.job} step={e.step}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
