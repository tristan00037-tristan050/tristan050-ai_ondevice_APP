# PoC Playbook

외부 기업 PoC 시연을 위한 단계별 가이드입니다.

## 사전 준비

### 1. 환경 설정

```bash
# 프로젝트 루트로 이동
cd webcore_appcore_starter_4_17

# 의존성 설치 (최초 1회)
npm install

# DB 및 BFF 서버 실행
docker compose up -d db
export DATABASE_URL="postgres://app:app@localhost:5432/app"
npm run db:migrate
docker compose up -d --build bff

# 샘플 데이터 생성 (선택)
npm run demo:seed
```

### 2. 서버 상태 확인

```bash
# Health Check
curl http://localhost:8081/healthz

# Ready Check
curl http://localhost:8081/readyz

# OS Dashboard API 확인
curl -H "X-Tenant: default" \
     -H "X-User-Role: auditor" \
     -H "X-User-Id: admin-1" \
     http://localhost:8081/v1/accounting/os/dashboard
```

## 시연 시나리오

### 시나리오 1: Mock 모드 데모 (서버 없이)

**목적**: 온디바이스 엔진의 동작을 보여주기

```bash
# 터미널 1: HUD 실행
npm run demo:app:mock
# → Expo 메뉴에서 'w' 키 입력하여 브라우저 열기
```

**시연 포인트**:
1. HUD 상단에 "Engine: On-device (localRuleEngineV1)" 표시 확인
2. 설명 입력 → "추천" 버튼 클릭
3. **체크포인트**: Chrome DevTools Network 탭에서 HTTP 호출이 **0개**인지 확인 (Mock 모드에서 네트워크 호출이 하나라도 나가면 실패)
4. 추천 카드 하단에 "ⓘ 이 추천은 온디바이스 엔진이 생성했습니다." 표시 확인
5. HIGH Risk 카드에서 "수동 검토 요청" 버튼 클릭
6. Alert로 "수동 검토 요청이 접수되었습니다. (모의)" 확인

### 시나리오 2: Live 모드 데모 (전체 플로우)

**목적**: 온디바이스 HUD ↔ OS 게이트웨이 ↔ Backoffice 전체 흐름 시연

```bash
# 터미널 1: Backoffice 실행
npm run demo:web
# → 브라우저에서 http://localhost:5173 접속

# 터미널 2: HUD 실행
npm run demo:app:live
# → Expo 메뉴에서 'w' 키 입력하여 브라우저 열기
```

**시연 순서**:

#### 1단계: OS Dashboard 확인
- Backoffice에서 `/os/dashboard` 접속
- 상단 카드 4개 확인:
  - Top-1 정확도
  - Manual Review 비율
  - BFF Success Rate
  - HIGH Risk 거래 수
- "Demo 플로우" 섹션에서 링크 확인

#### 2단계: HUD에서 추천 요청
- HUD에서 설명 입력 (예: "커피 영수증 4500원")
- "추천" 버튼 클릭
- HUD 상단에 "Engine: BFF(remote)" 표시 확인
- 추천 결과 카드 확인
- HIGH Risk 카드가 있으면 "⚠ 고위험 거래 – 수동 검토 권장" 표시 확인

#### 3단계: 수동 검토 요청
- HIGH Risk 카드에서 "수동 검토 요청" 버튼 클릭
- HUD 상단에 "수동 검토 큐에 추가되었습니다." 메시지 확인
- Backoffice에서 `/manual-review` 접속
- 방금 요청한 항목이 PENDING 상태로 표시되는지 확인

#### 4단계: Manual Review 처리
- Backoffice에서 auditor 권한으로 "승인" 또는 "거절" 버튼 클릭
- 상태가 APPROVED/REJECTED로 변경되는지 확인

#### 5단계: OS Dashboard 업데이트 확인
- `/os/dashboard`로 돌아가서
- Manual Review 비율이 업데이트되었는지 확인
- "오늘의 주요 이벤트" 섹션에서 처리된 항목 확인

### 시나리오 3: 오프라인 모드 데모

**목적**: 오프라인 큐 및 에러 처리 시연

```bash
# 터미널 1: HUD 실행
npm run demo:app:live

# 브라우저 개발자 도구에서 네트워크 차단 (Offline 모드)
```

