"""A-02 — canonical 준비 계획과의 ★정확한 동등성★. 포함관계가 아니다.

v3.1 §3 이 이 모듈의 계약이다.

    이전 판의 결함(v3.1 §1-2)
      `missing_steps()` 는 canonical ★누락만★ 찾고 ★추가는 허용★ 했다.
      회귀시험 `test_extra_ac25_steps_are_allowed` 가 그 방향을 고정하고 있었다.
      상위집합이 "동등" 으로 통과했다.

    이 판
      순서 · 중복 · argv · cwd · shell · env · action ref · action input 을
      ★전부★ 비교한다. 다섯 축(missing/extra/reordered/mutated/unsupported)
      중 하나라도 0 이 아니면 동등이 아니다.

★의미를 보존하지 못하는 문법은 추측하지 않고 닫는다(§3-2).
★계획을 ★만들 뿐★ 실행하지 않는다. 실행은 repo_contract_runner 다.
★PyYAML 을 쓰지 않는다. 이 코드는 신뢰 경로에서 돌고, `python3 -S` 로
  표준 라이브러리만으로 import 가능해야 한다(v3.1 §7).
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from .workflow_yaml import WorkflowYamlError, load_workflow

# ── 오류 코드 ──────────────────────────────────────────────────────────
CANONICAL_WORKFLOW_MISSING = "CANONICAL_WORKFLOW_MISSING"
CANONICAL_WORKFLOW_MALFORMED = "CANONICAL_WORKFLOW_MALFORMED"
CANONICAL_JOB_NOT_FOUND = "CANONICAL_JOB_NOT_FOUND"
CANONICAL_CONTRACT_STEP_NOT_FOUND = "CANONICAL_CONTRACT_STEP_NOT_FOUND"
CANONICAL_ACTION_UNRESOLVED = "CANONICAL_ACTION_UNRESOLVED"
CANONICAL_PLAN_INCOMPLETE = "CANONICAL_PLAN_INCOMPLETE"
# ★v3.1 §3-2 — 현재 parser 가 의미를 보존하지 못하는 문법을 만나면 이 코드로 닫는다.
CANONICAL_PLAN_UNSUPPORTED_SEMANTICS = "CANONICAL_PLAN_UNSUPPORTED_SEMANTICS"

CANONICAL_WORKFLOW_PATH = ".github/workflows/product-verify-repo-guards.yml"
CANONICAL_JOB_NAME = "product-verify-repo-guards"
CONTRACT_SCRIPT = "scripts/verify/verify_repo_contracts.sh"

# exact-head job 이 사는 곳. 실행 측 action·harness 선언을 여기서 읽는다.
EXECUTION_WORKFLOW_PATH = ".github/workflows/box5-ac25-stage-a-smoke.yml"
EXECUTION_JOB_NAME = "ac25-repo-contracts-exact-head"

# ★harness — exact-head job 이 실행해도 되는 유일한 run 명령(§3-5).
#   다른 이름·wrapper·shell 로 준비를 되살리면 여기서 EXTRA 로 잡힌다.
APPROVED_HARNESS_ARGV = ("python3", "-S", "-m", "ac25.repo_contract_runner")

# ★§3-3 (2) — mutable tag 를 고정할 수 있는, 저장소가 승인한 full SHA.
#   시험이 이 표와 실제 워크플로 pin 의 일치를 강제한다.
APPROVED_ACTION_PINS = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
}

# ★비교는 ★유효값★ 으로 한다. 명시하지 않은 input 은 action 의 문서화된
#   기본값과 같다 — canonical 의 `lfs: false` 와 무명시( = false)는 같은 뜻이다.
_ACTION_INPUT_DEFAULTS = {
    "actions/checkout": {
        "clean": "true",
        "fetch-depth": "1",
        "lfs": "false",
        "persist-credentials": "true",
        "ref": "",
        "submodules": "false",
    },
    "actions/setup-node": {
        "always-auth": "false",
        "check-latest": "false",
    },
}

# ★§3-3 이 허용한 차이 ①②와, 자격 비영속화 하나.
#   `ref` 는 exact PR head 로 고정된 값만 허용한다.
#   `persist-credentials=false` 는 자격을 ★남기지 않는★ 축소 방향 강화라
#   준비 결과(작업트리 내용)를 바꾸지 않는다. 확대 방향 차이는 허용하지 않는다.
EXACT_HEAD_MARKER = "<exact-pr-head>"
PR_BASE_MARKER = "<pr-base-sha>"
_ALLOWED_INPUT_OVERRIDES = {
    "actions/checkout": {
        "ref": (EXACT_HEAD_MARKER,),
        "persist-credentials": ("false",),
    },
}

# ★§3-3 (3) — 비변형 observation 명령 allowlist. 준비로 세지 않는다.
#   파일 설치·생성·삭제·수정으로 이어지면 observation 이 아니라 준비 위반이다.
OBSERVATION_ALLOWLIST = (
    ("git", "rev-parse", "HEAD"),
    ("git", "show", "-s", "--format=%T", "HEAD"),
    ("git", "rev-parse", "--is-shallow-repository"),
    ("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"),
    ("git", "diff", "--quiet"),
    ("git", "diff", "--cached", "--quiet"),
    ("python3", "--version"),
    ("node", "--version"),
    ("npm", "--version"),
    ("git", "--version"),
    ("helm", "version", "--short"),
)

# 셸 잡음. 명령이 아니므로 계획에 넣지 않는다.
_NOISE_PREFIXES = ("set ", "#")

_EXPRESSION_RE = re.compile(r"\$\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
# 표현식 치환 뒤에도 남은 셸 메타문자는 ★다른 의미★ 가 될 수 있다 — 닫는다.
_SHELL_META_RE = re.compile(r"[|;&<>`$]")

# 계획이 다루는 step 키. 이 밖의 의미 있는 키가 나오면 추측하지 않는다.
_KNOWN_STEP_KEYS = {
    "name", "run", "uses", "with", "env", "shell", "working-directory", "id",
}
_UNSUPPORTED_STEP_KEYS = {"if", "continue-on-error", "strategy", "timeout-minutes"}
_UNSUPPORTED_JOB_KEYS = {"strategy", "container", "services"}


class CanonicalPlanError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ── §3-2 계획 자료형 ───────────────────────────────────────────────────
@dataclass(frozen=True)
class CanonicalRunStep:
    index: int
    name: str
    argv: tuple[str, ...]
    cwd: str
    shell: str
    env: tuple[tuple[str, str], ...]
    source: str

    def fingerprint(self) -> tuple:
        """이름·index 를 뺀 ★내용★. 같은 anchor 에서 내용이 다르면 MUTATED 다."""
        return (self.argv, self.cwd, self.shell, self.env)

    def as_dict(self) -> dict:
        return {
            "index": self.index, "name": self.name, "argv": list(self.argv),
            "cwd": self.cwd, "shell": self.shell,
            "env": [list(pair) for pair in self.env], "source": self.source,
        }


@dataclass(frozen=True)
class CanonicalActionStep:
    index: int
    name: str
    uses: str
    with_args: tuple[tuple[str, str], ...]
    env: tuple[tuple[str, str], ...]
    source: str

    @property
    def family(self) -> str:
        return self.uses.split("@", 1)[0]

    @property
    def ref(self) -> str:
        return self.uses.split("@", 1)[1] if "@" in self.uses else ""

    def as_dict(self) -> dict:
        return {
            "index": self.index, "name": self.name, "uses": self.uses,
            "with": [list(pair) for pair in self.with_args],
            "env": [list(pair) for pair in self.env], "source": self.source,
        }


@dataclass(frozen=True)
class PlanDiff:
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    reordered: tuple[str, ...]
    mutated: tuple[str, ...]
    unsupported: tuple[str, ...]

    @property
    def exact(self) -> bool:
        return not any(
            (self.missing, self.extra, self.reordered, self.mutated, self.unsupported)
        )

    def merged(self, other: "PlanDiff") -> "PlanDiff":
        return PlanDiff(
            missing=self.missing + other.missing,
            extra=self.extra + other.extra,
            reordered=self.reordered + other.reordered,
            mutated=self.mutated + other.mutated,
            unsupported=self.unsupported + other.unsupported,
        )


EMPTY_DIFF = PlanDiff((), (), (), (), ())


@dataclass(frozen=True)
class CanonicalPlan:
    preparation: tuple[CanonicalRunStep, ...]
    actions: tuple[CanonicalActionStep, ...]
    contract_argv: tuple[str, ...]
    contract_env: tuple[tuple[str, str], ...]
    workflow_sha256: str

    def sha256(self) -> str:
        canonical = json.dumps(
            {
                "preparation": [step.as_dict() for step in self.preparation],
                "actions": [step.as_dict() for step in self.actions],
                "contract_argv": list(self.contract_argv),
                "contract_env": [list(pair) for pair in self.contract_env],
            },
            ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionPlan:
    """실행 측이 실제로 하려는 것 — 준비 run 과 워크플로 action·harness."""

    runs: tuple[CanonicalRunStep, ...]
    actions: tuple[CanonicalActionStep, ...]
    harness: tuple[CanonicalRunStep, ...]


# ── 표현식 ─────────────────────────────────────────────────────────────
def resolve_expressions(
    text: str,
    *,
    runner_temp: str,
    allowed: dict[str, str] | None = None,
) -> str:
    """`${{ runner.temp }}` 등 ★아는 표현식만★ 실제 값으로 바꾼다.

    모르는 표현식(동적 secrets 포함)은 추측하지 않고 닫는다(§3-2).
    """
    table = {"runner.temp": runner_temp}
    if allowed:
        table.update(allowed)

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in table:
            return table[key]
        raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)

    return _EXPRESSION_RE.sub(substitute, text)


def _scalar_text(value) -> str:
    """YAML 스칼라를 비교용 문자열로 정규화한다. bool 은 소문자로 간다."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _command_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(_NOISE_PREFIXES):
            continue
        lines.append(line)
    return lines


