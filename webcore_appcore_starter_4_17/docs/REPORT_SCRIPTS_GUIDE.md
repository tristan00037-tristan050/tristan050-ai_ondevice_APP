# 리포트 스크립트 실행 가이드

## 1. 현재 디렉토리 확인

```bash
cd "/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17"
pwd
```

**예상 출력:**
```
/Users/kwong/Desktop/AI 온디바이스 플랫폼 앱/웹코어자료/tristan050-ai_ondevice_APP/webcore_appcore_starter_4_17
```

---

## 2. DATABASE_URL 환경변수 설정

### 로컬 개발 환경 (기본값)

```bash
export DATABASE_URL="postgres://app:app@localhost:5432/app"
```

### .env 파일 사용 (권장)

```bash
# .env 파일이 있다면 자동으로 로드됨
# 없으면 위의 export 명령어 사용
```

### Docker Compose 사용 시

```bash
# docker-compose.yml에서 설정된 값 사용
export DATABASE_URL="postgres://app:app@localhost:5432/app"
```

### 확인

```bash
echo $DATABASE_URL
```

---

## 3. 파일럿 지표 리포트 실행

```bash
npm run report:pilot
```

### 날짜 범위 지정 (선택사항)

```bash
npm run report:pilot -- --from=2025-12-01 --to=2025-12-31
```

### 출력 예시

```
📊 파일럿 지표 리포트 (2025-12-01 ~ 2025-12-31)

============================================================

1️⃣  전체 추천 건수: 1,234

2️⃣  Top-1 정확도: 85.50% (1,055/1,234)

3️⃣  Top-5 정확도: 92.30% (1,139/1,234)

4️⃣  Manual Review 비율: 12.50% (154/1,234)

5️⃣  Export 실패 건수: 3

6️⃣  Recon 미매칭 비율: 8.20% (45/550)

============================================================

✅ 리포트 완료
```

---

## 4. 어댑터 SLO 리포트 실행

```bash
npm run report:adapter-slo
```

### 출력 예시

```
📡 외부 어댑터 SLO 체크

============================================================

✅ source=bank-sbx
   tenant=default
   lag=120s (2분)
   ✅ errors(last1h)=0 (0.00%)
   last_sync=2025-12-04T10:30:00.000Z

✅ source=pg-sbx
   tenant=default
   lag=45s (0분)
   ✅ errors(last1h)=1 (2.50%)
   last_sync=2025-12-04T10:35:00.000Z

⚠️ source=erp-sbx
   tenant=default
   lag=420s (7분)
   ⚠️ errors(last1h)=3 (7.50%)
   ⚠️  SLO 위반: sync 지연이 5분을 초과했습니다 (7분)
   ⚠️  SLO 위반: 오류율이 5%를 초과했습니다 (7.50%)
   last_sync=2025-12-04T10:20:00.000Z

============================================================

✅ SLO 체크 완료
```

---

## 5. 리포트 출력 확인 포인트

### 파일럿 지표 리포트 (`report:pilot`)

#### ✅ 정상적인 값 범위

1. **Top-1 정확도**
   - **목표:** 70% 이상
   - **확인:** `2️⃣  Top-1 정확도: XX.XX% (XXX/XXX)`
   - **주의:** 분모(전체 승인 건수)가 0이면 "0.00%"로 표시됨

2. **Top-5 정확도**
   - **목표:** 85% 이상
   - **확인:** `3️⃣  Top-5 정확도: XX.XX% (XXX/XXX)`
   - **주의:** `selected_rank` 필드가 없으면 0%로 표시될 수 있음

3. **Manual Review 비율**
   - **목표:** 30% 이하 (너무 높으면 문제)
   - **확인:** `4️⃣  Manual Review 비율: XX.XX% (XXX/XXX)`
   - **주의:** 분모는 suggest 호출 수 + manual_review_request 합계

4. **Export 실패 건수**
   - **목표:** 0건 (가능하면)
   - **확인:** `5️⃣  Export 실패 건수: X`

