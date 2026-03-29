## 개요
AI-24 Judge + Hard-case 배포 게이트 엔진 v6
judge 계층 실제 활성화, hard-case/adversarial 50건 세트 확장, dry-run/pytest 완료

## 핵심 변경
- eval_judge_rule_v1.py 추가
- eval_domain_v3.py: keyword 70% + rule_judge 30%
- eval_judge_v3.py: hardcase 결과 추가
- eval_verify_v3.py: rule judge + hardcase 검증 추가
- butler_hardcase_v1.jsonl 50건 포함

## dry-run 결과
- COMPILE_OK=1
- RULE_JUDGE_OK=1
- HARDCASE_DATASET_OK=1
- EVAL_VERIFY_OK=1
- pytest 전체 통과
- dry-run EVAL_PASS=1
- SHELL_SYNTAX_OK=1

## 범위
✅ 알고리즘팀 dry-run 완성
❌ real-run GPU 실측 / baseline 실운영 갱신 / 운영 배포 승인