def _argv_of(line: str) -> tuple[str, ...]:
    # 표현식 치환 뒤에도 셸 메타문자가 남았다면 shlex 분해가 ★뜻을 바꾼다★.
    if _SHELL_META_RE.search(line):
        raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)
    try:
        return tuple(shlex.split(line))
    except ValueError as exc:
        raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED) from exc


def _assert_supported_step(step: dict) -> None:
    for key in step:
        if key in _UNSUPPORTED_STEP_KEYS:
            raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)
        if key not in _KNOWN_STEP_KEYS:
            raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)


def _assert_supported_job(job: dict) -> None:
    for key in _UNSUPPORTED_JOB_KEYS:
        if key in job:
            raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)


def _run_defaults(scope: dict) -> tuple[str | None, str | None]:
    """defaults.run 의 (shell, working-directory)."""
    defaults = scope.get("defaults")
    run = defaults.get("run") if isinstance(defaults, dict) else None
    if not isinstance(run, dict):
        return None, None
    return (
        _scalar_text(run["shell"]) if "shell" in run else None,
        _scalar_text(run["working-directory"]) if "working-directory" in run else None,
    )


def _compose(step_value, job_value, workflow_value, fallback: str) -> str:
    for value in (step_value, job_value, workflow_value):
        if value:
            return value
    return fallback


