# 결함 기록 — e2e 스모크 스크립트 격리(중복 재실행) 결함

- 상태: `E2E_SCRIPT_ISOLATION_DEFECT=OPEN_SEPARATE_TRACK` (재검토팀 판정, 별도 트랙)
- 대상: `scripts/e2e/e2e_smoke_test.sh` (**이 문서는 기록만 — 스크립트를 고치지 않는다**)
- 최초 관측: 2026-08-02, 그룹A 인계 앱(overlay `559e61dd`) e2e 완주 시도 중
- 분류: 시험 하네스 결함(제품 결함 아님)

---

## 1. 증상

`BUTLER_REQUIRE_INSTALLED_APP_SMOKE=1` 로 `scripts/e2e/e2e_smoke_test.sh` 를 돌리면
**[7/7] 회귀 테스트 단계에서 pytest 가 exit 1** 로 끝나고, 스크립트가
`set -e` 로 중단되어 마지막 줄 `=== E2E 스모크 PASS ===`(line 187) 에 도달하지 못한다.

```
[6/7] /health 200 · /api/sidecar/health 200 · /api/model/status 200
[7/7] 회귀 테스트 실행...
INFO:     Shutting down
scripts/e2e/e2e_smoke_test.sh: line 16: <pid> Terminated: 15  ... butler_sidecar.py
→ E2E_RC=1
```

## 2. 원인 — 같은 lifecycle 시험의 **중복 재실행 + 인스턴스 겹침**

이 스크립트는 한 실행 안에서 Butler 인스턴스를 **여러 개 동시에 살려 둔다.**

- **[3/7]** (line 59, 70): 설치된 `Butler.app` 을 `open -n` 으로 기동 →
  기본 저장소(단일-인스턴스 락)를 잡은 채 유지된다.
- **[5/7]** (line 117): 소스 `butler_sidecar.py --port 5903` 을 기동 → 스크립트
  종료(trap)까지 살아 있다.
- **[7/7]** (line 176–178):
  ```
  RESULT=$(${PYTHON_CMD} -m pytest tests/test_sidecar_lifecycle.py -v --tb=short ...)
  ```
  그런데 `tests/test_sidecar_lifecycle.py` 안의
  `test_adv_wrapper_no_orphan_after_kill` 는 **또 다른 Butler 인스턴스**
  (`/Applications/Butler.app/.../butler-sidecar --port 5911`)를 띄운다.

[3/7]·[5/7] 인스턴스가 아직 저장소 단일-인스턴스 락을 쥐고 있는 상태에서
[7/7] 이 **같은 lifecycle 시험을 중복 재실행**하며 세 번째 인스턴스를 띄우므로,
`HOME_INSTANCE_ALREADY_RUNNING` 저장소 락 충돌로 그 케이스가 실패한다.

`pytest ... | tail -15` 는 `pipefail` 아래에서 pytest 의 exit 1 을 전파하고,
`RESULT=$(...)` 대입이 `set -e` 를 물어 스크립트가 [7/7] 에서 중단된다.

## 3. 대조 — 단독 실행은 통과

동일한 `tests/test_sidecar_lifecycle.py` 를 **다른 인스턴스 없이 단독 격리**로 돌리면
**7 passed / exit 0** 이다.

```
$ python -m pytest tests/test_sidecar_lifecycle.py -q
7 passed, 7 warnings
```

즉 lifecycle 시험 자체·제품은 정상이며, 실패는 **e2e 스크립트가 인스턴스를 겹쳐
띄운 채 같은 시험을 재실행**하기 때문이다.

## 4. 재현 방법

1. 재서명된 `Butler.app` 을 `/Applications` 에 설치.
2. 실행:
   ```
   BUTLER_APP_PATH="<Butler.app>" \
   BUTLER_REQUIRE_INSTALLED_APP_SMOKE=1 \
     bash scripts/e2e/e2e_smoke_test.sh
   ```
3. [3/7]·[5/7] 통과 후 **[7/7] 에서 pytest exit 1 → 스크립트 중단** 관측.
4. 대조: `python -m pytest tests/test_sidecar_lifecycle.py -q` 단독 → **7 passed**.

관측된 e2e 단계: **[4/7]~[6/7] 통과(엔드포인트 전부 200), [7/7] 에서만 중단.**

## 5. 고치는 방향 (제안만 — **이 트랙에서 구현하지 않는다**)

아래는 후보이며, 채택·구현은 별도 지시를 따른다.

- **(A) [7/7] 전 인스턴스 정리**: [7/7] 회귀 시험 직전에 [3/7]·[5/7] 인스턴스를
  종료(포트/프로세스 정리)해 단일 인스턴스만 남긴 뒤 lifecycle 시험을 돌린다.
- **(B) 중복 재실행 제거**: [3/7]/[5/7] 로 이미 기동 검증을 했다면, [7/7] 에서
  `test_sidecar_lifecycle.py` 전체를 재실행하지 말고 인스턴스를 새로 띄우지 않는
  케이스만 돌리거나 회귀 단계를 분리한다.
- **(C) 시험별 저장소 격리**: lifecycle 래퍼 시험이 `BUTLER_APP_DATA_DIR` 로
  독립 저장소를 쓰도록 하여 락 충돌을 피한다(단, 래퍼가 기본 저장소를 고정하는지
  먼저 확인 필요).

어느 방향이든 **`scripts/e2e/e2e_smoke_test.sh` 수정**이 필요하므로, 재검토팀
판정에 따라 **별도 트랙**에서 처리한다.

## 6. 재검토팀 판정 원문

> `E2E_SCRIPT_ISOLATION_DEFECT=OPEN_SEPARATE_TRACK`
>
> 같은 시험이 혼자 돌 때는 통과하고, 다른 인스턴스와 겹쳐 돌 때만 실패했다.
> 제품 결함이 아니라 `e2e_smoke_test.sh` 가 같은 시험을 두 번(중복 재실행) 도는
> 설계 결함이다. repo 는 이번 인계에서 고치지 않는다. 이 구조 결함은 별도 트랙에
> 둔다.

(그룹A 인계 판정, 2026-08-02. 인계 자체는 [4/7]~[6/7] 통과 + lifecycle 단독
7 passed 를 근거로 CONDITIONAL_GO.)
