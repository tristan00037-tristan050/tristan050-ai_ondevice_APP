# AGENTS.md

이 파일은 코딩/운영 에이전트가 레포에서 따라야 하는 프로젝트 지침입니다.

핵심 규율(불가침)
- verify 출력은 판정만: 키=0/1 + 짧은 ERROR_CODE만 허용
- meta-only/원문0: 비밀/원문/스택/긴 덤프 출력 금지
- fail-closed: 누락/드리프트/스키마 위반은 즉시 BLOCK
- CI clean-finish: CI에서 docs 변경(생성/수정 tracked+untracked) 금지(out 루트 사용)
- 경로 스코프: PATH_SCOPE SSOT를 읽고 허용된 범위에서만 동작

레포 앵커(불가침)
- bash scripts/verify/verify_repo_contracts.sh ; echo "EXIT=$?"

이 파일 내용은 리포트/로그에 원문으로 남기지 않습니다.
필요한 경우에도 해시(sha256)와 스코프만 meta-only로 기록합니다.

## Cursor Cloud specific instructions

### Services overview

| Service | Port | Start command | Directory |
|---------|------|---------------|-----------|
| Butler Sidecar (FastAPI) | 8765 | `python3 butler_sidecar.py --host 0.0.0.0 --port 8765` | repo root (the directory containing `butler_sidecar.py`) |
| BFF Accounting (Express) | 8081 | `npm run dev:bff` | `webcore_appcore_starter_4_17/` |
| Ops Console (Vite/React) | 5173 | `npm run dev:web` | `webcore_appcore_starter_4_17/` |
| Butler Desktop (Vite/React) | 1420 | `npx vite --host 0.0.0.0 --port 1420` | `butler-desktop/` |

### Running tests

- **Python tests**: `python3 -m pytest tests/ -v --ignore=tests/turboq/ --ignore=tests/eval/test_eval_hardcase.py --ignore=tests/eval/test_eval_judge_v3.py` (from repo root). `tests/turboq/` requires `torch`/GPU; `tests/eval/test_eval_hardcase.py` and `tests/eval/test_eval_judge_v3.py` have pre-existing import errors against `scripts/eval/eval_judge_v3.py` (`load_hardcase_records` / `run_full_eval` not exported).
- **Butler Desktop tests**: `npx vitest run` (from `butler-desktop/`).
- **Repo contracts**: `bash scripts/verify/verify_repo_contracts.sh` (must pass for all PRs).

### Gotchas

- `$HOME/.local/bin` must be on PATH for `pytest`, `uvicorn`, `fastapi` CLI tools installed via pip.
- The sidecar runs without a model file (`BUTLER_MODEL_PATH` unset) in "no_model" mode — health/precheck/request_parsing endpoints still work. LLM inference endpoints return stub responses.
- The `webcore_appcore_starter_4_17` BFF starts without `DATABASE_URL` and falls back to in-memory mode; set `DATABASE_URL=postgres://app:app@localhost:5432/app` with a running Postgres for full persistence.
- Build webcore server packages before starting the BFF: `npm run build:packages:server` (in `webcore_appcore_starter_4_17/`).
- Ops Console has a pre-existing syntax error in `packages/ops-console/src/pages/rollout/RolloutPage.tsx` that prevents the Vite dev server from rendering the rollout page. Other pages may work.