def _resolve_local_action(
    root: Path, reference: str, *, base_env: dict[str, str],
) -> list[tuple[str, tuple[str, ...], str, str, dict[str, str]]]:
    """로컬 composite action 을 내부 run step 의 shell·cwd·env 까지 펼친다.

    ★내부에 nested `uses` 가 있으면 의미를 보존할 수 없다 — 닫는다(§3-2).
    """
    action_dir = root / reference.removeprefix("./")
    for filename in ("action.yml", "action.yaml"):
        path = action_dir / filename
        if not path.is_file():
            continue
        try:
            document = load_workflow(path.read_text(encoding="utf-8"))
        except WorkflowYamlError as exc:
            raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED) from exc
        runs = document.get("runs") if isinstance(document, dict) else None
        steps = runs.get("steps") if isinstance(runs, dict) else None
        if not isinstance(steps, list):
            raise CanonicalPlanError(CANONICAL_ACTION_UNRESOLVED)
        collected: list[tuple[str, tuple[str, ...], str, str, dict[str, str]]] = []
        for step in steps:
            if not isinstance(step, dict):
                raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED)
            if "uses" in step:
                raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)
            _assert_supported_step(step)
            if "run" not in step:
                continue
            # composite run step 은 GitHub 가 shell 명시를 요구한다. 없으면 닫는다.
            if "shell" not in step:
                raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)
            shell = _scalar_text(step["shell"])
            cwd = _scalar_text(step.get("working-directory") or ".")
            step_env = step.get("env") if isinstance(step.get("env"), dict) else {}
            env = dict(base_env)
            env.update({str(k): _scalar_text(v) for k, v in step_env.items()})
            for line in _command_lines(str(step["run"])):
                collected.append(
                    (str(step.get("name") or reference), _argv_of(line), cwd, shell, env)
                )
        if not collected:
            raise CanonicalPlanError(CANONICAL_ACTION_UNRESOLVED)
        return collected
    raise CanonicalPlanError(CANONICAL_ACTION_UNRESOLVED)


