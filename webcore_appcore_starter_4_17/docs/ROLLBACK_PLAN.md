# 롤백 플랜

Phase 5.4 프로덕션 배포 실패 시 롤백 절차입니다.

## 🎯 롤백 시나리오

### 시나리오 1: Kubernetes 롤아웃 되돌리기

**조건**: 배포 후 즉시 문제 발견 (데이터 손실 없음)

**절차**:

1. **롤아웃 되돌리기**
   ```bash
   # 이전 버전으로 롤백
   kubectl rollout undo deployment/collector
   
   # 롤백 상태 확인
   kubectl rollout status deployment/collector
   
   # Pod 상태 확인
   kubectl get pods -l app=collector
   ```

2. **헬스 체크 확인**
   ```bash
   curl http://collector.production/health
   # 예상 응답: {"status":"ok","service":"collector","database":"connected"}
   ```

3. **스모크 테스트 실행**
   ```bash
   ./scripts/smoke.sh
   ```

**예상 소요 시간**: 2-3분

---

### 시나리오 2: 데이터베이스 복원

**조건**: 데이터베이스 손상 또는 잘못된 데이터 마이그레이션

**절차**:

1. **현재 상태 확인**
   ```bash
   # 데이터베이스 연결 확인
   psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT COUNT(*) FROM reports;"
   
   # 최근 백업 목록 확인
   ls -lh backups/collector_*.sql.gz
   ```

2. **백업 파일 선택**
   ```bash
   # 가장 최근 백업 또는 특정 시점 백업 선택
   BACKUP_FILE=./backups/collector_20250101_120000.sql.gz
   ```

3. **데이터베이스 복원**
   ```bash
   # 복원 스크립트 실행
   ./scripts/restore-db.sh $BACKUP_FILE
   
   # 복원 확인
   psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT COUNT(*) FROM reports;"
   ```

4. **서비스 재시작** (필요시)
   ```bash
   kubectl rollout restart deployment/collector
   kubectl rollout status deployment/collector
   ```

5. **검증**
   ```bash
   # 헬스 체크
   curl http://collector.production/health
   
   # 스모크 테스트
   ./scripts/smoke.sh
   ```

**예상 소요 시간**: 5-10분 (백업 크기에 따라 다름)

---

### 시나리오 3: 완전 롤백 (코드 + 데이터)

**조건**: 심각한 문제로 인한 완전 롤백 필요

**절차**:

1. **이전 버전 태그 확인**
   ```bash
   git tag | grep "v5.3"
   # 예: v5.3.0
   ```

2. **코드 롤백**
   ```bash
   # 이전 버전으로 체크아웃
   git checkout v5.3.0
   
   # 이전 버전 Docker 이미지 사용
   kubectl set image deployment/collector collector=collector:v5.3.0
   
   # 롤아웃 확인
   kubectl rollout status deployment/collector
   ```

3. **데이터베이스 복원** (필요시)
   ```bash
   # Phase 5.4 이전 백업 사용
   ./scripts/restore-db.sh ./backups/collector_pre_5.4.sql.gz
   ```

4. **검증**
   ```bash
   # 헬스 체크
   curl http://collector.production/health
   
   # 스모크 테스트
   ./scripts/smoke.sh
   ```

**예상 소요 시간**: 10-15분

---

## 🔄 롤백 전 확인사항

### 1. 영향 범위 평가

- [ ] 영향받는 테넌트 수 확인
- [ ] 데이터 손실 가능성 평가
- [ ] 서비스 중단 시간 예상

### 2. 백업 상태 확인

- [ ] 최근 백업 파일 존재 확인
- [ ] 백업 파일 무결성 검증
- [ ] 복원 테스트 완료 (스테이징 환경)

### 3. 통신 계획

- [ ] 관련 팀에 롤백 계획 공유
- [ ] 사용자 공지 준비 (필요시)
- [ ] 롤백 완료 후 공지

---

## 📋 롤백 체크리스트

### 롤백 전

- [ ] 문제 원인 파악
- [ ] 롤백 시나리오 선택
- [ ] 백업 파일 확인
- [ ] 롤백 절차 검토
- [ ] 관련 팀 통지

### 롤백 실행

- [ ] 롤백 명령 실행
- [ ] 롤백 상태 모니터링
- [ ] 헬스 체크 확인
- [ ] 스모크 테스트 실행

### 롤백 후

- [ ] 서비스 정상 동작 확인
- [ ] 데이터 무결성 확인
- [ ] 모니터링 대시보드 확인
- [ ] 롤백 완료 공지
- [ ] 사후 분석 계획

---

## 🚨 긴급 롤백

**조건**: 즉시 서비스 중단이 필요한 경우

**빠른 롤백 명령**:

```bash
# 1. 즉시 이전 버전으로 롤백
kubectl rollout undo deployment/collector

# 2. 헬스 체크 확인
curl http://collector.production/health

# 3. Pod 상태 확인
kubectl get pods -l app=collector
```

**예상 소요 시간**: 1-2분

---

## 📊 롤백 성공 기준

다음 조건을 모두 만족해야 롤백이 성공한 것으로 간주합니다:

- [ ] 모든 Pod가 정상 상태 (Running)
- [ ] 헬스 체크 통과 (`/health` → `{"status":"ok"}`)
- [ ] 데이터베이스 연결 정상
- [ ] 스모크 테스트 통과
- [ ] 에러율 정상 범위 내
- [ ] 응답 시간 정상 범위 내

---

## 🔍 사후 분석

롤백 후 다음 사항을 분석해야 합니다:

1. **문제 원인 분석**
   - 배포 전 검증 누락 여부
   - 코드 버그 여부
   - 인프라 문제 여부

2. **롤백 프로세스 개선**
   - 롤백 시간 단축 방안
   - 자동화 가능 여부
   - 문서화 개선

3. **재배포 계획**
   - 문제 해결 방안
   - 재배포 일정
   - 추가 검증 항목

---

## 📚 참고 문서

- `docs/GO_LIVE_CHECKLIST.md` - Go-Live 체크리스트
- `scripts/restore-db.sh` - 데이터베이스 복원 스크립트
- `scripts/smoke.sh` - 스모크 테스트 스크립트

---

**롤백 담당자**: DevOps 팀
**승인자**: 기술 리더
**긴급 연락처**: [연락처 정보]


