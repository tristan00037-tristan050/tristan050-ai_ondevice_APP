# R10-S6 완료 보고서

## 범위 요약

S6은 "품질 고도화 + 운영화" 트랙으로, 다음 작업을 완료했습니다:

- **S6-1**: Retriever 품질 개선 (결정성 유지)
- **S6-2**: 출처/스니펫 안전성 회귀 방지 강화
- **S6-3**: IndexedDB 운영 안정성 (fail-safe state machine)
- **S6-4**: 성능 KPI 운영화 (회귀 감지 루프 고정)

## S6 Golden Master 재현 커맨드

```bash
cd webcore_appcore_starter_4_17
./scripts/dev_bff.sh restart
bash scripts/verify_telemetry_rag_meta_only.sh
bash scripts/verify_perf_kpi_meta_only.sh
bash scripts/verify_perf_kpi_regression.sh
```

## 🔒 S6 Seal Index

### 정의

- **fileCount 정의**: `fileCount = Object.keys(opsProofSets).length`
  - manifest 내부에 `fileCountDefinition` 필드로 고정
  - fileCount는 opsProofSets 배열의 길이와 반드시 일치

### Seal Artifacts 경로

- **Manifest**: `webcore_appcore_starter_4_17/docs/ops/r10-s6-seal-manifest.json`
- **Checksums**: `webcore_appcore_starter_4_17/docs/ops/r10-s6-seal-checksums.txt`
- **Checksums SHA256**: `webcore_appcore_starter_4_17/docs/ops/r10-s6-seal-checksums.txt.sha256`
- **생성 스크립트**: `webcore_appcore_starter_4_17/scripts/generate_s6_seal_artifacts.sh`
- **검증 스크립트**: `webcore_appcore_starter_4_17/scripts/verify_ops_proof_manifest.sh`

### Golden Master 재현 커맨드 (2단계)

```bash
cd webcore_appcore_starter_4_17

# 1단계: Seal artifacts 생성 (비파괴 재생성)
bash scripts/generate_s6_seal_artifacts.sh

# 2단계: Seal 검증 (PASS 필수)
bash scripts/verify_ops_proof_manifest.sh
```

### Seal 검증 범위

- manifest 존재/JSON 파싱/manifestVersion==1
- fileCount == opsProofSets.length 일치
- manifest가 참조하는 .latest 파일 존재
- .latest가 참조하는 artifacts 존재
- checksums 커버리지 100% (누락/혼입 없음)
- checksums.txt.sha256로 checksums.txt 무결성 확인
- 금지키 스캔 (본문 덤프 없이)

## 운영 가드 증빙

PR Actions에서 다음을 확인하고 PR 코멘트로 남깁니다:

- [ ] PR Actions에서 deploy job skipped(배포 0%) 확인
- [ ] PR Actions 로그에서 금지 키워드 0건 확인
  - ssh | rsync | pm2 | 49.50.139.248 | /var/www/petad

**증빙 코멘트 템플릿:**
```
[증빙] PR Actions에서 deploy job skipped(배포 0%) 확인 완료. (Run ID: <run_id>)
```

또는

```
[증빙] PR Actions 로그에서 금지 키워드(ssh/rsync/pm2/49.50.139.248//var/www/petad) 0건 확인 완료. (Run ID: <run_id>)
```

## 기준선 유지

S6 완료 후 main에서 다음 게이트는 항상 PASS여야 합니다:

- `verify_telemetry_rag_meta_only.sh`: PASS
- `verify_perf_kpi_meta_only.sh`: PASS
- `verify_perf_kpi_regression.sh`: PASS
- `verify_ops_proof_manifest.sh`: PASS

