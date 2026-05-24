# 2026 Benchmarking Notes

이 문서는 산출물 내 설계 기준을 설명하기 위한 참고 문서입니다. 외부 문헌의 정확한 최신 여부는 최종 응답의 출처 인용으로 확인합니다.

- LLM routing은 cost/latency/quality/privacy trade-off를 명시적으로 모델링해야 합니다.
- GitHub Actions 기반 3OS CI는 Windows/macOS/Linux collector의 최소 자동 검증 경로입니다.
- OpenTelemetry식 metrics naming, units, attributes 원칙을 telemetry evidence 설계에 반영했습니다.
- Zero Trust 관점에서 IP #2 PEP/PDP decision 없이는 routing fire를 금지합니다.
- Windows battery measurement는 Win32_Battery/WMI 기반 수집 경로를 둡니다.
