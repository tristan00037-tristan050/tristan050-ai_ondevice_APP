# 실제 Butler 제품 편입 계약

실제 제품 모듈은 승인 product root 아래에 있어야 하고 파일 SHA-256 및 전체 commit OID와 결속되어야 합니다. 이름만 같은 임의 모듈, test·fixture·mock 경로, caller 제공 validator는 차단됩니다.

필수 호출 대상은 다음과 같습니다.

- `Box3ProductPipelineRuntime`
- `run_product_matrix`
- `run_cold_worker_handshake`
- `measure_dual_resident_pressure`
- `verify_samples_first`
- `butler_bench_run_v2`

integration evidence는 위 6개 entrypoint call count, production gate observer event, coverage artifact digest, route diff digest를 포함해야 합니다. 모든 call count는 1 이상, 제품 gate event는 5개 이상, `route_semantics_changed=false`, `runtime_activation_allowed=0`이어야 합니다.

`butler_bench_run_v2`는 실제 제품경로를 실행한 후 `run_id`와 output root 아래의 상대 `evidence_root_relative`만 반환합니다. 제품 adapter가 PASS boolean을 반환해도 owner runner는 신뢰하지 않으며 standalone offline verifier를 별도 프로세스로 다시 실행합니다.