def _load_job(root: Path, workflow_path: str, job_name: str) -> tuple[dict, dict, bytes]:
    path = root / workflow_path
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CanonicalPlanError(CANONICAL_WORKFLOW_MISSING) from exc
    try:
        document = load_workflow(raw.decode("utf-8"))
    except (UnicodeDecodeError, WorkflowYamlError) as exc:
        raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED) from exc
    jobs = document.get("jobs") if isinstance(document, dict) else None
    job = jobs.get(job_name) if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        raise CanonicalPlanError(CANONICAL_JOB_NOT_FOUND)
    _assert_supported_job(job)
    return document, job, raw


def _extract_job_steps(
    root: Path,
    *,
    workflow_path: str,
    job_name: str,
    runner_temp: str,
    allowed_expressions: dict[str, str] | None = None,
    expand_local_actions: bool = True,
) -> tuple[
    list[CanonicalRunStep], list[CanonicalActionStep],
    tuple[str, ...], dict[str, str], bytes,
]:
    """job 하나를 (run 목록, action 목록, 계약 argv, 계약 env, 원문) 으로 편다.

    cwd 는 workflow defaults → job defaults → step 순서로 합성한 실제 값이고,
    env 는 workflow → job → step 순서로 덮어쓴 최종 값이다(§3-2).
    """
    document, job, raw = _load_job(root, workflow_path, job_name)

    workflow_shell, workflow_cwd = _run_defaults(document)
    job_shell, job_cwd = _run_defaults(job)
    workflow_env = document.get("env") if isinstance(document.get("env"), dict) else {}
    job_env = job.get("env") if isinstance(job.get("env"), dict) else {}

    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED)

    def resolve(text: str) -> str:
        return resolve_expressions(
            text, runner_temp=runner_temp, allowed=allowed_expressions
        )

    runs: list[CanonicalRunStep] = []
    actions: list[CanonicalActionStep] = []
    contract_argv: tuple[str, ...] = ()
    contract_env: dict[str, str] = {}
    run_index = 0
    action_index = 0

    for step in steps:
        if not isinstance(step, dict):
            raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED)
        _assert_supported_step(step)
        name = str(step.get("name") or "")
        step_env_raw = step.get("env") if isinstance(step.get("env"), dict) else {}
        merged_env = {
            str(k): resolve(_scalar_text(v))
            for k, v in {**workflow_env, **job_env, **step_env_raw}.items()
        }

        if "uses" in step:
            reference = str(step["uses"])
            if reference.startswith("./"):
                if not expand_local_actions:
                    raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)
                # uses step 자신의 env 도 action 내부 run 에 흐른다 — 버리지 않는다.
                for src_name, argv, cwd, shell, env in _resolve_local_action(
                    root, reference, base_env=merged_env
                ):
                    if shell != "bash":
                        raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)
                    runs.append(CanonicalRunStep(
                        index=run_index, name=f"{name or src_name}#0",
                        argv=argv, cwd=cwd, shell=shell,
                        env=tuple(sorted(env.items())),
                        source=f"action:{reference}",
                    ))
                    run_index += 1
            else:
                with_raw = step.get("with") if isinstance(step.get("with"), dict) else {}
                actions.append(CanonicalActionStep(
                    index=action_index, name=name, uses=reference,
                    with_args=tuple(sorted(
                        (str(k), resolve(_scalar_text(v))) for k, v in with_raw.items()
                    )),
                    env=tuple(sorted(merged_env.items())),
                    source=f"workflow:{name or reference}",
                ))
                action_index += 1
            continue

        if "run" not in step:
            raise CanonicalPlanError(CANONICAL_WORKFLOW_MALFORMED)

        shell = _compose(
            _scalar_text(step["shell"]) if "shell" in step else None,
            job_shell, workflow_shell, "bash",
        )
        if shell != "bash":
            raise CanonicalPlanError(CANONICAL_PLAN_UNSUPPORTED_SEMANTICS)
        cwd = _compose(
            _scalar_text(step["working-directory"]) if "working-directory" in step else None,
            job_cwd, workflow_cwd, ".",
        )

        body = resolve(str(step["run"]))
        lines = _command_lines(body)
        if any(CONTRACT_SCRIPT in line for line in lines):
            # ★계약 자체는 준비가 아니다. 따로 담고 env 를 보존한다.
            for line in lines:
                if CONTRACT_SCRIPT in line:
                    contract_argv = _argv_of(line)
            contract_env = merged_env
            continue

        for ordinal, line in enumerate(lines):
            runs.append(CanonicalRunStep(
                index=run_index, name=f"{name or line[:40]}#{ordinal}",
                argv=_argv_of(line), cwd=cwd, shell=shell,
                env=tuple(sorted(merged_env.items())),
                source=f"workflow:{name}",
            ))
            run_index += 1

    return runs, actions, contract_argv, contract_env, raw