**시연 포인트**:
1. 네트워크를 끊은 상태에서 HUD에서 여러 액션 수행
2. HUD 상단에 "Offline" 상태 표시 확인
3. "전송 대기 항목 보기" 버튼 클릭
4. Queue Inspector에서 대기 중인 항목 확인
5. 네트워크를 다시 연결
6. 자동으로 큐가 flush되면서 항목이 사라지는지 확인

### 시나리오 4: 에러 처리 데모

**목적**: 에러 UX 및 BFF 설정 검증 시연

```bash
# BFF 서버를 중지한 상태에서
docker compose stop bff

# HUD 실행
npm run demo:app:live
```

**시연 포인트**:
1. HUD 상단에 "BFF 설정 오류" 배너 표시 확인
2. "BFF에 연결할 수 없습니다" 메시지 확인
3. 에러 발생 시 HUD 상단에 일관된 에러 메시지 표시
4. "자세히" 버튼 클릭하여 상세 에러 정보 확인

## 주요 화면 설명

### OS Dashboard (`/os/dashboard`)

**대상**: 운영팀, 대표, PoC 대상자

**핵심 메시지**:
- "AI 온디바이스 OS의 현재 상태를 한눈에 볼 수 있습니다"
- "Top-1 정확도, Manual Review 비율, Risk 분포를 실시간으로 모니터링합니다"

**시연 포인트**:
- 카드 4개로 핵심 지표 한눈에 파악
- "Demo 플로우" 섹션에서 전체 플로우 연결
- 30초마다 자동 새로고침

### Manual Review Workbench (`/manual-review`)

**대상**: auditor, 리스크 담당자

**핵심 메시지**:
- "HIGH Risk 거래를 검토하고 승인/거절할 수 있습니다"
- "HUD에서 요청한 수동 검토가 여기로 자동으로 들어옵니다"

**시연 포인트**:
- PENDING 상태 항목 확인
- 승인/거절 버튼으로 상태 변경
- 상태별 필터링 기능

### Accounting Demo (`/demo/accounting`)

**대상**: 회계팀, 운영팀

**핵심 메시지**:
- "회계 모듈의 상세 기능을 확인할 수 있습니다"
- "Risk Monitor에서 HIGH Risk 거래를 추적합니다"

## FAQ

### Q: Mock 모드와 Live 모드의 차이는?

**A**: 
- **Mock**: 온디바이스 엔진만 사용, 네트워크 호출 없음, localStorage 기반
- **Live**: BFF 서버와 연동, 실제 DB 저장, 전체 플로우 동작

### Q: BFF 서버가 없어도 동작하나요?

**A**: Mock 모드(`demo:app:mock`)에서는 BFF 없이도 동작합니다. Live 모드에서는 BFF가 필요합니다.

### Q: 데이터는 어디에 저장되나요?

**A**: 
- **Mock 모드**: 브라우저 localStorage
- **Live 모드**: PostgreSQL 데이터베이스

### Q: 외부 PoC에서 보여줄 핵심 포인트는?

**A**:
1. **온디바이스 엔진**: 서버 없이도 추천 가능
2. **Risk 기반 필터링**: 고액 거래 자동 감지
3. **Manual Review 워크플로우**: HUD → Backoffice → 처리 완료
4. **OS Dashboard**: 전체 상태 한눈에 파악

## 트러블슈팅

### BFF 연결 실패

```bash
# BFF 상태 확인
curl http://localhost:8081/healthz

# BFF 재시작
docker compose restart bff

# 로그 확인
docker compose logs bff
```

### DB 마이그레이션 실패

```bash
# 마이그레이션 상태 확인
./scripts/psql.sh -c "SELECT * FROM schema_migrations ORDER BY version DESC LIMIT 5;"

# 마이그레이션 재실행
npm run db:migrate
```

### HUD가 빈 화면

```bash
# 브라우저 콘솔 확인
# 일반적으로 CORS 또는 BFF 연결 문제

# CORS 설정 확인
# packages/bff-accounting/src/index.ts에서 cors() 미들웨어 확인
```

## 다음 단계

PoC 성공 후:
1. 실제 온디바이스 LLM 통합
2. 프로덕션 환경 배포
3. 모니터링 및 알람 설정
4. 사용자 교육 및 문서화

