# scripts/upgrade — continual autolearn / student QLoRA (v47 통합)

이 디렉터리는 **알고리즘팀 ZIP(v46 패키지 + v47 핫픽스)**에서 통합된 스크립트입니다.

- **진입점:** `run_continual_autolearn_cycle_v1.py` (`--root` 기본 `.`, `--dry-run`, `--model-id`)
- **버그 수정 요약:** 레포 루트 `out/BUG_FIX_REPORT_V47.md` 및 `out/ALGO_TEAM_ZIPS_V46_V47_SYNTHESIS.md` 참고
- **검증:** `scripts/verify/verify_ai15_dryrun_result_consistency_v1.py` (`finetune_qlora_v3_5.py` dry-run 후)

`autolearn/` 하위 디렉터리(incoming, replay, cycles 등)는 사이클 실행 시 생성·사용됩니다.