def extract_canonical_plan(root: Path, *, runner_temp: str = "/tmp") -> CanonicalPlan:
    """canonical 워크플로에서 ★전체 충실도★ 계획을 읽어 만든다."""
    runs, actions, contract_argv, contract_env, raw = _extract_job_steps(
        root,
        workflow_path=CANONICAL_WORKFLOW_PATH,
        job_name=CANONICAL_JOB_NAME,
        runner_temp=runner_temp,
    )
    if not contract_argv:
        raise CanonicalPlanError(CANONICAL_CONTRACT_STEP_NOT_FOUND)
    if not runs:
        raise CanonicalPlanError(CANONICAL_PLAN_INCOMPLETE)
    return CanonicalPlan(
        preparation=tuple(runs),
        actions=tuple(actions),
        contract_argv=contract_argv,
        contract_env=tuple(sorted(contract_env.items())),
        workflow_sha256=hashlib.sha256(raw).hexdigest(),
    )


def extract_execution_workflow(
    root: Path, *, runner_temp: str = "/tmp"
) -> tuple[tuple[CanonicalActionStep, ...], tuple[CanonicalRunStep, ...]]:
    """exact-head job 의 선언(action 목록, run 목록)을 읽는다.

    실행 측에서만 exact-head 표현식 둘을 marker 로 허용한다(§3-3 ①).
    """
    runs, actions, _argv, _env, _raw = _extract_job_steps(
        root,
        workflow_path=EXECUTION_WORKFLOW_PATH,
        job_name=EXECUTION_JOB_NAME,
        runner_temp=runner_temp,
        allowed_expressions={
            "github.event.pull_request.head.sha": EXACT_HEAD_MARKER,
            "github.event.pull_request.base.sha": PR_BASE_MARKER,
        },
        expand_local_actions=False,
    )
    return tuple(actions), tuple(runs)


# ── §3-4 완전 비교 ─────────────────────────────────────────────────────
def _anchors(steps: tuple[CanonicalRunStep, ...]) -> list[str]:
    return [step.name for step in steps]


def _compare_runs(
    expected: tuple[CanonicalRunStep, ...],
    actual: tuple[CanonicalRunStep, ...],
) -> PlanDiff:
    """순서·중복·argv·cwd·shell·env 완전 비교. anchor 는 step 이름+행 번호다."""
    expected_by_anchor: dict[str, list[CanonicalRunStep]] = {}
    for step in expected:
        expected_by_anchor.setdefault(step.name, []).append(step)
    actual_by_anchor: dict[str, list[CanonicalRunStep]] = {}
    for step in actual:
        actual_by_anchor.setdefault(step.name, []).append(step)

    missing: list[str] = []
    extra: list[str] = []
    mutated: list[str] = []

    for anchor in sorted(set(expected_by_anchor) | set(actual_by_anchor)):
        exp = expected_by_anchor.get(anchor, [])
        act = actual_by_anchor.get(anchor, [])
        for exp_step, act_step in zip(exp, act):
            if exp_step.fingerprint() != act_step.fingerprint():
                mutated.append(anchor)
        if len(exp) > len(act):
            missing.extend([anchor] * (len(exp) - len(act)))
        elif len(act) > len(exp):
            extra.extend([anchor] * (len(act) - len(exp)))

    reordered: list[str] = []
    if not (missing or extra):
        expected_order = _anchors(expected)
        actual_order = _anchors(actual)
        if expected_order != actual_order:
            reordered = [
                anchor for anchor, other in zip(expected_order, actual_order)
                if anchor != other
            ] or ["<order>"]

    return PlanDiff(
        missing=tuple(missing), extra=tuple(extra),
        reordered=tuple(reordered), mutated=tuple(mutated), unsupported=(),
    )


