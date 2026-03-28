# 2026 온디바이스/서빙 벤치마킹 메모

## A. 이번 번들에 직접 반영한 공개 기술 축
### 1) Google TurboQuant / PolarQuant / QJL
- 2026-03-24 Google Research 블로그 공개
- KV cache 3-bit 압축, 최소 6x 메모리 절감, 4-bit에서 H100 최대 8x attention-logit speedup은 **Google 논문/블로그 목표치**
- 공식 코드 미공개 상태이므로 본 번들은 **논문-정합 구현(research-faithful scaffold)** 으로만 기술

### 2) Alibaba MNN / Qwen3-4B-MNN
- Qwen3-4B-MNN 공개 카드 기준으로 MNN LLM 경로를 문서화
- 실제 run 형식: `./llm_demo /path/to/Qwen3-4B-MNN/config.json prompt.txt`
- 실제 cmake flags는 `-DMNN_LOW_MEMORY=true`, `-DMNN_CPU_WEIGHT_DEQUANT_GEMM=true`, `-DMNN_BUILD_LLM=true`, `-DMNN_SUPPORT_TRANSFORMER_FUSE=true`

### 3) Gemini Nano / ML Kit GenAI
- Android 쪽 경쟁 기준은 "완전 로컬 실행 + AICore 기반 공유 모델 + 고수준 use-case API"
- Butler 차별화 포인트는 범용 챗봇이 아니라 **Butler 업무 시나리오 + 로컬 KV cache 최적화 + 자체 툴 체인** 쪽이 적절

### 4) ExecuTorch
- PyTorch → export → quantize/compile → lightweight runtime 라는 표준 edge workflow를 제공
- Butler는 MNN 우선 경로를 유지하되, 추후 iOS/CoreML/Qualcomm 계열 비교를 위해 ExecuTorch compatibility 레이어를 검토 가능

### 5) OpenAI / Claude Code / Gemini API
- 2026년 경쟁 격차는 단순 모델 품질보다 **도구 사용, 멀티스텝 오케스트레이션, 코드 실행, 웹/파일 검색** 등 agentic stack에서 크게 벌어짐
- 따라서 온디바이스 모델 자체뿐 아니라, 로컬 inference + 툴 실행 경계 + 서버 fallback 전략을 함께 설계해야 함

## B. Butler 차별화 권장안
1. **KV 캐시 최적화 + 툴 사용 결합**
   - TurboQuant를 단독 기능으로 보지 말고, 긴 문맥 유지가 필요한 로컬 에이전트 작업(문서 요약, 장기 대화, 로컬 검색)에 결합
2. **fail-closed 운영성**
   - 압축 실패 시 원본 KV 경로 복귀
   - measured_*가 없으면 제품 성능 주장 금지
3. **실기기 중심 회귀 테스트**
   - 서버 benchmark보다 모바일 thermals / sustained latency / RAM spike가 더 중요
4. **모델 종속성 축소**
   - 현재는 Qwen3-4B 기준이지만, cache boundary 인터페이스를 일반화해 향후 다른 4B~8B 모델에도 이식 가능하도록 설계

## C. 현재 수준 평가
- 코드 스캐폴드: 완료
- CPU dry-run 검증: 완료
- 실제 서버 실측: 미완료
- 실기기 측정: 미완료
- 공식 코드 정합성 100% 검증: 불가 (공식 코드 미공개)
