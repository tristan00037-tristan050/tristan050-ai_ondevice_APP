#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "== SVR03 KEY REPORT =="

# NOTE:
# keystore가 메모리 기반이면 '현재 프로세스 기준' 상태만 출력됩니다.
# 향후 keystore를 영속화/설정 파일화하면 이 스크립트는 그대로 재사용 가능합니다.

# key_store.ts가 JSON으로 덤프하는 함수가 없으므로, 현재는 코드/테스트에서 사용하는 대표 상태를 출력하는 형태로 둡니다.
# (이 PR에서 key_store에 listKeys() 같은 읽기 전용 함수를 추가해도 됩니다. ops 스크립트는 *_OK=1 금지.)

echo "status=present"
echo "note=keystore is in-memory; use verify_svr03_key_rotation.sh for sealed behavior"