def _effective_inputs(action: CanonicalActionStep) -> dict[str, str]:
    effective = dict(_ACTION_INPUT_DEFAULTS.get(action.family, {}))
    effective.update(dict(action.with_args))
    return effective


def _compare_actions(
    expected: tuple[CanonicalActionStep, ...],
    actual: tuple[CanonicalActionStep, ...],
) -> PlanDiff:
    """family·ref·유효 input 을 순서까지 비교한다(§3-2·§3-3).

    허용 차이는 셋뿐이다 — exact-head ref · 승인된 full SHA pin ·
    자격 비영속화(축소 방향). 그 외 어떤 input 차이도 mutated 다.
    """
    missing: list[str] = []
    extra: list[str] = []
    mutated: list[str] = []
    reordered: list[str] = []

    expected_families = [step.family for step in expected]
    actual_families = [step.family for step in actual]
    if sorted(expected_families) == sorted(actual_families):
        if expected_families != actual_families:
            reordered = [f"action:{family}" for family in expected_families]
    else:
        seen = list(actual_families)
        for family in expected_families:
            if family in seen:
                seen.remove(family)
            else:
                missing.append(f"action:{family}")
        remainder = list(expected_families)
        for family in actual_families:
            if family in remainder:
                remainder.remove(family)
            else:
                extra.append(f"action:{family}")

    for exp_step, act_step in zip(expected, actual):
        if exp_step.family != act_step.family:
            continue  # 위에서 missing/extra 로 이미 잡혔다
        label = f"action:{exp_step.family}"
        if exp_step.env != act_step.env:
            mutated.append(f"{label}#env")
        if act_step.ref != exp_step.ref and act_step.ref != APPROVED_ACTION_PINS.get(
            exp_step.family, ""
        ):
            mutated.append(label)
            continue
        exp_inputs = _effective_inputs(exp_step)
        act_inputs = _effective_inputs(act_step)
        overrides = _ALLOWED_INPUT_OVERRIDES.get(exp_step.family, {})
        for key in sorted(set(exp_inputs) | set(act_inputs)):
            exp_value = exp_inputs.get(key, "")
            act_value = act_inputs.get(key, "")
            if exp_value == act_value:
                continue
            if act_value in overrides.get(key, ()):
                continue
            mutated.append(f"{label}#{key}")

    return PlanDiff(
        missing=tuple(missing), extra=tuple(extra),
        reordered=tuple(reordered), mutated=tuple(mutated), unsupported=(),
    )


def _compare_harness(harness: tuple[CanonicalRunStep, ...]) -> PlanDiff:
    """exact-head job 의 run step 은 승인된 harness 하나만 허용한다(§3-5)."""
    def metadata_exact(step: CanonicalRunStep) -> bool:
        env = dict(step.env)
        expected_keys = {
            "AC25_BASE_REF",
            "AC25_EVENT_HEAD_SHA",
            "GIT_LFS_SKIP_SMUDGE",
            "PLAYWRIGHT_BROWSERS_PATH",
            "PYTHONNOUSERSITE",
            "PYTHONPATH",
            "PYTHONDONTWRITEBYTECODE",
        }
        playwright = env.get("PLAYWRIGHT_BROWSERS_PATH", "")
        return (
            step.cwd == "."
            and step.shell == "bash"
            and set(env) == expected_keys
            and env["AC25_BASE_REF"] == PR_BASE_MARKER
            and env["AC25_EVENT_HEAD_SHA"] == EXACT_HEAD_MARKER
            and env["GIT_LFS_SKIP_SMUDGE"] == "1"
            and env["PYTHONNOUSERSITE"] == "1"
            and env["PYTHONDONTWRITEBYTECODE"] == "1"
            and env["PYTHONPATH"] == "scripts/ci"
            and playwright.startswith("/")
            and playwright.endswith("/ms-playwright")
            and "/../" not in playwright
        )

    if (
        len(harness) == 1
        and harness[0].argv == APPROVED_HARNESS_ARGV
        and metadata_exact(harness[0])
    ):
        return EMPTY_DIFF
    if not harness:
        return PlanDiff(("harness",), (), (), (), ())
    extra = tuple(
        f"harness:{step.name}" for step in harness
        if step.argv != APPROVED_HARNESS_ARGV
    )
    approved = [step for step in harness if step.argv == APPROVED_HARNESS_ARGV]
    missing = () if approved else ("harness",)
    mutated = () if not approved or all(
        metadata_exact(step) for step in approved
    ) else ("harness#metadata",)
    return PlanDiff(missing, extra, (), mutated, ())