5. **Recon 미매칭 비율**
   - **목표:** 10% 이하
   - **확인:** `6️⃣  Recon 미매칭 비율: XX.XX% (XXX/XXX)`

#### ⚠️ 문제가 있는 경우

- **Top-1 정확도가 0%**: `top1_selected` 필드가 누락되었을 수 있음
- **Top-5 정확도가 0%**: `selected_rank` 필드가 누락되었을 수 있음
- **Manual Review 비율이 100%**: 분모 계산 로직 문제 또는 실제로 모든 거래가 수동 검토됨
- **모든 지표가 0**: 날짜 범위에 이벤트가 없거나 테넌트가 맞지 않음

---

### 어댑터 SLO 리포트 (`report:adapter-slo`)

#### ✅ 정상적인 값 범위

1. **Sync 지연 (lag)**
   - **목표:** 5분(300초) 이하
   - **확인:** `lag=XXXs (X분)`
   - **정상:** `✅` 표시
   - **경고:** `⚠️` 표시 (5분 초과)

2. **오류율 (errorRate)**
   - **목표:** 5% 이하
   - **확인:** `✅ errors(last1h)=X (XX.XX%)` 또는 `⚠️ errors(last1h)=X (XX.XX%)`
   - **정상:** `✅` 표시
   - **경고:** `⚠️` 표시 (5% 초과)

3. **최근 1시간 오류 횟수**
   - **확인:** `errors(last1h)=X`
   - **주의:** 0이면 좋지만, 전체 시도 횟수도 확인 필요

#### ⚠️ 문제가 있는 경우

1. **SLO 위반 경고 메시지**
   ```
   ⚠️  SLO 위반: sync 지연이 5분을 초과했습니다 (X분)
   ⚠️  SLO 위반: 오류율이 5%를 초과했습니다 (XX.XX%)
   ```
   - 즉시 조치 필요

2. **동기화 이벤트 데이터 없음**
   ```
   ℹ️  동기화 이벤트 데이터가 없습니다 (audit 이벤트 없음)
   ```
   - `external_sync_*` 이벤트가 생성되지 않았을 수 있음
   - sync 작업이 실행되지 않았거나, audit 로깅이 비활성화되었을 수 있음

3. **lag가 N/A**
   ```
   lag=N/A (동기화 이력 없음)
   ```
   - `external_ledger_offset` 테이블에 데이터가 없음
   - sync가 한 번도 실행되지 않았을 수 있음

---

## 6. 빠른 확인 체크리스트

### 파일럿 지표

- [ ] Top-1 정확도가 70% 이상인가?
- [ ] Top-5 정확도가 85% 이상인가?
- [ ] Manual Review 비율이 30% 이하인가?
- [ ] Export 실패 건수가 0인가?

### 어댑터 SLO

- [ ] 모든 source의 lag가 5분 이하인가?
- [ ] 모든 source의 오류율이 5% 이하인가?
- [ ] SLO 위반 경고가 없는가?
- [ ] 모든 source에 `last_sync` 시간이 표시되는가?

---

## 7. 트러블슈팅

### DATABASE_URL 오류

```bash
❌ DATABASE_URL 환경변수가 설정되지 않았습니다.
```

**해결:**
```bash
export DATABASE_URL="postgres://app:app@localhost:5432/app"
```

### PostgreSQL 연결 실패

```bash
❌ 오류 발생: connect ECONNREFUSED
```

**해결:**
```bash
# Docker Compose 사용 시
docker compose up -d db

# 또는 로컬 PostgreSQL
brew services start postgresql@16
```

### 리포트에 데이터가 없음

**확인:**
1. 날짜 범위가 올바른가? (기본값: 최근 7일)
2. 테넌트가 `default` 또는 `pilot-a`인가?
3. 실제로 이벤트가 생성되었는가? (psql로 확인)

### 필드가 NULL 또는 0

**확인:**
1. 클라이언트 코드가 최신인가?
2. BFF 코드가 최신인가?
3. audit 이벤트 payload에 필드가 포함되어 있는가? (psql로 확인)

