"""F-04 — canonical 준비 계획을 ★추출★ 한다. 손으로 옮겨 적지 않는다.

감사 F-04 판정: 두 안 모두 자기가 정의한 ★축소 계획★ 을 들고 있었다.

    canonical `product-verify-repo-guards.yml` 이 실제로 하는 준비
      base ref preflight · ripgrep·jq 설치 · Node 20 · preflight_v1 ·
      ops dependency preflight · web_e2e npm ci · Playwright Chromium ·
      build stamp · artifact chain proof · 지정 환경변수
    두 안의 계획
      그 일부만

일부만 준비하고 계약을 돌리면, 통과해도 canonical 이 통과한 것과 같지 않다.
그런데 영수증에는 같은 이름으로 적힌다 — 이 트랙이 여섯 라운드 반복한 병이다.

★그래서 목록을 베끼지 않고 canonical YAML 에서 ★그때 읽어★ 만든다.
  canonical 이 바뀌면 이 계획도 바뀌고, 지문이 달라지고, 시험이 그것을 잡는다.
  손으로 옮겨 적으면 canonical 이 앞서갈 때 조용히 어긋난다.

★이 모듈은 계획을 ★만들 뿐★ 실행하지 않는다. 실행은 repo_contract_runner 다.
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

# ── 오류 코드 ──────────────────────────────────────────────────────────
CANONICAL_WORKFLOW_MISSING = "CANONICAL_WORKFLOW_MISSING"
CANONICAL_WORKFLOW_MALFORMED = "CANONICAL_WORKFLOW_MALFORMED"
CANONICAL_JOB_NOT_FOUND = "CANONICAL_JOB_NOT_FOUND"
CANONICAL_CONTRACT_STEP_NOT_FOUND = "CANONICAL_CONTRACT_STEP_NOT_FOUND"
CANONICAL_ACTION_UNRESOLVED = "CANONICAL_ACTION_UNRESOLVED"
CANONICAL_PLAN_INCOMPLETE = "CANONICAL_PLAN_INCOMPLETE"

CANONICAL_WORKFLOW_PATH = ".github/workflows/product-verify-repo-guards.yml"
CANONICAL_JOB_NAME = "product-verify-repo-guards"
CONTRACT_SCRIPT = "scripts/verify/verify_repo_contracts.sh"

# 셸 잡음. 명령이 아니므로 계획에 넣지 않는다.
_NOISE_PREFIXES = ("set ", "#")

# GitHub 표현식 — 실행 시 실제 값으로 바꾼다. 남겨 두면 문자열이 경로가 된다.
_EXPRESSION_RE = re.compile(r"\$\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


class CanonicalPlanError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CanonicalStep:
    """canonical 준비 단계 하나."""

    name: str
    kind: str            # "run" | "uses"
    argv: tuple[str, ...]
    cwd: str
    env: tuple[tuple[str, str], ...]
    source: str          # 어디서 왔는지(추적용). canonical step name 또는 action 경로

    def as_dict(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "argv": list(self.argv),
            "cwd": self.cwd, "env": [list(pair) for pair in self.env],
            "source": self.source,
        }


@dataclass(frozen=True)
class CanonicalPlan:
    """추출한 canonical 계획 전체."""

    preparation: tuple[CanonicalStep, ...]
    workflow_level: tuple[str, ...]     # uses: 로만 되는 것(checkout·setup-node 등)
    contract_argv: tuple[str, ...]
    contract_env: tuple[tuple[str, str], ...]
    workflow_sha256: str               # canonical 파일 원문 지문

    def sha256(self) -> str:
        canonical = json.dumps(
            {
                "preparation": [step.as_dict() for step in self.preparation],
                "workflow_level": list(self.workflow_level),
                "contract_argv": list(self.contract_argv),
                "contract_env": [list(pair) for pair in self.contract_env],
            },
            ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def command_keys(self) -> tuple[str, ...]:
        """비교용 정규화 키. 인자 순서까지 포함한다."""
        return tuple(" ".join(step.argv) for step in self.preparation)


def resolve_expressions(text: str, *, runner_temp: str) -> str:
    """`${{ runner.temp }}` 같은 표현식을 실제 값으로 바꾼다.

    알 수 없는 표현식은 남기지 않고 닫는다 — 문자열 그대로 경로가 되면
    존재하지 않는 디렉터리를 가리키고, 그 사실이 조용히 묻힌다.
    """
    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key == "runner.temp":
            return runner_temp
        raise CanonicalPlanError(CANONICAL_PLAN_INCOMPLETE)

    return _EXPRESSION_RE.sub(substitute, text)


def _command_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(_NOISE_PREFIXES):
            continue
        lines.append(line)
    return lines


def _argv_of(line: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(line))
    except ValueError as exc:
        raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED) from exc


def _resolve_local_action(root: Path, reference: str) -> list[tuple[str, tuple[str, ...]]]:
    """로컬 composite action 의 run 명령을 꺼낸다(`./.github/actions/...`)."""
    import yaml

    action_dir = root / reference.removeprefix("./")
    for filename in ("action.yml", "action.yaml"):
        path = action_dir / filename
        if path.is_file():
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED) from exc
            runs = document.get("runs") if isinstance(document, dict) else None
            steps = runs.get("steps") if isinstance(runs, dict) else None
            if not isinstance(steps, list):
                raise CanonicalPlanError(CANONICAL_ACTION_UNRESOLVED)
            collected: list[tuple[str, tuple[str, ...]]] = []
            for step in steps:
                if not isinstance(step, dict) or "run" not in step:
                    continue
                for line in _command_lines(str(step["run"])):
                    collected.append((str(step.get("name") or reference), _argv_of(line)))
            if not collected:
                raise CanonicalPlanError(CANONICAL_ACTION_UNRESOLVED)
            return collected
    raise CanonicalPlanError(CANONICAL_ACTION_UNRESOLVED)


def extract_canonical_plan(root: Path, *, runner_temp: str = "/tmp") -> CanonicalPlan:
    """canonical 워크플로에서 준비 계획을 읽어 만든다."""
    import yaml

    workflow_path = root / CANONICAL_WORKFLOW_PATH
    try:
        raw = workflow_path.read_bytes()
    except OSError as exc:
        raise CanonicalPlanError(CANONICAL_WORKFLOW_MISSING) from exc
    try:
        document = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED) from exc

    jobs = document.get("jobs") if isinstance(document, dict) else None
    job = jobs.get(CANONICAL_JOB_NAME) if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        raise CanonicalPlanError(CANONICAL_JOB_NOT_FOUND)
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED)

    job_env = job.get("env") if isinstance(job.get("env"), dict) else {}

    preparation: list[CanonicalStep] = []
    workflow_level: list[str] = []
    contract_argv: tuple[str, ...] = ()
    contract_env: dict[str, str] = {}

    for step in steps:
        if not isinstance(step, dict):
            raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED)
        name = str(step.get("name") or "")
        step_env = step.get("env") if isinstance(step.get("env"), dict) else {}
        merged_env = {
            str(k): resolve_expressions(str(v), runner_temp=runner_temp)
            for k, v in {**job_env, **step_env}.items()
        }

        if "uses" in step:
            reference = str(step["uses"])
            if reference.startswith("./"):
                for source_name, argv in _resolve_local_action(root, reference):
                    preparation.append(CanonicalStep(
                        name=name or source_name, kind="run", argv=argv, cwd=".",
                        env=tuple(sorted(merged_env.items())), source=reference,
                    ))
            else:
                # checkout·setup-node 등은 워크플로가 해야 한다. 명령으로 흉내내지 않는다.
                workflow_level.append(reference)
            continue

        if "run" not in step:
            raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED)

        body = resolve_expressions(str(step["run"]), runner_temp=runner_temp)
        lines = _command_lines(body)
        if any(CONTRACT_SCRIPT in line for line in lines):
            # ★계약 자체는 준비가 아니다. 따로 담고 env 를 보존한다.
            for line in lines:
                if CONTRACT_SCRIPT in line:
                    contract_argv = _argv_of(line)
            contract_env = merged_env
            continue

        for line in lines:
            preparation.append(CanonicalStep(
                name=name or line[:40], kind="run", argv=_argv_of(line), cwd=".",
                env=tuple(sorted(merged_env.items())), source=name,
            ))

    if not contract_argv:
        raise CanonicalPlanError(CANONICAL_CONTRACT_STEP_NOT_FOUND)
    if not preparation:
        raise CanonicalPlanError(CANONICAL_PLAN_INCOMPLETE)

    return CanonicalPlan(
        preparation=tuple(preparation),
        workflow_level=tuple(workflow_level),
        contract_argv=contract_argv,
        contract_env=tuple(sorted(contract_env.items())),
        workflow_sha256=hashlib.sha256(raw).hexdigest(),
    )


def missing_steps(
    plan: CanonicalPlan, executed_keys: tuple[str, ...]
) -> tuple[str, ...]:
    """canonical 이 요구하는데 실제 계획에 없는 명령을 돌려준다.

    ★"우리 계획에 canonical 이 다 들어 있는가" 를 묻는다. 반대가 아니다.
      AC-25 는 canonical 보다 ★더★ 준비할 수 있다(§7-3 이 요구한 npm build·helm).
      그러나 ★덜★ 준비하면 안 된다.
    """
    executed = set(executed_keys)
    return tuple(key for key in plan.command_keys() if key not in executed)


__all__ = [
    "CANONICAL_ACTION_UNRESOLVED",
    "CANONICAL_CONTRACT_STEP_NOT_FOUND",
    "CANONICAL_JOB_NAME",
    "CANONICAL_JOB_NOT_FOUND",
    "CANONICAL_PLAN_INCOMPLETE",
    "CANONICAL_WORKFLOW_MALFORMED",
    "CANONICAL_WORKFLOW_MISSING",
    "CANONICAL_WORKFLOW_PATH",
    "CONTRACT_SCRIPT",
    "CanonicalPlan",
    "CanonicalPlanError",
    "CanonicalStep",
    "extract_canonical_plan",
    "missing_steps",
    "resolve_expressions",
]