def compare_exact_plan(*, expected: CanonicalPlan, actual: ExecutionPlan) -> PlanDiff:
    """순서·중복·argv·cwd·shell·env·action ref·with 를 완전 비교한다(§3-4)."""
    return (
        _compare_runs(expected.preparation, actual.runs)
        .merged(_compare_actions(expected.actions, actual.actions))
        .merged(_compare_harness(actual.harness))
    )


def observation_only(argv: tuple[str, ...]) -> bool:
    """§3-3 (3) — allowlist 에 정확히 일치하는 명령만 observation 이다."""
    return tuple(argv) in OBSERVATION_ALLOWLIST


# ── §7 self-check — `python3 -S -m ac25.canonical_plan --self-check` ──
def _self_check() -> int:
    import sys

    root = Path.cwd()
    try:
        plan = extract_canonical_plan(root, runner_temp="/tmp")
        actions, harness = extract_execution_workflow(root, runner_temp="/tmp")
        execution = ExecutionPlan(plan.preparation, actions, harness)
        diff = compare_exact_plan(expected=plan, actual=execution)
        if not diff.exact:
            raise CanonicalPlanError(CANONICAL_PLAN_INCOMPLETE)
    except CanonicalPlanError as exc:
        print("CANONICAL_SELF_CHECK=FAIL")
        print(f"ERROR_CODE={exc.code}")
        return 1
    # ★production import graph 가 표준 라이브러리만으로 여기까지 왔다는 사실
    #   자체가 -S 실행에서의 증거다. 수치는 관측값만 낸다.
    stdlib_names = getattr(sys, "stdlib_module_names", frozenset())
    third_party = []
    for name, module in sorted(sys.modules.items()):
        top = name.split(".")[0]
        if top in stdlib_names or name.startswith(("ac25", "_")):
            continue
        location = str(getattr(module, "__file__", "") or "")
        if not location or (
            "site-packages" not in location and "dist-packages" not in location
        ):
            continue
        third_party.append(name)
    print("CANONICAL_SELF_CHECK=PASS")
    print(f"CANONICAL_STEP_COUNT={len(plan.preparation)}")
    print(f"CANONICAL_ACTION_COUNT={len(plan.actions)}")
    print(f"EXECUTION_ACTION_COUNT={len(actions)}")
    print(f"EXECUTION_HARNESS_STEP_COUNT={len(harness)}")
    print(f"CANONICAL_PLAN_SHA256={plan.sha256()}")
    print(f"PRODUCTION_THIRD_PARTY_IMPORT_COUNT={len(third_party)}")
    return 0 if not third_party else 1


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["--self-check"]:
        raise SystemExit(_self_check())
    print("CANONICAL_SELF_CHECK=FAIL")
    print("ERROR_CODE=CANONICAL_SELF_CHECK_USAGE")
    raise SystemExit(1)


__all__ = [
    "APPROVED_ACTION_PINS",
    "APPROVED_HARNESS_ARGV",
    "CANONICAL_ACTION_UNRESOLVED",
    "CANONICAL_CONTRACT_STEP_NOT_FOUND",
    "CANONICAL_JOB_NAME",
    "CANONICAL_JOB_NOT_FOUND",
    "CANONICAL_PLAN_INCOMPLETE",
    "CANONICAL_PLAN_UNSUPPORTED_SEMANTICS",
    "CANONICAL_WORKFLOW_MALFORMED",
    "CANONICAL_WORKFLOW_MISSING",
    "CANONICAL_WORKFLOW_PATH",
    "CONTRACT_SCRIPT",
    "EMPTY_DIFF",
    "EXACT_HEAD_MARKER",
    "EXECUTION_JOB_NAME",
    "EXECUTION_WORKFLOW_PATH",
    "OBSERVATION_ALLOWLIST",
    "PR_BASE_MARKER",
    "CanonicalActionStep",
    "CanonicalPlan",
    "CanonicalPlanError",
    "CanonicalRunStep",
    "ExecutionPlan",
    "PlanDiff",
    "compare_exact_plan",
    "extract_canonical_plan",
    "extract_execution_workflow",
    "observation_only",
    "resolve_expressions",
]
