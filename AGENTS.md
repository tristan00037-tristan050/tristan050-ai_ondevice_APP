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
