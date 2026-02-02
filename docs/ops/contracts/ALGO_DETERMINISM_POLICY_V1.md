# Algorithm Determinism Policy v1 (SSOT)

## Modes
- D0_BIT_EXACT: 동일 환경(동일 런타임/동일 백엔드/동일 디바이스 또는 CI CPU)에서 결과가 완전 동일해야 함
- D1_EPSILON: 백엔드/디바이스 차이 가능 경로는 허용오차(epsilon)를 정책으로 고정(후속 단계)

## Fixed rules
MODE=D0_BIT_EXACT
SEED=1234

# D0에서는 결과 해시(sha256)가 완전 동일해야 한다.
# D1에서는 epsilon 정책을 추가로 정의한다(후속 PR).

## Output contract (meta-only)
- 결과는 원문 없이 체크섬/모드/버전만 남긴다.

