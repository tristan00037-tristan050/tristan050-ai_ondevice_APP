#!/usr/bin/env bash
set -euo pipefail

# R10-S5: 결정적 RAG 테스트 픽스처 검증
# 
# DoD:
# - 로컬에서 단 한 번의 스크립트로 PASS/FAIL이 결정됨
# - 업스트림/BFF 상태와 무관하게(=mock) 동작
# - 인덱스 생성 → 질의 → topK 결과가 기대 키워드를 포함하는지 검증

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES_DIR="${ROOT}/tools/rag_fixtures"
FIXTURES_FILE="${FIXTURES_DIR}/cs_tickets.json"

echo "[verify] RAG Retrieval 검증"
echo ""

# 1) 픽스처 파일 존재 확인
if [ ! -f "${FIXTURES_FILE}" ]; then
  echo "[FAIL] 픽스처 파일이 없습니다: ${FIXTURES_FILE}"
  exit 1
fi

echo "[OK] 픽스처 파일 존재: ${FIXTURES_FILE}"

# 2) 픽스처 파일 형식 검증 (JSON 유효성)
# Node.js로 JSON 검증 (jq 없이도 동작)
VALIDATION_SCRIPT=$(cat <<'NODE'
const fs = require('fs');
try {
  const data = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
  if (!Array.isArray(data)) {
    console.error('FAIL: JSON is not an array');
    process.exit(1);
  }
  console.log(data.length);
  
  // 필수 필드 검증
  let missingFields = 0;
  for (const ticket of data) {
    if (!ticket.id || !ticket.subject || !ticket.body) {
      missingFields++;
    }
  }
  
  if (missingFields > 0) {
    console.error(`FAIL: ${missingFields} tickets missing required fields`);
    process.exit(1);
  }
  
  console.log('OK');
} catch (e) {
  console.error('FAIL: Invalid JSON:', e.message);
  process.exit(1);
}
NODE
)

TICKET_COUNT=$(node -e "${VALIDATION_SCRIPT}" "${FIXTURES_FILE}" 2>&1 | head -1)
VALIDATION_RESULT=$(node -e "${VALIDATION_SCRIPT}" "${FIXTURES_FILE}" 2>&1 | tail -1)

if [ "$VALIDATION_RESULT" != "OK" ]; then
  echo "[FAIL] 픽스처 파일 검증 실패: ${VALIDATION_RESULT}"
  exit 1
fi

echo "[OK] 픽스처 파일 형식 검증: ${TICKET_COUNT}개 티켓"
echo "[OK] 모든 티켓에 필수 필드 존재"

# 4) 검색 테스트 케이스 정의 (주석으로만 표시, 실제 검증은 RAG 구현 후)
# 질의 예시:
# - "로그인 문제" → 기대 키워드: 로그인|인증|비밀번호
# - "결제 오류" → 기대 키워드: 결제|카드|처리
# - "배송 지연" → 기대 키워드: 배송|도착|지연
# - "환불 요청" → 기대 키워드: 환불|취소|반환

# 5) 검색 테스트 실행 (Node.js 스크립트로 실제 RAG 검증)
# TODO: 실제 RAG 검증 로직 구현
# - 인덱스 생성
# - 질의
# - topK 결과가 기대 키워드를 포함하는지 검증

# 현재는 픽스처 파일 검증만 수행
echo ""
echo "[INFO] RAG 검색 테스트 (stub)"
echo "[INFO] TODO: 실제 RAG 검증 로직 구현"
echo "  - 인덱스 생성"
echo "  - 질의: 로그인 문제, 결제 오류, 배송 지연, 환불 요청"
echo "  - topK 결과 검증"

# 6) 검증 완료
echo ""
echo "[OK] RAG Retrieval 검증 완료 (픽스처 검증 PASS)"
echo "[INFO] 실제 검색 테스트는 RAG 구현 완료 후 활성화 예정"
